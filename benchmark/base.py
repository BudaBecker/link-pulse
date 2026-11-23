"""Base de referência do benchmark: carregar, copiar, restaurar e conferir.

Roda no computador do host, com Python 3.11+ e o Docker; só usa a biblioteca
padrão. Os bancos rodam com docker-compose.yml + docker-compose.benchmark.yml,
que usa volumes próprios do benchmark (linkpulse-benchmark-*).

    python benchmark/base.py carregar     # recria os volumes de benchmark, carrega, confere e copia
    python benchmark/base.py restaurar    # volta os bancos à cópia guardada e confere o CA-1
    python benchmark/base.py conferir [--completo]
    python benchmark/base.py copiar       # guarda de novo a cópia do estado atual
    python benchmark/base.py manifesto    # só reescreve benchmark/base-de-referencia.json

Detalhes em benchmark/README.md.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from referencia import FIM_PADRAO, SEMENTE_PADRAO, Base, assinatura_gerada, descrever

RAIZ = Path(__file__).resolve().parent.parent
MANIFESTO = Path(__file__).with_name("base-de-referencia.json")
REGISTROS = Path(__file__).with_name("registros")
COMPOSE = [
    "docker", "compose",
    "-f", str(RAIZ / "docker-compose.yml"),
    "-f", str(RAIZ / "docker-compose.benchmark.yml"),
]
# Ordem de parada: a réplica antes do master.
BANCOS = ("redis-replica", "redis-master", "cassandra", "postgres")
VOLUMES = {banco: f"linkpulse-benchmark-{banco}" for banco in BANCOS}
# Onde cada banco guarda os dados no contêiner.
CAMINHO_DADOS = {
    "redis-replica": "/data",
    "redis-master": "/data",
    "cassandra": "/var/lib/cassandra",
    "postgres": "/var/lib/postgresql",
}
# Cada cópia é uma geração: um volume por banco mais um selo com o manifesto.
# O selo só é criado depois que as quatro cópias terminam bem, e a restauração
# só aceita uma geração selada.
ROTULO_GERACAO = "linkpulse.benchmark.geracao"
ROTULO_PAPEL = "linkpulse.benchmark.papel"
SELO = "selo"
# Cópias do formato anterior, sem geração; são apagadas na próxima cópia.
COPIAS_ANTIGAS = [f"linkpulse-benchmark-copia-{banco}" for banco in BANCOS]
COMPARADOS = ("redis-master", "cassandra", "postgres")
# Imagem já usada pelo ambiente, para copiar os volumes sem baixar outra.
IMAGEM_AUXILIAR = "redis:8.2.11-bookworm"


def rodar(comando: list[str], capturar: bool = False) -> str:
    resultado = subprocess.run(comando, check=True, text=True, capture_output=capturar, encoding="utf-8")
    return resultado.stdout if capturar else ""


def compose(*argumentos: str, capturar: bool = False) -> str:
    return rodar(COMPOSE + list(argumentos), capturar)


def volume_existe(nome: str) -> bool:
    return subprocess.run(["docker", "volume", "inspect", nome], capture_output=True).returncode == 0


def conteiner(servico: str) -> str:
    identificador = compose("ps", "-q", servico, capturar=True).strip()
    if not identificador:
        sys.exit(f"serviço {servico} não está no ar")
    return identificador


def exigir_volumes_de_benchmark() -> None:
    """Recusa parar bancos que estejam no ar com outros volumes.

    O docker-compose.yml e o docker-compose.benchmark.yml usam o mesmo projeto e
    os mesmos serviços. Sem esta conferência, restaurar ou copiar encerraria os
    bancos de desenvolvimento se eles estivessem no ar.
    """
    problemas = []
    for banco in BANCOS:
        for identificador in compose("ps", "-q", banco, capturar=True).split():
            montagens = json.loads(rodar(["docker", "inspect", "-f", "{{json .Mounts}}", identificador], True))
            volume = next(
                (m.get("Name") for m in montagens if m["Destination"] == CAMINHO_DADOS[banco]), None
            )
            if volume != VOLUMES[banco]:
                problemas.append(f"{banco} está no ar com {volume or 'outro armazenamento'} em {CAMINHO_DADOS[banco]}")
    if problemas:
        sys.exit(
            "Nada foi parado: os bancos no ar não usam os volumes de benchmark.\n  "
            + "\n  ".join(problemas)
            + "\nPare-os com parada normal (docker compose stop) e rode o comando de novo."
        )


def geracoes() -> dict[str, dict[str, str]]:
    """Volumes de cópia por geração: {geração: {banco ou "selo": volume}}."""
    formato = "{{.Name}}\t{{.Label \"%s\"}}\t{{.Label \"%s\"}}" % (ROTULO_GERACAO, ROTULO_PAPEL)
    saida = rodar(
        ["docker", "volume", "ls", "--filter", f"label={ROTULO_GERACAO}", "--format", formato],
        capturar=True,
    )
    resultado: dict[str, dict[str, str]] = {}
    for linha in saida.splitlines():
        nome, geracao, papel = linha.split("\t")
        resultado.setdefault(geracao, {})[papel] = nome
    return resultado


def copia_valida() -> tuple[str, dict[str, str]] | None:
    """A geração selada mais recente, com os quatro bancos."""
    for geracao, volumes in sorted(geracoes().items(), reverse=True):
        if SELO in volumes and all(banco in volumes for banco in BANCOS):
            return geracao, volumes
    return None


def criar_volume(nome: str, geracao: str, papel: str) -> None:
    rodar(["docker", "volume", "create", "--label", "linkpulse.benchmark=copia",
           "--label", f"{ROTULO_GERACAO}={geracao}", "--label", f"{ROTULO_PAPEL}={papel}", nome], capturar=True)


def remover_volumes(nomes) -> int:
    removidos = 0
    for nome in nomes:
        if volume_existe(nome):
            rodar(["docker", "volume", "rm", nome], capturar=True)
            removidos += 1
    return removidos


def ler_selo(volume: str) -> dict:
    texto = rodar(["docker", "run", "--rm", "-v", f"{volume}:/selo:ro", "--entrypoint", "cat",
                   IMAGEM_AUXILIAR, "/selo/base-de-referencia.json"], capturar=True)
    return json.loads(texto)


def subir() -> float:
    inicio = time.monotonic()
    compose("up", "-d", "--wait")
    return time.monotonic() - inicio


def copiar_volumes(origem: dict[str, str], destino: dict[str, str]) -> float:
    """Copia, em paralelo e com os bancos parados, cada volume de origem no de destino."""
    montagens = []
    for banco in BANCOS:
        montagens += ["-v", f"{origem[banco]}:/origem/{banco}:ro", "-v", f"{destino[banco]}:/destino/{banco}"]
    script = (
        "falha=0; pids=''; "
        f"for n in {' '.join(BANCOS)}; do "
        "( find /destino/$n -mindepth 1 -delete && cp -a /origem/$n/. /destino/$n/ ) & pids=\"$pids $!\"; "
        "done; "
        "for p in $pids; do wait $p || falha=1; done; "
        "du -sh /destino/*; exit $falha"
    )
    inicio = time.monotonic()
    rodar(["docker", "run", "--rm", *montagens, "--entrypoint", "sh", IMAGEM_AUXILIAR, "-c", script])
    return time.monotonic() - inicio


_UNIDADES = {"B": 1, "KiB": 2**10, "MiB": 2**20, "GiB": 2**30, "kB": 10**3, "MB": 10**6, "GB": 10**9}


def _bytes(texto: str) -> float:
    numero, unidade = re.fullmatch(r"([\d.]+)\s*([A-Za-z]+)", texto.strip()).groups()
    return float(numero) * _UNIDADES[unidade]


class MonitorMemoria:
    """Amostra o `docker stats` dos bancos comparados enquanto a carga roda."""

    def __init__(self) -> None:
        self.ids = {conteiner(s): s for s in COMPARADOS}
        self.pico: dict[str, float] = {s: 0.0 for s in COMPARADOS}
        self.teto: dict[str, float] = {}
        self.amostras = 0
        self._parar = threading.Event()
        self._thread = threading.Thread(target=self._amostrar, daemon=True)

    def _amostrar(self) -> None:
        while not self._parar.is_set():
            saida = subprocess.run(
                ["docker", "stats", "--no-stream", "--format", "{{.ID}} {{.MemUsage}}", *self.ids],
                capture_output=True, text=True,
            ).stdout
            for linha in saida.splitlines():
                identificador, uso = linha.split(" ", 1)
                atual, teto = uso.split(" / ")
                servico = next(s for i, s in self.ids.items() if i.startswith(identificador))
                self.pico[servico] = max(self.pico[servico], _bytes(atual))
                self.teto[servico] = _bytes(teto)
            self.amostras += 1
            self._parar.wait(1)

    def __enter__(self) -> "MonitorMemoria":
        self._thread.start()
        return self

    def __exit__(self, *_) -> None:
        self._parar.set()
        self._thread.join()

    def relatorio(self) -> dict:
        dados = {}
        for identificador, servico in self.ids.items():
            estado = json.loads(rodar(["docker", "inspect", "-f", "{{json .State}}", identificador], True))
            pico_cgroup = subprocess.run(
                ["docker", "exec", identificador, "cat", "/sys/fs/cgroup/memory.peak"],
                capture_output=True, text=True,
            ).stdout.strip()
            dados[servico] = {
                "pico_docker_stats_mib": round(self.pico[servico] / 2**20),
                "teto_mib": round(self.teto.get(servico, 0) / 2**20),
                "pico_cgroup_mib": round(int(pico_cgroup) / 2**20) if pico_cgroup.isdigit() else None,
                "encerrado_por_falta_de_memoria": estado["OOMKilled"],
                "rodando": estado["Running"],
            }
        dados["amostras"] = self.amostras
        return dados


def registrar(comando: str, dados: dict) -> None:
    REGISTROS.mkdir(exist_ok=True)
    arquivo = REGISTROS / f"{datetime.now():%Y%m%d-%H%M%S}-{comando}.json"
    arquivo.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Registro: {arquivo.relative_to(RAIZ)}")


def cmd_manifesto(semente: int, fim: str, processos: int) -> dict:
    base = Base(semente=semente, fim=fim)
    inicio = time.monotonic()
    manifesto = descrever(base, assinatura_gerada(base, processos))
    MANIFESTO.write_text(json.dumps(manifesto, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Manifesto em {MANIFESTO.relative_to(RAIZ)} ({time.monotonic() - inicio:.0f} s): "
          f"semente {manifesto['semente']}, fim {manifesto['fim']}, "
          f"link popular {manifesto['link_popular']['short_code']}, "
          f"assinatura {manifesto['assinatura_cliques']}")
    return manifesto


def cmd_conferir(completo: bool) -> float:
    exigir_volumes_de_benchmark()
    valida = copia_valida()
    if valida is not None and ler_selo(valida[1][SELO]) != json.loads(MANIFESTO.read_text(encoding="utf-8")):
        print(f"Aviso: o manifesto difere do guardado na cópia {valida[0]}; "
              "se a base no ar for a da cópia, restaure para repor o manifesto.", file=sys.stderr)
    inicio = time.monotonic()
    argumentos = ["run", "--rm", "carga", "python", "benchmark/conferir.py"]
    compose(*argumentos, *(["--completo"] if completo else []))
    return time.monotonic() - inicio


def cmd_copiar() -> dict:
    exigir_volumes_de_benchmark()
    manifesto = MANIFESTO.read_text(encoding="utf-8")
    print("Cópia da base: gravando o RDB do Redis e parando os bancos")
    for servico in ("redis-master", "redis-replica"):
        rodar(["docker", "exec", conteiner(servico), "redis-cli", "SAVE"])
    cassandra = conteiner("cassandra")
    inicio = time.monotonic()
    # A parada normal do Cassandra esvazia as memtables no disco (drain);
    # o prazo longo evita que o Docker o encerre à força no meio.
    compose("stop", "-t", "300", *BANCOS)
    parada = time.monotonic() - inicio
    logs = subprocess.run(["docker", "logs", "--tail", "200", cassandra], capture_output=True, text=True)
    # O gancho de parada do Cassandra 5 grava as memtables ("Reason: DRAIN")
    # e termina com esta linha.
    drenado = "Cassandra shutdown complete" in logs.stdout + logs.stderr
    print(f"  bancos parados em {parada:.0f} s; Cassandra drenado: {'sim' if drenado else 'NÃO'}")
    # A cópia anterior só é apagada depois que a nova estiver selada.
    geracao = datetime.now().strftime("%Y%m%d-%H%M%S")
    novas = {banco: f"linkpulse-benchmark-copia-{geracao}-{banco}" for banco in BANCOS}
    selo = f"linkpulse-benchmark-copia-{geracao}-{SELO}"
    try:
        for banco, volume in novas.items():
            criar_volume(volume, geracao, banco)
        copia_s = copiar_volumes(VOLUMES, novas)
        criar_volume(selo, geracao, SELO)
        subprocess.run(
            ["docker", "run", "--rm", "-i", "-v", f"{selo}:/selo", "--entrypoint", "sh", IMAGEM_AUXILIAR,
             "-c", "cat > /selo/base-de-referencia.json"],
            input=manifesto, text=True, encoding="utf-8", check=True,
        )
    except BaseException:
        print("  a cópia falhou; a geração incompleta foi apagada e a cópia anterior continua valendo",
              file=sys.stderr)
        remover_volumes([*novas.values(), selo])
        subir()
        raise
    subida_s = subir()
    antigas = [v for g, volumes in geracoes().items() if g != geracao for v in volumes.values()]
    removidos = remover_volumes(antigas + COPIAS_ANTIGAS)
    print(f"  geração {geracao} selada; cópia em {copia_s:.0f} s; bancos de volta em {subida_s:.0f} s; "
          f"{removidos} volume(s) de cópias anteriores apagados")
    return {"geracao": geracao, "parada_s": round(parada, 1), "cassandra_drenado": drenado,
            "copia_s": round(copia_s, 1), "subida_s": round(subida_s, 1)}


def cmd_restaurar(conferir: bool) -> dict:
    exigir_volumes_de_benchmark()
    valida = copia_valida()
    if valida is None:
        sys.exit("nenhuma cópia selada; rode antes: python benchmark/base.py carregar")
    geracao, volumes = valida
    manifesto_copia = ler_selo(volumes[SELO])
    print(f"Restauração da base (cópia {geracao})")
    inicio = time.monotonic()
    # O estado atual é descartado, então os bancos não precisam de parada normal.
    compose("kill", *BANCOS)
    parada = time.monotonic() - inicio
    copia = copiar_volumes({b: volumes[b] for b in BANCOS}, VOLUMES)
    # Os volumes e o manifesto voltam juntos: a janela do histórico e o link
    # popular passam a ser os da base copiada.
    atual = json.loads(MANIFESTO.read_text(encoding="utf-8")) if MANIFESTO.exists() else None
    reposto = atual != manifesto_copia
    if reposto:
        MANIFESTO.write_text(json.dumps(manifesto_copia, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"  manifesto reposto pelo da cópia (semente {manifesto_copia['semente']}, "
              f"fim {manifesto_copia['fim']}); o anterior descrevia outra base")
    subida = subir()
    total = time.monotonic() - inicio
    print(f"  pronto para uso em {total:.0f} s (parada {parada:.0f} s, cópia {copia:.0f} s, subida {subida:.0f} s)")
    dados = {"geracao": geracao, "manifesto_reposto": reposto, "parada_s": round(parada, 1),
             "copia_s": round(copia, 1), "subida_s": round(subida, 1), "pronto_s": round(total, 1)}
    if conferir:
        dados["conferencia_s"] = round(cmd_conferir(completo=False), 1)
    return dados


def cmd_carregar(semente: int, fim: str, processos: int) -> dict:
    manifesto = cmd_manifesto(semente, fim, processos)
    print("Recriando os volumes de benchmark vazios: " + ", ".join(VOLUMES.values()))
    compose("rm", "--stop", "--force", *BANCOS, "cassandra-esquema")
    for volume in VOLUMES.values():
        if volume_existe(volume):
            rodar(["docker", "volume", "rm", volume], capturar=True)
    subida = subir()
    print(f"  bancos no ar em {subida:.0f} s")

    inicio = time.monotonic()
    with MonitorMemoria() as monitor:
        try:
            compose("run", "--rm", "carga", "python", "benchmark/carregar.py", "--processos", str(processos))
        finally:
            carga = time.monotonic() - inicio
            memoria = monitor.relatorio()
    print(f"  carga em {carga:.0f} s")
    for servico in COMPARADOS:
        m = memoria[servico]
        print(f"  memória {servico}: pico {m['pico_docker_stats_mib']} MiB de {m['teto_mib']} MiB "
              f"(docker stats); cgroup {m['pico_cgroup_mib']} MiB; "
              f"falta de memória: {'SIM' if m['encerrado_por_falta_de_memoria'] else 'não'}")
    dados = {"manifesto": manifesto, "subida_s": round(subida, 1), "carga_s": round(carga, 1), "memoria": memoria}
    dados["conferencia_completa_s"] = round(cmd_conferir(completo=True), 1)
    dados["copia"] = cmd_copiar()
    return dados


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="comando", required=True)
    for nome in ("carregar", "manifesto"):
        p = sub.add_parser(nome)
        p.add_argument("--semente", type=int, default=SEMENTE_PADRAO)
        p.add_argument("--fim", default=FIM_PADRAO, help="instante final dos cliques, ISO 8601 com fuso")
        p.add_argument("--processos", type=int, default=4)
    sub.add_parser("copiar")
    p = sub.add_parser("restaurar")
    p.add_argument("--sem-conferir", action="store_true")
    p = sub.add_parser("conferir")
    p.add_argument("--completo", action="store_true")
    args = parser.parse_args()
    try:
        executar(args)
    except subprocess.CalledProcessError as erro:
        print(f"\nFalhou ({erro.returncode}): {' '.join(erro.cmd)}", file=sys.stderr)
        return 1
    return 0


def executar(args: argparse.Namespace) -> None:
    if args.comando == "manifesto":
        cmd_manifesto(args.semente, args.fim, args.processos)
    elif args.comando == "carregar":
        registrar("carregar", cmd_carregar(args.semente, args.fim, args.processos))
    elif args.comando == "copiar":
        registrar("copiar", cmd_copiar())
    elif args.comando == "restaurar":
        registrar("restaurar", cmd_restaurar(conferir=not args.sem_conferir))
    else:
        cmd_conferir(args.completo)


if __name__ == "__main__":
    sys.exit(main())
