import re
from datetime import UTC, datetime, timedelta

import pytest
from cassandra.util import uuid_from_time
from fastapi.testclient import TestClient

from app.analytics import ConsultasDeCliques
from app.main import criar_app
from app.tests.test_redirecionamento import IPHONE, acessar, criar_link, esperar_cliques

INICIO = "2026-11-20T00:00:00-03:00"
FIM = "2026-11-22T23:59:59.999-03:00"
WINDOWS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"


def instante(texto: str) -> datetime:
    return datetime.fromisoformat(texto).astimezone(UTC)


def gravar_cliques(sessao, codigo: str, *instantes: str, dispositivo: str | None = None) -> None:
    insercao = sessao.prepare(
        "INSERT INTO cliques_por_link (short_code, clicado_em, clique_id, dispositivo) VALUES (?, ?, ?, ?)"
    )
    for texto in instantes:
        momento = instante(texto)
        sessao.execute(insercao, (codigo, momento, uuid_from_time(momento), dispositivo))


def consultar(api, consulta: str, **parametros):
    return api.get(f"/analytics/{consulta}", params={"inicio": INICIO, "fim": FIM} | parametros)


@pytest.fixture
def eventos(api, sessao_cassandra) -> dict:
    links = {
        "instagram": criar_link(api, canal="instagram"),
        "email": criar_link(api, canal="email"),
        "sms": criar_link(api, canal="sms"),
        "sem_canal": criar_link(api),
        "outro_cliente": criar_link(api, cliente_id="c2", canal="instagram"),
    }
    gravar_cliques(
        sessao_cassandra,
        links["instagram"],
        "2026-11-20T02:59:59.999Z",  # 1 ms antes do início: fora
        "2026-11-20T03:00:00.000Z",  # o próprio início: 20/11
        "2026-11-21T01:30:00.000Z",  # 20/11 às 22:30 em Brasília, 21/11 em UTC
        "2026-11-21T15:00:00.000Z",  # dois cliques no mesmo milissegundo: 21/11
        "2026-11-21T15:00:00.000Z",
        "2026-11-23T02:59:59.999Z",  # o próprio fim: 22/11
        "2026-11-23T03:00:00.000Z",  # 1 ms depois do fim: fora
    )
    gravar_cliques(sessao_cassandra, links["email"], "2026-11-10T12:00:00Z", "2026-11-21T12:00:00Z", "2026-11-22T12:00:00Z")
    gravar_cliques(sessao_cassandra, links["sms"], "2026-11-20T10:00:00Z", "2026-11-22T20:00:00Z")
    gravar_cliques(sessao_cassandra, links["sem_canal"], "2026-11-25T12:00:00Z")
    gravar_cliques(sessao_cassandra, links["outro_cliente"], "2026-11-21T12:00:00Z", "2026-11-21T13:00:00Z")
    return links


def test_cliques_por_dia_agrupa_pelos_dias_de_brasilia(api, eventos):
    resposta = consultar(api, "por-dia", short_code=eventos["instagram"])

    assert resposta.status_code == 200
    assert resposta.json() == {
        "short_code": eventos["instagram"],
        "dias": [
            {"dia": "2026-11-20", "cliques": 2},
            {"dia": "2026-11-21", "cliques": 2},
            {"dia": "2026-11-22", "cliques": 1},
        ],
    }


def test_cliques_por_dia_traz_zero_nos_dias_sem_clique(api, eventos):
    resposta = consultar(api, "por-dia", short_code=eventos["email"])

    assert resposta.json()["dias"] == [
        {"dia": "2026-11-20", "cliques": 0},
        {"dia": "2026-11-21", "cliques": 1},
        {"dia": "2026-11-22", "cliques": 1},
    ]


def test_cliques_por_canal_compara_os_links_do_cliente(api, eventos):
    resposta = consultar(api, "por-canal", cliente_id="c1")

    empatados = sorted([(eventos["email"], "email"), (eventos["sms"], "sms")])
    assert resposta.status_code == 200
    assert resposta.json() == {
        "cliente_id": "c1",
        "canais": [
            {"short_code": eventos["instagram"], "canal": "instagram", "cliques": 5},
            *({"short_code": codigo, "canal": canal, "cliques": 2} for codigo, canal in empatados),
            {"short_code": eventos["sem_canal"], "canal": None, "cliques": 0},
        ],
    }


def test_total_conta_o_intervalo_fechado(api, eventos):
    totais = {nome: consultar(api, "total", short_code=codigo).json() for nome, codigo in eventos.items()}

    assert totais["instagram"] == {"short_code": eventos["instagram"], "cliques": 5}
    assert {nome: total["cliques"] for nome, total in totais.items()} == {
        "instagram": 5,
        "email": 2,
        "sms": 2,
        "sem_canal": 0,
        "outro_cliente": 2,
    }


