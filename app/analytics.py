from collections import Counter
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import redis

FUSO_DOS_DIAS = ZoneInfo("America/Sao_Paulo")

CONTAR_CLIQUES = (
    "SELECT COUNT(*) FROM cliques_por_link WHERE short_code = ? AND clicado_em >= ? AND clicado_em <= ?"
)
INSTANTES_DOS_CLIQUES = (
    "SELECT clicado_em FROM cliques_por_link WHERE short_code = ? AND clicado_em >= ? AND clicado_em <= ?"
)


class LinkInexistente(Exception):
    pass


def em_milissegundos(inicio: datetime, fim: datetime) -> tuple[datetime, datetime]:
    # O driver trunca os microssegundos; sem subir o início, entraria um clique anterior a ele.
    def truncar(momento: datetime) -> datetime:
        return momento.replace(microsecond=momento.microsecond // 1000 * 1000)

    inicio_ms = truncar(inicio)
    if inicio_ms < inicio:
        inicio_ms += timedelta(milliseconds=1)
    return inicio_ms, truncar(fim)


class ConsultasDeCliques:
    def __init__(self, sessao):
        self._sessao = sessao
        self._contar = sessao.prepare(CONTAR_CLIQUES)
        self._instantes = sessao.prepare(INSTANTES_DOS_CLIQUES)

    def total(self, short_code: str, inicio: datetime, fim: datetime) -> int:
        return self._sessao.execute(self._contar, (short_code, *em_milissegundos(inicio, fim))).one().count

    def totais(self, short_codes: list[str], inicio: datetime, fim: datetime) -> dict[str, int]:
        janela = em_milissegundos(inicio, fim)
        futuros = {c: self._sessao.execute_async(self._contar, (c, *janela)) for c in short_codes}
        return {c: futuro.result().one().count for c, futuro in futuros.items()}

    def instantes(self, short_code: str, inicio: datetime, fim: datetime) -> Iterator[datetime]:
        linhas = self._sessao.execute(self._instantes, (short_code, *em_milissegundos(inicio, fim)))
        # O driver devolve o timestamp sem fuso, em UTC.
        return (linha.clicado_em.replace(tzinfo=UTC) for linha in linhas)


def exigir_link(master: redis.Redis, short_code: str) -> None:
    if not master.exists(f"link:{short_code}"):
        raise LinkInexistente("short_code não existe")


def cliques_por_dia(
    master: redis.Redis, consultas: ConsultasDeCliques, short_code: str, inicio: datetime, fim: datetime
) -> dict:
    exigir_link(master, short_code)
    contagem = Counter(i.astimezone(FUSO_DOS_DIAS).date() for i in consultas.instantes(short_code, inicio, fim))

    primeiro = inicio.astimezone(FUSO_DOS_DIAS).date()
    ultimo = fim.astimezone(FUSO_DOS_DIAS).date()
    dias = (primeiro + timedelta(days=n) for n in range((ultimo - primeiro).days + 1))
    return {
        "short_code": short_code,
        "dias": [{"dia": dia.isoformat(), "cliques": contagem[dia]} for dia in dias],
    }


def cliques_por_canal(
    master: redis.Redis, consultas: ConsultasDeCliques, cliente_id: str, inicio: datetime, fim: datetime
) -> dict:
    codigos = list(master.smembers(f"links:cliente:{cliente_id}"))
    pipe = master.pipeline(transaction=False)
    for codigo in codigos:
        pipe.hget(f"link:{codigo}", "canal")

    canais = pipe.execute()
    totais = consultas.totais(codigos, inicio, fim)
    itens = [
        {"short_code": codigo, "canal": canal, "cliques": totais[codigo]}
        for codigo, canal in zip(codigos, canais)
    ]
    itens.sort(key=lambda item: (-item["cliques"], item["short_code"]))
    return {"cliente_id": cliente_id, "canais": itens}


def total_de_cliques(
    master: redis.Redis, consultas: ConsultasDeCliques, short_code: str, inicio: datetime, fim: datetime
) -> dict:
    exigir_link(master, short_code)
    return {"short_code": short_code, "cliques": consultas.total(short_code, inicio, fim)}
