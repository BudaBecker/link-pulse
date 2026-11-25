"""Cenário de queda do Cassandra, em laço aberto pela aplicação (SPEC-005, passo 5).

Envia 200 redirecionamentos por segundo à API, todos no link popular, numa
agenda fixa: um envio atrasado nunca é descartado, e a latência do gerador conta
do instante agendado (Q-64, Q-67). Aos 30 s para o contêiner do Cassandra e aos
60 s o religa, pela API do Docker (Q-65). A cada 0,25 s lê as falhas de gravação
em `GET /metricas` e o contador no Redis e, em outra thread, sonda a porta CQL do
Cassandra. Depois da carga, espera 10 s e conta
os cliques do link no Cassandra desde o início da etapa.

Não é chamado à mão: `python benchmark/medir.py --operacoes queda` sobe a API e
roda este script no contêiner `gerador-queda`. O resultado sai numa linha
`RESULTADO {json}`. Detalhes em benchmark/README.md.
"""

from __future__ import annotations

import argparse
import http.client
import json
import math
import queue
import socket
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import redis
from cassandra.cluster import Cluster

from carregar import MANIFESTO
from gerador import cpu_usada_s, cpus_do_limite, memoria_pico_mib, percentil
from referencia import manifesto_valido

DURACAO = 90.0  # s (ADR-0014)
PARADA = 30.0
RELIGAMENTO = 60.0
TAXA = 200  # redirecionamentos por segundo
WORKERS = 32
PRAZO_PARADA = 10  # s, o mesmo do docker compose stop
ATRASO_TOLERADO = 0.005  # s; um envio que sai depois disso conta como atrasado
INTERVALO_LEITURA = 0.25  # s, entre as leituras das falhas e do contador, e entre as sondagens da porta
ESPERA_FINAL = 10.0  # s depois da carga, cinco vezes o tempo limite da gravação (Q-41, Q-67)
PRAZO_VOLTA = 60.0  # s sem carga esperando o Cassandra, se ele não voltou na etapa (Q-66)
TETO_P95_MS = 50.0  # RNF-02
FASES = {"antes": (0.0, PARADA), "parado": (PARADA, RELIGAMENTO), "volta": (RELIGAMENTO, DURACAO)}


class _ConexaoUnix(http.client.HTTPConnection):
    def __init__(self, caminho: str, timeout: float):
        super().__init__("docker", timeout=timeout)
        self.caminho = caminho

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.caminho)


class Docker:
    """A API do Docker pelo socket montado no contêiner, sem o cliente do Docker na imagem."""

    def __init__(self, caminho: str = "/var/run/docker.sock"):
        self.caminho = caminho

    def pedir(self, metodo: str, rota: str, timeout: float = 30) -> dict | None:
        conexao = _ConexaoUnix(self.caminho, timeout)
        try:
            conexao.request(metodo, rota)
            resposta = conexao.getresponse()
            corpo = resposta.read()
        finally:
            conexao.close()
        if resposta.status >= 400:
            raise RuntimeError(f"Docker {metodo} {rota}: {resposta.status} {corpo[:200]!r}")
        return json.loads(corpo) if corpo else None

    def parar(self, conteiner: str) -> None:
        self.pedir("POST", f"/containers/{conteiner}/stop?t={PRAZO_PARADA}", timeout=PRAZO_PARADA + 30)

    def religar(self, conteiner: str) -> None:
        self.pedir("POST", f"/containers/{conteiner}/start")

    def saude(self, conteiner: str) -> str | None:
        return self.pedir("GET", f"/containers/{conteiner}/json")["State"].get("Health", {}).get("Status")


def tempo_do_servidor(cabecalho: str | None) -> float:
    """Milissegundos do `Server-Timing: app;dur=…` posto pelo benchmark/api_cronometrada.py."""
    for parte in (cabecalho or "").split(";"):
        if parte.strip().startswith("dur="):
            return float(parte.strip()[4:])
    return math.nan


