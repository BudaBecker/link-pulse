"""Para e religa o Cassandra do benchmark à mão: reserva do cenário de queda (ADR-0013).

    python benchmark/queda_manual.py parar
    python benchmark/queda_manual.py religar

Uso: `python benchmark/medir.py --operacoes queda --queda-manual` avisa a hora
de rodar cada comando, num segundo terminal. Por isso este script não pega a
trava: a medição em andamento já está com ela. Recusa bancos no ar com os
volumes de desenvolvimento, como os comandos da base.
"""

from __future__ import annotations

import argparse
import sys
import time

from base import compose, exigir_volumes_de_benchmark


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("acao", choices=("parar", "religar"))
    args = parser.parse_args()

    exigir_volumes_de_benchmark()
    inicio = time.monotonic()
    if args.acao == "parar":
        compose("stop", "cassandra")
        print(f"Cassandra parado em {time.monotonic() - inicio:.1f} s")
    else:
        compose("start", "--wait", "cassandra")
        print(f"Cassandra saudável pelo healthcheck em {time.monotonic() - inicio:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
