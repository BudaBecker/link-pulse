import pytest


def test_cliente_cadastrado_aparece_na_listagem(api, master):
    resposta = api.post("/clientes", json={"nome": "Loja Aurora"})

    assert resposta.status_code == 201
    cliente_id = resposta.json()["cliente_id"]
    assert master.hgetall(f"cliente:{cliente_id}") == {"nome": "Loja Aurora"}
    assert master.sismember("clientes", cliente_id)
    assert api.get("/clientes").json() == [{"cliente_id": cliente_id, "nome": "Loja Aurora"}]


def test_listagem_ignora_clientes_do_benchmark(api, master):
    master.hset("cliente:bench-001", mapping={"nome": "Cliente do benchmark"})
    cliente_id = api.post("/clientes", json={"nome": "Demonstração"}).json()["cliente_id"]

    assert api.get("/clientes").json() == [{"cliente_id": cliente_id, "nome": "Demonstração"}]


@pytest.mark.parametrize("corpo", [{}, {"nome": ""}], ids=["sem-nome", "nome-vazio"])
def test_cliente_sem_nome_e_rejeitado(api, master, corpo):
    assert api.post("/clientes", json=corpo).status_code == 422
    assert master.dbsize() == 0
