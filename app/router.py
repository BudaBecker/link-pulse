from fastapi import APIRouter, HTTPException, Request

from app import service
from app.models import NovaCampanha, NovoCliente, NovoLink

router = APIRouter()


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
