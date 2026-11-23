"""Confere a base de referência nos dois lados (CA-1 da SPEC-005).

Roda no contêiner `carga`: python benchmark/base.py conferir [--completo]

Sempre, consultando os próprios bancos:
- links: chaves `link:*` no Redis e linhas de `links` no PostgreSQL;
- cliques: COUNT(*) de cada partição de `cliques_por_link`, com a lista de
  partições lida do próprio Cassandra, e COUNT(*) por short_code em `cliques`,
  comparados link a link; nenhum clique pode ser de um link inexistente;
- link popular: total e percentual dos cliques nos dois lados;
- contadores: `contador:*` no Redis e `contadores` no PostgreSQL iguais aos
  cliques de cada link;
- clientes do benchmark fora do Set `clientes`.

Com --completo, também lê todos os cliques dos dois lados: distribuição de
dispositivos e assinatura dos cliques, comparada com a do manifesto.

Sai com código 1 se alguma conferência falhar.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter

import psycopg
import redis
from cassandra.cluster import Cluster
from cassandra.concurrent import execute_concurrent_with_args
from cassandra.query import SimpleStatement

from referencia import Assinatura, Base, Clique, datetime_para_ms
from carregar import MANIFESTO

falhas: list[str] = []
# Acima disso, a partição é contada em fatias de um dia (ver lado_nosql).
LIMITE_PARTICAO_INTEIRA = 100_000


def conferir(condicao: bool, descricao: str) -> None:
    print(f"  [{'ok' if condicao else 'FALHA'}] {descricao}")
    if not condicao:
        falhas.append(descricao)


def postgres() -> psycopg.Connection:
    return psycopg.connect(
        host="postgres",
        user="linkpulse",
        password=os.environ.get("POSTGRES_PASSWORD", "linkpulse"),
        dbname="linkpulse",
    )


def lado_nosql(sessao, base: Base, esperado_por_link: dict[str, int]) -> dict:
    mestre = redis.Redis(host="redis-master", decode_responses=True)
    links = [chave.removeprefix("link:") for chave in mestre.scan_iter("link:*", count=5000)]
    # Todos os contadores, não só os dos links: um contador a mais também conta.
    chaves = list(mestre.scan_iter("contador:*", count=5000))
    contadores = {}
    for i in range(0, len(chaves), 5000):
        fatia = chaves[i : i + 5000]
        for chave, valor in zip(fatia, mestre.mget(fatia)):
            contadores[chave.removeprefix("contador:")] = int(valor)
    clientes_bench = sum(1 for _ in mestre.scan_iter("cliente:bench-*", count=5000))
    no_set = [c for c in mestre.smembers("clientes") if c.startswith("bench-")]

    # As partições vêm do próprio Cassandra, para um clique fora dos links do
    # Redis também entrar no total.
    particoes = {
        linha.short_code
        for linha in sessao.execute(
            SimpleStatement("SELECT DISTINCT short_code FROM cliques_por_link", fetch_size=5000)
        )
    }
    codigos = sorted(particoes | set(links))

    # O COUNT(*) de uma partição com milhões de linhas passa do tempo limite de
    # leitura do servidor (5 s no padrão). Partições grandes, e as que estourarem
    # o tempo, são contadas em fatias de um dia, mais uma fatia aberta antes do
    # início e outra depois do fim, para não deixar nenhum clique de fora.
    grandes = {c for c in codigos if esperado_por_link.get(c, 0) > LIMITE_PARTICAO_INTEIRA}
    consulta = sessao.prepare("SELECT COUNT(*) FROM cliques_por_link WHERE short_code = ?")
    pequenos = [c for c in codigos if c not in grandes]
    resultados = execute_concurrent_with_args(
        sessao, consulta, [(c,) for c in pequenos], concurrency=16, raise_on_first_error=False
    )
    cliques = {}
    for codigo, resultado in zip(pequenos, resultados):
        if resultado.success:
            cliques[codigo] = resultado.result_or_exc.one()[0]
        else:
            grandes.add(codigo)
    fatia = sessao.prepare(
        "SELECT COUNT(*) FROM cliques_por_link WHERE short_code = ? AND clicado_em >= ? AND clicado_em < ?"
    )
    for codigo in grandes:
        cortes = [-(2**62), *range(base.inicio_ms, base.fim_ms + 1, 86_400_000), 2**62]
        argumentos = [(codigo, de, ate) for de, ate in zip(cortes, cortes[1:])]
        partes = execute_concurrent_with_args(sessao, fatia, argumentos, concurrency=4, raise_on_first_error=True)
        cliques[codigo] = sum(r.result_or_exc.one()[0] for r in partes)
    return {
        "links": len(links),
        "cliques_por_link": cliques,
        "contadores": contadores,
        "sem_link": sorted(particoes - set(links)),
        "clientes_bench": clientes_bench,
        "clientes_bench_no_set": no_set,
    }


def lado_postgres(conexao) -> dict:
    cursor = conexao.cursor()
    links = cursor.execute("SELECT count(*) FROM links").fetchone()[0]
    cliques = dict(cursor.execute("SELECT short_code, count(*) FROM cliques GROUP BY short_code"))
    contadores = dict(cursor.execute("SELECT short_code, total FROM contadores"))
    sem_link = [
        linha[0]
        for linha in cursor.execute(
            "SELECT DISTINCT c.short_code FROM cliques c "
            "LEFT JOIN links l USING (short_code) WHERE l.short_code IS NULL"
        )
    ]
    return {"links": links, "cliques_por_link": cliques, "contadores": contadores, "sem_link": sem_link}


def ler_tudo_nosql(sessao) -> tuple[Counter, Assinatura]:
    dispositivos: Counter = Counter()
    assinatura = Assinatura()
    consulta = SimpleStatement(
        "SELECT short_code, clicado_em, clique_id, pais, dispositivo, referrer FROM cliques_por_link",
        fetch_size=5000,
    )
    for linha in sessao.execute(consulta, timeout=120):
        dispositivos[linha.dispositivo] += 1
        assinatura.somar(
            Clique(linha.short_code, datetime_para_ms(linha.clicado_em), linha.clique_id,
                   linha.pais, linha.dispositivo, linha.referrer)
        )
    return dispositivos, assinatura


def ler_tudo_postgres(conexao) -> tuple[Counter, Assinatura]:
    dispositivos: Counter = Counter()
    assinatura = Assinatura()
    with conexao.cursor(name="todos_os_cliques") as cursor:
        cursor.itersize = 20_000
        cursor.execute(
            "SELECT short_code, clicado_em, clique_id, pais, dispositivo, referrer FROM cliques"
        )
        for short_code, clicado_em, clique_id, pais, dispositivo, referrer in cursor:
            dispositivos[dispositivo] += 1
            assinatura.somar(
                Clique(short_code, datetime_para_ms(clicado_em), clique_id, pais, dispositivo, referrer)
            )
    return dispositivos, assinatura


def relatar(nome: str, lado: dict, esperado: dict) -> dict:
    popular = esperado["link_popular"]["short_code"]
    total = sum(lado["cliques_por_link"].values())
    do_popular = lado["cliques_por_link"].get(popular, 0)
    percentual = 100 * do_popular / total if total else 0.0
    print(f"{nome}")
    print(f"  links {lado['links']:,} · cliques {total:,} · link popular {popular} "
          f"com {do_popular:,} ({percentual:.4f}%)")
    conferir(lado["links"] == esperado["links"], f"{esperado['links']:,} links")
    conferir(total == esperado["cliques"], f"{esperado['cliques']:,} cliques")
    conferir(do_popular == esperado["link_popular"]["cliques"], "link popular com 20% dos cliques")
    conferir(not lado["sem_link"], "nenhum clique de link inexistente")
    conferir(lado["contadores"] == lado["cliques_por_link"], "contador de cada link igual aos seus cliques")
    return {"links": lado["links"], "cliques": total, "popular": do_popular, "percentual_popular": round(percentual, 4)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--completo", action="store_true", help="lê todos os cliques dos dois lados")
    args = parser.parse_args()

    esperado = json.loads(MANIFESTO.read_text(encoding="utf-8"))
    base = Base(semente=esperado["semente"], fim=esperado["fim"])
    esperado_por_link = {l.short_code: l.cliques for l in base.links()}
    inicio = time.monotonic()

    cluster = Cluster(["cassandra"], protocol_version=5)
    sessao = cluster.connect("linkpulse")
    sessao.default_timeout = 120
    nosql = lado_nosql(sessao, base, esperado_por_link)
    with postgres() as conexao:
        sql = lado_postgres(conexao)

    resumo = {"NoSQL": relatar("Lado NoSQL (Redis + Cassandra)", nosql, esperado),
              "PostgreSQL": relatar("Lado PostgreSQL", sql, esperado)}
    print("Comparação")
    conferir(nosql["links"] == sql["links"], "mesmo número de links nos dois lados")
    conferir(nosql["cliques_por_link"] == sql["cliques_por_link"], "mesmos cliques em cada link nos dois lados")
    conferir(sql["cliques_por_link"] == esperado_por_link, "cliques de cada link iguais aos gerados pela semente")
    conferir(nosql["clientes_bench"] == esperado["clientes"], f"{esperado['clientes']} clientes do benchmark no Redis")
    conferir(not nosql["clientes_bench_no_set"], "clientes do benchmark fora do Set clientes")

    if args.completo:
        print("Leitura completa dos cliques")
        t = time.monotonic()
        disp_nosql, ass_nosql = ler_tudo_nosql(sessao)
        print(f"  Cassandra lido em {time.monotonic() - t:.0f} s")
        t = time.monotonic()
        with postgres() as conexao:
            disp_sql, ass_sql = ler_tudo_postgres(conexao)
        print(f"  PostgreSQL lido em {time.monotonic() - t:.0f} s")
        for nome, disp in (("NoSQL", disp_nosql), ("PostgreSQL", disp_sql)):
            total = sum(disp.values())
            partes = ", ".join(f"{d} {disp[d]:,} ({100 * disp[d] / total:.2f}%)" for d in esperado["dispositivos"])
            print(f"  {nome}: {partes}")
            resumo[nome]["dispositivos"] = dict(disp)
        conferir(dict(disp_nosql) == esperado["dispositivos"], "dispositivos 60/30/5/5 no lado NoSQL")
        conferir(dict(disp_sql) == esperado["dispositivos"], "dispositivos 60/30/5/5 no PostgreSQL")
        print(f"  assinatura NoSQL {ass_nosql.texto()} · PostgreSQL {ass_sql.texto()} · "
              f"manifesto {esperado.get('assinatura_cliques', '-')}")
        conferir(ass_nosql.texto() == ass_sql.texto(), "mesmos cliques (assinatura) nos dois lados")
        conferir(ass_sql.texto() == esperado.get("assinatura_cliques"), "assinatura igual à do manifesto")
        resumo["NoSQL"]["assinatura"], resumo["PostgreSQL"]["assinatura"] = ass_nosql.texto(), ass_sql.texto()

    cluster.shutdown()
    print(f"Conferência em {time.monotonic() - inicio:.0f} s")
    print("RESUMO " + json.dumps(resumo))
    if falhas:
        print(f"\n{len(falhas)} conferência(s) falharam.")
        return 1
    print("\nCA-1 conferido.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
