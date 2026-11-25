import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.main import PASTA_ESTATICA, TEMPO_LIMITE_CLIQUE
from app.tests.test_tela import PRAZO_RNF_03, intervalo_de_atualizacao, janela_da_tela

EXECUTOR = Path(__file__).with_name("dados_da_tela.mjs")
CODIGO = "abc1234"
CLIENTE = "c1"
AGORA = "2026-11-24T18:00:00Z"


def rodar(funcao: str, argumentos: list, respostas: dict) -> dict:
    return executar({"funcao": funcao, "argumentos": argumentos, "respostas": respostas})


def executar(pedido: dict) -> dict:
    node = shutil.which("node")
    assert node, "os testes da tela precisam do Node no PATH (Q-56)"
    entrada = json.dumps(pedido)
    saida = subprocess.run(
        [node, str(EXECUTOR), str(PASTA_ESTATICA / "dados.js")],
        input=entrada,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=30,
    )
    return json.loads(saida.stdout)


def leitura(cliques_por_dia: list[int], dispositivos: list[int], cliques_do_link: int) -> dict:
    return {
        "/analytics/por-dia": {"dias": [{"dia": f"2026-11-{18 + n}", "cliques": c} for n, c in enumerate(cliques_por_dia)]},
        "/analytics/por-dispositivo": {
            "dispositivos": [{"dispositivo": d, "cliques": c} for d, c in zip(("mobile", "desktop", "tablet", "outro"), dispositivos)]
        },
        "/analytics/por-canal": {"canais": [{"short_code": CODIGO, "canal": "instagram", "cliques": cliques_do_link}]},
    }


def respostas_em_sequencia(*leituras: tuple[int, dict]) -> dict:
    respostas = {"/analytics/total": []}
    for total, partes in leituras:
        respostas["/analytics/total"].append({"short_code": CODIGO, "cliques": total})
        for rota, corpo in partes.items():
            respostas.setdefault(rota, []).append(corpo)
    return respostas


def buscar_historico(respostas: dict) -> dict:
    return rodar("buscarHistorico", [CODIGO, CLIENTE, None, f"data:{AGORA}"], respostas)


def chamadas_de(saida: dict, rota: str) -> list[dict]:
    return [c["parametros"] for c in saida["chamadas"] if c["rota"] == rota]


@pytest.mark.parametrize("agora", ["2026-11-24T18:00:00Z", "2026-11-25T01:30:00Z", "2026-11-25T03:00:00Z", "2027-01-01T02:59:59Z"])
def test_janela_da_pagina_e_a_mesma_dos_testes_de_dados(agora):
    saida = rodar("janelaDosSeteDias", [f"data:{agora}"], {})

    janela = saida["resultado"]
    esperado = janela_da_tela(datetime.fromisoformat(agora))
    assert {"inicio": janela["inicio"], "fim": janela["fim"]} == esperado


def test_conjunto_coerente_sai_na_primeira_leitura_com_a_janela_da_tela():
    saida = buscar_historico(respostas_em_sequencia((3, leitura([1, 0, 0, 0, 0, 0, 2], [2, 1, 0, 0], 3))))

    historico = saida["resultado"]
    assert historico["total"] == 3
    janela = janela_da_tela(datetime.fromisoformat(AGORA))
    assert chamadas_de(saida, "/analytics/total") == [{"short_code": CODIGO} | janela]
    assert chamadas_de(saida, "/analytics/por-dia") == [{"short_code": CODIGO} | janela]
    assert chamadas_de(saida, "/analytics/por-dispositivo") == [{"short_code": CODIGO} | janela]
    assert chamadas_de(saida, "/analytics/por-canal") == [{"cliente_id": CLIENTE} | janela]


