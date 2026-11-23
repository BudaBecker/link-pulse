"""Carrega a base de referência nos dois lados do benchmark (SPEC-005, passo 1).

Roda no contêiner `carga`, com as bibliotecas fixadas; quem o chama é
`python benchmark/base.py carregar`, que antes recria os volumes de benchmark.
Os parâmetros vêm do manifesto benchmark/base-de-referencia.json.

- Redis: Hash `cliente:{id}` (fora do Set `clientes`), Hash `link:{short_code}`,
  Set `links:cliente:{id}` e `contador:{short_code}` com o total de cliques.
- Cassandra: `cliques_por_link`, em lotes UNLOGGED de uma só partição, com um
  número limitado de lotes em andamento por processo.
- PostgreSQL: `links`, `contadores` e `cliques` por COPY, no modelo do ADR-0014;
  depois `VACUUM (ANALYZE)` e `CHECKPOINT`, para o autovacuum não rodar no meio
  das medições.

Os cliques são gerados bloco a bloco em cada processo e nunca ficam todos em
memória. A carga recusa bancos que já tenham dados.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import get_context
from pathlib import Path

import psycopg
import redis
from cassandra import ConsistencyLevel
from cassandra.cluster import Cluster
from cassandra.query import BatchStatement, BatchType

from referencia import Base, Bloco, ms_para_datetime, iso

MANIFESTO = Path(__file__).with_name("base-de-referencia.json")
LINHAS_POR_LOTE_CASSANDRA = 30  # cerca de 3 KiB, abaixo do aviso de 5 KiB do Cassandra
LOTES_EM_ANDAMENTO = 16  # por processo
LINHAS_POR_TAREFA = 100_000
TENTATIVAS = 5


def ler_base() -> Base:
    dados = json.loads(MANIFESTO.read_text(encoding="utf-8"))
    return Base(semente=dados["semente"], fim=dados["fim"])


def conectar_postgres() -> psycopg.Connection:
    return psycopg.connect(
        host="postgres",
        user="linkpulse",
        password=os.environ.get("POSTGRES_PASSWORD", "linkpulse"),
        dbname="linkpulse",
    )


def tarefas(base: Base) -> list[list[Bloco]]:
    """Agrupa os blocos em tarefas de cerca de LINHAS_POR_TAREFA cliques."""
    grupos: list[list[Bloco]] = [[]]
    linhas = 0
    for bloco in base.blocos():
        if linhas >= LINHAS_POR_TAREFA:
            grupos.append([])
            linhas = 0
        grupos[-1].append(bloco)
        linhas += bloco.quantidade
    return grupos


class Progresso:
    def __init__(self, rotulo: str, total: int) -> None:
        self.rotulo, self.total = rotulo, total
        self.feito = 0
        self.inicio = time.monotonic()
        self.ultimo = 0.0

    def somar(self, n: int) -> None:
        self.feito += n
        agora = time.monotonic()
        if agora - self.ultimo >= 10 or self.feito == self.total:
            self.ultimo = agora
            decorrido = agora - self.inicio
            print(
                f"  {self.rotulo}: {self.feito:,}/{self.total:,} cliques "
                f"({100 * self.feito / self.total:.0f}%) em {decorrido:.0f} s, "
                f"{self.feito / max(decorrido, 1e-9):,.0f}/s",
                flush=True,
            )

    def segundos(self) -> float:
        return time.monotonic() - self.inicio


# --- Redis -------------------------------------------------------------------


def carregar_redis(base: Base) -> None:
    mestre = redis.Redis(host="redis-master")
    if mestre.dbsize():
        sys.exit("Redis já tem dados; a carga parte de volumes vazios (base.py carregar).")

    links = base.links()
    inicio = time.monotonic()
    pipe = mestre.pipeline(transaction=False)
    for cliente in base.clientes():
        pipe.hset(f"cliente:{cliente.cliente_id}", mapping={"nome": cliente.nome})
    pipe.execute()

    def gravar(fatia):
        p = mestre.pipeline(transaction=False)
        for link in fatia:
            p.hset(
                f"link:{link.short_code}",
                mapping={
                    "url": link.url,
                    "cliente_id": link.cliente_id,
                    "canal": link.canal,
                    "criado_em": iso(link.criado_em_ms),
                },
            )
            p.sadd(f"links:cliente:{link.cliente_id}", link.short_code)
            p.set(f"contador:{link.short_code}", link.cliques)
        p.execute()
        return len(fatia)

    # Concorrência limitada: 4 conexões, 500 links (1.500 comandos) por pipeline.
    fatias = [links[i : i + 500] for i in range(0, len(links), 500)]
    with ThreadPoolExecutor(max_workers=4) as executor:
        total = sum(executor.map(gravar, fatias))
    print(f"  Redis: {len(base.clientes())} clientes e {total:,} links em {time.monotonic() - inicio:.1f} s")


# --- Cassandra ---------------------------------------------------------------

_sessao = None
_insercao = None


def _iniciar_cassandra() -> None:
    global _sessao, _insercao
    cluster = Cluster(["cassandra"], protocol_version=5)
    _sessao = cluster.connect("linkpulse")
    _sessao.default_timeout = 60
    _insercao = _sessao.prepare(
        "INSERT INTO cliques_por_link "
        "(short_code, clicado_em, clique_id, pais, dispositivo, referrer) "
        "VALUES (?, ?, ?, ?, ?, ?)"
    )
    _insercao.is_idempotent = True  # a mesma linha, com a mesma chave, pode ser reenviada


def _lotes(base: Base, blocos: list[Bloco]):
    for bloco in blocos:
        lote, linhas = None, 0
        for clique in base.cliques(bloco):
            if lote is None:
                lote = BatchStatement(BatchType.UNLOGGED, consistency_level=ConsistencyLevel.ONE)
            lote.add(_insercao, clique)
            linhas += 1
            if linhas == LINHAS_POR_LOTE_CASSANDRA:
                yield lote, linhas
                lote, linhas = None, 0
        if lote is not None:
            yield lote, linhas


def _tarefa_cassandra(argumentos: tuple[Base, list[Bloco]]) -> int:
    base, blocos = argumentos
    vagas = threading.BoundedSemaphore(LOTES_EM_ANDAMENTO)
    erros: list[BaseException] = []

    def enviar(lote, tentativa):
        futuro = _sessao.execute_async(lote)
        futuro.add_callbacks(lambda _: vagas.release(), falhou, errback_args=(lote, tentativa))

    def falhou(erro, lote, tentativa):
        if tentativa < TENTATIVAS:
            # Reenvia fora da thread do driver, que não pode ser bloqueada.
            threading.Timer(0.2 * tentativa, enviar, args=(lote, tentativa + 1)).start()
        else:
            erros.append(erro)
            vagas.release()

    linhas = 0
    for lote, n in _lotes(base, blocos):
        if erros:
            break
        vagas.acquire()
        enviar(lote, 1)
        linhas += n
    for _ in range(LOTES_EM_ANDAMENTO):
        vagas.acquire()
    if erros:
        raise RuntimeError(f"lote recusado {TENTATIVAS} vezes pelo Cassandra: {erros[0]!r}")
    return linhas


def carregar_cassandra(base: Base, processos: int) -> float:
    cluster = Cluster(["cassandra"], protocol_version=5)
    sessao = cluster.connect("linkpulse")
    if sessao.execute("SELECT short_code FROM cliques_por_link LIMIT 1").one() is not None:
        sys.exit("Cassandra já tem dados; a carga parte de volumes vazios (base.py carregar).")
    cluster.shutdown()

    progresso = Progresso("Cassandra", sum(b.quantidade for g in tarefas(base) for b in g))
    with get_context("spawn").Pool(processos, initializer=_iniciar_cassandra) as pool:
        for linhas in pool.imap_unordered(_tarefa_cassandra, [(base, g) for g in tarefas(base)]):
            progresso.somar(linhas)
    return progresso.segundos()


def esperar_compactacoes(limite_s: int = 1800, quieto_s: int = 30) -> float:
    """Espera as compactações acabarem, para não rodarem durante as medições.

    Usa as tabelas virtuais por CQL: o nodetool abriria outra JVM dentro do
    teto de memória do contêiner do Cassandra.
    """
    cluster = Cluster(["cassandra"], protocol_version=5)
    sessao = cluster.connect()
    inicio = time.monotonic()
    quieto_desde = None
    while time.monotonic() - inicio < limite_s:
        pool = sessao.execute(
            "SELECT active_tasks, pending_tasks FROM system_views.thread_pools "
            "WHERE name = 'CompactionExecutor'"
        ).one()
        tarefas_sstable = list(sessao.execute("SELECT kind FROM system_views.sstable_tasks"))
        ocupado = pool.active_tasks or pool.pending_tasks or tarefas_sstable
        if ocupado:
            quieto_desde = None
        elif quieto_desde is None:
            quieto_desde = time.monotonic()
        elif time.monotonic() - quieto_desde >= quieto_s:
            break
        time.sleep(2)
    else:
        print(f"  aviso: compactações ainda ativas depois de {limite_s} s")
    cluster.shutdown()
    decorrido = time.monotonic() - inicio
    print(f"  Cassandra: compactações paradas há {quieto_s} s ({decorrido:.0f} s de espera)")
    return decorrido


# --- PostgreSQL --------------------------------------------------------------


def _tarefa_postgres(argumentos: tuple[Base, list[Bloco]]) -> int:
    base, blocos = argumentos
    linhas = 0
    with conectar_postgres() as conexao, conexao.cursor() as cursor:
        with cursor.copy(
            "COPY cliques (short_code, clicado_em, clique_id, pais, dispositivo, referrer) FROM STDIN"
        ) as copia:
            for bloco in blocos:
                for c in base.cliques(bloco):
                    copia.write_row(
                        (c.short_code, ms_para_datetime(c.clicado_em_ms), c.clique_id, c.pais, c.dispositivo, c.referrer)
                    )
                    linhas += 1
    return linhas


def carregar_postgres(base: Base, processos: int) -> float:
    with conectar_postgres() as conexao, conexao.cursor() as cursor:
        ocupado = cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM links) OR EXISTS (SELECT 1 FROM contadores) "
            "OR EXISTS (SELECT 1 FROM cliques)"
        ).fetchone()[0]
        if ocupado:
            sys.exit("PostgreSQL já tem dados; a carga parte de volumes vazios (base.py carregar).")
        links = base.links()
        with cursor.copy("COPY links (short_code, url, cliente_id, canal, criado_em, expira_em) FROM STDIN") as copia:
            for link in links:
                copia.write_row(
                    (link.short_code, link.url, link.cliente_id, link.canal, ms_para_datetime(link.criado_em_ms), None)
                )
        with cursor.copy("COPY contadores (short_code, total) FROM STDIN") as copia:
            for link in links:
                copia.write_row((link.short_code, link.cliques))
    print(f"  PostgreSQL: {len(links):,} links e contadores")

    grupos = tarefas(base)
    progresso = Progresso("PostgreSQL", sum(b.quantidade for g in grupos for b in g))
    with get_context("spawn").Pool(processos) as pool:
        for linhas in pool.imap_unordered(_tarefa_postgres, [(base, g) for g in grupos]):
            progresso.somar(linhas)
    segundos = progresso.segundos()

    inicio = time.monotonic()
    with psycopg.connect(
        host="postgres",
        user="linkpulse",
        password=os.environ.get("POSTGRES_PASSWORD", "linkpulse"),
        dbname="linkpulse",
        autocommit=True,
    ) as conexao:
        conexao.execute("VACUUM (ANALYZE) links, contadores, cliques")
        conexao.execute("CHECKPOINT")
    print(f"  PostgreSQL: VACUUM (ANALYZE) e CHECKPOINT em {time.monotonic() - inicio:.0f} s")
    return segundos


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lado", choices=("ambos", "nosql", "postgres"), default="ambos")
    parser.add_argument("--processos", type=int, default=4)
    args = parser.parse_args()

    base = ler_base()
    print(f"Base: semente {base.semente}, cliques de {iso(base.inicio_ms)} a {iso(base.fim_ms)}")
    tempos: dict[str, float] = {}
    if args.lado in ("ambos", "nosql"):
        print("Lado NoSQL")
        inicio = time.monotonic()
        carregar_redis(base)
        tempos["cassandra_insercao_s"] = round(carregar_cassandra(base, args.processos), 1)
        tempos["cassandra_compactacao_s"] = round(esperar_compactacoes(), 1)
        tempos["nosql_total_s"] = round(time.monotonic() - inicio, 1)
    if args.lado in ("ambos", "postgres"):
        print("Lado PostgreSQL")
        inicio = time.monotonic()
        tempos["postgres_copy_s"] = round(carregar_postgres(base, args.processos), 1)
        tempos["postgres_total_s"] = round(time.monotonic() - inicio, 1)
    print("TEMPOS " + json.dumps(tempos))
    return 0


if __name__ == "__main__":
    sys.exit(main())
