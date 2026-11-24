"""Mede as quatro operações nos dois lados com o gerador de carga (SPEC-005, passo 2).

Roda no próprio computador, como o base.py, e chama benchmark/gerador.py no
contêiner `gerador` para cada operação e cada lado, um de cada vez. Restaura a
base antes de começar e antes do histórico por período, se uma escrita rodou
antes dele. Usa a trava do base.py: nenhum comando da base roda no meio.

    python benchmark/medir.py
    python benchmark/medir.py --operacoes contador registro --lados postgres --duracao 20 --aquecimento 5

O resultado vai para benchmark/registros/, fora do Git. Detalhes em benchmark/README.md.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

from base import (
    COMPOSE, ROTULO_AUXILIAR, Trava, cmd_restaurar, exigir_bancos_no_ar, exigir_volumes_de_benchmark,
    manifesto_da_base, registrar,
)
# As mesmas de gerador.py, que não é importado: ele usa os drivers dos bancos.
OPERACOES = ("redirecionamento", "contador", "registro", "historico")
LADOS = ("nosql", "postgres")
ESCRITAS = ("contador", "registro")
NOMES = {"nosql": "NoSQL", "postgres": "PostgreSQL"}


def executar(operacao: str, lado: str, args: argparse.Namespace) -> dict:
    comando = [*COMPOSE, "run", "--rm", "--no-deps", "--label", f"{ROTULO_AUXILIAR}=medir", "gerador",
               "python", "benchmark/gerador.py", "--operacao", operacao, "--lado", lado,
               "--conexoes", str(args.conexoes), "--duracao", str(args.duracao),
               "--aquecimento", str(args.aquecimento)]
    resultado = None
    with subprocess.Popen(comando, stdout=subprocess.PIPE, text=True, encoding="utf-8") as gerador:
        for linha in gerador.stdout:
            if linha.startswith("RESULTADO "):
                resultado = json.loads(linha.removeprefix("RESULTADO "))
            else:
                print("  " + linha, end="")
    if gerador.returncode or resultado is None:
        raise subprocess.CalledProcessError(gerador.returncode or 1, comando)
    print(f"  vazão {resultado['vazao_ops']:,.0f} ops/s · p50 {resultado['p50_ms']} ms · "
          f"p95 {resultado['p95_ms']} ms · p99 {resultado['p99_ms']} ms · "
          f"erros {resultado['taxa_erro']:.4%} · CPU do gerador {resultado['cpu_gerador_pct']}%")
    return resultado


def tabela(execucoes: list[dict]) -> None:
    print("\n| Operação | Lado | Vazão (ops/s) | p50 (ms) | p95 (ms) | p99 (ms) | Taxa de erro | CPU do gerador |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for e in execucoes:
        print(f"| {e['operacao']} | {NOMES[e['lado']]} | {e['vazao_ops']:,.0f} | {e['p50_ms']} | {e['p95_ms']} | "
              f"{e['p99_ms']} | {e['taxa_erro']:.4%} | {e['cpu_gerador_pct']}% |")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--operacoes", nargs="+", choices=OPERACOES, default=list(OPERACOES))
    parser.add_argument("--lados", nargs="+", choices=LADOS, default=list(LADOS))
    parser.add_argument("--conexoes", type=int, default=8, help="padrão 8, até a calibração (RM-42)")
    parser.add_argument("--duracao", type=float, default=60, help="segundos medidos por lado")
    parser.add_argument("--aquecimento", type=float, default=10, help="segundos descartados antes da medição")
    parser.add_argument("--sem-restaurar", action="store_true", help="mede sobre o estado atual da base")
    args = parser.parse_args()

    dados = {"parametros": vars(args), "restauracoes": [], "execucoes": []}
    try:
        with Trava("medir"):
            exigir_volumes_de_benchmark()
            if args.sem_restaurar:
                exigir_bancos_no_ar()
                manifesto_da_base()
            else:
                dados["restauracoes"].append(cmd_restaurar(conferir=True))
            houve_escrita = False
            # Sempre na ordem da sequência de testes, qualquer que seja a ordem pedida.
            for operacao in [o for o in OPERACOES if o in args.operacoes]:
                if operacao == "historico" and houve_escrita:
                    print("Restaurando a base antes do histórico por período")
                    dados["restauracoes"].append(cmd_restaurar(conferir=True))
                for lado in [l for l in LADOS if l in args.lados]:
                    print(f"\n{operacao} / {NOMES[lado]}")
                    dados["execucoes"].append(executar(operacao, lado, args))
                houve_escrita |= operacao in ESCRITAS
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
