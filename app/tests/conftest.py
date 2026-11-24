import os

import pytest
import redis
from fastapi.testclient import TestClient
from pymongo import MongoClient

from app.main import criar_app

# Banco 15 do Redis e um banco próprio no MongoDB, para não apagar os dados da demonstração.
BANCO_REDIS = 15
BANCO_MONGO = "linkpulse_testes"


def conectar_redis(variavel_porta: str, porta_padrao: str) -> redis.Redis:
    return redis.Redis(
        host=os.environ.get("REDIS_MASTER_HOST", "127.0.0.1"),
        port=int(os.environ.get(variavel_porta, porta_padrao)),
        db=BANCO_REDIS,
        decode_responses=True,
    )


@pytest.fixture
def master():
    conexao = conectar_redis("REDIS_MASTER_PORT", "6379")
    conexao.flushdb()
    yield conexao
    conexao.flushdb()
    conexao.close()


@pytest.fixture
def replica():
    conexao = conectar_redis("REDIS_REPLICA_PORT", "6380")
    yield conexao
    conexao.close()


@pytest.fixture
def campanhas():
    mongo = MongoClient(os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017"), serverSelectionTimeoutMS=3000)
    mongo.drop_database(BANCO_MONGO)
    yield mongo[BANCO_MONGO]["campanhas"]
    mongo.drop_database(BANCO_MONGO)
    mongo.close()


@pytest.fixture
def api(master, campanhas):
    return TestClient(criar_app(master, campanhas))


@pytest.fixture
def criar_campanha(api):
    def criar(**campos):
        corpo = {"cliente_id": "c1", "nome": "Natal"} | campos
        return api.post("/campanhas", json=corpo).json()["campanha_id"]

    return criar
