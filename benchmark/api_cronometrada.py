"""A aplicação com o tempo de cada redirecionamento no cabeçalho `Server-Timing` (Q-63).

Só o cenário de queda do Cassandra sobe a API por aqui, chamado pelo medir.py;
a aplicação não muda. O tempo vai da chegada do pedido ao início da resposta,
como na Q-59, e fica fora o das tarefas que rodam depois da resposta.
"""

import time

from app.main import app as aplicacao


async def app(scope, receive, send):
    if scope["type"] != "http" or not scope["path"].startswith("/r/"):
        return await aplicacao(scope, receive, send)

    inicio = time.perf_counter()

    async def enviar(mensagem):
        if mensagem["type"] == "http.response.start":
            duracao_ms = (time.perf_counter() - inicio) * 1000
            cabecalhos = [*mensagem.get("headers", []), (b"server-timing", f"app;dur={duracao_ms:.3f}".encode())]
            mensagem = {**mensagem, "headers": cabecalhos}
        await send(mensagem)

    await aplicacao(scope, receive, enviar)
