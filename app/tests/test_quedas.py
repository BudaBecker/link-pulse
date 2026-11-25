"""CA-11 e CA-14 com a réplica do Redis e o Cassandra de fato parados (Q-58)."""

import math
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

import pytest
import redis
from fastapi.testclient import TestClient

from app.tests.test_redirecionamento import URL, acessar, criar_link

pytestmark = pytest.mark.quedas

COMPOSE = ["docker", "compose", "-f", str(Path(__file__).parents[2] / "docker-compose.yml")]
PEDIDOS_P95 = 200  # Q-59
PRAZO_FALHAS = 5.0  # os 2 s da gravação (Q-41) mais folga (Q-60)
PRAZO_VOLTA = 120.0


def esperar(condicao, prazo: float):
    fim = time.monotonic() + prazo
    while True:
        try:
            if condicao() is not False:
                return
        except Exception:
            if time.monotonic() > fim:
                raise
        if time.monotonic() > fim:
            raise AssertionError(f"condição não atendida em {prazo} s")
        time.sleep(0.2)


@contextmanager
def parado(servico: str, voltou=lambda: True):
    subprocess.run([*COMPOSE, "stop", servico], check=True, capture_output=True)
    try:
        yield
    finally:
        subprocess.run([*COMPOSE, "start", "--wait", servico], check=True, capture_output=True)
        esperar(voltou, PRAZO_VOLTA)


class Cronometro:
    """Marca, dentro do processo da aplicação, o tempo até o início da resposta de cada redirecionamento (Q-59)."""

    def __init__(self, app):
        self.app = app
        self.tempos = []

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/r/"):
            return await self.app(scope, receive, send)

        inicio = time.perf_counter()

        async def enviar(mensagem):
            if mensagem["type"] == "http.response.start":
                self.tempos.append(time.perf_counter() - inicio)
            await send(mensagem)

        await self.app(scope, receive, enviar)


def p95(tempos: list[float]) -> float:
    return sorted(tempos)[math.ceil(0.95 * len(tempos)) - 1]


def test_ca11_replica_parada_redireciona(api, replica):
    codigo = criar_link(api)
    cronometro = Cronometro(api.app)
    api_cronometrada = TestClient(cronometro)
    # Com o link já na réplica, o 302 só sai do master porque a réplica parou.
    esperar(lambda: replica.exists(f"link:{codigo}") == 1, prazo=5)

    with parado("redis-replica"):
        with pytest.raises(redis.RedisError):
            replica.ping()

        respostas = [acessar(api_cronometrada, codigo) for _ in range(5)]

    assert {r.status_code for r in respostas} == {302}
    assert {r.headers["location"] for r in respostas} == {URL}
    assert len(cronometro.tempos) == 5
    assert max(cronometro.tempos) < 1.0  # Q-61


def test_ca14_cassandra_parado_redireciona_rapido_e_conta_falhas(api, master, sessao_cassandra):
    codigo = criar_link(api)
    cronometro = Cronometro(api.app)
    api_cronometrada = TestClient(cronometro)
    falhas_antes = api.get("/metricas").json()["falhas_gravacao_clique"]

    def falhas() -> int:
        return api.get("/metricas").json()["falhas_gravacao_clique"] - falhas_antes

    with parado("cassandra", voltou=lambda: sessao_cassandra.execute("SELECT key FROM system.local")):
        respostas = [acessar(api_cronometrada, codigo) for _ in range(PEDIDOS_P95)]
        esperar(lambda: falhas() >= PEDIDOS_P95, PRAZO_FALHAS)
        falhas_durante = falhas()
        contador = master.get(f"contador:{codigo}")

    assert {r.status_code for r in respostas} == {302}
    assert {r.headers["location"] for r in respostas} == {URL}
    assert len(cronometro.tempos) == PEDIDOS_P95
    assert p95(cronometro.tempos) < 0.050
    assert falhas_durante == PEDIDOS_P95
    assert contador == str(PEDIDOS_P95)
