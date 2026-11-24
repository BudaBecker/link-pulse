"""Calibra o número de conexões do gerador de carga (SPEC-005, passo 3).

Mede as quatro operações nos dois lados com 8, 32 e 64 conexões, cada número
com a sequência e as restaurações do medir.py. Vale o maior número em que o
gerador fica abaixo de 70% da sua cota de CPU em todas as combinações
(ADR-0014). Se alguma chegar a 70% já com 8 conexões, a calibração para: pela
regra do ADR-0013, o laço de disparo seria reescrito em outra linguagem.

    python benchmark/calibrar.py

O resultado vai para benchmark/registros/, fora do Git. Detalhes em benchmark/README.md.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from base import Trava, exigir_volumes_de_benchmark, registrar
from medir import LADOS, NOMES, OPERACOES, argumentos_de_duracao, sequencia, tabela

CONEXOES = (8, 32, 64)
TETO_CPU_GERADOR_PCT = 70.0
COMBINACOES = len(OPERACOES) * len(LADOS)


def aprovado(nivel: dict) -> bool:
    execucoes = nivel["execucoes"]
    return len(execucoes) == COMBINACOES and all(e["cpu_gerador_pct"] < TETO_CPU_GERADOR_PCT for e in execucoes)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos_de_duracao(parser)
    args = parser.parse_args()
    args.operacoes, args.lados, args.sem_restaurar = list(OPERACOES), list(LADOS), False

    dados = {"parametros": {**vars(args), "conexoes": CONEXOES}, "niveis": []}
    codigo = 0
    try:
        with Trava("calibrar"):
            exigir_volumes_de_benchmark()
            for conexoes in CONEXOES:
                print(f"\n=== {conexoes} conexões ===")
                nivel = {"conexoes": conexoes, "restauracoes": [], "execucoes": []}
                dados["niveis"].append(nivel)
                sequencia(args, conexoes, nivel)
                if conexoes == CONEXOES[0] and not aprovado(nivel):
                    break
    except subprocess.CalledProcessError as erro:
        print(f"\nFalhou ({erro.returncode}): {' '.join(erro.cmd)}", file=sys.stderr)
        codigo = 1
    finally:
        aprovados = [n["conexoes"] for n in dados["niveis"] if aprovado(n)]
        dados["escolha"] = max(aprovados) if aprovados else None
        if dados["niveis"]:
            registrar("calibrar", dados)

    tabela([e for n in dados["niveis"] for e in n["execucoes"]])
    if codigo:
        return codigo
    if dados["escolha"] is None:
        acima = [e for e in dados["niveis"][0]["execucoes"] if e["cpu_gerador_pct"] >= TETO_CPU_GERADOR_PCT]
        print(f"\nCom {CONEXOES[0]} conexões, o gerador chegou a {TETO_CPU_GERADOR_PCT:.0f}% da cota em: "
              + ", ".join(f"{e['operacao']} / {NOMES[e['lado']]} ({e['cpu_gerador_pct']}%)" for e in acima)
              + ". Pela regra do ADR-0013, o laço de disparo seria reescrito; a calibração parou aqui.")
        return 2
    print(f"\nEscolha: {dados['escolha']} conexões, o maior número com o gerador abaixo de "
          f"{TETO_CPU_GERADOR_PCT:.0f}% da cota em todas as combinações.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
