import re
import time
from datetime import UTC, datetime, timedelta
from datetime import time as horario
from zoneinfo import ZoneInfo

from app.main import PASTA_ESTATICA, TEMPO_LIMITE_CLIQUE
from app.tests.test_analytics import WINDOWS, gravar_cliques
from app.tests.test_redirecionamento import IPHONE, acessar, criar_link

BRASILIA = ZoneInfo("America/Sao_Paulo")
PRAZO_RNF_03 = 60.0  # segundos
ARQUIVOS_DA_TELA = ("index.html", "painel.css", "painel.js")


def intervalo_de_atualizacao() -> float:
    codigo = (PASTA_ESTATICA / "painel.js").read_text(encoding="utf-8")
    return int(re.search(r"^const INTERVALO_ATUALIZACAO_MS = (\d+);\s*$", codigo, re.M).group(1)) / 1000


def janela_da_tela(agora: datetime) -> dict:
    """Hoje e os 6 dias anteriores, no horário de Brasília (Q-53)."""
    hoje = agora.astimezone(BRASILIA).date()
    inicio = datetime.combine(hoje - timedelta(days=6), horario(0), BRASILIA)
    fim = datetime.combine(hoje, horario(23, 59, 59, 999000), BRASILIA)
    return {"inicio": inicio.isoformat(timespec="milliseconds"), "fim": fim.isoformat(timespec="milliseconds")}


def dados_da_tela(api, codigo: str, cliente_id: str, janela: dict) -> dict:
    link = {"short_code": codigo} | janela
    return {
        "total": api.get("/analytics/total", params=link).json()["cliques"],
        "dias": api.get("/analytics/por-dia", params=link).json()["dias"],
        "dispositivos": api.get("/analytics/por-dispositivo", params=link).json()["dispositivos"],
        "canais": api.get("/analytics/por-canal", params={"cliente_id": cliente_id} | janela).json()["canais"],
        "links": api.get("/links", params={"cliente_id": cliente_id}).json(),
    }


def test_janela_da_tela_cobre_sete_dias_inteiros_de_brasilia():
    # 01:30 UTC de 25/11 ainda é 24/11 em Brasília.
    assert janela_da_tela(datetime(2026, 11, 25, 1, 30, tzinfo=UTC)) == {
        "inicio": "2026-11-18T00:00:00.000-03:00",
        "fim": "2026-11-24T23:59:59.999-03:00",
    }


def test_dados_da_tela_sao_coerentes_entre_si_e_com_as_consultas(api, master, sessao_cassandra):
    janela = janela_da_tela(datetime(2026, 11, 24, 15, 0, tzinfo=BRASILIA))
    codigo = criar_link(api, canal="instagram")
    outro = criar_link(api, canal="email")
    gravar_cliques(sessao_cassandra, codigo, "2026-11-17T23:59:59.999-03:00", dispositivo="mobile")  # fora
    gravar_cliques(sessao_cassandra, codigo, "2026-11-18T00:00:00.000-03:00", dispositivo="mobile")
    gravar_cliques(sessao_cassandra, codigo, "2026-11-20T22:30:00-03:00", "2026-11-20T23:00:00-03:00", dispositivo="desktop")
    gravar_cliques(sessao_cassandra, codigo, "2026-11-24T23:59:59.999-03:00", dispositivo="tablet")
    gravar_cliques(sessao_cassandra, codigo, "2026-11-25T00:00:00.000-03:00", dispositivo="outro")  # fora
    gravar_cliques(sessao_cassandra, outro, "2026-11-22T12:00:00-03:00", dispositivo="mobile")
    master.set(f"contador:{codigo}", 6)

    dados = dados_da_tela(api, codigo, "c1", janela)

    assert dados["total"] == 4
    assert [d["dia"] for d in dados["dias"]] == [f"2026-11-{dia}" for dia in range(18, 25)]
    assert [d["cliques"] for d in dados["dias"]] == [1, 0, 2, 0, 0, 0, 1]
    assert {d["dispositivo"]: d["cliques"] for d in dados["dispositivos"]} == {
        "mobile": 1,
        "desktop": 2,
        "tablet": 1,
        "outro": 0,
    }
    assert sum(d["cliques"] for d in dados["dias"]) == sum(d["cliques"] for d in dados["dispositivos"]) == dados["total"]
    assert dados["canais"] == [
        {"short_code": codigo, "canal": "instagram", "cliques": 4},
        {"short_code": outro, "canal": "email", "cliques": 1},
    ]
    # O contador do Redis não tem janela e pode ser maior que o histórico (Q-51).
    assert {link["short_code"]: link["contador"] for link in dados["links"]} == {codigo: 6, outro: 0}


def test_clique_novo_aparece_nos_dados_da_tela_em_ate_60_s(api):
    codigo = criar_link(api, canal="instagram")
    janela = janela_da_tela(datetime.now(UTC))
    antes = dados_da_tela(api, codigo, "c1", janela)

    clicado = time.monotonic()
    acessar(api, codigo, **{"user-agent": IPHONE})
    acessar(api, codigo, **{"user-agent": WINDOWS})
    while (dados := dados_da_tela(api, codigo, "c1", janela))["total"] < 2:
        assert time.monotonic() - clicado < PRAZO_RNF_03
        time.sleep(0.1)
    atraso = time.monotonic() - clicado

    assert antes["total"] == 0
    assert sum(d["cliques"] for d in dados["dias"]) == 2
    assert {d["dispositivo"]: d["cliques"] for d in dados["dispositivos"]} == {
        "mobile": 1,
        "desktop": 1,
        "tablet": 0,
        "outro": 0,
    }
    assert dados["canais"] == [{"short_code": codigo, "canal": "instagram", "cliques": 2}]
    assert dados["links"][0]["contador"] == 2
    # O clique ainda espera, no pior caso, um ciclo inteiro da tela até a próxima consulta.
    assert atraso + intervalo_de_atualizacao() < PRAZO_RNF_03


def test_pagina_e_servida_na_raiz_com_os_arquivos_locais(api):
    resposta = api.get("/")

    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/html")
    referencias = re.findall(r'(?:src|href)="([^"#]+)"', resposta.text)
    assert {"/static/painel.css", "/static/painel.js", "/static/vendor/chart.js-4.6.1/chart.umd.min.js"} <= set(referencias)
    for referencia in referencias:
        assert referencia.startswith("/static/"), referencia
        assert api.get(referencia).status_code == 200, referencia
    assert "Chart.js v4.6.1" in api.get("/static/vendor/chart.js-4.6.1/chart.umd.min.js").text[:100]


def test_tela_funciona_sem_internet():
    for nome in ARQUIVOS_DA_TELA:
        texto = (PASTA_ESTATICA / nome).read_text(encoding="utf-8")
        assert not re.search(r"https?://|//[a-z0-9-]+\.[a-z]", texto, re.I), nome
        assert "@import" not in texto and "url(" not in texto, nome


def test_intervalo_de_atualizacao_cabe_no_prazo_do_rnf_03():
    # Pior caso: o clique chega logo depois de uma consulta e a gravação usa todo o tempo limite.
    assert intervalo_de_atualizacao() + TEMPO_LIMITE_CLIQUE < PRAZO_RNF_03
