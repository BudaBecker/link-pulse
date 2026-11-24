import os
from contextlib import asynccontextmanager

import redis
from cassandra.cluster import Cluster
from fastapi import FastAPI
from pymongo import MongoClient
from pymongo.collection import Collection
from redis.backoff import NoBackoff
from redis.retry import Retry

from app.cliques import RegistroDeCliques
from app.router import router

TEMPO_LIMITE_CLIQUE = 2.0  # segundos (Q-41)


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    cluster = None
    if app.state.cliques is None:
        cluster = Cluster(
            [os.environ.get("CASSANDRA_HOST", "127.0.0.1")],
            port=int(os.environ.get("CASSANDRA_PORT", "9042")),
            protocol_version=5,
        )
        sessao = cluster.connect(os.environ.get("CASSANDRA_KEYSPACE", "linkpulse"))
        app.state.cliques = RegistroDeCliques(sessao, TEMPO_LIMITE_CLIQUE)
    yield
    if cluster is not None:
        cluster.shutdown()


def criar_app(
    master: redis.Redis | None = None,
    campanhas: Collection | None = None,
    replica: redis.Redis | None = None,
    cliques: RegistroDeCliques | None = None,
) -> FastAPI:
    if master is None:
        master = redis.Redis(
            host=os.environ.get("REDIS_MASTER_HOST", "127.0.0.1"),
            port=int(os.environ.get("REDIS_MASTER_PORT", "6379")),
            decode_responses=True,
        )

    if replica is None:
        # Sem novas tentativas: se a réplica não responde, a leitura vai direto ao master (Q-31).
        replica = redis.Redis(
            host=os.environ.get("REDIS_REPLICA_HOST", "127.0.0.1"),
            port=int(os.environ.get("REDIS_REPLICA_PORT", "6380")),
            decode_responses=True,
            retry=Retry(NoBackoff(), 0),
        )

    if campanhas is None:
        mongo = MongoClient(os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017"))
        campanhas = mongo[os.environ.get("MONGO_DB", "linkpulse")]["campanhas"]

    app = FastAPI(title="LinkPulse", lifespan=ciclo_de_vida)
    app.state.master = master
    app.state.replica = replica
    app.state.campanhas = campanhas
    app.state.cliques = cliques
    app.include_router(router)
    return app


app = criar_app()
