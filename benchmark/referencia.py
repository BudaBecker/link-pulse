"""Base de referência do benchmark: geração determinística dos dados.

O benchmark do LinkPulse compara o lado NoSQL (Redis e Cassandra) com o
PostgreSQL sobre os mesmos dados. Este módulo gera esses dados: a mesma
semente e o mesmo instante final produzem os mesmos clientes, links e cliques,
com os mesmos identificadores e horários, em qualquer dia e em qualquer
máquina. Os números seguem a spec dos testes de stress (docs/specs/SPEC-005) e
o modelo de dados do benchmark (docs/decisoes/ADR-0014).

É importado por base.py, no computador, para gerar e validar o manifesto da
base, e por carregar.py e conferir.py, no contêiner `carga`. Por isso só usa a
biblioteca padrão.

- 150 clientes com 300 links cada (45 mil links).
- 10 milhões de cliques nos 90 dias que terminam em `fim`.
- O primeiro link é o popular, com 20% dos cliques; o restante é dividido entre
  os outros links o mais igualmente possível (177 ou 178 cada).
- Dispositivo em proporção exata: 60% mobile, 30% desktop, 5% tablet, 5% outro.

Os cliques são gerados em blocos de até `BLOCO` cliques, cada um com o seu
próprio gerador de números aleatórios. Assim, qualquer bloco pode ser gerado
sozinho, em qualquer ordem e em qualquer processo, sem manter os 10 milhões em
memória.
"""

from __future__ import annotations

import hashlib
import math
import random
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Iterator, NamedTuple
from uuid import UUID

SEMENTE_PADRAO = 2026
FIM_PADRAO = "2026-11-01T00:00:00Z"

CLIENTES = 150
LINKS_POR_CLIENTE = 300
LINKS = CLIENTES * LINKS_POR_CLIENTE
CLIQUES = 10_000_000
PARCELA_POPULAR = 0.20
DIAS = 90
BLOCO = 10_000

# Proporção decidida na questão sobre as categorias de dispositivo (Q-37). Cada
# parcela dos 10 milhões de cliques dá um número inteiro, e o total sai exato.
DISPOSITIVOS = (("mobile", 0.60), ("desktop", 0.30), ("tablet", 0.05), ("outro", 0.05))

# Origem do clique; None é acesso direto, sem referrer.
REFERRERS = (
    (None, 0.35),
    ("https://www.google.com/", 0.25),
    ("https://www.instagram.com/", 0.20),
    ("https://www.facebook.com/", 0.10),
    ("https://t.co/", 0.05),
    ("https://www.linkedin.com/", 0.05),
)
CANAIS = ("instagram", "email", "anuncio", "whatsapp", "site")
BASE62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

EPOCA = datetime(1970, 1, 1, tzinfo=UTC)
# Intervalo aceito para o instante final de um manifesto.
FIM_MINIMO = datetime(2000, 1, 1, tzinfo=UTC)
FIM_MAXIMO = datetime(2100, 1, 1, tzinfo=UTC)
# O UUID versão 1 conta o tempo em intervalos de 100 ns desde 15/10/1582. Este
# é o número desses intervalos até 01/01/1970, o início do tempo Unix.
_DESLOCAMENTO_UUID1 = 0x01B21DD213814000


class Cliente(NamedTuple):
    cliente_id: str
    nome: str


class Link(NamedTuple):
    indice: int
    short_code: str
    cliente_id: str
    url: str
    canal: str
    criado_em_ms: int
    cliques: int
    primeiro_clique: int  # índice global do primeiro clique do link


class Bloco(NamedTuple):
    link: int
    short_code: str
    numero: int
    primeiro_clique: int
    quantidade: int


class Clique(NamedTuple):
    short_code: str
    clicado_em_ms: int
    clique_id: UUID
    pais: str | None
    dispositivo: str
    referrer: str | None



def ms_para_datetime(ms: int) -> datetime:
    return EPOCA + timedelta(milliseconds=ms)


