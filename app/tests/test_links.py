import re

import pytest
import redis
from bson import ObjectId
from fastapi.testclient import TestClient
from redis.backoff import NoBackoff
from redis.retry import Retry

from app import service
from app.main import criar_app

INSTANTE_UTC = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z")


def fixar_codigos(monkeypatch, *codigos):
    sequencia = iter(codigos)
    monkeypatch.setattr(service, "gerar_short_code", lambda: next(sequencia))


def test_link_grava_url_cliente_e_criado_em(api, master):
    url = "https://Exemplo.com:443/Oferta?canal=A"
    resposta = api.post("/links", json={"url": url, "cliente_id": "c1"})

    assert resposta.status_code == 201
    codigo = resposta.json()["short_code"]
    link = master.hgetall(f"link:{codigo}")
    assert link.keys() == {"url", "cliente_id", "criado_em"}
    assert link["url"] == url
    assert link["cliente_id"] == "c1"
    assert INSTANTE_UTC.fullmatch(link["criado_em"])
    assert master.smembers("links:cliente:c1") == {codigo}


def test_link_grava_canal_e_expira_em_em_utc(api, master):
    corpo = {
        "url": "http://exemplo.com.br/a?b=1",
        "cliente_id": "c1",
        "canal": "instagram-stories",
        "expira_em": "2026-12-25T20:59:59-03:00",
    }

    link = master.hgetall(f"link:{api.post('/links', json=corpo).json()['short_code']}")

    assert link["canal"] == "instagram-stories"
    assert link["expira_em"] == "2026-12-25T23:59:59.000Z"


@pytest.mark.parametrize(
    "corpo",
    [
        {"url": "https://exemplo.com.br"},
        {"url": "https://exemplo.com.br", "cliente_id": ""},
        {"url": "https://exemplo.com.br", "cliente_id": None},
    ],
    ids=["ausente", "vazio", "nulo"],
)
def test_link_sem_cliente_e_rejeitado(api, master, corpo):
    resposta = api.post("/links", json=corpo)

    assert resposta.status_code == 422
    assert "short_code" not in resposta.json()
    assert master.dbsize() == 0


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        "exemplo.com.br",
        "ftp://exemplo.com.br/a",
        "https://",
        "javascript:alert(1)",
        "https://exem plo.com",
        "https://exemplo.com:abc/oferta",
        "https://loja|azul.com/oferta",
        "https:/loja.example/oferta",
        "https:///loja.example/oferta",
        " https://exemplo.com.br",
        "https://exemplo.com.br ",
    ],
)
def test_url_invalida_nao_grava_nada(api, master, campanhas, criar_campanha, url):
    campanha_id = criar_campanha()
    corpo = {"cliente_id": "c1", "campanha_id": campanha_id} | ({} if url is None else {"url": url})

    assert api.post("/links", json=corpo).status_code == 422
    assert master.dbsize() == 0
    assert campanhas.find_one({"_id": ObjectId(campanha_id)})["links"] == []


@pytest.mark.parametrize(
    "expira_em",
    [1798243200, "1798243200", "2026-12-25T23:59:59", "2026-12-25T20:59:59-03:75"],
    ids=["timestamp-numero", "timestamp-texto", "sem-fuso", "fuso-invalido"],
)
def test_expira_em_invalido_e_rejeitado(api, master, expira_em):
    corpo = {"url": "https://exemplo.com.br", "cliente_id": "c1", "expira_em": expira_em}

    resposta = api.post("/links", json=corpo)

    assert resposta.status_code == 422
    assert "short_code" not in resposta.json()
    assert master.dbsize() == 0


def test_colisao_preserva_o_link_existente(api, master, monkeypatch):
    existente = {"url": "https://existente.com.br", "cliente_id": "outro", "criado_em": "2026-01-01T00:00:00.000Z"}
    master.hset("link:AAAAAAA", mapping=existente)
    fixar_codigos(monkeypatch, "AAAAAAA", "BBBBBBB")

    resposta = api.post("/links", json={"url": "https://novo.com.br", "cliente_id": "c1"})

    assert resposta.status_code == 201
    assert resposta.json()["short_code"] == "BBBBBBB"
    assert master.hgetall("link:AAAAAAA") == existente
    assert master.hget("link:BBBBBBB", "url") == "https://novo.com.br"
    assert master.smembers("links:cliente:c1") == {"BBBBBBB"}


def test_colisoes_esgotadas_respondem_503(api, master, monkeypatch):
    master.hset("link:AAAAAAA", mapping={"url": "https://existente.com.br"})
    fixar_codigos(monkeypatch, *["AAAAAAA"] * service.MAX_TENTATIVAS)

    resposta = api.post("/links", json={"url": "https://novo.com.br", "cliente_id": "c1"})

    assert resposta.status_code == 503
    assert "short_code" not in resposta.json()
    assert master.keys() == ["link:AAAAAAA"]


def test_link_entra_na_lista_da_campanha(api, campanhas, criar_campanha):
    campanha_id = criar_campanha()

    codigos = []
    for canal in ("instagram", "email"):
        corpo = {"url": f"https://exemplo.com.br/{canal}", "cliente_id": "c1", "canal": canal, "campanha_id": campanha_id}
        codigos.append(api.post("/links", json=corpo).json()["short_code"])

    assert campanhas.find_one({"_id": ObjectId(campanha_id)})["links"] == codigos


@pytest.mark.parametrize("campanha_id", [str(ObjectId()), "nao-e-um-id"], ids=["id-livre", "id-malformado"])
def test_campanha_inexistente_nao_grava_nada(api, master, campanha_id):
    corpo = {"url": "https://exemplo.com.br", "cliente_id": "c1", "campanha_id": campanha_id}

    resposta = api.post("/links", json=corpo)

    assert resposta.status_code == 422
    assert "short_code" not in resposta.json()
    assert master.dbsize() == 0


@pytest.fixture(params=["replica", "redis-fora-do-ar"])
def redis_que_falha(request):
    if request.param == "replica":
        # A réplica responde READONLY a qualquer escrita.
        yield request.getfixturevalue("replica")
        return
    conexao = redis.Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.5, retry=Retry(NoBackoff(), 0))
    yield conexao
    conexao.close()


def test_falha_de_escrita_responde_503_sem_short_code(master, campanhas, redis_que_falha):
    campanha_id = str(campanhas.insert_one({"cliente_id": "c1", "nome": "Natal", "links": []}).inserted_id)
    api = TestClient(criar_app(redis_que_falha, campanhas))

    resposta = api.post("/links", json={"url": "https://exemplo.com.br", "cliente_id": "c1", "campanha_id": campanha_id})

    assert resposta.status_code == 503
    assert "short_code" not in resposta.json()
    assert master.dbsize() == 0
    assert campanhas.find_one({"_id": ObjectId(campanha_id)})["links"] == []
