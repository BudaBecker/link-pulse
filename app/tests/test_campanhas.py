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