def test_cliques_por_dispositivo_traz_as_quatro_categorias(api, sessao_cassandra):
    codigo = criar_link(api)
    gravar_cliques(sessao_cassandra, codigo, "2026-11-20T03:00:00.000Z", "2026-11-21T12:00:00Z", dispositivo="mobile")
    gravar_cliques(sessao_cassandra, codigo, "2026-11-21T12:00:00Z", "2026-11-21T12:00:00Z", dispositivo="mobile")
    gravar_cliques(sessao_cassandra, codigo, "2026-11-23T02:59:59.999Z", dispositivo="desktop")
    gravar_cliques(sessao_cassandra, codigo, "2026-11-22T10:00:00Z", dispositivo="outro")
    gravar_cliques(sessao_cassandra, codigo, "2026-11-20T02:59:59.999Z", "2026-11-23T03:00:00.000Z", dispositivo="tablet")

    resposta = consultar(api, "por-dispositivo", short_code=codigo)

    assert resposta.status_code == 200
    assert resposta.json() == {
        "short_code": codigo,
        "dispositivos": [
            {"dispositivo": "mobile", "cliques": 4},
            {"dispositivo": "desktop", "cliques": 1},
            {"dispositivo": "tablet", "cliques": 0},
            {"dispositivo": "outro", "cliques": 1},
        ],
    }


def test_janela_de_um_unico_instante(api, eventos):
    resposta = consultar(api, "total", short_code=eventos["instagram"], inicio=INICIO, fim=INICIO)

    assert resposta.json()["cliques"] == 1


@pytest.mark.parametrize(
    ("inicio", "fim", "esperado"),
    [
        ("2026-11-20T12:00:00.000500Z", "2026-11-20T12:00:00.001Z", 0),
        ("2026-11-20T11:59:59Z", "2026-11-20T11:59:59.999900Z", 0),
        ("2026-11-20T12:00:00.000100Z", "2026-11-20T12:00:00.000900Z", 0),
        ("2026-11-20T11:59:59.999500Z", "2026-11-20T12:00:00.000900Z", 1),
        ("2026-11-20T12:00:00.000000001Z", "2026-11-20T12:00:00.001Z", 0),
        ("2026-11-20T12:00:00.000000001Z", "2026-11-20T12:00:00.000000002Z", 0),
        ("2026-11-20T12:00:00.0000000002Z", "2026-11-20T12:00:00.000000001Z", 0),
        ("2026-11-20T12:00:00.000000000Z", "2026-11-20T12:00:00.000000001Z", 1),
    ],
)
@pytest.mark.parametrize("separador", [".", ","])
def test_limites_com_fracao_de_milissegundo_respeitam_o_intervalo_fechado(
    api, sessao_cassandra, inicio, fim, esperado, separador
):
    codigo = criar_link(api, cliente_id="c3")
    gravar_cliques(sessao_cassandra, codigo, "2026-11-20T12:00:00.000Z", dispositivo="mobile")
    janela = {"inicio": inicio.replace(".", separador), "fim": fim.replace(".", separador)}

    assert consultar(api, "total", short_code=codigo, **janela).json()["cliques"] == esperado
    assert consultar(api, "por-dia", short_code=codigo, **janela).json()["dias"] == [
        {"dia": "2026-11-20", "cliques": esperado}
    ]
    assert consultar(api, "por-canal", cliente_id="c3", **janela).json()["canais"][0]["cliques"] == esperado
    dispositivos = consultar(api, "por-dispositivo", short_code=codigo, **janela).json()["dispositivos"]
    assert sum(d["cliques"] for d in dispositivos) == esperado


@pytest.mark.parametrize(
    ("inicio", "fim"),
    [
        ("2026-11-20T12:00:00.000000001Z", "2026-11-20T12:00:00.000000000Z"),
        ("2026-11-20T12:00:00.000000001Z", "2026-11-20T12:00:00.0000000005Z"),
    ],
)
@pytest.mark.parametrize("separador", [".", ","])
def test_inicio_depois_do_fim_alem_do_microssegundo_responde_422(api, inicio, fim, separador):
    codigo = criar_link(api, cliente_id="c3")
    janela = {"inicio": inicio.replace(".", separador), "fim": fim.replace(".", separador)}

    assert consultar(api, "total", short_code=codigo, **janela).status_code == 422
    assert consultar(api, "por-dia", short_code=codigo, **janela).status_code == 422
    assert consultar(api, "por-canal", cliente_id="c3", **janela).status_code == 422
    assert consultar(api, "por-dispositivo", short_code=codigo, **janela).status_code == 422


