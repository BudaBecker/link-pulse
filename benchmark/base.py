"""Base de referência do benchmark: carregar, copiar, restaurar e conferir.

O benchmark do LinkPulse mede as mesmas operações no lado NoSQL (Redis e
Cassandra) e no PostgreSQL, e a comparação só vale se os dois lados tiverem os
mesmos dados. Este script prepara esses dados, a base de referência, e guarda
uma cópia dos volumes dos bancos para voltar a ela antes de cada repetição das
medições.

Roda no próprio computador, fora dos contêineres, com Python 3.11 ou mais novo
e o Docker, e só usa a biblioteca padrão. Os bancos sobem com
docker-compose.yml mais docker-compose.benchmark.yml, que troca os volumes de
desenvolvimento por volumes próprios do benchmark (linkpulse-benchmark-*). O
trabalho dentro dos bancos fica com carregar.py e conferir.py, que rodam no
contêiner `carga`.

    python benchmark/base.py carregar     # recria os volumes de benchmark, carrega, confere e copia
    python benchmark/base.py restaurar    # volta os bancos à cópia guardada e confere o CA-1
    python benchmark/base.py conferir [--completo]
    python benchmark/base.py copiar       # guarda de novo a cópia do estado atual
    python benchmark/base.py manifesto    # só reescreve o espelho benchmark/base-de-referencia.json

Um comando por vez: todos, menos `manifesto`, pegam a trava, que é o contêiner
linkpulse-benchmark-trava no Docker. Detalhes em benchmark/README.md.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from referencia import FIM_PADRAO, SEMENTE_PADRAO, Base, assinatura_gerada, descrever, manifesto_valido

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
# Manifesto da base que está nos volumes de benchmark. Só a carga e a
# restauração o gravam; a carga e a conferência o leem dali. O arquivo
# benchmark/base-de-referencia.json é um espelho para leitura e para o Git.
VOLUME_MANIFESTO = "linkpulse-benchmark-manifesto"
ARQUIVO_MANIFESTO = "base-de-referencia.json"
# A trava é um contêiner com nome fixo: o Docker não aceita dois com o mesmo
# nome, e os volumes e o projeto Compose também têm nome fixo, iguais para
# qualquer cópia do repositório que use o mesmo Docker.
NOME_TRAVA = "linkpulse-benchmark-trava"
ROTULO_TRAVA = "linkpulse.benchmark.trava"
# Todo contêiner que um comando cria para mexer na base leva este rótulo. Eles
# rodam no Docker e podem sobreviver ao comando; quem pega a trava espera por eles.
ROTULO_AUXILIAR = "linkpulse.benchmark.auxiliar"
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


class Trava:
    """Um comando por vez sobre a base de benchmark, em qualquer cópia do repositório.

    Copiar e restaurar deixam os bancos parados enquanto trocam os volumes; outro
    comando no meio poderia religá-los. A trava é o contêiner NOME_TRAVA, que lê
    a entrada padrão deste processo: quando o comando termina ou morre, essa
    entrada fecha, o contêiner sai e o `--rm` o apaga.
    """

    def __init__(self, comando: str) -> None:
        self.dono = f"{comando}, pid {os.getpid()}, pasta {RAIZ}, desde {datetime.now():%H:%M:%S}"

    def __enter__(self) -> "Trava":
        self.processo = subprocess.Popen(
            ["docker", "run", "--rm", "-i", "--name", NOME_TRAVA, "--label", f"{ROTULO_TRAVA}={self.dono}",
             "--network", "none", "--entrypoint", "sh", IMAGEM_AUXILIAR,
             "-c", "echo travado; exec cat > /dev/null"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        if self.processo.stdout.readline().strip() == b"travado":
            esperar_auxiliares()
            return self
        erro = self.processo.communicate()[1].decode("utf-8", "replace").strip()
        dono = subprocess.run(
            ["docker", "inspect", "-f", f'{{{{index .Config.Labels "{ROTULO_TRAVA}"}}}}', NOME_TRAVA],
            capture_output=True, text=True, encoding="utf-8",
        ).stdout.strip()
        if dono or "already in use" in erro:
            sys.exit(f"outro comando da base está rodando ({dono or 'sem detalhes'}); espere ele terminar")
        sys.exit(f"não foi possível pegar a trava {NOME_TRAVA}: {erro}")

    def __exit__(self, *_) -> None:
        self.processo.stdin.close()
        try:
            self.processo.wait(timeout=30)
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "rm", "-f", NOME_TRAVA], capture_output=True)


def esperar_auxiliares() -> None:
    """Espera terminarem os contêineres de um comando anterior interrompido.

    Uma cópia de volumes ou uma carga continua no Docker mesmo se o comando que
    a iniciou morrer. Com a trava já tomada, nenhum auxiliar novo aparece aqui.
    """
    avisado = False
    while True:
        ids = rodar(["docker", "ps", "-q", "--filter", f"label={ROTULO_AUXILIAR}"], capturar=True).split()
        if not ids:
            return
        if not avisado:
            nomes = rodar(["docker", "ps", "--filter", f"label={ROTULO_AUXILIAR}", "--format", "{{.Names}}"],
                          capturar=True).split()
            print(f"Esperando terminar {len(ids)} contêiner(es) de um comando anterior: {', '.join(nomes)}",
                  file=sys.stderr)
            avisado = True
        # Um contêiner com --rm pode sumir antes do wait; o laço confere de novo.
        subprocess.run(["docker", "wait", *ids], capture_output=True)


def auxiliar(papel: str) -> list[str]:
    """Início de um `docker run` auxiliar, rotulado para a trava esperar por ele."""
    return ["docker", "run", "--rm", "--label", f"{ROTULO_AUXILIAR}={papel}"]


def ler_do_volume(volume: str) -> str | None:
    resultado = subprocess.run(
        [*auxiliar("ler-manifesto"), "-v", f"{volume}:/v:ro", "--entrypoint", "cat", IMAGEM_AUXILIAR,
         f"/v/{ARQUIVO_MANIFESTO}"],
        capture_output=True, text=True, encoding="utf-8",
    )
    return resultado.stdout if resultado.returncode == 0 else None


def gravar_no_volume(volume: str, texto: str) -> None:
    # Grava num temporário e renomeia: o arquivo aparece inteiro ou não aparece.
    temporario = f"/v/.{ARQUIVO_MANIFESTO}.tmp"
    subprocess.run(
        [*auxiliar("gravar-manifesto"), "-i", "-v", f"{volume}:/v", "--entrypoint", "sh", IMAGEM_AUXILIAR,
         "-c", f"cat > {temporario} && mv {temporario} /v/{ARQUIVO_MANIFESTO}"],
        input=texto, text=True, encoding="utf-8", check=True,
    )


def interpretar_manifesto(texto: str | None) -> dict | None:
    try:
        dados = json.loads(texto or "")
    except ValueError:
        return None
    return dados if manifesto_valido(dados) else None


def manifesto_da_base() -> str:
    """Texto do manifesto vinculado aos volumes de benchmark."""
    texto = ler_do_volume(VOLUME_MANIFESTO) if volume_existe(VOLUME_MANIFESTO) else None
    if interpretar_manifesto(texto) is None:
        sys.exit(f"a base de benchmark não tem manifesto válido em {VOLUME_MANIFESTO}; "
                 "rode carregar, ou restaurar para repor a cópia")
    return texto


def gravar_manifesto_da_base(texto: str) -> None:
    if not volume_existe(VOLUME_MANIFESTO):
        rodar(["docker", "volume", "create", "--label", "linkpulse.benchmark=manifesto", VOLUME_MANIFESTO],
              capturar=True)
    gravar_no_volume(VOLUME_MANIFESTO, texto)


def espelho_difere(texto: str) -> bool:
    # Compara só o texto: um espelho corrompido não pode interromper a restauração.
    try:
        return MANIFESTO.read_text(encoding="utf-8", errors="replace") != texto
    except OSError:
        return True


def espelhar_manifesto(texto: str) -> bool:
    if not espelho_difere(texto):
        return False
    MANIFESTO.write_text(texto, encoding="utf-8")
    return True


def exigir_bancos_no_ar() -> None:
    parados = [b for b in BANCOS if not compose("ps", "-q", b, capturar=True).strip()]
    if parados:
        sys.exit(f"bancos parados ({', '.join(parados)}); a conferência não liga bancos. "
                 "Suba-os com python benchmark/base.py restaurar")


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


def copia_valida() -> tuple[str, dict[str, str], str] | None:
    """A geração mais recente com os quatro bancos e um selo íntegro.

    Devolve a geração, os volumes e o texto do manifesto guardado no selo. Um
    selo ausente, vazio ou inválido faz a escolha passar para a geração anterior.
    """
    for geracao, volumes in sorted(geracoes().items(), reverse=True):
        if not all(banco in volumes for banco in BANCOS) or SELO not in volumes:
            continue
        texto = ler_do_volume(volumes[SELO])
        if interpretar_manifesto(texto) is None:
            print(f"  aviso: a cópia {geracao} tem selo incompleto e foi ignorada", file=sys.stderr)
            continue
        return geracao, volumes, texto
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


def subir() -> float:
    inicio = time.monotonic()
    compose("up", "-d", "--wait")
    return time.monotonic() - inicio


def copiar_volumes(origem: dict[str, str], destino: dict[str, str]) -> float:
    """Copia, em paralelo e com os bancos parados, cada volume de origem no de destino."""
    # Para cada banco, em segundo plano: esvazia o destino e copia a origem
    # mantendo dono, permissões e datas (cp -a). Sai com erro se alguma cópia
    # falhar; o du mostra no fim o tamanho de cada destino.
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
    rodar([*auxiliar("copiar-volumes"), *montagens, "--entrypoint", "sh", IMAGEM_AUXILIAR, "-c", script])
    return time.monotonic() - inicio


# Unidades em que o docker stats mostra a memória.
_UNIDADES = {"B": 1, "KiB": 2**10, "MiB": 2**20, "GiB": 2**30, "kB": 10**3, "MB": 10**6, "GB": 10**9}


def _bytes(texto: str) -> float:
    numero, unidade = re.fullmatch(r"([\d.]+)\s*([A-Za-z]+)", texto.strip()).groups()
    return float(numero) * _UNIDADES[unidade]


class MonitorMemoria:
    """Mede o pico de memória dos bancos comparados enquanto a carga roda.

    Amostra o `docker stats` numa thread à parte. O relatório junta o pico
    registrado pelo cgroup (o controle de recursos do Linux que aplica o teto do
    contêiner) e diz se o Docker encerrou o contêiner por falta de memória.
    """

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
    MANIFESTO.write_text(texto_do_manifesto(manifesto), encoding="utf-8")
    print(f"Manifesto em {MANIFESTO.relative_to(RAIZ)} ({time.monotonic() - inicio:.0f} s): "
          f"semente {manifesto['semente']}, fim {manifesto['fim']}, "
          f"link popular {manifesto['link_popular']['short_code']}, "
          f"assinatura {manifesto['assinatura_cliques']}")
    return manifesto


def texto_do_manifesto(manifesto: dict) -> str:
    return json.dumps(manifesto, indent=2, ensure_ascii=False) + "\n"


def cmd_conferir(completo: bool) -> float:
    exigir_volumes_de_benchmark()
    exigir_bancos_no_ar()
    if espelho_difere(manifesto_da_base()):
        print(f"Aviso: {MANIFESTO.relative_to(RAIZ)} difere do manifesto da base ({VOLUME_MANIFESTO}); "
              "a conferência usa o da base.", file=sys.stderr)
    inicio = time.monotonic()
    # --no-deps: a conferência nunca liga bancos, nem no meio de outra operação.
    argumentos = ["run", "--rm", "--no-deps", "--label", f"{ROTULO_AUXILIAR}=conferir", "carga",
                  "python", "benchmark/conferir.py"]
    compose(*argumentos, *(["--completo"] if completo else []))
    return time.monotonic() - inicio


def cmd_copiar() -> dict:
    exigir_volumes_de_benchmark()
    # O selo leva o manifesto vinculado aos volumes, não o espelho local.
    manifesto = manifesto_da_base()
    print("Cópia da base: gravando o RDB do Redis e parando os bancos")
    for servico in ("redis-master", "redis-replica"):
        rodar(["docker", "exec", conteiner(servico), "redis-cli", "SAVE"])
    cassandra = conteiner("cassandra")
    inicio = time.monotonic()
    # Na parada normal, o Cassandra grava no disco os dados que ainda estavam só
    # na memória (as memtables), o que ele chama de drain. O prazo longo evita
    # que o Docker o encerre à força no meio.
    compose("stop", "-t", "300", *BANCOS)
    parada = time.monotonic() - inicio
    logs = subprocess.run(["docker", "logs", "--tail", "200", cassandra], capture_output=True, text=True)
    # Esse drain aparece no log como "Reason: DRAIN", e a parada termina com
    # esta linha.
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
        gravar_no_volume(selo, manifesto)
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
        sys.exit("nenhuma cópia selada e íntegra; rode antes: python benchmark/base.py carregar")
    geracao, volumes, manifesto = valida
    print(f"Restauração da base (cópia {geracao})")
    inicio = time.monotonic()
    # O estado atual é descartado, então os bancos não precisam de parada normal.
    compose("kill", *BANCOS)
    parada = time.monotonic() - inicio
    try:
        copia = copiar_volumes({b: volumes[b] for b in BANCOS}, VOLUMES)
    except subprocess.CalledProcessError:
        print("  a reposição dos volumes falhou; os bancos ficam parados para não subir com dados pela "
              "metade. Rode restaurar de novo.", file=sys.stderr)
        raise
    # Volumes e manifesto voltam juntos: a janela do histórico e o link popular
    # passam a ser os da base copiada. Sem o manifesto oficial gravado, os bancos
    # não sobem, para não voltarem com dados e manifesto divergentes.
    try:
        gravar_manifesto_da_base(manifesto)
    except (subprocess.CalledProcessError, OSError):
        print("  a gravação do manifesto da base falhou; os bancos ficam parados para não subir com "
              "dados e manifesto divergentes. Rode restaurar de novo.", file=sys.stderr)
        raise
    # Uma falha só no espelho local não impede a subida.
    try:
        reposto = espelhar_manifesto(manifesto)
        if reposto:
            print(f"  espelho {MANIFESTO.relative_to(RAIZ)} reposto pelo manifesto da cópia")
    except OSError as erro:
        reposto = False
        print(f"  aviso: o espelho {MANIFESTO.relative_to(RAIZ)} não foi atualizado ({erro})", file=sys.stderr)
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
    print("Recriando os volumes de benchmark vazios: " + ", ".join([*VOLUMES.values(), VOLUME_MANIFESTO]))
    compose("rm", "--stop", "--force", *BANCOS, "cassandra-esquema")
    remover_volumes([*VOLUMES.values(), VOLUME_MANIFESTO])
    # O manifesto fica vinculado aos volumes desde a carga. Vai para o volume o
    # texto gerado aqui, e não o espelho, que outro comando pode ter reescrito.
    texto = texto_do_manifesto(manifesto)
    gravar_manifesto_da_base(texto)
    subida = subir()
    print(f"  bancos no ar em {subida:.0f} s")

    inicio = time.monotonic()
    with MonitorMemoria() as monitor:
        try:
            compose("run", "--rm", "--no-deps", "--label", f"{ROTULO_AUXILIAR}=carregar", "carga",
                    "python", "benchmark/carregar.py", "--processos", str(processos))
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
    if espelhar_manifesto(texto):
        print(f"  espelho {MANIFESTO.relative_to(RAIZ)} reposto pelo manifesto da carga")
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
        if args.comando == "manifesto":
            executar(args)
        else:
            with Trava(args.comando):
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
