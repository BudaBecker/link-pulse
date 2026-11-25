"""Mede as quatro operações, o pico e a queda do Cassandra com o gerador de carga (SPEC-005, passos 2, 4 e 5).

Roda no próprio computador, como o base.py, e chama benchmark/gerador.py no
contêiner `gerador` para cada operação e cada lado, um de cada vez. Restaura a
base antes de começar e de novo antes do histórico e antes do pico, se uma
escrita rodou desde a última restauração. Na sequência completa, o pico vem
depois do histórico, que não escreve, e não restaura de novo. Com
--sem-restaurar, não restaura em momento nenhum. Usa a trava
do base.py: nenhum comando da base roda no meio. Os argumentos são validados
aqui, antes da trava. Na janela medida, lê também a CPU dos bancos exercitados.
Na queda do Cassandra, a última etapa, sobe a API no computador com o Python do
.venv e roda benchmark/queda.py no contêiner `gerador-queda` (Q-62).

    python benchmark/medir.py
    python benchmark/medir.py --operacoes contador registro --lados postgres --duracao 20 --aquecimento 5
    python benchmark/medir.py --operacoes pico
    python benchmark/medir.py --operacoes queda

O resultado vai para benchmark/registros/, fora do Git. Detalhes em benchmark/README.md.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import socket
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from base import (
    COMPOSE, RAIZ, REGISTROS, ROTULO_AUXILIAR, Trava, cmd_restaurar, conteiner, exigir_bancos_no_ar,
    exigir_volumes_de_benchmark, manifesto_da_base, registrar, rodar,
)
# As mesmas de gerador.py, que não é importado: ele usa os drivers dos bancos.
OPERACOES = ("redirecionamento", "contador", "registro", "historico")
PICO = "pico"
QUEDA = "queda"
ETAPAS = (*OPERACOES, PICO, QUEDA)  # a ordem da sequência de testes
LADOS = ("nosql", "postgres")
ESCRITAS = ("contador", "registro", PICO)
NOMES = {"nosql": "NoSQL", "postgres": "PostgreSQL"}
# Bancos que cada etapa exercita, para ler a CPU deles na janela medida.
BANCOS = {
    "nosql": {"redirecionamento": ("redis-master",), "contador": ("redis-master",),
              "registro": ("cassandra",), "historico": ("cassandra",), PICO: ("redis-master", "cassandra")},
    "postgres": dict.fromkeys(ETAPAS, ("postgres",)),
}


def cpu_do_banco(identificador: str) -> tuple[float, float, float]:
    """CPU já usada pelo contêiner (s), CPUs do seu teto e o instante da leitura."""
    texto = rodar(["docker", "exec", identificador, "cat", "/sys/fs/cgroup/cpu.max", "/sys/fs/cgroup/cpu.stat"],
                  capturar=True)
    instante = time.perf_counter()
    linhas = texto.splitlines()
    cota, periodo = linhas[0].split()
    usado = next(int(l.split()[1]) for l in linhas if l.startswith("usage_usec "))
    return usado / 1e6, (int(cota) / int(periodo) if cota != "max" else math.nan), instante


def executar(operacao: str, lado: str, conexoes: int, args: argparse.Namespace) -> dict:
    comando = [*COMPOSE, "run", "--rm", "--no-deps", "--label", f"{ROTULO_AUXILIAR}=medir", "gerador",
               "python", "benchmark/gerador.py", "--operacao", operacao, "--lado", lado,
               "--conexoes", str(conexoes), "--duracao", str(args.duracao),
               "--aquecimento", str(args.aquecimento)]
    if args.processos:
        comando += ["--processos", str(args.processos)]
    bancos = {banco: conteiner(banco) for banco in BANCOS[lado][operacao]}
    resultado, janela = None, {}
    leitor = ThreadPoolExecutor(max_workers=len(bancos))
    with leitor, subprocess.Popen(comando, stdout=subprocess.PIPE, text=True, encoding="utf-8") as gerador:
        for linha in gerador.stdout:
            if linha.startswith("RESULTADO "):
                resultado = json.loads(linha.removeprefix("RESULTADO "))
            elif linha.startswith("JANELA "):
                # O gerador marca o início e o fim da janela medida. Os bancos são lidos
                # em paralelo, para nenhuma leitura esperar a do outro banco.
                leituras = {b: leitor.submit(cpu_do_banco, i) for b, i in bancos.items()}
                janela[linha.split()[1]] = {b: f.result() for b, f in leituras.items()}
            else:
                print("  " + linha, end="")
    if gerador.returncode or resultado is None or len(janela) != 2:
        raise subprocess.CalledProcessError(gerador.returncode or 1, comando)
    resultado["cpu_bancos"] = {}
    for banco in bancos:
        (usado_antes, teto, antes), (usado_depois, _, depois) = janela["inicio"][banco], janela["fim"][banco]
        nucleos = (usado_depois - usado_antes) / (depois - antes)
        resultado["cpu_bancos"][banco] = {"nucleos": round(nucleos, 2), "pct": round(100 * nucleos / teto, 1),
                                          "limite": teto}
    if len(bancos) == 1:  # campos de um banco só, como nos registros da calibração
        banco, cpu = next(iter(resultado["cpu_bancos"].items()))
        resultado |= {"banco": banco, "cpu_banco_nucleos": cpu["nucleos"], "cpu_banco_pct": cpu["pct"],
                      "limite_cpu_banco": cpu["limite"]}
    for nome, metricas in linhas_de_operacao(resultado):
        print(f"  {nome}: vazão {metricas['vazao_ops']:,.0f} ops/s · p50 {metricas['p50_ms']} ms · "
              f"p95 {metricas['p95_ms']} ms · p99 {metricas['p99_ms']} ms · "
              f"{metricas['operacoes']:,} sucessos · {metricas['erros']:,} erros ({taxa(metricas['taxa_erro'])})")
    print(f"  CPU do gerador {resultado['cpu_gerador_nucleos']} núcleos ({resultado['cpu_gerador_pct']}%) · "
          f"{cpu_dos_bancos(resultado)} · pico de memória do gerador {resultado['memoria_pico_gerador_mib']} MiB")
    return resultado


PORTA_API = 8001  # própria do cenário, fora da 8000 da demonstração (Q-62)
PRAZO_API = 60  # s para a API responder depois de subir
# A API usa os bancos do benchmark no ar, e não o que as variáveis do terminal apontarem (Q-62).
CONEXOES_DA_API = {
    "REDIS_MASTER_HOST": "127.0.0.1", "REDIS_MASTER_PORT": "6379",
    "REDIS_REPLICA_HOST": "127.0.0.1", "REDIS_REPLICA_PORT": "6380",
    "CASSANDRA_HOST": "127.0.0.1", "CASSANDRA_PORT": "9042", "CASSANDRA_KEYSPACE": "linkpulse",
    "MONGO_URL": "mongodb://127.0.0.1:27017", "MONGO_DB": "linkpulse",
}


def python_do_venv() -> str:
    for caminho in (RAIZ / ".venv" / "Scripts" / "python.exe", RAIZ / ".venv" / "bin" / "python"):
        if caminho.exists():
            return str(caminho)
    sys.exit("a queda do Cassandra sobe a API com o Python do .venv, que não existe; veja app/README.md")


def subir_api(log) -> subprocess.Popen:
    """A API no computador, como na demonstração, pelo envoltório que mede o tempo no servidor (Q-62, Q-63)."""
    # Sem esta conferência, a espera abaixo aceitaria outro processo que já respondesse na porta.
    try:
        socket.create_connection(("127.0.0.1", PORTA_API), timeout=1).close()
        sys.exit(f"a porta {PORTA_API} já está em uso; encerre o processo que a ocupa e repita")
    except OSError:
        pass
    # Um processo só, qualquer que seja o WEB_CONCURRENCY do terminal: as falhas em `/metricas` ficam na memória
    # de cada processo, e a leitura veria as de um só.
    api = subprocess.Popen(
        [python_do_venv(), "-m", "uvicorn", "benchmark.api_cronometrada:app", "--port", str(PORTA_API),
         "--workers", "1", "--no-access-log"], cwd=RAIZ, stdout=log, stderr=subprocess.STDOUT,
        env={**os.environ, **CONEXOES_DA_API})
    limite = time.monotonic() + PRAZO_API
    while time.monotonic() < limite:
        if api.poll() is not None:
            sys.exit(f"a API saiu com código {api.returncode} ao subir; veja {log.name}")
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORTA_API}/metricas", timeout=1).read()
            return api
        except OSError:
            time.sleep(0.5)
    api.terminate()
    sys.exit(f"a API não respondeu em {PRAZO_API} s; veja {log.name}")


def executar_queda(args: argparse.Namespace) -> dict:
    # Na parada manual, o serviço `gerador`, sem o socket do Docker montado.
    servico = "gerador" if args.queda_manual else "gerador-queda"
    comando = [*COMPOSE, "run", "--rm", "--no-deps", "--label", f"{ROTULO_AUXILIAR}=medir", servico,
               "python", "benchmark/queda.py", "--api", f"http://host.docker.internal:{PORTA_API}",
               "--cassandra", conteiner("cassandra")]
    if args.queda_manual:
        comando.append("--queda-manual")
    REGISTROS.mkdir(exist_ok=True)
    caminho_log = REGISTROS / f"queda-api-{datetime.now():%Y%m%d-%H%M%S}.log"
    resultado = None
    with open(caminho_log, "w", encoding="utf-8") as log:
        api = subir_api(log)
        try:
            with subprocess.Popen(comando, stdout=subprocess.PIPE, text=True, encoding="utf-8") as gerador:
                for linha in gerador.stdout:
                    if linha.startswith("RESULTADO "):
                        resultado = json.loads(linha.removeprefix("RESULTADO "))
                    else:
                        print("  " + linha, end="")
        finally:
            api.terminate()
            api.wait()
    if gerador.returncode or resultado is None:
        raise subprocess.CalledProcessError(gerador.returncode or 1, comando)
    resultado["log_da_api"] = caminho_log.relative_to(RAIZ).as_posix()
    resumo_da_queda(resultado)
    return resultado


def numero(valor, sinal: str = "") -> str:
    """Um campo da queda que pode faltar, quando a leitura não respondeu ou o Cassandra não voltou."""
    return "indisponível" if valor is None else f"{sinal}{valor:,}"


def resumo_da_queda(r: dict) -> None:
    q, c, m = r["queda"], r["conferencia"], r["marcos"]
    print(f"  queda vista pela aplicação: de {q['janela_s'][0]:.0f} a {q['janela_s'][1]:.1f} s"
          + ("" if q["gravacao_voltou_na_etapa"] else " (a gravação não voltou na etapa)"))
    print(f"  {q['respostas_302']:,} de {q['envios']:,} envios com 302 · p95 no servidor {q['p95_servidor_ms']} ms · "
          f"p95 no gerador {q['p95_gerador_ms']} ms · contador {numero(q['contador_somou'], '+')} · "
          f"falhas {numero(q['falhas_somaram'], '+')}")
    print("  marcos (s): " + " · ".join(f"{k.removesuffix('_s')} {v}" for k, v in m.items()))
    print(f"  conferência: contador {numero(c['contador'], '+')} · histórico {numero(c['historico'], '+')} · "
          f"falhas {numero(c['falhas'], '+')} · diferença {numero(c['diferenca_contador_historico'])} "
          f"(diferença menos falhas: {numero(c['diferenca_menos_falhas'])})"
          + (f" · a consulta ao Cassandra falhou: {c['erro']}" if c["erro"] else ""))
    ca6 = "cumprido" if q["ca6"] else "NÃO cumprido"
    if r["erros_no_controle"]:
        ca6 = f"rodada inválida, o controle do Cassandra falhou ({'; '.join(r['erros_no_controle'])}); repita"
    print(f"  CA-6 nesta execução: {ca6} · CPU do gerador {r['cpu_gerador_nucleos']} núcleos "
          f"({r['cpu_gerador_pct']}%)")


def linhas_de_operacao(execucao: dict) -> list[tuple[str, dict]]:
    """Uma linha por operação: no pico, as três; nas outras etapas, a própria."""
    if "por_operacao" in execucao:
        return [(f"pico: {o}", m) for o, m in execucao["por_operacao"].items()]
    return [(execucao["operacao"], execucao)]


def cpu_dos_bancos(execucao: dict) -> str:
    return " · ".join(f"CPU do {b} {c['nucleos']} núcleos ({c['pct']}%)" for b, c in execucao["cpu_bancos"].items())


def taxa(valor: float | None) -> str:
    """Sem tentativas na janela, a taxa de erro é nula; a calibração trata como medição inválida."""
    return "—" if valor is None else f"{valor:.4%}"


def tabela(execucoes: list[dict]) -> None:
    execucoes = [e for e in execucoes if e["operacao"] != QUEDA]  # a queda tem resumo próprio
    if not execucoes:
        return
    print("\n| Conexões | Operação | Lado | Vazão (ops/s) | p50 (ms) | p95 (ms) | p99 (ms) | Sucessos | Erros "
          "| Taxa de erro | CPU do gerador | CPU dos bancos | Memória do gerador (MiB) |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for e in execucoes:
        # Registros antigos, de antes da CPU de vários bancos, têm só os campos de um banco.
        cpus = e.get("cpu_bancos") or {e["banco"]: {"nucleos": e["cpu_banco_nucleos"], "pct": e["cpu_banco_pct"]}}
        bancos = ", ".join(f"{b} {c['nucleos']} ({c['pct']}%)" for b, c in cpus.items())
        for nome, m in linhas_de_operacao(e):
            print(f"| {e['conexoes']} | {nome} | {NOMES[e['lado']]} | {m['vazao_ops']:,.0f} | {m['p50_ms']} | "
                  f"{m['p95_ms']} | {m['p99_ms']} | {m['operacoes']:,} | {m['erros']:,} | {taxa(m['taxa_erro'])} | "
                  f"{e['cpu_gerador_nucleos']} ({e['cpu_gerador_pct']}%) | {bancos} | "
                  f"{e['memoria_pico_gerador_mib']} |")


def sequencia(args: argparse.Namespace, conexoes: int, dados: dict) -> None:
    """Mede as operações e os lados pedidos, com as restaurações descritas no início do arquivo."""
    if args.sem_restaurar:
        exigir_bancos_no_ar()
        manifesto_da_base()
    else:
        dados["restauracoes"].append(cmd_restaurar(conferir=True))
    houve_escrita = False
    # Sempre na ordem da sequência de testes, qualquer que seja a ordem pedida.
    for operacao in [o for o in ETAPAS if o in args.operacoes]:
        # O histórico lê as linhas acrescentadas, e o pico partiria de bases diferentes em cada lado.
        if operacao in ("historico", PICO) and houve_escrita and not args.sem_restaurar:
            print(f"Restaurando a base antes do {'histórico por período' if operacao == 'historico' else 'pico'}")
            dados["restauracoes"].append(cmd_restaurar(conferir=True))
            houve_escrita = False
        if operacao == QUEDA:  # só o lado NoSQL, pela aplicação, sobre o estado em que o pico deixou a base
            if "nosql" in args.lados:
                print("\nqueda do Cassandra / NoSQL, pela aplicação")
                dados["execucoes"].append(executar_queda(args))
            continue
        for lado in [l for l in LADOS if l in args.lados]:
            print(f"\n{operacao} / {NOMES[lado]}, {conexoes} conexões")
            dados["execucoes"].append(executar(operacao, lado, conexoes, args))
        houve_escrita |= operacao in ESCRITAS


def positivo(tipo, zero: bool = False):
    """Tipo do argparse que recusa negativos, e zero se zero=False, antes de pegar a trava."""
    def converter(texto: str):
        valor = tipo(texto)
        if not math.isfinite(valor) or valor < 0 or (valor == 0 and not zero):
            raise argparse.ArgumentTypeError(f"precisa ser finito e {'>= 0' if zero else '> 0'}")
        return valor
    return converter


def argumentos_de_duracao(parser: argparse.ArgumentParser) -> None:
    """Argumentos comuns ao medir.py e ao calibrar.py."""
    parser.add_argument("--duracao", type=positivo(float), default=60, help="segundos medidos por lado")
    parser.add_argument("--aquecimento", type=positivo(float, zero=True), default=10,
                        help="segundos descartados antes da medição")
    parser.add_argument("--processos", type=positivo(int), help="processos do gerador; padrão: um por conexão")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--operacoes", nargs="+", choices=ETAPAS, default=list(ETAPAS),
                        help="etapas a medir; padrão: as quatro operações, o pico e a queda do Cassandra")
    parser.add_argument("--lados", nargs="+", choices=LADOS, default=list(LADOS))
    parser.add_argument("--conexoes", type=positivo(int), default=8, help="padrão 8, o número escolhido pela calibração")
    argumentos_de_duracao(parser)
    parser.add_argument("--sem-restaurar", action="store_true",
                        help="mede sobre o estado atual da base, sem restaurar em momento nenhum")
    parser.add_argument("--queda-manual", action="store_true",
                        help="na queda, não mexe no Docker: avisa a hora de rodar benchmark/queda_manual.py")
    args = parser.parse_args()
    if set(args.operacoes) == {QUEDA} and "nosql" not in args.lados:
        parser.error("a queda do Cassandra só tem o lado nosql; nada seria medido")

    dados = {"parametros": vars(args), "restauracoes": [], "execucoes": []}
    try:
        with Trava("medir"):
            exigir_volumes_de_benchmark()
            sequencia(args, args.conexoes, dados)
    except subprocess.CalledProcessError as erro:
        print(f"\nFalhou ({erro.returncode}): {' '.join(erro.cmd)}", file=sys.stderr)
        return 1
    finally:
        if dados["execucoes"]:
            registrar("medir", dados)
    tabela(dados["execucoes"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
