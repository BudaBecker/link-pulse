"""Gerador de carga em laço fechado do benchmark (SPEC-005, passo 2).

Mede uma operação, ou o pico de tráfego, em um lado: um número fixo de
conexões, e cada uma só envia a próxima operação quando a anterior responde
(ADR-0014). No pico, cada conexão repete leitura, contador e registro no link
popular (Q-39). As conexões se
dividem entre processos, por padrão um por conexão, com uma thread por
conexão. Os comandos são
preparados no Cassandra e no PostgreSQL; o Redis não tem comando preparado.
Com --curva-extra, o PostgreSQL roda com synchronous_commit=off na sessão (Q-73).

Não é chamado à mão: `python benchmark/medir.py` roda este script no contêiner
`gerador`. O resultado sai numa linha `RESULTADO {json}`; as linhas
`JANELA inicio` e `JANELA fim` marcam a janela medida, para o medir.py ler a
CPU do banco no mesmo intervalo. `PARTIDA` marca o início da carga, e cada
`PARCIAL {json}`, um segundo dela, para as curvas da tela de testes (Q-71).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import queue
import random
import sys
import threading
import time
from array import array
from collections import defaultdict
from datetime import UTC, datetime
from multiprocessing import get_context
from threading import BrokenBarrierError
from pathlib import Path

import psycopg
import redis
from cassandra.cluster import Cluster
from cassandra.util import uuid_from_time

from carregar import MANIFESTO
from referencia import DISPOSITIVOS, REFERRERS, Base, manifesto_valido

OPERACOES = ("redirecionamento", "contador", "registro", "historico")
PICO = "pico"
# Operações que cada conexão repete, em ordem, a cada volta do laço.
CICLO = {o: (o,) for o in OPERACOES} | {PICO: ("redirecionamento", "contador", "registro")}
LADOS = ("nosql", "postgres")
SORTEIO_POPULAR = 0.20  # parcela das chamadas que cai no link popular (ADR-0014)
LIMITE_HISTORICO = 1000
COLUNAS_CLIQUE = "short_code, clicado_em, clique_id, pais, dispositivo, referrer"
CGROUP = Path("/sys/fs/cgroup")
FOLGA_PARCIAL = 0.25  # s depois do fim de cada segundo para juntar as operações concluídas nele
_SAIDA = threading.Lock()

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


def emitir(linha: str) -> None:
    """Uma linha inteira por vez: as parciais saem de outra thread que não a da janela medida."""
    with _SAIDA:
        sys.stdout.write(linha + "\n")
        sys.stdout.flush()


def novo_clique(codigo: str, rng) -> tuple:
    agora = datetime.now(UTC)
    dispositivo = rng.choices([d for d, _ in DISPOSITIVOS], [p for _, p in DISPOSITIVOS])[0]
    referrer = rng.choices([r for r, _ in REFERRERS], [p for _, p in REFERRERS])[0]
    return (codigo, agora, uuid_from_time(agora), None, dispositivo, referrer)


def preparar(etapa: str, lado: str, janela: tuple[datetime, datetime], curva_extra: bool = False):
    """Devolve `conectar()`, que abre uma conexão e devolve {operação: executar(codigo, rng) -> bool}.

    `executar` devolve False quando o banco responde sem o dado esperado (link
    ou contador ausente); isso conta como erro. No pico, as operações de uma
    conexão compartilham a conexão de cada banco.
    """
    operacoes = CICLO[etapa]

    def conectar():
        if lado == "postgres":
            return conectar_postgres(operacoes, janela, curva_extra)
        executores = {}
        if {"redirecionamento", "contador"} & set(operacoes):
            conexao = redis.Redis(host="redis-master", single_connection_client=True)
            conexao.ping()
            executores["redirecionamento"] = lambda codigo, rng: bool(conexao.hgetall(f"link:{codigo}"))
            executores["contador"] = lambda codigo, rng: conexao.incr(f"contador:{codigo}") > 1
        if {"registro", "historico"} & set(operacoes):
            # Um Cluster por conexão: o driver abre uma conexão de dados com o nó,
            # e esta thread mantém nela uma operação pendente, como nos outros bancos.
            sessao = Cluster(["cassandra"], protocol_version=5, executor_threads=1,
                             schema_metadata_enabled=False, token_metadata_enabled=False).connect("linkpulse")
            if "registro" in operacoes:
                registro = sessao.prepare(CQL["registro"])
                executores["registro"] = lambda codigo, rng: sessao.execute(
                    registro, novo_clique(codigo, rng)) is not None
            if "historico" in operacoes:
                historico = sessao.prepare(CQL["historico"])
                executores["historico"] = lambda codigo, rng: list(
                    sessao.execute(historico, (codigo, *janela))) is not None
        return {o: executores[o] for o in operacoes}
    return conectar


def conectar_postgres(operacoes: tuple[str, ...], janela, curva_extra: bool = False) -> dict:
    conexao = psycopg.connect(
        host="postgres", user="linkpulse", dbname="linkpulse", autocommit=True,
        password=os.environ.get("POSTGRES_PASSWORD", "linkpulse"),
    )
    cursor = conexao.cursor()
    if curva_extra:
        # Só nesta sessão: a configuração do servidor continua a padrão (ADR-0014, Q-73).
        cursor.execute("SET synchronous_commit = off")
        if cursor.execute("SHOW synchronous_commit").fetchone()[0] != "off":
            raise RuntimeError("o PostgreSQL não aceitou synchronous_commit=off na sessão")
    executores = {
        "redirecionamento": lambda codigo, rng: cursor.execute(
            SQL["redirecionamento"], (codigo,), prepare=True).fetchone() is not None,
        "contador": lambda codigo, rng: cursor.execute(SQL["contador"], (codigo,), prepare=True).rowcount == 1,
        "registro": lambda codigo, rng: cursor.execute(
            SQL["registro"], novo_clique(codigo, rng), prepare=True) is not None,
        "historico": lambda codigo, rng: cursor.execute(
            SQL["historico"], (codigo, *janela), prepare=True).fetchall() is not None,
    }
    return {o: executores[o] for o in operacoes}


def processo(numero: int, conexoes: int, args: argparse.Namespace, popular: str, outros: list[str],
             janela, prontos, partida, marcos, saida, parciais) -> None:
    try:
        conectar = preparar(args.operacao, args.lado, janela, args.curva_extra)
        conexoes_abertas = [conectar() for _ in range(conexoes)]
    except BaseException:
        prontos.abort()  # o processo principal desiste em vez de esperar este
        raise
    resultados = [None] * conexoes
    # Por conexão: segundo desde a partida -> {operação: (latências, [erros])}, pela hora de conclusão.
    segundos = [defaultdict(dict) for _ in range(conexoes)]

    def conexao(indice: int) -> None:
        executores = conexoes_abertas[indice]
        rng = random.Random(f"{args.operacao}:{args.lado}:{numero}:{indice}")
        inicio_medida, fim, origem = marcos[0], marcos[1], marcos[2]
        medidas = {o: (array("d"), [0], []) for o in executores}  # latências, erros, exemplos
        por_segundo = segundos[indice]
        pico = args.operacao == PICO
        while True:
            # No pico, todas as chamadas vão ao link popular.
            codigo = popular if pico or rng.random() < SORTEIO_POPULAR else rng.choice(outros)
            for operacao, executar in executores.items():
                t0 = time.perf_counter()
                if t0 >= fim:
                    resultados[indice] = medidas
                    return
                try:
                    ok = executar(codigo, rng)
                except Exception as erro:  # noqa: BLE001 - toda falha conta como erro da operação
                    ok = False
                    exemplos = medidas[operacao][2]
                    if len(exemplos) < 3:
                        exemplos.append(f"{type(erro).__name__}: {erro}"[:200])
                t1 = time.perf_counter()
                duracao = t1 - t0
                parcial = por_segundo[int(t1 - origem)].setdefault(operacao, (array("d"), [0]))
                if ok:
                    parcial[0].append(duracao)
                else:
                    parcial[1][0] += 1
                if t0 < inicio_medida:
                    continue  # aquecimento descartado
                if ok:
                    medidas[operacao][0].append(duracao)
                else:
                    medidas[operacao][1][0] += 1

    def relatar() -> None:
        """A cada segundo, junta o que as conexões concluíram nele e manda ao processo principal."""
        origem, fim = marcos[2], marcos[1]
        for s in range(math.ceil(fim - origem)):
            time.sleep(max(0.0, origem + s + 1 + FOLGA_PARCIAL - time.perf_counter()))
            junto: dict = {}
            for por_segundo in segundos:
                for operacao, (latencias, erros) in por_segundo.pop(s, {}).items():
                    soma = junto.setdefault(operacao, (array("d"), [0]))
                    soma[0].extend(latencias)
                    soma[1][0] += erros[0]
            parciais.put((s, {o: (latencias, erros[0]) for o, (latencias, erros) in junto.items()}))

    try:
        prontos.wait()
    except BrokenBarrierError:
        return
    partida.wait()
    threads = [threading.Thread(target=conexao, args=(i,)) for i in range(conexoes)]
    threads.append(threading.Thread(target=relatar))
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    juntas = {}
    for operacao in CICLO[args.operacao]:
        latencias = array("d")
        for r in resultados:
            latencias.extend(r[operacao][0])
        juntas[operacao] = (latencias, sum(r[operacao][1][0] for r in resultados),
                            [e for r in resultados for e in r[operacao][2]][:3])
    saida.put(juntas)


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


def memoria_pico_mib() -> float | None:
    try:
        return round(int((CGROUP / "memory.peak").read_text()) / 2**20, 1)
    except OSError:
        return None


def percentil(ordenadas: list[float], p: float) -> float | None:
    if not ordenadas:
        return None
    return ordenadas[max(0, math.ceil(p / 100 * len(ordenadas)) - 1)]


def estatisticas(latencias, erros: int, exemplos: list[str], duracao: float) -> dict:
    ordenadas = sorted(latencias)
    total = len(ordenadas) + erros
    ms = lambda s: None if s is None else round(s * 1000, 3)  # noqa: E731
    return {
        "operacoes": len(ordenadas),
        "erros": erros,
        "vazao_ops": round(len(ordenadas) / duracao, 1),
        "p50_ms": ms(percentil(ordenadas, 50)),
        "p95_ms": ms(percentil(ordenadas, 95)),
        "p99_ms": ms(percentil(ordenadas, 99)),
        "taxa_erro": round(erros / total, 6) if total else None,  # sem tentativas, indefinida
        "exemplos_de_erro": exemplos[:3],
    }


def juntar_parciais(parciais, processos: int, operacoes: tuple[str, ...], segundos: int, serie: list) -> None:
    """Emite um `PARCIAL` por segundo, quando todos os processos entregaram aquele segundo."""
    recebidos: dict[int, list] = {}
    for _ in range(processos * segundos):
        try:
            s, parte = parciais.get(timeout=FOLGA_PARCIAL + 30)
        except queue.Empty:
            return  # o resultado final não depende das parciais
        recebidos.setdefault(s, []).append(parte)
        if len(recebidos[s]) < processos:
            continue
        partes = recebidos.pop(s)
        por_operacao = {}
        for operacao in operacoes:
            latencias = sorted(x for p in partes if operacao in p for x in p[operacao][0])
            p95 = percentil(latencias, 95)
            por_operacao[operacao] = {"ops": len(latencias), "erros": sum(p[operacao][1] for p in partes
                                                                           if operacao in p),
                                      "p95_ms": None if p95 is None else round(p95 * 1000, 3)}
        linha = {"s": s, "por_operacao": por_operacao}
        serie.append(linha)
        emitir("PARCIAL " + json.dumps(linha))


def encerrar(filhos, motivo: str) -> int:
    emitir(f"Medição interrompida: {motivo}")
    for filho in filhos:
        filho.terminate()
    for filho in filhos:
        filho.join()
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--operacao", choices=(*OPERACOES, PICO), required=True)
    parser.add_argument("--lado", choices=LADOS, required=True)
    parser.add_argument("--conexoes", type=int, default=8)
    parser.add_argument("--duracao", type=float, default=60)
    parser.add_argument("--aquecimento", type=float, default=10)
    parser.add_argument("--processos", type=int, help="padrão: um por conexão")
    parser.add_argument("--curva-extra", action="store_true",
                        help="PostgreSQL com synchronous_commit=off na sessão, fora do padrão (ADR-0014)")
    args = parser.parse_args()
    if args.curva_extra and (args.lado != "postgres" or args.operacao not in ("contador", "registro")):
        parser.error("a curva extra só existe no PostgreSQL, no contador e no registro de clique")

    manifesto = json.loads(MANIFESTO.read_text(encoding="utf-8"))
    if not manifesto_valido(manifesto):
        print(f"Manifesto inválido em {MANIFESTO}; nada foi medido.")
        return 1
    popular = manifesto["link_popular"]["short_code"]
    outros = [l.short_code for l in Base(semente=manifesto["semente"], fim=manifesto["fim"]).links()
              if l.short_code != popular]
    janela = tuple(datetime.fromisoformat(manifesto["janela_historico"][k]) for k in ("inicio", "fim"))

    limite_cpu = cpus_do_limite()
    processos = max(1, min(args.conexoes, args.processos or args.conexoes))
    divisao = [args.conexoes // processos + (1 if i < args.conexoes % processos else 0) for i in range(processos)]

    ctx = get_context("spawn")
    prontos, partida = ctx.Barrier(processos + 1), ctx.Event()
    # perf_counter usa o relógio monotônico do sistema, o mesmo em todos os processos.
    # marcos: início da janela medida, fim dela e partida da carga.
    marcos, saida, parciais = ctx.Array("d", 3), ctx.Queue(), ctx.Queue()
    filhos = [ctx.Process(target=processo,
                          args=(i, n, args, popular, outros, janela, prontos, partida, marcos, saida, parciais))
              for i, n in enumerate(divisao)]
    for filho in filhos:
        filho.start()
    try:
        prontos.wait(timeout=120)  # todas as conexões abertas e os comandos preparados
    except BrokenBarrierError:
        prontos.abort()
        return encerrar(filhos, "um processo não conseguiu abrir as conexões")
    agora = time.perf_counter()
    marcos[0], marcos[1], marcos[2] = agora + args.aquecimento, agora + args.aquecimento + args.duracao, agora
    inicio = datetime.now(UTC)
    serie: list[dict] = []
    juntador = threading.Thread(target=juntar_parciais, daemon=True, args=(
        parciais, processos, CICLO[args.operacao], math.ceil(args.aquecimento + args.duracao), serie))
    juntador.start()
    partida.set()
    emitir("PARTIDA")
    extra = ", synchronous_commit=off" if args.curva_extra else ""
    emitir(f"{args.operacao} / {args.lado}{extra}: {args.conexoes} conexões em {processos} processos, "
           f"{args.aquecimento:.0f} s de aquecimento e {args.duracao:.0f} s medidos")

    time.sleep(max(0.0, marcos[0] - time.perf_counter()))
    cpu_antes, relogio_antes = cpu_usada_s(), time.perf_counter()
    emitir("JANELA inicio")
    time.sleep(max(0.0, marcos[1] - time.perf_counter()))
    cpu_depois, relogio_depois = cpu_usada_s(), time.perf_counter()
    emitir("JANELA fim")

    juntas = {o: (array("d"), 0, []) for o in CICLO[args.operacao]}
    for _ in filhos:
        try:
            parte = saida.get(timeout=120)
        except queue.Empty:
            return encerrar(filhos, "um processo não devolveu o resultado")
        for operacao, (latencias, erros, exemplos) in parte.items():
            soma = juntas[operacao]
            soma[0].extend(latencias)
            juntas[operacao] = (soma[0], soma[1] + erros, soma[2] + exemplos)
    for filho in filhos:
        filho.join()
    juntador.join(timeout=FOLGA_PARCIAL + 5)

    nucleos = (cpu_depois - cpu_antes) / (relogio_depois - relogio_antes)
    por_operacao = {o: estatisticas(*juntas[o], args.duracao) for o in CICLO[args.operacao]}
    resultado = {
        "operacao": args.operacao,
        "lado": args.lado,
        "curva_extra": args.curva_extra,
        "inicio": inicio.isoformat(timespec="seconds"),
        "conexoes": args.conexoes,
        "processos": processos,
        "aquecimento_s": args.aquecimento,
        "duracao_s": args.duracao,
        # Nas etapas isoladas, as métricas da operação ficam no topo, onde o calibrar.py as lê.
        **(por_operacao[args.operacao] if args.operacao != PICO else {"por_operacao": por_operacao}),
        "cpu_gerador_nucleos": round(nucleos, 2),
        "cpu_gerador_pct": round(100 * nucleos / limite_cpu, 1),
        "cpu_gerador_pct_exato": 100 * nucleos / limite_cpu,  # comparado com os 70% sem arredondar
        "limite_cpu_gerador": limite_cpu,
        "memoria_pico_gerador_mib": memoria_pico_mib(),
        "serie": sorted(serie, key=lambda linha: linha["s"]),  # um segundo por linha, desde a partida
    }
    emitir("RESULTADO " + json.dumps(resultado, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
