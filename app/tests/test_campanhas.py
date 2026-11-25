import pytest
from bson import ObjectId


def test_campanha_guarda_os_campos_e_comeca_sem_links(api, campanhas):
    corpo = {"cliente_id": "c1", "nome": "Black Friday", "descricao": "Novembro", "tags": ["promo", "varejo"]}

    resposta = api.post("/campanhas", json=corpo)

    assert resposta.status_code == 201
    documento = campanhas.find_one({"_id": ObjectId(resposta.json()["campanha_id"])}, {"_id": 0})
    assert documento == corpo | {"links": []}


def test_descricao_e_tags_sao_opcionais(campanhas, criar_campanha):
    campanha_id = criar_campanha()

    documento = campanhas.find_one({"_id": ObjectId(campanha_id)}, {"_id": 0})
    assert documento == {"cliente_id": "c1", "nome": "Natal", "descricao": None, "tags": [], "links": []}


@pytest.mark.parametrize(
    "corpo",
    [{"nome": "Natal"}, {"cliente_id": "c1"}, {"cliente_id": "c1", "nome": ""}],
    ids=["sem-cliente", "sem-nome", "nome-vazio"],
)
def test_campanha_incompleta_e_rejeitada(api, campanhas, corpo):
    assert api.post("/campanhas", json=corpo).status_code == 422
    assert campanhas.count_documents({}) == 0


def test_listagem_traz_as_campanhas_do_cliente_em_ordem_de_nome(api, criar_campanha):
    natal = criar_campanha(nome="natal", descricao="Dezembro", tags=["promo"])
    black = criar_campanha(nome="Black Friday")
    criar_campanha(cliente_id="c2", nome="Outra")
    codigo = api.post("/links", json={"url": "https://exemplo.com", "cliente_id": "c1", "campanha_id": natal}).json()[
        "short_code"
    ]

    resposta = api.get("/campanhas", params={"cliente_id": "c1"})

    assert resposta.status_code == 200
    assert resposta.json() == [
        {"campanha_id": black, "nome": "Black Friday", "descricao": None, "tags": [], "links": []},
        {"campanha_id": natal, "nome": "natal", "descricao": "Dezembro", "tags": ["promo"], "links": [codigo]},
    ]


def test_cliente_sem_campanhas_recebe_lista_vazia(api):
    resposta = api.get("/campanhas", params={"cliente_id": "sem-campanhas"})

    assert resposta.status_code == 200
    assert resposta.json() == []


@pytest.mark.parametrize("parametros", [{}, {"cliente_id": ""}], ids=["sem-cliente", "cliente-vazio"])
def test_listagem_sem_cliente_responde_422(api, parametros):
    assert api.get("/campanhas", params=parametros).status_code == 422
