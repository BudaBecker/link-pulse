import re

from app.service import gerar_short_code


def test_dez_mil_codigos_tem_sete_caracteres_base62():
    codigos = [gerar_short_code() for _ in range(10_000)]

    assert all(re.fullmatch(r"[A-Za-z0-9]{7}", codigo) for codigo in codigos)


def test_codigos_seguidos_nao_diferem_so_no_ultimo_caractere():
    codigos = [gerar_short_code() for _ in range(10_000)]

    assert not [(a, b) for a, b in zip(codigos, codigos[1:]) if a[:6] == b[:6]]
