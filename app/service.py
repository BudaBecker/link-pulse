import secrets
import string
import uuid
from datetime import UTC, datetime

import redis
from bson import ObjectId
from bson.errors import InvalidId
from pymongo.collection import Collection

from app.cliques import RegistroDeCliques
from app.models import NovaCampanha, NovoCliente, NovoLink

ALFABETO_SHORT_CODE = string.ascii_uppercase + string.ascii_lowercase + string.digits
TAMANHO_SHORT_CODE = 7
MAX_TENTATIVAS = 5

# Conferir e gravar no mesmo script impede que dois pedidos ocupem o mesmo código.
GRAVAR_LINK_SE_LIVRE = """
if redis.call('EXISTS', KEYS[1]) == 1 then
  return 0
end
redis.call('HSET', KEYS[1], unpack(ARGV, 2))
redis.call('SADD', KEYS[2], ARGV[1])
return 1
"""


class CampanhaInexistente(Exception):
    pass


class FalhaNaGravacao(Exception):
    pass


class LinkInexistente(Exception):
    pass


class LinkExpirado(Exception):
    pass


def gerar_short_code() -> str:
    # secrets, e não random: um código não pode servir para adivinhar o próximo.
    return "".join(secrets.choice(ALFABETO_SHORT_CODE) for _ in range(TAMANHO_SHORT_CODE))


def formatar_instante(momento: datetime) -> str:
    return momento.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def cadastrar_cliente(master: redis.Redis, pedido: NovoCliente) -> str:
    cliente_id = uuid.uuid4().hex
    pipe = master.pipeline()
    pipe.hset(f"cliente:{cliente_id}", mapping={"nome": pedido.nome})
    pipe.sadd("clientes", cliente_id)
    pipe.execute()
    return cliente_id


def listar_clientes(master: redis.Redis) -> list[dict]:
    ids = sorted(master.smembers("clientes"))
    pipe = master.pipeline(transaction=False)
    
    for cliente_id in ids:
        pipe.hget(f"cliente:{cliente_id}", "nome")
        
    clientes = [{"cliente_id": i, "nome": nome} for i, nome in zip(ids, pipe.execute())]
    return sorted(clientes, key=lambda c: (c["nome"] or "").lower())


def criar_campanha(campanhas: Collection, pedido: NovaCampanha) -> str:
    resultado = campanhas.insert_one(pedido.model_dump() | {"links": []})
    return str(resultado.inserted_id)


def criar_link(master: redis.Redis, campanhas: Collection, pedido: NovoLink) -> str:
    campanha_id = None
    if pedido.campanha_id is not None:
        try:
            campanha_id = ObjectId(pedido.campanha_id)
            
        except InvalidId:
            pass
        
        if campanha_id is None or campanhas.count_documents({"_id": campanha_id}, limit=1) == 0:
            raise CampanhaInexistente("campanha_id não existe")

    campos = {
        "url": pedido.url,
        "cliente_id": pedido.cliente_id,
        "criado_em": formatar_instante(datetime.now(UTC)),
    }
    
    if pedido.canal is not None:
        campos["canal"] = pedido.canal
        
    if pedido.expira_em is not None:
        campos["expira_em"] = formatar_instante(pedido.expira_em)
        
    pares = [valor for par in campos.items() for valor in par]

    gravar_link_se_livre = master.register_script(GRAVAR_LINK_SE_LIVRE)
    codigo = None
    try:
        for _ in range(MAX_TENTATIVAS):
            candidato = gerar_short_code()
            chaves = [f"link:{candidato}", f"links:cliente:{pedido.cliente_id}"]
            if gravar_link_se_livre(keys=chaves, args=[candidato, *pares]) == 1:
                codigo = candidato
                break
            
    except redis.RedisError as erro:
        raise FalhaNaGravacao("falha ao gravar o link; tente de novo") from erro
    
    if codigo is None:
        raise FalhaNaGravacao("não foi possível gerar um short_code livre; tente de novo")

    if campanha_id is not None:
        campanhas.update_one({"_id": campanha_id}, {"$push": {"links": codigo}})

    return codigo


def buscar_url(replica: redis.Redis, master: redis.Redis, short_code: str) -> str:
    chave = f"link:{short_code}"
    try:
        link = replica.hgetall(chave)

    except redis.RedisError:
        link = {}

    # Um link recém-criado pode ainda não ter chegado à réplica (Q-31).
    if not link:
        link = master.hgetall(chave)

    if not link:
        raise LinkInexistente("short_code não existe")

    expira_em = link.get("expira_em")
    if expira_em is not None and datetime.fromisoformat(expira_em) < datetime.now(UTC):
        raise LinkExpirado("link expirado")

    return link["url"]


def contar_clique(
    master: redis.Redis, cliques: RegistroDeCliques, short_code: str, user_agent: str | None, referrer: str | None
) -> None:
    # Primeiro o evento, que não espera o Cassandra: uma falha no INCR não impede o registro.
    cliques.registrar(short_code, user_agent, referrer)
    master.incr(f"contador:{short_code}")
