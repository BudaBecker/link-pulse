"""Mede as quatro operações nos dois lados com o gerador de carga (SPEC-005, passo 2).

Roda no próprio computador, como o base.py, e chama benchmark/gerador.py no
contêiner `gerador` para cada operação e cada lado, um de cada vez. Restaura a
base antes de começar e antes do histórico por período, se uma escrita rodou
antes dele; com --sem-restaurar, não restaura em momento nenhum. Usa a trava
do base.py: nenhum comando da base roda no meio. Os argumentos são validados
aqui, antes da trava. Na janela medida, lê também a CPU do banco exercitado.

    python benchmark/medir.py
    python benchmark/medir.py --operacoes contador registro --lados postgres --duracao 20 --aquecimento 5

O resultado vai para benchmark/registros/, fora do Git. Detalhes em benchmark/README.md.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time

from base import (
    COMPOSE, ROTULO_AUXILIAR, Trava, cmd_restaurar, conteiner, exigir_bancos_no_ar, exigir_volumes_de_benchmark,
    manifesto_da_base, registrar, rodar,
)
# As mesmas de gerador.py, que não é importado: ele usa os drivers dos bancos.
OPERACOES = ("redirecionamento", "contador", "registro", "historico")
LADOS = ("nosql", "postgres")
ESCRITAS = ("contador", "registro")
NOMES = {"nosql": "NoSQL", "postgres": "PostgreSQL"}
# Banco que cada operação exercita, para ler a CPU dele na janela medida.
BANCO = {
    "nosql": {"redirecionamento": "redis-master", "contador": "redis-master",
              "registro": "cassandra", "historico": "cassandra"},
    "postgres": dict.fromkeys(OPERACOES, "postgres"),
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
    banco = BANCO[lado][operacao]
    identificador = conteiner(banco)
    resultado, janela = None, {}
    with subprocess.Popen(comando, stdout=subprocess.PIPE, text=True, encoding="utf-8") as gerador:
        for linha in gerador.stdout:
            if linha.startswith("RESULTADO "):
                resultado = json.loads(linha.removeprefix("RESULTADO "))
            elif linha.startswith("JANELA "):
                # O gerador marca o início e o fim da janela medida.
                janela[linha.split()[1]] = cpu_do_banco(identificador)
            else:
                print("  " + linha, end="")
    if gerador.returncode or resultado is None or len(janela) != 2:
        raise subprocess.CalledProcessError(gerador.returncode or 1, comando)
    (usado_antes, teto, antes), (usado_depois, _, depois) = janela["inicio"], janela["fim"]
    nucleos = (usado_depois - usado_antes) / (depois - antes)
    resultado |= {"banco": banco, "cpu_banco_nucleos": round(nucleos, 2),
                  "cpu_banco_pct": round(100 * nucleos / teto, 1), "limite_cpu_banco": teto}
    print(f"  vazão {resultado['vazao_ops']:,.0f} ops/s · p50 {resultado['p50_ms']} ms · "
          f"p95 {resultado['p95_ms']} ms · p99 {resultado['p99_ms']} ms · erros {resultado['taxa_erro']:.4%}\n"
          f"  CPU do gerador {resultado['cpu_gerador_nucleos']} núcleos ({resultado['cpu_gerador_pct']}%) · "
          f"CPU do {banco} {resultado['cpu_banco_nucleos']} núcleos ({resultado['cpu_banco_pct']}%) · "
          f"pico de memória do gerador {resultado['memoria_pico_gerador_mib']} MiB")
    return resultado


def tabela(execucoes: list[dict]) -> None:
    print("\n| Conexões | Operação | Lado | Vazão (ops/s) | p50 (ms) | p95 (ms) | p99 (ms) | Taxa de erro "
          "| CPU do gerador | CPU do banco | Memória do gerador (MiB) |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for e in execucoes:
        print(f"| {e['conexoes']} | {e['operacao']} | {NOMES[e['lado']]} | {e['vazao_ops']:,.0f} | {e['p50_ms']} | "
              f"{e['p95_ms']} | {e['p99_ms']} | {e['taxa_erro']:.4%} | "
              f"{e['cpu_gerador_nucleos']} ({e['cpu_gerador_pct']}%) | "
              f"{e['cpu_banco_nucleos']} ({e['cpu_banco_pct']}%) | {e['memoria_pico_gerador_mib']} |")


def sequencia(args: argparse.Namespace, conexoes: int, dados: dict) -> None:
    """Mede as operações e os lados pedidos, com as restaurações descritas no início do arquivo."""
    if args.sem_restaurar:
        exigir_bancos_no_ar()
        manifesto_da_base()
    else:
        dados["restauracoes"].append(cmd_restaurar(conferir=True))
    houve_escrita = False
    # Sempre na ordem da sequência de testes, qualquer que seja a ordem pedida.
    for operacao in [o for o in OPERACOES if o in args.operacoes]:
        if operacao == "historico" and houve_escrita and not args.sem_restaurar:
            print("Restaurando a base antes do histórico por período")
            dados["restauracoes"].append(cmd_restaurar(conferir=True))
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
    parser.add_argument("--operacoes", nargs="+", choices=OPERACOES, default=list(OPERACOES))
    parser.add_argument("--lados", nargs="+", choices=LADOS, default=list(LADOS))
    parser.add_argument("--conexoes", type=positivo(int), default=8, help="padrão 8, o número escolhido pela calibração")
    argumentos_de_duracao(parser)
    parser.add_argument("--sem-restaurar", action="store_true",
                        help="mede sobre o estado atual da base, sem restaurar em momento nenhum")
    args = parser.parse_args()

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