class Disparo:
    """A agenda fixa: o envio i sai no instante i / TAXA, entregue ao primeiro worker livre."""

    def __init__(self, api: str, codigo: str, envios: int):
        partes = urlsplit(api)
        self.endereco = (partes.hostname, partes.port or 80)
        self.rota = f"/r/{codigo}"
        self.agendado = [i / TAXA for i in range(envios)]
        self.saida = [math.nan] * envios
        self.total = [math.nan] * envios
        self.servidor = [math.nan] * envios
        self.status = [0] * envios  # 0: sem resposta
        self.exemplos_de_erro: list[str] = []
        self.fila: queue.SimpleQueue = queue.SimpleQueue()

    def worker(self, partida: float) -> None:
        conexao = None
        while (i := self.fila.get()) is not None:
            self.saida[i] = time.perf_counter() - partida
            try:
                if conexao is None:
                    conexao = http.client.HTTPConnection(*self.endereco, timeout=10)
                conexao.request("GET", self.rota)
                resposta = conexao.getresponse()
                resposta.read()
                self.status[i] = resposta.status
                self.servidor[i] = tempo_do_servidor(resposta.getheader("server-timing"))
            except (OSError, http.client.HTTPException) as erro:
                if conexao is not None:
                    conexao.close()
                conexao = None
                if len(self.exemplos_de_erro) < 3:
                    self.exemplos_de_erro.append(f"{type(erro).__name__}: {erro}"[:200])
            self.total[i] = time.perf_counter() - partida - self.agendado[i]

    def rodar(self, partida: float) -> None:
        workers = [threading.Thread(target=self.worker, args=(partida,)) for _ in range(WORKERS)]
        for w in workers:
            w.start()
        for i, instante in enumerate(self.agendado):
            espera = partida + instante - time.perf_counter()
            if espera > 0:
                time.sleep(espera)
            self.fila.put(i)
        for _ in workers:
            self.fila.put(None)
        for w in workers:
            w.join()


class Leituras:
    """A cada 0,25 s: falhas de gravação na API e contador do link no Redis."""

    def __init__(self, api: str, codigo: str):
        partes = urlsplit(api)
        self.endereco = (partes.hostname, partes.port or 80)
        self.redis = redis.Redis(host="redis-master")
        self.chave = f"contador:{codigo}"
        self.amostras: list[dict] = []  # {t, falhas, contador}
        self.parar = threading.Event()
        self.conexao = None

    def falhas(self) -> int | None:
        try:
            if self.conexao is None:
                self.conexao = http.client.HTTPConnection(*self.endereco, timeout=2)
            self.conexao.request("GET", "/metricas")
            resposta = self.conexao.getresponse()
            return json.loads(resposta.read())["falhas_gravacao_clique"]
        except (OSError, http.client.HTTPException, ValueError, KeyError):
            if self.conexao is not None:
                self.conexao.close()
            self.conexao = None
            return None

    def contador(self) -> int | None:
        try:
            valor = self.redis.get(self.chave)
            return int(valor) if valor is not None else 0
        except redis.RedisError:
            return None

    def ler(self, partida: float) -> dict:
        amostra = {"t": round(time.perf_counter() - partida, 3), "falhas": self.falhas(), "contador": self.contador()}
        self.amostras.append(amostra)
        return amostra

    def rodar(self, partida: float) -> None:
        proxima = time.perf_counter()
        while not self.parar.is_set():
            self.ler(partida)
            proxima += INTERVALO_LEITURA
            self.parar.wait(max(0.0, proxima - time.perf_counter()))


def porta_aberta() -> bool:
    try:
        socket.create_connection(("cassandra", 9042), timeout=0.2).close()
        return True
    except OSError:
        return False


def sondar_porta(partida: float, sondagens: list[tuple[float, bool]], parar: threading.Event) -> None:
    """Fica em thread própria: com o contêiner parado, resolver o nome `cassandra` leva alguns segundos."""
    while not parar.is_set():
        aberta = porta_aberta()
        sondagens.append((round(time.perf_counter() - partida, 3), aberta))
        parar.wait(INTERVALO_LEITURA)


def controlar(docker: Docker | None, conteiner: str, partida: float, marcos: dict) -> None:
    """Para o Cassandra aos 30 s e o religa aos 60 s, sem esperar o healthcheck (Q-65)."""
    def no_instante(t: float) -> None:
        time.sleep(max(0.0, partida + t - time.perf_counter()))

    agora = lambda: round(time.perf_counter() - partida, 3)  # noqa: E731
    no_instante(PARADA)
    marcos["parada_pedida_s"] = agora()
    if docker is None:
        print(f"[{agora():5.1f} s] PARE o Cassandra agora: python benchmark/queda_manual.py parar", flush=True)
    else:
        print(f"[{agora():5.1f} s] parando o Cassandra", flush=True)
        docker.parar(conteiner)
        marcos["parada_concluida_s"] = agora()
        print(f"[{agora():5.1f} s] Cassandra parado", flush=True)
    no_instante(RELIGAMENTO)
    marcos["religamento_pedido_s"] = agora()
    if docker is None:
        print(f"[{agora():5.1f} s] RELIGUE o Cassandra agora: python benchmark/queda_manual.py religar", flush=True)
        return
    docker.religar(conteiner)
    print(f"[{agora():5.1f} s] religamento disparado", flush=True)
    while time.perf_counter() < partida + DURACAO + PRAZO_VOLTA:
        if docker.saude(conteiner) == "healthy":
            marcos["saudavel_s"] = agora()
            print(f"[{agora():5.1f} s] Cassandra saudável pelo healthcheck", flush=True)
            return
        time.sleep(0.5)


