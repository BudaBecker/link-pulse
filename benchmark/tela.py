"""Servidor da tela de testes do benchmark (SPEC-005, passo 6; Q-70, Q-76).

Serve a tela de benchmark/tela/, com o CSS e o Chart.js da aplicação, sem
internet. Os botões da tela rodam, um por vez, os comandos do benchmark: parar
os bancos, restaurar, conferir ou carregar a base, medir e voltar ao ambiente de
desenvolvimento (Q-76). A saída de cada comando, e as linhas `EVENTO` do
medir.py, chegam à tela por Server-Sent Events. As execuções completas salvas em
benchmark/gravacoes/ abrem sem Docker e sem bancos.

    python benchmark/tela.py                # http://127.0.0.1:8002
    python benchmark/tela.py --porta 8012   # outra porta

Só a biblioteca padrão, como o base.py. Detalhes em benchmark/README.md.
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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from base import BANCOS, VOLUMES

PASTA = Path(__file__).resolve().parent
RAIZ = PASTA.parent
GRAVACOES = PASTA / "gravacoes"
REGISTROS = PASTA / "registros"
ESTATICA = RAIZ / "app" / "static"
PORTA = 8002  # fora da 8000 da demonstração e da 8001 da queda
JS, CSS = "text/javascript; charset=utf-8", "text/css; charset=utf-8"
# O CSS e o Chart.js são os mesmos arquivos da tela da aplicação, sem cópia (ADR-0013, Q-76).
ARQUIVOS = {
    "/": (PASTA / "tela" / "index.html", "text/html; charset=utf-8"),
    "/tela.css": (PASTA / "tela" / "tela.css", CSS),
    "/tela.js": (PASTA / "tela" / "tela.js", JS),
    "/static/painel.css": (ESTATICA / "painel.css", CSS),
    "/static/vendor/chart.js-4.6.1/chart.umd.min.js": (ESTATICA / "vendor" / "chart.js-4.6.1" / "chart.umd.min.js", JS),
}
NOME_DE_REGISTRO = re.compile(r"^(\d{8}-\d{6})-(\w+)\.json$")
NOME_DE_GRAVACAO = re.compile(r"^(\d{8}-\d{6})-(completa|teste)\.json$")
PING_S = 15  # comentário periódico para o navegador não fechar a conexão de eventos

MEDIR = [sys.executable, "-u", str(PASTA / "medir.py")]
BASE = [sys.executable, "-u", str(PASTA / "base.py")]
DESENVOLVIMENTO = ["docker", "compose"]  # só o docker-compose.yml: os volumes de desenvolvimento
# Nome na rota -> (rótulo, comandos em sequência, se é uma medição com linhas EVENTO).
TAREFAS = {
    "ao-vivo": ("Sequência ao vivo", [[*MEDIR, "--ao-vivo", "--eventos"]], True),
    "completa": ("Execução completa", [[*MEDIR, "--completa", "--eventos"]], True),
    "completa-teste": ("Execução completa de teste",
                       [[*MEDIR, "--completa", "--duracao", "5", "--aquecimento", "2", "--eventos"]], True),
    "parar": ("Parar os bancos", [[*DESENVOLVIMENTO, "stop"]], False),
    "restaurar": ("Restaurar a base", [[*BASE, "restaurar"]], False),
    "conferir": ("Conferir a base", [[*BASE, "conferir"]], False),
    "carregar": ("Carregar a base do zero", [[*BASE, "carregar"]], False),
    "desenvolvimento": ("Voltar ao desenvolvimento",
                        [[*DESENVOLVIMENTO, "stop"], [*DESENVOLVIMENTO, "up", "-d", "--wait"]], False),
}


def legivel(comando: list[str]) -> str:
    """O comando como se digitaria na raiz do repositório."""
    return " ".join("python" if a == sys.executable else Path(a).relative_to(RAIZ).as_posix()
                    if a.startswith(str(RAIZ)) else a for a in comando if a != "-u")


def encerrar_arvore(processo: subprocess.Popen) -> None:
    """O comando e os filhos dele: a API da queda e os clientes do Docker (a trava se solta sozinha)."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(processo.pid), "/T", "/F"], capture_output=True)
    else:
        os.killpg(processo.pid, 15)


