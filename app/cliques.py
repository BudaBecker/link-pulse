import logging
import threading
from datetime import UTC, datetime

from cassandra.util import uuid_from_time

log = logging.getLogger(__name__)

INSERIR_CLIQUE = (
    "INSERT INTO cliques_por_link (short_code, clicado_em, clique_id, pais, dispositivo, referrer) "
    "VALUES (?, ?, ?, ?, ?, ?)"
)

# Pré-visualizações de redes sociais e clientes de linha de comando entram em "outro" (Q-37).
MARCAS_DE_ROBO = ("bot", "crawl", "spider", "slurp", "facebookexternalhit", "whatsapp", "preview", "curl", "wget")


def classificar_dispositivo(user_agent: str | None) -> str:
    ua = (user_agent or "").lower()
    if not ua or any(marca in ua for marca in MARCAS_DE_ROBO):
        return "outro"

    # Tablets Android não trazem "mobile"; celulares Android trazem.
    if "ipad" in ua or "tablet" in ua or ("android" in ua and "mobile" not in ua):
        return "tablet"

    if any(marca in ua for marca in ("mobi", "iphone", "ipod", "android", "windows phone")):
        return "mobile"

    if any(marca in ua for marca in ("windows", "macintosh", "x11", "linux", "cros")):
        return "desktop"

    return "outro"


class RegistroDeCliques:
    """Grava cada clique no Cassandra sem esperar a resposta e conta os que falham (RN-07)."""

    def __init__(self, sessao, tempo_limite: float):
        self._sessao = sessao
        self._insercao = sessao.prepare(INSERIR_CLIQUE)
        self._tempo_limite = tempo_limite
        self._falhas = 0
        self._trava = threading.Lock()

    @property
    def falhas(self) -> int:
        return self._falhas

    def registrar(self, short_code: str, user_agent: str | None, referrer: str | None) -> None:
        # O Cassandra guarda milissegundos; o clique_id leva o mesmo instante de clicado_em.
        agora = datetime.now(UTC)
        clicado_em = agora.replace(microsecond=agora.microsecond // 1000 * 1000)
        valores = (
            short_code,
            clicado_em,
            uuid_from_time(clicado_em),
            None,
            classificar_dispositivo(user_agent),
            referrer or None,
        )
        try:
            futuro = self._sessao.execute_async(self._insercao, valores, timeout=self._tempo_limite)

        except Exception as erro:
            self._falhou(short_code, erro)
            return

        futuro.add_errback(lambda erro: self._falhou(short_code, erro))

    # Roda na thread do driver, por isso a trava.
    def _falhou(self, short_code: str, erro: BaseException) -> None:
        with self._trava:
            self._falhas += 1
        log.warning("clique descartado em %s: %r", short_code, erro)