def ultima_falha(amostras: list[dict]) -> float | None:
    """Última leitura, durante a carga, em que as falhas aumentaram.

    Não prova a volta: uma leitura ausente esconderia falhas. A prova é o primeiro clique gravado no Cassandra.
    """
    durante = [a for a in amostras if a["t"] <= DURACAO and a["falhas"] is not None]
    ultima = None
    for anterior, atual in zip(durante, durante[1:]):
        if atual["falhas"] > anterior["falhas"]:
            ultima = atual["t"]
    return ultima


def leitura_em(amostras: list[dict], t: float, campo: str) -> int | None:
    """Valor da última leitura válida até o instante t."""
    valor = None
    for a in amostras:
        if a["t"] > t:
            break
        if a[campo] is not None:
            valor = a[campo]
    return valor


def transicoes_da_porta(sondagens: list[tuple[float, bool]]) -> tuple[float | None, float | None]:
    """Primeira sondagem com a porta CQL fechada depois dos 30 s e a primeira aberta depois dela."""
    fechada = next((t for t, aberta in sondagens if t >= PARADA and not aberta), None)
    if fechada is None:
        return None, None
    return fechada, next((t for t, aberta in sondagens if t > fechada and aberta), None)


def metricas(d: Disparo, inicio: float, fim: float) -> dict:
    indices = [i for i, t in enumerate(d.agendado) if inicio <= t < fim]
    respondidos = [i for i in indices if d.status[i]]
    servidor = sorted(d.servidor[i] for i in respondidos if not math.isnan(d.servidor[i]))
    gerador = sorted(d.total[i] for i in respondidos)
    atrasos = [d.saida[i] - d.agendado[i] for i in indices]
    ms = lambda s: None if s is None else round(s * 1000, 3)  # noqa: E731
    arred = lambda v: None if v is None else round(v, 3)  # noqa: E731
    return {
        "janela_s": [inicio, fim],
        "envios": len(indices),
        "respostas_302": sum(1 for i in indices if d.status[i] == 302),
        "outras_respostas": sum(1 for i in respondidos if d.status[i] != 302),
        "sem_resposta": len(indices) - len(respondidos),
        "p50_servidor_ms": arred(percentil(servidor, 50)),
        "p95_servidor_ms": arred(percentil(servidor, 95)),
        "p99_servidor_ms": arred(percentil(servidor, 99)),
        "p50_gerador_ms": ms(percentil(gerador, 50)),
        "p95_gerador_ms": ms(percentil(gerador, 95)),
        "p99_gerador_ms": ms(percentil(gerador, 99)),
        "envios_atrasados": sum(1 for a in atrasos if a > ATRASO_TOLERADO),
        "atraso_maximo_ms": ms(max(atrasos, default=None)),
    }


def serie(d: Disparo, amostras: list[dict]) -> list[dict]:
    linhas = []
    for s in range(int(DURACAO)):
        m = metricas(d, float(s), float(s + 1))
        linhas.append({"s": s, "envios": m["envios"], "respostas_302": m["respostas_302"],
                       "p95_servidor_ms": m["p95_servidor_ms"], "p95_gerador_ms": m["p95_gerador_ms"],
                       "falhas": leitura_em(amostras, s + 1, "falhas"),
                       "contador": leitura_em(amostras, s + 1, "contador")})
    return linhas