class Tarefas:
    """A tarefa em andamento, uma por vez, e os eventos para quem conectar depois.

    Quem conecta recebe os eventos desde o início da última medição, para remontar
    as curvas dela, e os das tarefas seguintes.
    """

    def __init__(self) -> None:
        self.condicao = threading.Condition()
        self.eventos: list[dict] = []
        self.primeiro_id = 0  # id do eventos[0]; os ids não se repetem enquanto o servidor roda
        self.numero = 0
        self.nome: str | None = None
        self.processo: subprocess.Popen | None = None
        self.rodando = False
        self.interrompida = False
        self.inicio = 0.0

    @property
    def proximo_id(self) -> int:
        return self.primeiro_id + len(self.eventos)

    def iniciar(self, nome: str) -> bool:
        rotulo, comandos, medicao = TAREFAS[nome]
        with self.condicao:
            if self.rodando:
                return False
            if medicao:  # a medição nova substitui a anterior para quem conectar depois
                self.primeiro_id, self.eventos = self.proximo_id, []
            self.numero += 1
            self.nome, self.rodando, self.interrompida = nome, True, False
            self.inicio = time.monotonic()
            self._publicar({"tipo": "inicio", "nome": nome, "rotulo": rotulo, "medicao": medicao,
                            "em": datetime.now().astimezone().isoformat(timespec="seconds")})
        threading.Thread(target=self._rodar, args=(comandos,), daemon=True).start()
        return True

    def interromper(self) -> bool:
        with self.condicao:
            if not self.rodando:
                return False
            self.interrompida = True
            processo = self.processo
        if processo is not None and processo.poll() is None:
            encerrar_arvore(processo)
        return True

    def _publicar(self, evento: dict) -> None:
        """Chamado com a condição tomada. O tempo decorrido conta do clique no botão (CA-7)."""
        evento |= {"id": self.proximo_id, "tarefa": self.numero,
                   "decorrido_s": round(time.monotonic() - self.inicio, 1)}
        self.eventos.append(evento)
        self.condicao.notify_all()

    def _rodar(self, comandos: list[list[str]]) -> None:
        codigo = 0
        for comando in comandos:
            with self.condicao:
                if self.interrompida:
                    break
                self._publicar({"tipo": "log", "texto": "$ " + legivel(comando)})
                try:
                    self.processo = subprocess.Popen(
                        comando, cwd=RAIZ, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                        encoding="utf-8", errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                        **({} if os.name == "nt" else {"start_new_session": True}))
                except OSError as erro:
                    self._publicar({"tipo": "log", "texto": f"não foi possível rodar o comando: {erro}"})
                    codigo = 1
                    break
            for linha in self.processo.stdout:
                linha = linha.rstrip("\r\n")
                try:
                    evento = json.loads(linha.removeprefix("EVENTO ")) if linha.startswith("EVENTO ") else None
                except ValueError:
                    evento = None
                with self.condicao:
                    self._publicar(evento or {"tipo": "log", "texto": linha})
            codigo = self.processo.wait()
            if codigo:
                break
        with self.condicao:
            self.rodando, self.processo = False, None
            self._publicar({"tipo": "saida", "codigo": codigo, "interrompida": self.interrompida})


TAREFA = Tarefas()


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