def datetime_para_ms(momento: datetime) -> int:
    if momento.tzinfo is None:  # o cassandra-driver devolve datetime sem fuso, em UTC
        momento = momento.replace(tzinfo=UTC)
    return (momento - EPOCA) // timedelta(milliseconds=1)


def iso(ms: int) -> str:
    return ms_para_datetime(ms).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _ler_instante(texto: str) -> datetime:
    momento = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    if momento.tzinfo is None:
        raise ValueError(f"instante sem fuso: {texto}")
    return momento.astimezone(UTC)


def validar_fim(texto: str) -> str:
    """Confere um instante final e o devolve; lança ValueError se não servir.

    A regra é uma só para a linha de comando e para o manifesto: data e hora em
    ISO 8601 com fuso, entre 2000 e 2100.
    """
    try:
        momento = _ler_instante(texto)
    except (TypeError, ValueError, AttributeError, OverflowError) as erro:
        raise ValueError(f"instante final inválido ({texto}): use ISO 8601 com fuso, como {FIM_PADRAO}") from erro
    if not FIM_MINIMO <= momento <= FIM_MAXIMO:
        raise ValueError(f"instante final fora do intervalo aceito, de 2000 a 2100: {texto}")
    return texto


@dataclass(frozen=True)
class Base:
    """Parâmetros da base e tudo o que deriva deles sem gerar os cliques."""

    semente: int = SEMENTE_PADRAO
    fim: str = FIM_PADRAO

    @property
    def fim_ms(self) -> int:
        return datetime_para_ms(_ler_instante(self.fim))

    @property
    def duracao_ms(self) -> int:
        return DIAS * 86_400_000

    @property
    def inicio_ms(self) -> int:
        return self.fim_ms - self.duracao_ms

    def clientes(self) -> list[Cliente]:
        return [
            Cliente(f"bench-{n:03d}", f"Cliente de benchmark {n:03d}")
            for n in range(1, CLIENTES + 1)
        ]

    def cliques_por_link(self) -> list[int]:
        popular = round(CLIQUES * PARCELA_POPULAR)
        outros = LINKS - 1
        cada, sobra = divmod(CLIQUES - popular, outros)
        return [popular] + [cada + 1 if i < sobra else cada for i in range(outros)]

    def links(self) -> list[Link]:
        rng = random.Random(f"{self.semente}:links")
        codigos: list[str] = []
        vistos: set[str] = set()
        while len(codigos) < LINKS:
            codigo = "".join(rng.choices(BASE62, k=7))
            if codigo not in vistos:
                vistos.add(codigo)
                codigos.append(codigo)

        clientes = self.clientes()
        links = []
        primeiro = 0
        for indice, (codigo, total) in enumerate(zip(codigos, self.cliques_por_link())):
            cliente = clientes[indice // LINKS_POR_CLIENTE]
            # Cada link é criado até 30 dias antes do primeiro dia de cliques.
            criado_em = self.inicio_ms - rng.randrange(30 * 86_400_000)
            links.append(
                Link(
                    indice=indice,
                    short_code=codigo,
                    cliente_id=cliente.cliente_id,
                    url=f"https://exemplo.com.br/{cliente.cliente_id}/{indice % LINKS_POR_CLIENTE + 1}",
                    canal=rng.choice(CANAIS),
                    criado_em_ms=criado_em,
                    cliques=total,
                    primeiro_clique=primeiro,
                )
            )
            primeiro += total
        return links

    def blocos(self, links: list[Link] | None = None) -> list[Bloco]:
        blocos = []
        for link in links or self.links():
            for numero, inicio in enumerate(range(0, link.cliques, BLOCO)):
                blocos.append(
                    Bloco(
                        link=link.indice,
                        short_code=link.short_code,
                        numero=numero,
                        primeiro_clique=link.primeiro_clique + inicio,
                        quantidade=min(BLOCO, link.cliques - inicio),
                    )
                )
        return blocos

    def _permutacao_dispositivo(self) -> tuple[int, int]:
        # Cada clique i recebe a posição f(i) = (a*i + b) mod N, com N = 10
        # milhões. Quando a e N não têm divisor comum, cada posição de 0 a N-1
        # aparece uma única vez. Assim, cortar as posições nos limites 60/30/5/5
        # dá a proporção exata no total. Um passo a perto de 0,618 N (a razão
        # áurea) espalha os dispositivos entre os links, sem agrupá-los.
        a = int(CLIQUES * 0.6180339887498949)
        while math.gcd(a, CLIQUES) != 1:
            a += 1
        b = random.Random(f"{self.semente}:dispositivo").randrange(CLIQUES)
        return a, b

    def cliques(self, bloco: Bloco) -> Iterator[Clique]:
        rng = random.Random(f"{self.semente}:cliques:{bloco.link}:{bloco.numero}")
        a, b = self._permutacao_dispositivo()
        limites = []
        acumulado = 0
        for nome, parcela in DISPOSITIVOS:
            acumulado += round(CLIQUES * parcela)
            limites.append((acumulado, nome))
        pesos_referrer = []
        acumulado_ref = 0.0
        for referrer, peso in REFERRERS:
            acumulado_ref += peso
            pesos_referrer.append((acumulado_ref, referrer))

        inicio_ms, duracao_ms = self.inicio_ms, self.duracao_ms
        for i in range(bloco.primeiro_clique, bloco.primeiro_clique + bloco.quantidade):
            ms = inicio_ms + rng.randrange(duracao_ms)
            # Monta o timeuuid do clique, um UUID versão 1. O relógio do UUID
            # cai dentro do milissegundo do clique; a fração abaixo do
            # milissegundo, a sequência e o nó, que um UUID real tiraria do
            # relógio e da placa de rede, vêm do gerador do bloco. O bit 40 do
            # nó o marca como sorteado, e não como endereço de placa de rede.
            # Os bits de versão (1) e de variante ficam onde o padrão manda.
            ts = ms * 10_000 + rng.randrange(10_000) + _DESLOCAMENTO_UUID1
            sequencia = rng.getrandbits(14)
            no = rng.getrandbits(48) | (1 << 40)
            valor = (
                ((ts & 0xFFFFFFFF) << 96)
                | (((ts >> 32) & 0xFFFF) << 80)
                | ((((ts >> 48) & 0x0FFF) | 0x1000) << 64)
                | ((((sequencia >> 8) & 0x3F) | 0x80) << 56)
                | ((sequencia & 0xFF) << 48)
                | no
            )
            posicao = (a * i + b) % CLIQUES
            dispositivo = next(nome for limite, nome in limites if posicao < limite)
            sorteio = rng.random()
            referrer = next((r for limite, r in pesos_referrer if sorteio < limite), None)
            yield Clique(bloco.short_code, ms, UUID(int=valor), None, dispositivo, referrer)

    def dispositivos_esperados(self) -> dict[str, int]:
        return {nome: round(CLIQUES * parcela) for nome, parcela in DISPOSITIVOS}


def linha_canonica(clique: Clique) -> bytes:
    """Texto de um clique usado na assinatura; igual para gerador e bancos."""
    return (
        f"{clique.short_code}|{clique.clicado_em_ms}|{clique.clique_id}|"
        f"{clique.dispositivo}|{clique.referrer or ''}|{clique.pais or ''}"
    ).encode()


class Assinatura:
    """Assinatura de um conjunto de cliques, para comparar bancos sem ler linha a linha.

    Cada clique vira um resumo (hash) de 8 bytes da sua linha canônica, e a
    assinatura é a soma dos resumos, descartando o que passa de 64 bits. A soma
    não depende da ordem: dois bancos lidos em ordens diferentes dão a mesma
    assinatura se tiverem os mesmos cliques.
    """

    MODULO = 1 << 64

    def __init__(self) -> None:
        self.valor = 0
        self.linhas = 0

    def somar(self, clique: Clique) -> None:
        digest = hashlib.blake2b(linha_canonica(clique), digest_size=8).digest()
        self.valor = (self.valor + int.from_bytes(digest, "big")) % self.MODULO
        self.linhas += 1

    def juntar(self, outra: "Assinatura") -> None:
        self.valor = (self.valor + outra.valor) % self.MODULO
        self.linhas += outra.linhas

    def texto(self) -> str:
        return f"{self.valor:016x}"


def _assinar_blocos(argumentos: tuple[Base, list[Bloco]]) -> tuple[int, int]:
    base, blocos = argumentos
    assinatura = Assinatura()
    for bloco in blocos:
        for clique in base.cliques(bloco):
            assinatura.somar(clique)
    return assinatura.valor, assinatura.linhas


def assinatura_gerada(base: Base, processos: int) -> Assinatura:
    """Assina os cliques gerados, em paralelo, sem guardá-los em memória."""
    from multiprocessing import get_context

    blocos = base.blocos()
    # Oito partes por processo, com os blocos intercalados, para dividir o
    # trabalho por igual entre os processos.
    partes = [(base, blocos[n::processos * 8]) for n in range(processos * 8)]
    total = Assinatura()
    with get_context("spawn").Pool(processos) as pool:
        for valor, linhas in pool.imap_unordered(_assinar_blocos, partes):
            parcial = Assinatura()
            parcial.valor, parcial.linhas = valor, linhas
            total.juntar(parcial)
    return total


def descrever(base: Base, assinatura: Assinatura | None = None) -> dict:
    """Manifesto da base: o que o histórico e o gerador de carga precisam saber."""
    links = base.links()
    popular = links[0]
    por_link = base.cliques_por_link()
    descricao = {
        "semente": base.semente,
        "inicio": iso(base.inicio_ms),
        "fim": iso(base.fim_ms),
        "janela_historico": {"inicio": iso(base.fim_ms - 86_400_000), "fim": iso(base.fim_ms)},
        "clientes": CLIENTES,
        "prefixo_cliente_id": "bench-",
        "links": LINKS,
        "cliques": CLIQUES,
        "link_popular": {
            "short_code": popular.short_code,
            "cliente_id": popular.cliente_id,
            "cliques": popular.cliques,
            "percentual": round(100 * popular.cliques / CLIQUES, 4),
        },
        "cliques_por_link_comum": {"minimo": min(por_link[1:]), "maximo": max(por_link[1:])},
        "dispositivos": base.dispositivos_esperados(),
    }
    if assinatura is not None:
        descricao["assinatura_cliques"] = assinatura.texto()
    return descricao


def manifesto_valido(dados: object) -> bool:
    """Diz se o manifesto é exatamente o que a semente e o instante final geram.

    Recalcula todos os campos a partir de `semente` e `fim` (menos de 1 s) e
    exige igualdade, mais uma assinatura de 16 dígitos hexadecimais e um `fim`
    com fuso entre 2000 e 2100. Pega campo faltando, campo a mais e valor
    alterado, e nunca lança exceção: um manifesto que não passa só é recusado.
    """
    if not isinstance(dados, dict) or not isinstance(dados.get("semente"), int):
        return False
    assinatura = dados.get("assinatura_cliques")
    if not isinstance(assinatura, str) or not re.fullmatch(r"[0-9a-f]{16}", assinatura):
        return False
    fim = dados.get("fim")
    if not isinstance(fim, str):
        return False
    try:
        validar_fim(fim)
        esperado = descrever(Base(semente=dados["semente"], fim=fim))
    except Exception:  # noqa: BLE001 - qualquer erro torna o manifesto inválido, sem interromper quem valida
        return False
    return {k: v for k, v in dados.items() if k != "assinatura_cliques"} == esperado