def cliques_no_historico(codigo: str, desde: datetime, parada: datetime | None) -> tuple[int, datetime | None]:
    """Cliques do link desde o início da etapa e o primeiro gravado depois da parada."""
    cluster = Cluster(["cassandra"], protocol_version=5, schema_metadata_enabled=False, token_metadata_enabled=False)
    try:
        sessao = cluster.connect("linkpulse")
        total = sessao.execute(
            "SELECT COUNT(*) FROM cliques_por_link WHERE short_code = %s AND clicado_em >= %s",
            (codigo, desde), timeout=30).one()[0]
        primeiro = None
        if parada is not None:
            linha = sessao.execute(
                "SELECT clicado_em FROM cliques_por_link WHERE short_code = %s AND clicado_em > %s "
                "ORDER BY clicado_em ASC LIMIT 1", (codigo, parada), timeout=30).one()
            primeiro = linha[0].replace(tzinfo=UTC) if linha else None
        return total, primeiro
    finally:
        cluster.shutdown()


def esperar_cassandra(docker: Docker | None, conteiner: str, marcos: dict, partida: float) -> bool:
    """Depois da carga, espera o Cassandra por até PRAZO_VOLTA, sem carga, para a conferência (Q-66).

    Na parada manual não há healthcheck consultado: vale a porta CQL, já registrada pela sondagem.
    """
    limite = time.perf_counter() + PRAZO_VOLTA
    while time.perf_counter() < limite:
        pronto = docker.saude(conteiner) == "healthy" if docker else porta_aberta()
        if pronto:
            if docker:
                marcos.setdefault("saudavel_s", round(time.perf_counter() - partida, 3))
            return True
        time.sleep(0.5)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api", required=True, help="endereço da API, como http://host.docker.internal:8001")
    parser.add_argument("--cassandra", required=True, help="identificador do contêiner do Cassandra")
    parser.add_argument("--queda-manual", action="store_true",
                        help="não mexe no Docker; avisa a hora de rodar benchmark/queda_manual.py")
    args = parser.parse_args()

    manifesto = json.loads(MANIFESTO.read_text(encoding="utf-8"))
    if not manifesto_valido(manifesto):
        print(f"Manifesto inválido em {MANIFESTO}; nada foi medido.")
        return 1
    codigo = manifesto["link_popular"]["short_code"]
    if datetime.fromisoformat(manifesto["fim"]) > datetime.now(UTC):
        print(f"A base vai até {manifesto['fim']}, depois de agora: a conferência contaria cliques da base "
              "como cliques da etapa. Use uma base com --fim no passado; nada foi medido.")
        return 1
    docker = None if args.queda_manual else Docker()
    if docker is not None and docker.saude(args.cassandra) != "healthy":
        print("O Cassandra não está saudável; nada foi medido.")
        return 1

    disparo = Disparo(args.api, codigo, int(DURACAO * TAXA))
    leituras = Leituras(args.api, codigo)
    antes = leituras.ler(time.perf_counter())
    if antes["falhas"] is None or antes["contador"] is None:
        print(f"A API em {args.api} ou o Redis não responderam; nada foi medido.")
        return 1
    leituras.amostras.clear()

    marcos: dict = {}
    limite_cpu = cpus_do_limite()
    print(f"queda: {TAXA} redirecionamentos por segundo em {codigo}, {DURACAO:.0f} s; o Cassandra para aos "
          f"{PARADA:.0f} s e volta aos {RELIGAMENTO:.0f} s{' (parada manual)' if docker is None else ''}", flush=True)
    partida = time.perf_counter() + 0.5
    inicio = datetime.now(UTC) + timedelta(seconds=0.5)
    sondagens: list[tuple[float, bool]] = []
    leitoras = [threading.Thread(target=leituras.rodar, args=(partida,), daemon=True),
                threading.Thread(target=sondar_porta, args=(partida, sondagens, leituras.parar), daemon=True)]
    for leitora in leitoras:
        leitora.start()
    controle = threading.Thread(target=controlar, args=(docker, args.cassandra, partida, marcos), daemon=True)
    controle.start()
    time.sleep(max(0.0, partida - time.perf_counter()))
    cpu_antes, relogio_antes = cpu_usada_s(), time.perf_counter()
    disparo.rodar(partida)
    cpu_depois, relogio_depois = cpu_usada_s(), time.perf_counter()
    fim_da_carga = round(relogio_depois - partida, 3)
    print(f"[{fim_da_carga:5.1f} s] fim da carga", flush=True)

    cassandra_no_ar = esperar_cassandra(docker, args.cassandra, marcos, partida)
    if not cassandra_no_ar:
        print(f"O Cassandra não voltou em {PRAZO_VOLTA:.0f} s depois da carga; o resultado sai sem a "
              "conferência do histórico", flush=True)
    time.sleep(ESPERA_FINAL)
    controle.join(timeout=PRAZO_VOLTA)
    leituras.parar.set()
    for leitora in leitoras:  # a leitura final não pode dividir a conexão com a thread de leitura
        leitora.join()
    depois = leituras.ler(partida)

    fechada, aberta = transicoes_da_porta(sondagens)
    ultima = ultima_falha(leituras.amostras)
    marcos |= {"porta_fechada_s": fechada, "porta_aberta_s": aberta, "ultima_falha_s": ultima}
    parada_concluida = marcos.get("parada_concluida_s", fechada)
    instante = lambda t: None if t is None else inicio + timedelta(seconds=t)  # noqa: E731
    historico, primeiro = None, None
    if cassandra_no_ar:
        historico, primeiro = cliques_no_historico(codigo, inicio - timedelta(seconds=0.5),
                                                   instante(parada_concluida))
    primeiro_s = None if primeiro is None else round((primeiro - inicio).total_seconds(), 3)
    marcos["primeiro_clique_gravado_apos_parada_s"] = primeiro_s
    # A volta é o primeiro clique gravado depois da parada, dentro da carga; sem ele, a janela vai até o fim.
    # A janela vai até a leitura que detectou o último aumento das falhas, se ela vier depois: com leituras a
    # cada 0,25 s, a falha pode ser anterior ou posterior ao clique (Q-68).
    volta = primeiro_s if primeiro_s is not None and primeiro_s < DURACAO else None
    marcos["gravacao_voltou_s"] = volta
    if volta is None:
        print("A gravação dos cliques não voltou na etapa", flush=True)

    fim_da_queda = DURACAO if volta is None else max(volta, ultima or volta)
    queda = metricas(disparo, PARADA, fim_da_queda)
    contador_na_queda = [leitura_em(leituras.amostras, t, "contador") for t in (PARADA, fim_da_queda)]
    falhas_na_queda = [leitura_em(leituras.amostras, t, "falhas") for t in (PARADA, fim_da_queda)]
    queda |= {
        "gravacao_voltou_na_etapa": volta is not None,
        "contador_somou": None if None in contador_na_queda else contador_na_queda[1] - contador_na_queda[0],
        "falhas_somaram": None if None in falhas_na_queda else falhas_na_queda[1] - falhas_na_queda[0],
    }
    queda["ca6"] = (queda["envios"] > 0 and queda["respostas_302"] == queda["envios"]
                    and queda["p95_servidor_ms"] is not None and queda["p95_servidor_ms"] < TETO_P95_MS
                    and (queda["contador_somou"] or 0) > 0 and (queda["falhas_somaram"] or 0) > 0)

    aumento = {campo: None if depois[campo] is None else depois[campo] - antes[campo]
               for campo in ("contador", "falhas")}
    diferenca = None if None in (aumento["contador"], historico) else aumento["contador"] - historico
    conferencia = {
        "contador": aumento["contador"],
        "historico": historico,  # None: o Cassandra não voltou a tempo da conferência
        "falhas": aumento["falhas"],
        "diferenca_contador_historico": diferenca,
        "diferenca_menos_falhas": None if None in (diferenca, aumento["falhas"]) else diferenca - aumento["falhas"],
    }
    nucleos = (cpu_depois - cpu_antes) / (relogio_depois - relogio_antes)
    resultado = {
        "operacao": "queda",
        "lado": "nosql",
        "inicio": inicio.isoformat(timespec="seconds"),
        "short_code": codigo,
        "taxa_por_s": TAXA,
        "workers": WORKERS,
        "duracao_s": DURACAO,
        "parada_manual": docker is None,
        "fim_da_carga_s": fim_da_carga,
        "marcos": marcos,
        "total": metricas(disparo, 0.0, DURACAO),
        "fases": {nome: metricas(disparo, *janela) for nome, janela in FASES.items()},
        "queda": queda,
        "conferencia": conferencia,
        "serie": serie(disparo, leituras.amostras),
        "exemplos_de_erro": disparo.exemplos_de_erro,
        "cpu_gerador_nucleos": round(nucleos, 2),
        "cpu_gerador_pct": round(100 * nucleos / limite_cpu, 1),
        "limite_cpu_gerador": limite_cpu,
        "memoria_pico_gerador_mib": memoria_pico_mib(),
    }
    print("RESULTADO " + json.dumps(resultado, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
