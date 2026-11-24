"""Confere a configuração dos bancos e os esquemas do ambiente local."""

import os
import sys
import time
import uuid

import psycopg
import redis
from cassandra.cluster import Cluster
from pymongo import MongoClient

falhas: list[str] = []


def conferir(condicao: bool, descricao: str) -> None:
    print(f"  [{'ok' if condicao else 'FALHA'}] {descricao}")
    if not condicao:
        falhas.append(descricao)


def conferir_redis() -> None:
    print("Redis")
    master = redis.Redis(host="redis-master", decode_responses=True)
    replica = redis.Redis(host="redis-replica", decode_responses=True)

    info_master = master.info()
    print(f"  versão {info_master['redis_version']}")
    conferir(info_master["role"] == "master", "redis-master tem o papel master")
    conferir(info_master["connected_slaves"] >= 1, "master com ao menos 1 réplica conectada")
    conferir(info_master["aof_enabled"] == 0, "AOF desligado no master")
    conferir(master.config_get("save")["save"] != "", "fotografias RDB ligadas no master")

    info_replica = replica.info("replication")
    conferir(info_replica["role"] == "slave", "redis-replica tem o papel de réplica")
    conferir(info_replica["master_link_status"] == "up", "réplica ligada ao master")

    chave = f"verificacao:{uuid.uuid4()}"
    master.set(chave, "1", ex=60)
    replicado = False
    for _ in range(20):
        if replica.get(chave) == "1":
            replicado = True
            break
        time.sleep(0.1)
    master.delete(chave)
    conferir(replicado, "escrita no master aparece na réplica")


def conferir_cassandra() -> None:
    print("Cassandra")
    cluster = Cluster(["cassandra"])
    sessao = cluster.connect()
    versao = sessao.execute("SELECT release_version FROM system.local").one()
    print(f"  versão {versao.release_version}")

    keyspace = sessao.execute(
        "SELECT replication FROM system_schema.keyspaces WHERE keyspace_name = 'linkpulse'"
    ).one()
    conferir(keyspace is not None, "keyspace linkpulse existe")
    if keyspace is not None:
        conferir(
            keyspace.replication.get("replication_factor") == "1",
            "fator de replicação 1 declarado no keyspace",
        )

    colunas = {
        linha.column_name: linha
        for linha in sessao.execute(
            "SELECT column_name, kind, position, clustering_order, type "
            "FROM system_schema.columns "
            "WHERE keyspace_name = 'linkpulse' AND table_name = 'cliques_por_link'"
        )
    }
    conferir(bool(colunas), "tabela cliques_por_link existe")
    if colunas:
        particao = [n for n, c in colunas.items() if c.kind == "partition_key"]
        clustering = sorted(
            (c.position, n, c.clustering_order)
            for n, c in colunas.items()
            if c.kind == "clustering"
        )
        conferir(particao == ["short_code"], "partition key é short_code")
        conferir(
            clustering == [(0, "clicado_em", "desc"), (1, "clique_id", "desc")],
            "clustering (clicado_em DESC, clique_id DESC)",
        )
        conferir(colunas["clique_id"].type == "timeuuid", "clique_id é timeuuid")
        conferir(
            {"pais", "dispositivo", "referrer"} <= colunas.keys(),
            "colunas pais, dispositivo e referrer existem",
        )
    cluster.shutdown()


def conferir_postgres() -> None:
    print("PostgreSQL")
    senha = os.environ.get("POSTGRES_PASSWORD", "linkpulse")
    with psycopg.connect(
        host="postgres", user="linkpulse", password=senha, dbname="linkpulse"
    ) as conexao:
        cursor = conexao.cursor()
        print(f"  versão {cursor.execute('SHOW server_version').fetchone()[0]}")

        tabelas = {
            linha[0]
            for linha in cursor.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            )
        }
        conferir(tabelas == {"links", "contadores", "cliques"}, "tabelas links, contadores e cliques")

        chaves_estrangeiras = cursor.execute(
            "SELECT count(*) FROM information_schema.table_constraints "
            "WHERE table_schema = 'public' AND constraint_type = 'FOREIGN KEY'"
        ).fetchone()[0]
        conferir(chaves_estrangeiras == 0, "nenhuma chave estrangeira")

        indices = cursor.execute(
            "SELECT count(*) FROM pg_indexes WHERE schemaname = 'public'"
        ).fetchone()[0]
        conferir(indices == 3, "só os índices das chaves primárias")

        chave_cliques = [
            linha[0]
            for linha in cursor.execute(
                "SELECT a.attname FROM pg_index i "
                "JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS k(attnum, ordem) ON true "
                "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum "
                "WHERE i.indrelid = 'cliques'::regclass AND i.indisprimary ORDER BY k.ordem"
            )
        ]
        conferir(
            chave_cliques == ["short_code", "clicado_em", "clique_id"],
            "chave primária de cliques é (short_code, clicado_em, clique_id)",
        )

        synchronous_commit = cursor.execute("SHOW synchronous_commit").fetchone()[0]
        conferir(synchronous_commit == "on", "synchronous_commit no padrão (on)")


def conferir_mongo() -> None:
    print("MongoDB")
    cliente = MongoClient("mongo", 27017, serverSelectionTimeoutMS=5000)
    conferir(cliente.admin.command("ping")["ok"] == 1.0, "responde ao ping")
    print(f"  versão {cliente.server_info()['version']}")
    cliente.close()


def main() -> int:
    print(f"Python {sys.version.split()[0]}")
    for conferencia in (conferir_redis, conferir_cassandra, conferir_postgres, conferir_mongo):
        try:
            conferencia()
        except Exception as erro:  # noqa: BLE001 - relata e segue para o próximo banco
            conferir(False, f"{conferencia.__name__}: {erro!r}")
    if falhas:
        print(f"\n{len(falhas)} conferência(s) falharam.")
        return 1
    print("\nAmbiente conferido.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
