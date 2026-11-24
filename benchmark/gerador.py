"""Gerador de carga em laço fechado do benchmark (SPEC-005, passo 2).

Mede uma operação em um lado: um número fixo de conexões, e cada uma só envia
a próxima operação quando a anterior responde (ADR-0014). As conexões se
dividem entre processos, com uma thread por conexão. Os comandos são
preparados no Cassandra e no PostgreSQL; o Redis não tem comando preparado.

Não é chamado à mão: `python benchmark/medir.py` roda este script no contêiner
`gerador`. O resultado sai numa linha `RESULTADO {json}`.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import threading
import time
from array import array
from datetime import UTC, datetime
from multiprocessing import get_context
from pathlib import Path

import psycopg
import redis
from cassandra.cluster import Cluster
from cassandra.util import uuid_from_time

from carregar import MANIFESTO
from referencia import DISPOSITIVOS, REFERRERS, Base, manifesto_valido

OPERACOES = ("redirecionamento", "contador", "registro", "historico")
LADOS = ("nosql", "postgres")
SORTEIO_POPULAR = 0.20  # parcela das chamadas que cai no link popular (ADR-0014)
LIMITE_HISTORICO = 1000
COLUNAS_CLIQUE = "short_code, clicado_em, clique_id, pais, dispositivo, referrer"
CGROUP = Path("/sys/fs/cgroup")

SQL = {
    "redirecionamento": "SELECT url, cliente_id, canal, criado_em, expira_em FROM links WHERE short_code = %s",
    "contador": "UPDATE contadores SET total = total + 1 WHERE short_code = %s",
    "registro": f"INSERT INTO cliques ({COLUNAS_CLIQUE}) VALUES (%s, %s, %s, %s, %s, %s)",
    "historico": (
        f"SELECT {COLUNAS_CLIQUE} FROM cliques WHERE short_code = %s AND clicado_em >= %s AND clicado_em < %s "
        f"ORDER BY clicado_em DESC, clique_id DESC LIMIT {LIMITE_HISTORICO}"
    ),
}
CQL = {
    "registro": f"INSERT INTO cliques_por_link ({COLUNAS_CLIQUE}) VALUES (?, ?, ?, ?, ?, ?)",
    # A ordem decrescente já é a da tabela (CLUSTERING ORDER).
    "historico": (
        f"SELECT {COLUNAS_CLIQUE} FROM cliques_por_link WHERE short_code = ? AND clicado_em >= ? "
        f"AND clicado_em < ? LIMIT {LIMITE_HISTORICO}"
    ),
}


def novo_clique(codigo: str, rng) -> tuple:
    agora = datetime.now(UTC)
    dispositivo = rng.choices([d for d, _ in DISPOSITIVOS], [p for _, p in DISPOSITIVOS])[0]
    referrer = rng.choices([r for r, _ in REFERRERS], [p for _, p in REFERRERS])[0]
    return (codigo, agora, uuid_from_time(agora), None, dispositivo, referrer)


def preparar(operacao: str, lado: str, janela: tuple[datetime, datetime]):
    """Devolve `conectar()`, que abre uma conexão e devolve `executar(codigo, rng) -> bool`.

    `executar` devolve False quando o banco responde sem o dado esperado (link
    ou contador ausente); isso conta como erro.
    """
    if lado == "nosql" and operacao in ("redirecionamento", "contador"):
        def conectar():
            conexao = redis.Redis(host="redis-master", single_connection_client=True)
            conexao.ping()
            if operacao == "redirecionamento":
                return lambda codigo, rng: bool(conexao.hgetall(f"link:{codigo}"))
            return lambda codigo, rng: conexao.incr(f"contador:{codigo}") > 1
        return conectar

    if lado == "nosql":
        # Uma sessão por processo, compartilhada pelas threads: o driver
        # multiplexa as operações nas conexões dele.
        sessao = Cluster(["cassandra"], protocol_version=5).connect("linkpulse")
        comando = sessao.prepare(CQL[operacao])
        if operacao == "registro":
            def executar(codigo, rng):
                sessao.execute(comando, novo_clique(codigo, rng))
                return True
        else:
            def executar(codigo, rng):
                list(sessao.execute(comando, (codigo, *janela)))
                return True
        return lambda: executar

    def conectar():
        conexao = psycopg.connect(
            host="postgres", user="linkpulse", dbname="linkpulse", autocommit=True,
            password=os.environ.get("POSTGRES_PASSWORD", "linkpulse"),
        )
        cursor = conexao.cursor()
        sql = SQL[operacao]
        if operacao == "redirecionamento":
            return lambda codigo, rng: cursor.execute(sql, (codigo,), prepare=True).fetchone() is not None
        if operacao == "contador":
            return lambda codigo, rng: cursor.execute(sql, (codigo,), prepare=True).rowcount == 1
        if operacao == "registro":
            return lambda codigo, rng: cursor.execute(sql, novo_clique(codigo, rng), prepare=True) is not None
        return lambda codigo, rng: cursor.execute(sql, (codigo, *janela), prepare=True).fetchall() is not None
    return conectar


def processo(numero: int, conexoes: int, args: argparse.Namespace, popular: str, outros: list[str],
             janela, prontos, partida, marcos, saida) -> None:
    conectar = preparar(args.operacao, args.lado, janela)
    operacoes = [conectar() for _ in range(conexoes)]
    resultados = [None] * conexoes

    def conexao(indice: int) -> None:
        executar = operacoes[indice]
        rng = random.Random(f"{args.operacao}:{args.lado}:{numero}:{indice}")
        inicio_medida, fim = marcos[0], marcos[1]
        latencias = array("d")
        erros, exemplos = 0, []
        while True:
            codigo = popular if rng.random() < SORTEIO_POPULAR else rng.choice(outros)
            t0 = time.perf_counter()
            if t0 >= fim:
                break
            try:
                ok = executar(codigo, rng)
            except Exception as erro:  # noqa: BLE001 - toda falha conta como erro da operação
                ok = False
                if len(exemplos) < 3:
                    exemplos.append(f"{type(erro).__name__}: {erro}"[:200])
            duracao = time.perf_counter() - t0
            if t0 < inicio_medida:
                continue  # aquecimento descartado
            if ok:
                latencias.append(duracao)
            else:
                erros += 1
        resultados[indice] = (latencias, erros, exemplos)

    prontos.wait()
    partida.wait()
    threads = [threading.Thread(target=conexao, args=(i,)) for i in range(conexoes)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    latencias = array("d")
    for parte, _, _ in resultados:
        latencias.extend(parte)
    saida.put((latencias, sum(r[1] for r in resultados), [e for r in resultados for e in r[2]][:3]))


def cpus_do_limite() -> float:
    try:
        cota, periodo = (CGROUP / "cpu.max").read_text().split()
        if cota != "max":
            return int(cota) / int(periodo)
    except OSError:
        pass
    return float(os.cpu_count() or 1)


def cpu_usada_s() -> float:
    for linha in (CGROUP / "cpu.stat").read_text().splitlines():
        nome, valor = linha.split()
        if nome == "usage_usec":
            return int(valor) / 1e6
    raise RuntimeError("cpu.stat sem usage_usec")


def percentil(ordenadas: list[float], p: float) -> float | None:
    if not ordenadas:
        return None
    return ordenadas[max(0, math.ceil(p / 100 * len(ordenadas)) - 1)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--operacao", choices=OPERACOES, required=True)
    parser.add_argument("--lado", choices=LADOS, required=True)
    parser.add_argument("--conexoes", type=int, default=8)
    parser.add_argument("--duracao", type=float, default=60)
    parser.add_argument("--aquecimento", type=float, default=10)
    parser.add_argument("--processos", type=int, help="padrão: as CPUs do limite do contêiner")
    args = parser.parse_args()

    manifesto = json.loads(MANIFESTO.read_text(encoding="utf-8"))
    if not manifesto_valido(manifesto):
        print(f"Manifesto inválido em {MANIFESTO}; nada foi medido.")
        return 1
    popular = manifesto["link_popular"]["short_code"]
    outros = [l.short_code for l in Base(semente=manifesto["semente"], fim=manifesto["fim"]).links()
              if l.short_code != popular]
    janela = tuple(datetime.fromisoformat(manifesto["janela_historico"][k]) for k in ("inicio", "fim"))

    limite_cpu = cpus_do_limite()
    processos = max(1, min(args.conexoes, args.processos or math.floor(limite_cpu)))
    divisao = [args.conexoes // processos + (1 if i < args.conexoes % processos else 0) for i in range(processos)]

    ctx = get_context("spawn")
    prontos, partida = ctx.Barrier(processos + 1), ctx.Event()
    # perf_counter usa o relógio monotônico do sistema, o mesmo em todos os processos.
    marcos, saida = ctx.Array("d", 2), ctx.Queue()
    filhos = [ctx.Process(target=processo, args=(i, n, args, popular, outros, janela, prontos, partida, marcos, saida))
              for i, n in enumerate(divisao)]
    for filho in filhos:
        filho.start()
    prontos.wait()  # todas as conexões abertas e os comandos preparados
    agora = time.perf_counter()
    marcos[0], marcos[1] = agora + args.aquecimento, agora + args.aquecimento + args.duracao
    inicio = datetime.now(UTC)
    partida.set()
    print(f"{args.operacao} / {args.lado}: {args.conexoes} conexões em {processos} processos, "
          f"{args.aquecimento:.0f} s de aquecimento e {args.duracao:.0f} s medidos", flush=True)

    time.sleep(max(0.0, marcos[0] - time.perf_counter()))
    cpu_antes, relogio_antes = cpu_usada_s(), time.perf_counter()
    time.sleep(max(0.0, marcos[1] - time.perf_counter()))
    cpu_depois, relogio_depois = cpu_usada_s(), time.perf_counter()

    latencias, erros, exemplos = array("d"), 0, []
    for _ in filhos:
        parte, erros_parte, exemplos_parte = saida.get()
        latencias.extend(parte)
        erros += erros_parte
        exemplos += exemplos_parte
    for filho in filhos:
        filho.join()

    ordenadas = sorted(latencias)
    total = len(ordenadas) + erros
    ms = lambda s: None if s is None else round(s * 1000, 3)  # noqa: E731
    resultado = {
        "operacao": args.operacao,
        "lado": args.lado,
        "inicio": inicio.isoformat(timespec="seconds"),
        "conexoes": args.conexoes,
        "processos": processos,
        "aquecimento_s": args.aquecimento,
        "duracao_s": args.duracao,
        "operacoes": len(ordenadas),
        "erros": erros,
        "vazao_ops": round(len(ordenadas) / args.duracao, 1),
        "p50_ms": ms(percentil(ordenadas, 50)),
        "p95_ms": ms(percentil(ordenadas, 95)),
        "p99_ms": ms(percentil(ordenadas, 99)),
        "taxa_erro": round(erros / total, 6) if total else None,
        "cpu_gerador_pct": round(100 * (cpu_depois - cpu_antes) / ((relogio_depois - relogio_antes) * limite_cpu), 1),
        "limite_cpu_gerador": limite_cpu,
        "exemplos_de_erro": exemplos[:3],
    }
    print("RESULTADO " + json.dumps(resultado, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
