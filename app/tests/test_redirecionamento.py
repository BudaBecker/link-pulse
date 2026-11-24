import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import redis
from fastapi.testclient import TestClient
from redis.backoff import NoBackoff
from redis.retry import Retry

from app import service
from app.cliques import RegistroDeCliques, classificar_dispositivo
from app.main import criar_app

URL = "https://exemplo.com.br/natal?utm_source=instagram&cupom=50%25"
IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"


def criar_link(api, **campos) -> str:
    corpo = {"url": URL, "cliente_id": "c1"} | campos
    return api.post("/links", json=corpo).json()["short_code"]


def acessar(api, codigo, **cabecalhos):
    return api.get(f"/r/{codigo}", headers=cabecalhos, follow_redirects=False)


def esperar_cliques(sessao, codigo, quantidade, prazo=10.0) -> list:
    fim = time.monotonic() + prazo
    while True:
        linhas = list(sessao.execute("SELECT * FROM cliques_por_link WHERE short_code = %s", (codigo,)))
        if len(linhas) >= quantidade or time.monotonic() > fim:
            return linhas
        time.sleep(0.05)


def fixar_agora(monkeypatch, momento: datetime):
    class Relogio(datetime):
        @classmethod
        def now(cls, tz=None):
            return momento

    monkeypatch.setattr(service, "datetime", Relogio)


def test_link_sem_expiracao_redireciona_em_qualquer_data(api, monkeypatch):
    sem_expiracao = criar_link(api)
    com_expiracao = criar_link(api, expira_em="2099-12-31T23:59:59Z")
    fixar_agora(monkeypatch, datetime(2100, 1, 1, tzinfo=UTC))

    resposta = acessar(api, sem_expiracao)

    assert resposta.status_code == 302
    assert resposta.headers["location"] == URL
    assert acessar(api, com_expiracao).status_code == 410


def test_link_com_expiracao_futura_redireciona(api):
    expira_em = (datetime.now(UTC) + timedelta(days=1)).isoformat()

    resposta = acessar(api, criar_link(api, expira_em=expira_em))

    assert resposta.status_code == 302
    assert resposta.headers["location"] == URL


@pytest.mark.parametrize(
    ("url", "location"),
    [
        ("https://café.example/oferta?q=a%20b", "https://xn--caf-dma.example/oferta?q=a%20b"),
        ("https://Café.example:8443/ação#topo", "https://xn--caf-dma.example:8443/a%C3%A7%C3%A3o#topo"),
    ],
)
def test_dominio_com_acento_sai_em_idna(api, url, location):
    resposta = acessar(api, criar_link(api, url=url))

    assert resposta.status_code == 302
    assert resposta.headers["location"] == location


def test_link_expirado_responde_410_sem_contar_nem_gravar(api, master, sessao_cassandra):
    codigo = criar_link(api, expira_em="2026-01-01T00:00:00-03:00")

    resposta = acessar(api, codigo)

    assert resposta.status_code == 410
    assert "Link expirado" in resposta.text
    assert "location" not in resposta.headers
    assert master.get(f"contador:{codigo}") is None
    assert esperar_cliques(sessao_cassandra, codigo, 1, prazo=0.5) == []


def test_link_inexistente_responde_404_sem_contar(api, master, sessao_cassandra):
    resposta = acessar(api, "XXXXXXX")

    assert resposta.status_code == 404
    assert master.get("contador:XXXXXXX") is None
    assert esperar_cliques(sessao_cassandra, "XXXXXXX", 1, prazo=0.5) == []


@pytest.fixture
def replica_sem_o_link():
    # Outro banco do servidor da réplica: o link gravado no banco 15 do master nunca chega a ele.
    conexao = redis.Redis(
        host=os.environ.get("REDIS_MASTER_HOST", "127.0.0.1"),
        port=int(os.environ.get("REDIS_REPLICA_PORT", "6380")),
        db=14,
        decode_responses=True,
    )
    yield conexao
    conexao.close()


@pytest.fixture
def replica_fora_do_ar():
    conexao = redis.Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.5, retry=Retry(NoBackoff(), 0))
    yield conexao
    conexao.close()


@pytest.mark.parametrize("replica_do_teste", ["replica_sem_o_link", "replica_fora_do_ar"])
def test_link_fora_da_replica_e_lido_do_master(api, master, campanhas, cliques, request, replica_do_teste):
    codigo = criar_link(api)
    replica = request.getfixturevalue(replica_do_teste)
    if replica_do_teste == "replica_sem_o_link":
        assert replica.exists(f"link:{codigo}") == 0
    api_da_replica = TestClient(criar_app(master, campanhas, replica, cliques))

    resposta = acessar(api_da_replica, codigo)

    assert resposta.status_code == 302
    assert resposta.headers["location"] == URL