def ambiente() -> dict:
    """Com que volumes cada banco comparado está no ar, para a tela saber que botões oferecer."""
    try:
        saida = subprocess.run(
            ["docker", "ps", "--filter", "label=com.docker.compose.project=linkpulse", "--no-trunc", "--format",
             '{{.Label "com.docker.compose.service"}}|{{.Mounts}}'],
            capture_output=True, text=True, encoding="utf-8", timeout=10, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return {"situacao": "sem_docker", "parados": list(BANCOS)}
    no_ar = {}
    for linha in saida.splitlines():
        servico, _, montagens = linha.partition("|")
        if servico in VOLUMES:
            no_ar[servico] = "benchmark" if VOLUMES[servico] in montagens.split(",") else "desenvolvimento"
    parados = [b for b in BANCOS if b not in no_ar]
    tipos = set(no_ar.values())
    if not no_ar:
        situacao = "parado"
    elif tipos == {"benchmark"}:
        situacao = "benchmark" if not parados else "benchmark_parcial"
    else:  # algum banco com os volumes de desenvolvimento: o benchmark recusa mexer neles
        situacao = "desenvolvimento"
    return {"situacao": situacao, "parados": parados}


def gravacoes() -> list[dict]:
    """As execuções salvas, da mais nova para a mais antiga."""
    nomes = sorted((a.name for a in GRAVACOES.glob("*.json") if NOME_DE_GRAVACAO.match(a.name)), reverse=True)
    return [{"nome": n, "tipo": NOME_DE_GRAVACAO.match(n).group(2),
             "gravada_em": datetime.strptime(n[:15], "%Y%m%d-%H%M%S").isoformat()} for n in nomes]


class Tela(BaseHTTPRequestHandler):
    def log_message(self, formato, *args) -> None:
        pass  # a tela pede /api/estado a cada poucos segundos; o terminal fica limpo

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
            with TAREFA.condicao:
                tarefa = {"numero": TAREFA.numero, "nome": TAREFA.nome, "rodando": TAREFA.rodando}
            return self.json(200, {"tarefa": tarefa, "base": estado_da_base(), "ambiente": ambiente()})
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
        # Só a própria tela: outra página aberta no navegador não restaura nem mede.
        porta = self.server.server_address[1]
        origens = {f"http://127.0.0.1:{porta}", f"http://localhost:{porta}"}
        origem = f"http://{self.headers.get('Host', '')}"
        if origem not in origens or self.headers.get("Origin", origem) not in origens:
            return self.json(403, {"erro": "pedido de fora da tela de testes"})
        if self.path == "/api/interromper":
            if not TAREFA.interromper():
                return self.json(409, {"erro": "nenhuma tarefa rodando"})
            return self.json(202, {"numero": TAREFA.numero})
        nome = self.path.removeprefix("/api/tarefas/")
        if not self.path.startswith("/api/tarefas/") or nome not in TAREFAS:
            return self.json(404, {"erro": "não encontrado"})
        if not TAREFA.iniciar(nome):
            return self.json(409, {"erro": "outra tarefa está rodando"})
        self.json(202, {"numero": TAREFA.numero})

    def eventos(self) -> None:
        """Os eventos guardados e os seguintes conforme chegam; numa reconexão, a partir do último recebido."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        ultimo = self.headers.get("Last-Event-ID", "")
        proximo = int(ultimo) + 1 if ultimo.isdigit() else 0
        try:
            while True:
                with TAREFA.condicao:
                    if proximo > TAREFA.proximo_id:  # o servidor reiniciou: os ids recomeçaram
                        proximo = 0
                    if proximo == TAREFA.proximo_id:
                        TAREFA.condicao.wait(PING_S)
                    novos = TAREFA.eventos[max(0, proximo - TAREFA.primeiro_id):]
                    proximo = TAREFA.proximo_id
                if not novos:
                    self.wfile.write(b": ping\n\n")
                for evento in novos:
                    self.wfile.write(f"id: {evento['id']}\ndata: ".encode()
                                     + json.dumps(evento, ensure_ascii=False).encode() + b"\n\n")
                self.wfile.flush()
        except (ConnectionError, OSError):
            return  # a aba fechou ou recarregou


class Servidor(ThreadingHTTPServer):
    # No Windows, SO_REUSEADDR deixaria uma segunda tela abrir a mesma porta sem erro.
    allow_reuse_address = os.name != "nt"
    daemon_threads = True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--porta", type=int, default=PORTA)
    porta = parser.parse_args().porta
    try:
        servidor = Servidor(("127.0.0.1", porta), Tela)
    except OSError as erro:
        sys.exit(f"a porta {porta} não abriu ({erro}); outra tela já está aberta?")
    print(f"Tela de testes em http://127.0.0.1:{porta} (Ctrl+C encerra)")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        TAREFA.interromper()
    return 0


if __name__ == "__main__":
    sys.exit(main())
