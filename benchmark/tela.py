"""Servidor da tela de testes do benchmark (SPEC-005, passo 6; Q-70).

Serve a tela de benchmark/tela/ e o Chart.js da aplicação, sem internet. O botão
da tela roda `medir.py --ao-vivo --eventos` como processo filho, um por vez, e
as linhas `EVENTO` dele chegam à tela por Server-Sent Events. As execuções
completas salvas em benchmark/gravacoes/ abrem sem Docker e sem bancos.

    python benchmark/tela.py        # http://127.0.0.1:8002

Só a biblioteca padrão, como o base.py. Detalhes em benchmark/README.md.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PASTA = Path(__file__).resolve().parent
RAIZ = PASTA.parent
GRAVACOES = PASTA / "gravacoes"
REGISTROS = PASTA / "registros"
PORTA = 8002  # fora da 8000 da demonstração e da 8001 da queda
CHART_JS = "/vendor/chart.js-4.6.1/chart.umd.min.js"
ARQUIVOS = {
    "/": (PASTA / "tela" / "index.html", "text/html; charset=utf-8"),
    "/tela.css": (PASTA / "tela" / "tela.css", "text/css; charset=utf-8"),
    "/tela.js": (PASTA / "tela" / "tela.js", "text/javascript; charset=utf-8"),
    # O mesmo arquivo da tela da aplicação, sem cópia (ADR-0013).
    CHART_JS: (RAIZ / "app" / "static" / CHART_JS.removeprefix("/"), "text/javascript; charset=utf-8"),
}
NOME_DE_REGISTRO = re.compile(r"^(\d{8}-\d{6})-(\w+)\.json$")
NOME_DE_GRAVACAO = re.compile(r"^(\d{8}-\d{6})-(completa|teste)\.json$")
PING_S = 15  # comentário periódico para o navegador não fechar a conexão de eventos


class Sequencia:
    """A sequência ao vivo em andamento, ou a última, com os eventos para quem conectar depois."""

    def __init__(self) -> None:
        self.condicao = threading.Condition()
        self.numero = 0
        self.eventos: list[dict] = []
        self.processo: subprocess.Popen | None = None
        self.inicio = 0.0

    def rodando(self) -> bool:
        return self.processo is not None and self.processo.poll() is None

    def iniciar(self) -> bool:
        with self.condicao:
            if self.rodando():
                return False
            self.numero += 1
            self.eventos = []
            self.inicio = time.monotonic()
            self.processo = subprocess.Popen(
                [sys.executable, "-u", str(PASTA / "medir.py"), "--ao-vivo", "--eventos"], cwd=RAIZ,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"})
            self._publicar({"tipo": "inicio", "em": datetime.now().astimezone().isoformat(timespec="seconds")})
        threading.Thread(target=self._ler, args=(self.processo,), daemon=True).start()
        return True

    def _publicar(self, evento: dict) -> None:
        """Chamado com a condição tomada. O tempo decorrido conta do clique no botão (CA-7)."""
        evento["decorrido_s"] = round(time.monotonic() - self.inicio, 1)
        self.eventos.append(evento)
        self.condicao.notify_all()

    def _ler(self, processo: subprocess.Popen) -> None:
        for linha in processo.stdout:
            linha = linha.rstrip("\r\n")
            try:
                evento = json.loads(linha.removeprefix("EVENTO ")) if linha.startswith("EVENTO ") else None
            except ValueError:
                evento = None
            with self.condicao:
                self._publicar(evento or {"tipo": "log", "texto": linha})
        codigo = processo.wait()
        with self.condicao:
            self._publicar({"tipo": "saida", "codigo": codigo})


SEQUENCIA = Sequencia()


def estado_da_base() -> dict:
    """Hora da última restauração ou carga, e medições registradas depois dela; só informa (Q-72)."""
    # A execução completa grava em gravacoes/, e não em registros/, mas também muda a base.
    registros = sorted((m.group(1), "medir" if a.parent == GRAVACOES else m.group(2))
                       for a in [*REGISTROS.glob("*.json"), *GRAVACOES.glob("*.json")]
                       if (m := NOME_DE_REGISTRO.match(a.name)))
    restauracoes = [r for r in registros if r[1] in ("restaurar", "carregar")]
    if not restauracoes:
        return {"ultima_restauracao": None, "medicoes_depois": 0}
    ultima = restauracoes[-1][0]
    return {"ultima_restauracao": datetime.strptime(ultima, "%Y%m%d-%H%M%S").isoformat(),
            "medicoes_depois": sum(1 for quando, tipo in registros if quando > ultima and tipo in ("medir", "calibrar"))}


def gravacoes() -> list[dict]:
    """As execuções salvas, da mais nova para a mais antiga."""
    nomes = sorted((a.name for a in GRAVACOES.glob("*.json") if NOME_DE_GRAVACAO.match(a.name)), reverse=True)
    return [{"nome": n, "tipo": NOME_DE_GRAVACAO.match(n).group(2),
             "gravada_em": datetime.strptime(n[:15], "%Y%m%d-%H%M%S").isoformat()} for n in nomes]


class Tela(BaseHTTPRequestHandler):
    def log_message(self, formato, *args) -> None:
        pass  # a tela pede /api/estado a cada poucos segundos; o terminal fica para a medição

    def responder(self, status: int, corpo: bytes, tipo: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def json(self, status: int, dados) -> None:
        self.responder(status, json.dumps(dados, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def do_GET(self) -> None:
        rota = self.path.split("?", 1)[0]
        if rota in ARQUIVOS:
            caminho, tipo = ARQUIVOS[rota]
            return self.responder(200, caminho.read_bytes(), tipo)
        if rota == "/api/estado":
            return self.json(200, {"rodando": SEQUENCIA.rodando(), "base": estado_da_base()})
        if rota == "/api/gravacoes":
            return self.json(200, gravacoes())
        if rota.startswith("/api/gravacoes/"):
            nome = rota.removeprefix("/api/gravacoes/")
            if nome in {g["nome"] for g in gravacoes()}:  # só nomes listados, nunca um caminho
                return self.responder(200, (GRAVACOES / nome).read_bytes(), "application/json; charset=utf-8")
            return self.json(404, {"erro": "gravação não encontrada"})
        if rota == "/api/eventos":
            return self.eventos()
        self.json(404, {"erro": "não encontrado"})

    def do_POST(self) -> None:
        if self.path != "/api/ao-vivo":
            return self.json(404, {"erro": "não encontrado"})
        if not SEQUENCIA.iniciar():
            return self.json(409, {"erro": "a sequência ao vivo já está rodando"})
        self.json(202, {"numero": SEQUENCIA.numero})

    def eventos(self) -> None:
        """Os eventos da sequência atual desde o início, e os seguintes conforme chegam."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        numero, enviados = None, 0
        try:
            while True:
                with SEQUENCIA.condicao:
                    if numero == SEQUENCIA.numero and enviados == len(SEQUENCIA.eventos):
                        SEQUENCIA.condicao.wait(PING_S)
                    if numero != SEQUENCIA.numero:  # uma sequência nova começa do primeiro evento
                        numero, enviados = SEQUENCIA.numero, 0
                    novos = SEQUENCIA.eventos[enviados:]
                    enviados += len(novos)
                if not novos:
                    self.wfile.write(b": ping\n\n")
                for evento in novos:
                    self.wfile.write(b"data: " + json.dumps(evento, ensure_ascii=False).encode() + b"\n\n")
                self.wfile.flush()
        except (ConnectionError, OSError):
            return  # a aba fechou ou recarregou


def main() -> int:
    servidor = ThreadingHTTPServer(("127.0.0.1", PORTA), Tela)
    servidor.daemon_threads = True
    print(f"Tela de testes em http://127.0.0.1:{PORTA} (Ctrl+C encerra)")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
