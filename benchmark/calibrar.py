"""Calibra o número de conexões do gerador de carga (SPEC-005, passo 3).

Mede as quatro operações nos dois lados com 8, 32 e 64 conexões, cada número
com a sequência e as restaurações do medir.py. Vale o maior número em que o
gerador fica abaixo de 70% da sua cota de CPU em todas as combinações
(ADR-0014). Se alguma chegar a 70% já com 8 conexões, a calibração para: pela
regra do ADR-0013, o laço de disparo seria reescrito em outra linguagem. Uma
execução sem operação concluída ou com erro invalida o nível, e a calibração
para sem escolha.

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
APROVADO, ACIMA_DO_TETO, INVALIDA, INTERROMPIDO = "aprovado", "cpu_acima_do_teto", "medicao_invalida", "interrompido"
SAIDA_ACIMA_DO_TETO, SAIDA_INVALIDA = 2, 3


def invalida(execucao: dict) -> bool:
    """Sem operação concluída ou com erro, a CPU do gerador não mede a carga."""
    return execucao["operacoes"] == 0 or execucao["erros"] > 0


def acima_do_teto(execucao: dict) -> bool:
    return execucao["cpu_gerador_pct_exato"] >= TETO_CPU_GERADOR_PCT


def motivo(nivel: dict) -> str:
    if any(invalida(e) for e in nivel["execucoes"]):
        return INVALIDA
    return ACIMA_DO_TETO if any(acima_do_teto(e) for e in nivel["execucoes"]) else APROVADO


def continuar(nivel: dict) -> bool:
    """Para num nível inválido e no primeiro nível reprovado por CPU (ADR-0013)."""
    return nivel["motivo"] == APROVADO or (nivel["motivo"] == ACIMA_DO_TETO and nivel["conexoes"] != CONEXOES[0])


def escolha(niveis: list[dict]) -> int | None:
    if any(n["motivo"] == INVALIDA for n in niveis):
        return None
    return max((n["conexoes"] for n in niveis if n["motivo"] == APROVADO), default=None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos_de_duracao(parser)
    args = parser.parse_args()
    args.operacoes, args.lados, args.sem_restaurar = list(OPERACOES), list(LADOS), False

    dados = {"parametros": {**vars(args), "conexoes": CONEXOES}, "niveis": [], "escolha": None}
    codigo = 0
    try:
        with Trava("calibrar"):
            exigir_volumes_de_benchmark()
            for conexoes in CONEXOES:
                print(f"\n=== {conexoes} conexões ===")
                nivel = {"conexoes": conexoes, "motivo": INTERROMPIDO, "restauracoes": [], "execucoes": []}
                dados["niveis"].append(nivel)
                sequencia(args, conexoes, nivel)
                nivel["motivo"] = motivo(nivel)
                if not continuar(nivel):
                    break
        # Só aqui: uma falha no meio deixa a escolha nula e guarda o que já foi medido.
        dados["escolha"] = escolha(dados["niveis"])
    except subprocess.CalledProcessError as erro:
        print(f"\nFalhou ({erro.returncode}): {' '.join(erro.cmd)}", file=sys.stderr)
        codigo = 1
    finally:
        if dados["niveis"]:
            registrar("calibrar", dados)

    tabela([e for n in dados["niveis"] for e in n["execucoes"]])
    if codigo:
        return codigo
    ultimo = dados["niveis"][-1]
    if ultimo["motivo"] == INVALIDA:
        print(f"\nCom {ultimo['conexoes']} conexões, medição inválida, sem operação concluída ou com erro, em: "
              + ", ".join(f"{e['operacao']} / {NOMES[e['lado']]} ({e['operacoes']} operações, {e['erros']} erros)"
                          for e in ultimo["execucoes"] if invalida(e))
              + ". A CPU do gerador não vale nesse nível; a calibração parou aqui, sem escolha.")
        return SAIDA_INVALIDA
    if dados["escolha"] is None:
        acima = [e for e in ultimo["execucoes"] if acima_do_teto(e)]
        print(f"\nCom {CONEXOES[0]} conexões, o gerador chegou a {TETO_CPU_GERADOR_PCT:.0f}% da cota em: "
              + ", ".join(f"{e['operacao']} / {NOMES[e['lado']]} ({e['cpu_gerador_pct']}%)" for e in acima)
              + ". Pela regra do ADR-0013, o laço de disparo seria reescrito; a calibração parou aqui.")
        return SAIDA_ACIMA_DO_TETO
    print(f"\nEscolha: {dados['escolha']} conexões, o maior número com o gerador abaixo de "
          f"{TETO_CPU_GERADOR_PCT:.0f}% da cota em todas as combinações.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
