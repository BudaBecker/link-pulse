from collections import Counter
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import redis

from app.models import Janela

FUSO_DOS_DIAS = ZoneInfo("America/Sao_Paulo")

CONTAR_CLIQUES = (
    "SELECT COUNT(*) FROM cliques_por_link WHERE short_code = ? AND clicado_em >= ? AND clicado_em <= ?"
)
INSTANTES_DOS_CLIQUES = (
    "SELECT clicado_em FROM cliques_por_link WHERE short_code = ? AND clicado_em >= ? AND clicado_em <= ?"
)
DISPOSITIVOS_DOS_CLIQUES = (
    "SELECT dispositivo FROM cliques_por_link WHERE short_code = ? AND clicado_em >= ? AND clicado_em <= ?"
)
DISPOSITIVOS = ("mobile", "desktop", "tablet", "outro")


class LinkInexistente(Exception):
    pass


class ConsultasDeCliques:
    def __init__(self, sessao):
        self._sessao = sessao
        self._contar = sessao.prepare(CONTAR_CLIQUES)
        self._instantes = sessao.prepare(INSTANTES_DOS_CLIQUES)
        self._dispositivos = sessao.prepare(DISPOSITIVOS_DOS_CLIQUES)

    def total(self, short_code: str, janela: Janela) -> int:
        return self._sessao.execute(self._contar, (short_code, *janela.milissegundos_incluidos)).one().count

    def totais(self, short_codes: list[str], janela: Janela) -> dict[str, int]:
        futuros = {c: self._sessao.execute_async(self._contar, (c, *janela.milissegundos_incluidos)) for c in short_codes}
        return {c: futuro.result().one().count for c, futuro in futuros.items()}

    def instantes(self, short_code: str, janela: Janela) -> Iterator[datetime]:
        linhas = self._sessao.execute(self._instantes, (short_code, *janela.milissegundos_incluidos))
        # O driver devolve o timestamp sem fuso, em UTC.
        return (linha.clicado_em.replace(tzinfo=UTC) for linha in linhas)

    def dispositivos(self, short_code: str, janela: Janela) -> Iterator[str]:
        linhas = self._sessao.execute(self._dispositivos, (short_code, *janela.milissegundos_incluidos))
        return (linha.dispositivo for linha in linhas)


def exigir_link(master: redis.Redis, short_code: str) -> None:
    if not master.exists(f"link:{short_code}"):
        raise LinkInexistente("short_code não existe")


def cliques_por_dia(master: redis.Redis, consultas: ConsultasDeCliques, short_code: str, janela: Janela) -> dict:
    exigir_link(master, short_code)
    contagem = Counter(i.astimezone(FUSO_DOS_DIAS).date() for i in consultas.instantes(short_code, janela))

    primeiro = janela.inicio.astimezone(FUSO_DOS_DIAS).date()
    ultimo = janela.fim.astimezone(FUSO_DOS_DIAS).date()
    dias = (primeiro + timedelta(days=n) for n in range((ultimo - primeiro).days + 1))
    return {
        "short_code": short_code,
        "dias": [{"dia": dia.isoformat(), "cliques": contagem[dia]} for dia in dias],
    }


def cliques_por_canal(master: redis.Redis, consultas: ConsultasDeCliques, cliente_id: str, janela: Janela) -> dict:
    codigos = list(master.smembers(f"links:cliente:{cliente_id}"))
    pipe = master.pipeline(transaction=False)
    for codigo in codigos:
        pipe.hget(f"link:{codigo}", "canal")

    canais = pipe.execute()
    totais = consultas.totais(codigos, janela)
    itens = [
        {"short_code": codigo, "canal": canal, "cliques": totais[codigo]}
        for codigo, canal in zip(codigos, canais)
    ]
    itens.sort(key=lambda item: (-item["cliques"], item["short_code"]))
    return {"cliente_id": cliente_id, "canais": itens}


def total_de_cliques(master: redis.Redis, consultas: ConsultasDeCliques, short_code: str, janela: Janela) -> dict:
    exigir_link(master, short_code)
    return {"short_code": short_code, "cliques": consultas.total(short_code, janela)}


def cliques_por_dispositivo(master: redis.Redis, consultas: ConsultasDeCliques, short_code: str, janela: Janela) -> dict:
    exigir_link(master, short_code)
    contagem = Counter(consultas.dispositivos(short_code, janela))
    return {
        "short_code": short_code,
        "dispositivos": [{"dispositivo": d, "cliques": contagem[d]} for d in DISPOSITIVOS],
    }