def test_clique_valido_grava_evento_e_soma_no_contador(api, master, sessao_cassandra):
    codigo = criar_link(api)
    antes = datetime.now(UTC) - timedelta(seconds=1)

    acessar(api, codigo, **{"user-agent": IPHONE, "referer": "https://instagram.com/"})

    [linha] = esperar_cliques(sessao_cassandra, codigo, 1)
    assert linha.short_code == codigo
    assert antes <= linha.clicado_em.replace(tzinfo=UTC) <= datetime.now(UTC)
    assert linha.clique_id.version == 1
    assert linha.dispositivo == "mobile"
    assert linha.referrer == "https://instagram.com/"
    assert linha.pais is None
    assert master.get(f"contador:{codigo}") == "1"


def test_nenhuma_operacao_da_aplicacao_executa_update_no_cassandra():
    # Só os comandos CQL usam UPDATE em maiúsculas; o update_one do MongoDB não casa.
    arquivos = list(Path(service.__file__).parent.glob("*.py"))
    assert arquivos
    for arquivo in arquivos:
        assert not re.search(r"\bUPDATE\b", arquivo.read_text(encoding="utf-8")), arquivo.name


def test_acessos_concorrentes_somam_exatamente_n(api, master, sessao_cassandra):
    codigo = criar_link(api)
    n = 50

    with ThreadPoolExecutor(max_workers=16) as executor:
        respostas = list(executor.map(lambda _: acessar(api, codigo), range(n)))

    assert {r.status_code for r in respostas} == {302}
    assert master.get(f"contador:{codigo}") == str(n)
    assert len(esperar_cliques(sessao_cassandra, codigo, n)) == n


class SemCassandra:
    def registrar(self, *args):
        pass


def test_confirmacao_perdida_do_incr_nao_soma_duas_vezes(master, monkeypatch, caplog):
    ler = redis.connection.Connection.read_response
    perdidas = []

    # O Redis aplica o INCR, mas a resposta não chega: repetir o comando somaria de novo.
    def perder_a_primeira(self, *args, **kwargs):
        resposta = ler(self, *args, **kwargs)
        if not perdidas:
            perdidas.append(resposta)
            raise redis.ConnectionError("confirmação perdida")
        return resposta

    monkeypatch.setattr(redis.connection.Connection, "read_response", perder_a_primeira)
    with caplog.at_level(logging.WARNING, logger="app.service"):
        service.contar_clique(master, SemCassandra(), "AAAAAAA", None, None)
    monkeypatch.undo()

    assert master.get("contador:AAAAAAA") == "1"
    assert "AAAAAAA" in caplog.text


class FuturoComFalha:
    def __init__(self, erro):
        self.erro = erro

    def add_errback(self, funcao):
        funcao(self.erro)


class SessaoForaDoAr:
    """Responde como o driver com o Cassandra parado: o futuro termina em erro."""

    def prepare(self, cql):
        return cql

    def execute_async(self, *args, **kwargs):
        return FuturoComFalha(ConnectionError("Cassandra fora do ar"))


def test_falha_na_gravacao_nao_muda_a_resposta_e_soma_nas_falhas(master, campanhas, replica, caplog):
    cliques = RegistroDeCliques(SessaoForaDoAr(), tempo_limite=2.0)
    api = TestClient(criar_app(master, campanhas, replica, cliques))
    codigo = criar_link(api)

    with caplog.at_level(logging.WARNING, logger="app.cliques"):
        resposta = acessar(api, codigo)

    assert resposta.status_code == 302
    assert resposta.headers["location"] == URL
    assert api.get("/metricas").json() == {"falhas_gravacao_clique": 1}
    assert codigo in caplog.text
    assert master.get(f"contador:{codigo}") == "1"


def test_metricas_comeca_sem_falhas(api):
    assert api.get("/metricas").json() == {"falhas_gravacao_clique": 0}


@pytest.mark.parametrize(
    ("user_agent", "dispositivo"),
    [
        (IPHONE, "mobile"),
        ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/126.0 Mobile Safari/537.36", "mobile"),
        ("Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148", "tablet"),
        ("Mozilla/5.0 (Linux; Android 14; SM-X710) AppleWebKit/537.36 Chrome/126.0 Safari/537.36", "tablet"),
        ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36", "desktop"),
        ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 Safari/605.1.15", "desktop"),
        ("Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)", "outro"),
        ("facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)", "outro"),
        ("curl/8.7.1", "outro"),
        ("", "outro"),
        (None, "outro"),
    ],
)
def test_dispositivo_sai_do_user_agent(user_agent, dispositivo):
    assert classificar_dispositivo(user_agent) == dispositivo