def test_clique_entre_as_leituras_refaz_as_consultas_antes_de_publicar():
    # O total foi lido antes do clique; as barras, os dispositivos e os canais, depois.
    antes_e_depois = (0, leitura([0, 0, 0, 0, 0, 0, 1], [1, 0, 0, 0], 1))
    depois = (1, leitura([0, 0, 0, 0, 0, 0, 1], [1, 0, 0, 0], 1))

    saida = buscar_historico(respostas_em_sequencia(antes_e_depois, depois))

    historico = saida["resultado"]
    assert historico["total"] == 1
    assert sum(d["cliques"] for d in historico["dias"]) == 1
    assert sum(d["cliques"] for d in historico["dispositivos"]) == 1
    assert historico["canais"][0]["cliques"] == 1
    assert len(chamadas_de(saida, "/analytics/total")) == 2


@pytest.mark.parametrize(
    "incoerente",
    [
        (2, leitura([0, 0, 0, 0, 0, 0, 3], [2, 0, 0, 0], 2)),
        (2, leitura([0, 0, 0, 0, 0, 0, 2], [2, 1, 0, 0], 2)),
        (2, leitura([0, 0, 0, 0, 0, 0, 2], [2, 0, 0, 0], 3)),
    ],
    ids=["barras", "dispositivos", "canais"],
)
def test_sem_conjunto_coerente_em_3_leituras_nada_e_publicado(incoerente):
    saida = buscar_historico(respostas_em_sequencia(incoerente))

    assert saida["resultado"] is None
    assert len(chamadas_de(saida, "/analytics/total")) == 3


def test_contexto_le_as_campanhas_a_cada_ciclo():
    links = [{"short_code": "novo123"}, {"short_code": CODIGO}]
    sem_o_link = [{"campanha_id": "k1", "nome": "Natal", "links": [CODIGO]}]
    com_o_link = [{"campanha_id": "k1", "nome": "Natal", "links": [CODIGO, "novo123"]}]

    # Dois ciclos: entre eles, o link novo entrou na campanha por outra aba.
    primeiro = rodar("buscarContexto", [CLIENTE], {"/links": [links], "/campanhas": [sem_o_link]})
    segundo = rodar("buscarContexto", [CLIENTE], {"/links": [links], "/campanhas": [com_o_link]})

    for saida in (primeiro, segundo):
        assert [c["rota"] for c in saida["chamadas"]] == ["/links", "/campanhas"]
        assert all(c["parametros"] == {"cliente_id": CLIENTE} for c in saida["chamadas"])
    assert rodar("campanhaDoLink", [primeiro["resultado"]["campanhas"], "novo123"], {})["resultado"] is None
    assert rodar("campanhaDoLink", [segundo["resultado"]["campanhas"], "novo123"], {})["resultado"]["nome"] == "Natal"


def test_falha_nas_campanhas_mantem_os_links():
    saida = rodar("buscarContexto", [CLIENTE], {"/links": [[{"short_code": CODIGO}]]})

    assert saida["resultado"] == {"links": [{"short_code": CODIGO}], "campanhas": None, "falhou": True}


def test_clique_chega_a_tela_publicada_em_ate_60_s_com_cliques_continuos():
    # 500 cliques por minuto, cada leitura 130 ms depois da anterior e a gravação no tempo limite.
    cada, marcado = 120, 10_000
    saida = executar(
        {
            "simulacao": {
                "codigo": CODIGO,
                "clienteId": CLIENTE,
                "inicio": "2026-11-24T15:00:00-03:00",
                "cliqueACadaMs": cada,
                "gravacaoMs": TEMPO_LIMITE_CLIQUE * 1000,
                "defasagemMs": 130,
                "cicloMs": intervalo_de_atualizacao() * 1000,
                "duracaoMs": 90_000,
            }
        }
    )

    publicacoes = saida["publicacoes"]
    cliques_ate_o_marcado = marcado // cada + 1
    primeira = next(p for p in publicacoes if p["total"] >= cliques_ate_o_marcado)
    assert primeira["em"] - marcado < PRAZO_RNF_03 * 1000
    assert len(publicacoes) == 90_000 // (intervalo_de_atualizacao() * 1000)
