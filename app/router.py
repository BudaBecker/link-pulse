from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import analytics, service
from app.models import URL_HTTP, JanelaDoCliente, JanelaDoLink, NovaCampanha, NovoCliente, NovoLink

router = APIRouter()

PAGINA_EXPIRADO = """<!doctype html>
<html lang="pt-BR">
<head><meta charset="utf-8"><title>Link expirado</title></head>
<body><h1>Link expirado</h1><p>Este link curto passou da data de expiração e não redireciona mais.</p></body>
</html>
"""


@router.post("/clientes", status_code=201)
def cadastrar_cliente(pedido: NovoCliente, request: Request) -> dict:
    return {
        "cliente_id": service.cadastrar_cliente(request.app.state.master, pedido)
        }


@router.get("/clientes")
def listar_clientes(request: Request) -> list[dict]:
    return service.listar_clientes(request.app.state.master)


@router.post("/campanhas", status_code=201)
def criar_campanha(pedido: NovaCampanha, request: Request) -> dict:
    return {
        "campanha_id": service.criar_campanha(request.app.state.campanhas, pedido)
        }


@router.post("/links", status_code=201)
def criar_link(pedido: NovoLink, request: Request) -> dict:
    try:
        codigo = service.criar_link(request.app.state.master, request.app.state.campanhas, pedido)
        
    except service.CampanhaInexistente as erro:
        raise HTTPException(422, str(erro)) from erro
    
    except service.FalhaNaGravacao as erro:
        raise HTTPException(503, str(erro)) from erro

    return {"short_code": codigo}


@router.get("/r/{short_code}", status_code=302, response_class=RedirectResponse)
def redirecionar(short_code: str, request: Request, tarefas: BackgroundTasks):
    estado = request.app.state
    try:
        url = service.buscar_url(estado.replica, estado.master, short_code)

    except service.LinkInexistente as erro:
        raise HTTPException(404, str(erro)) from erro

    except service.LinkExpirado:
        return HTMLResponse(PAGINA_EXPIRADO, status_code=410)

    # As tarefas rodam depois que a resposta sai (RNF-02).
    tarefas.add_task(
        service.contar_clique,
        estado.master,
        estado.cliques,
        short_code,
        request.headers.get("user-agent"),
        request.headers.get("referer"),
    )
    return RedirectResponse(host_em_idna(url), status_code=302)


def host_em_idna(url: str) -> str:
    # O RedirectResponse codificaria "café" como "caf%C3%A9". O validador do cadastro dá o mesmo
    # host que ele aceitou ("faß" em "xn--fa-hia", e não "fass" como o codec idna do Python).
    if urlsplit(url).hostname.isascii():
        return url
    return str(URL_HTTP.validate_python(url))


@router.get("/metricas")
def metricas(request: Request) -> dict:
    return {"falhas_gravacao_clique": request.app.state.cliques.falhas}


@router.get("/analytics/por-dia")
def cliques_por_dia(janela: Annotated[JanelaDoLink, Query()], request: Request) -> dict:
    estado = request.app.state
    try:
        return analytics.cliques_por_dia(estado.master, estado.consultas, janela.short_code, janela)

    except analytics.LinkInexistente as erro:
        raise HTTPException(404, str(erro)) from erro


@router.get("/analytics/por-canal")
def cliques_por_canal(janela: Annotated[JanelaDoCliente, Query()], request: Request) -> dict:
    estado = request.app.state
    return analytics.cliques_por_canal(estado.master, estado.consultas, janela.cliente_id, janela)


@router.get("/analytics/total")
def total_de_cliques(janela: Annotated[JanelaDoLink, Query()], request: Request) -> dict:
    estado = request.app.state
    try:
        return analytics.total_de_cliques(estado.master, estado.consultas, janela.short_code, janela)

    except analytics.LinkInexistente as erro:
        raise HTTPException(404, str(erro)) from erro
