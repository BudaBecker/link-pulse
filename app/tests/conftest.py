import os
from pathlib import Path

import pytest
from cassandra.cluster import Cluster
from fastapi.testclient import TestClient
from pymongo import MongoClient

from app.analytics import ConsultasDeCliques
from app.cliques import RegistroDeCliques
from app.main import TEMPO_LIMITE_CLIQUE, abrir_redis, criar_app

# Banco 15 do Redis e bancos próprios no MongoDB e no Cassandra, para não apagar os dados da demonstração.
BANCO_REDIS = 15
BANCO_MONGO = "linkpulse_testes"
KEYSPACE_CASSANDRA = "linkpulse_testes"
ESQUEMA_CASSANDRA = Path(__file__).parents[2] / "infra" / "cassandra" / "esquema.cql"


@pytest.fixture
def master():
    conexao = abrir_redis("REDIS_MASTER_HOST", "REDIS_MASTER_PORT", "6379", db=BANCO_REDIS)
    conexao.flushdb()
    yield conexao
    conexao.flushdb()
    conexao.close()


@pytest.fixture
def replica():
    conexao = abrir_redis("REDIS_MASTER_HOST", "REDIS_REPLICA_PORT", "6380", db=BANCO_REDIS)
    yield conexao
    conexao.close()


@pytest.fixture
def campanhas():
    mongo = MongoClient(os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017"), serverSelectionTimeoutMS=3000)
    mongo.drop_database(BANCO_MONGO)
    yield mongo[BANCO_MONGO]["campanhas"]
    mongo.drop_database(BANCO_MONGO)
    mongo.close()


@pytest.fixture(scope="session")
def sessao_cassandra():
    cluster = Cluster(
        [os.environ.get("CASSANDRA_HOST", "127.0.0.1")],
        port=int(os.environ.get("CASSANDRA_PORT", "9042")),
        protocol_version=5,
    )
    sessao = cluster.connect()
    esquema = ESQUEMA_CASSANDRA.read_text(encoding="utf-8").replace("linkpulse", KEYSPACE_CASSANDRA)
    for comando in esquema.split(";"):
        if comando.strip():
            sessao.execute(comando)
    sessao.set_keyspace(KEYSPACE_CASSANDRA)
    yield sessao
    cluster.shutdown()


@pytest.fixture
def cliques(sessao_cassandra, master):
    yield RegistroDeCliques(sessao_cassandra, TEMPO_LIMITE_CLIQUE)
    # Roda antes do flushdb do master: apaga os cliques dos links que o teste criou.
    for chave in master.scan_iter("link:*"):
        sessao_cassandra.execute("DELETE FROM cliques_por_link WHERE short_code = %s", (chave.removeprefix("link:"),))


@pytest.fixture
def consultas(sessao_cassandra):
    return ConsultasDeCliques(sessao_cassandra)


@pytest.fixture
def api(master, campanhas, replica, cliques, consultas):
    return TestClient(criar_app(master, campanhas, replica, cliques, consultas))


@pytest.fixture
def criar_campanha(api):
    def criar(**campos):
        corpo = {"cliente_id": "c1", "nome": "Natal"} | campos
        return api.post("/campanhas", json=corpo).json()["campanha_id"]

    return criar