def test_consultas_refletem_os_redirecionamentos(api, sessao_cassandra):
    codigo = criar_link(api, canal="instagram")
    for user_agent in (IPHONE, IPHONE, WINDOWS):
        assert acessar(api, codigo, **{"user-agent": user_agent}).status_code == 302
    assert len(esperar_cliques(sessao_cassandra, codigo, 3)) == 3

    agora = datetime.now(UTC)
    janela = {"inicio": (agora - timedelta(hours=1)).isoformat(), "fim": (agora + timedelta(hours=1)).isoformat()}

    assert consultar(api, "total", short_code=codigo, **janela).json()["cliques"] == 3
    assert sum(d["cliques"] for d in consultar(api, "por-dia", short_code=codigo, **janela).json()["dias"]) == 3
    assert consultar(api, "por-canal", cliente_id="c1", **janela).json()["canais"] == [
        {"short_code": codigo, "canal": "instagram", "cliques": 3}
    ]
    assert consultar(api, "por-dispositivo", short_code=codigo, **janela).json()["dispositivos"] == [
        {"dispositivo": "mobile", "cliques": 2},
        {"dispositivo": "desktop", "cliques": 1},
        {"dispositivo": "tablet", "cliques": 0},
        {"dispositivo": "outro", "cliques": 0},
    ]


class SessaoGravada:
    def __init__(self, sessao):
        self._sessao = sessao
        self.preparados: list[str] = []
        self.executados: list[str] = []

    def prepare(self, comando):
        self.preparados.append(comando)
        return self._sessao.prepare(comando)

    def execute(self, comando, *args, **kwargs):
        self.executados.append(comando.query_string)
        return self._sessao.execute(comando, *args, **kwargs)

    def execute_async(self, comando, *args, **kwargs):
        self.executados.append(comando.query_string)
        return self._sessao.execute_async(comando, *args, **kwargs)


def test_consultas_executadas_informam_short_code_sem_allow_filtering(
    master, campanhas, replica, cliques, sessao_cassandra, eventos
):
    sessao = SessaoGravada(sessao_cassandra)
    api = TestClient(criar_app(master, campanhas, replica, cliques, ConsultasDeCliques(sessao)))

    consultar(api, "por-dia", short_code=eventos["instagram"])
    consultar(api, "por-canal", cliente_id="c1")
    consultar(api, "total", short_code=eventos["instagram"])
    consultar(api, "por-dispositivo", short_code=eventos["instagram"])

    assert len(sessao.executados) == 1 + 4 + 1 + 1
    assert set(sessao.executados) <= set(sessao.preparados)
    for comando in sessao.preparados:
        assert re.search(r"\bFROM cliques_por_link WHERE short_code = \?", comando), comando
        assert "ALLOW FILTERING" not in comando.upper(), comando


@pytest.mark.parametrize("consulta", ["por-dia", "total", "por-dispositivo"])
def test_link_inexistente_responde_404(api, consulta):
    assert consultar(api, consulta, short_code="naoExiste").status_code == 404


def test_link_sem_cliques_responde_zeros(api):
    codigo = criar_link(api)

    assert consultar(api, "total", short_code=codigo).json()["cliques"] == 0
    assert [d["cliques"] for d in consultar(api, "por-dia", short_code=codigo).json()["dias"]] == [0, 0, 0]
    dispositivos = consultar(api, "por-dispositivo", short_code=codigo).json()["dispositivos"]
    assert [d["cliques"] for d in dispositivos] == [0, 0, 0, 0]


def test_cliente_sem_links_responde_lista_vazia(api):
    resposta = consultar(api, "por-canal", cliente_id="sem-links")

    assert resposta.status_code == 200
    assert resposta.json() == {"cliente_id": "sem-links", "canais": []}


@pytest.mark.parametrize(
    "parametros",
    [
        {"short_code": None},
        {"short_code": ""},
        {"inicio": None},
        {"fim": None},
        {"inicio": "2026-11-20T00:00:00"},
        {"fim": "1798243200"},
        {"inicio": "20/11/2026"},
        {"inicio": FIM, "fim": INICIO},
    ],
)
@pytest.mark.parametrize("consulta", ["por-dia", "total", "por-dispositivo"])
def test_janela_invalida_responde_422(api, consulta, parametros):
    codigo = criar_link(api)
    pedido = {"short_code": codigo, "inicio": INICIO, "fim": FIM} | parametros

    resposta = api.get(f"/analytics/{consulta}", params={k: v for k, v in pedido.items() if v is not None})

    assert resposta.status_code == 422


def test_por_canal_sem_cliente_id_responde_422(api):
    assert api.get("/analytics/por-canal", params={"inicio": INICIO, "fim": FIM}).status_code == 422
