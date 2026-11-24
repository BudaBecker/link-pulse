import os
from contextlib import asynccontextmanager

import redis
from cassandra.cluster import Cluster
from fastapi import FastAPI
from pymongo import MongoClient
from pymongo.collection import Collection
from redis.backoff import NoBackoff
from redis.retry import Retry

from app.analytics import ConsultasDeCliques
from app.cliques import RegistroDeCliques
from app.router import router

TEMPO_LIMITE_CLIQUE = 2.0  # segundos (Q-41)


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    cluster = None
    if app.state.cliques is None or app.state.consultas is None:
        cluster = Cluster(
            [os.environ.get("CASSANDRA_HOST", "127.0.0.1")],
            port=int(os.environ.get("CASSANDRA_PORT", "9042")),
            protocol_version=5,
        )
        sessao = cluster.connect(os.environ.get("CASSANDRA_KEYSPACE", "linkpulse"))
        if app.state.cliques is None:
            app.state.cliques = RegistroDeCliques(sessao, TEMPO_LIMITE_CLIQUE)
        if app.state.consultas is None:
            app.state.consultas = ConsultasDeCliques(sessao)
    yield
    if cluster is not None:
        cluster.shutdown()


def abrir_redis(variavel_host: str, variavel_porta: str, porta_padrao: str, db: int = 0) -> redis.Redis:
    # Sem novas tentativas: um INCR repetido depois de uma resposta perdida somaria duas vezes,
    # e a leitura que falha na réplica vai direto ao master (Q-31).
    return redis.Redis(
        host=os.environ.get(variavel_host, "127.0.0.1"),
        port=int(os.environ.get(variavel_porta, porta_padrao)),
        db=db,
        decode_responses=True,
        retry=Retry(NoBackoff(), 0),
    )


def criar_app(
    master: redis.Redis | None = None,
    campanhas: Collection | None = None,
    replica: redis.Redis | None = None,
    cliques: RegistroDeCliques | None = None,
    consultas: ConsultasDeCliques | None = None,
) -> FastAPI:
    if master is None:
        master = abrir_redis("REDIS_MASTER_HOST", "REDIS_MASTER_PORT", "6379")

    if replica is None:
        replica = abrir_redis("REDIS_REPLICA_HOST", "REDIS_REPLICA_PORT", "6380")

    if campanhas is None:
        mongo = MongoClient(os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017"))
        campanhas = mongo[os.environ.get("MONGO_DB", "linkpulse")]["campanhas"]

    app = FastAPI(title="LinkPulse", lifespan=ciclo_de_vida)
    app.state.master = master
    app.state.replica = replica
    app.state.campanhas = campanhas
    app.state.cliques = cliques
    app.state.consultas = consultas
    app.include_router(router)
    return app


app = criar_app()
