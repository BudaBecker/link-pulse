import os

import redis
from fastapi import FastAPI
from pymongo import MongoClient
from pymongo.collection import Collection

from app.router import router


def criar_app(master: redis.Redis | None = None, campanhas: Collection | None = None) -> FastAPI:
    if master is None:
        master = redis.Redis(
            host=os.environ.get("REDIS_MASTER_HOST", "127.0.0.1"),
            port=int(os.environ.get("REDIS_MASTER_PORT", "6379")),
            decode_responses=True,
        )
        
    if campanhas is None:
        mongo = MongoClient(os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017"))
        campanhas = mongo[os.environ.get("MONGO_DB", "linkpulse")]["campanhas"]

    app = FastAPI(title="LinkPulse")
    app.state.master = master
    app.state.campanhas = campanhas
    app.include_router(router)
    return app


app = criar_app()
