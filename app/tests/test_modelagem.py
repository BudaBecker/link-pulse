import re
from pathlib import Path

from app.main import abrir_redis

PASTA_APP = Path(__file__).parents[1]
COMANDO_CQL = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE)\b[^\"]*\bcliques_por_link\b[^\"]*", re.IGNORECASE)


def comandos_cql_da_aplicacao() -> list[str]:
    comandos = []
    for arquivo in PASTA_APP.glob("*.py"):
        # Junta as partes de uma string quebrada em várias linhas.
        texto = re.sub(r'"\s*\n\s*"', "", arquivo.read_text(encoding="utf-8"))
        comandos += [m.group(0) for m in COMANDO_CQL.finditer(texto)]
    return comandos


def test_tabela_tem_short_code_como_partition_key_e_ordem_decrescente(sessao_cassandra):
    colunas = {
        c.column_name: (c.kind, c.position, c.clustering_order)
        for c in sessao_cassandra.execute(
            "SELECT column_name, kind, position, clustering_order FROM system_schema.columns "
            "WHERE keyspace_name = 'linkpulse' AND table_name = 'cliques_por_link'"
        )
    }

    assert [nome for nome, (tipo, _, _) in colunas.items() if tipo == "partition_key"] == ["short_code"]
    assert colunas["clicado_em"] == ("clustering", 0, "desc")
    assert colunas["clique_id"] == ("clustering", 1, "desc")


def test_keyspace_declara_fator_de_replicacao(sessao_cassandra):
    replicacao = sessao_cassandra.execute(
        "SELECT replication FROM system_schema.keyspaces WHERE keyspace_name = 'linkpulse'"
    ).one().replication

    assert int(replicacao["replication_factor"]) >= 1


def test_consultas_cql_informam_short_code_e_nao_usam_allow_filtering():
    comandos = comandos_cql_da_aplicacao()

    assert any(c.upper().startswith("SELECT") for c in comandos)
    for comando in comandos:
        assert "ALLOW FILTERING" not in comando.upper(), comando
        if not comando.upper().startswith("INSERT"):
            assert re.search(r"\bWHERE short_code = \?", comando), comando


def test_redis_tem_um_master_e_uma_replica():
    master = abrir_redis("REDIS_MASTER_HOST", "REDIS_MASTER_PORT", "6379")
    replica = abrir_redis("REDIS_REPLICA_HOST", "REDIS_REPLICA_PORT", "6380")
    try:
        assert master.info("replication")["role"] == "master"
        assert master.info("replication")["connected_slaves"] >= 1
        assert replica.info("replication")["role"] == "slave"
    finally:
        master.close()
        replica.close()
