import dataclasses
import warnings
from datetime import date

import numpy as np
import pandas as pd

from nordeste.validacao import validar
from test_validacao import cenario, cenario_com_valores_ne


def _avisos(c, regra):
    return [a for a in validar(**c).avisos if a.regra == regra]


def test_a01_salto():
    r = validar(**cenario_com_valores_ne({2002: 100, 2003: 200}))  # limiar padrao 50
    assert any(a.regra == "A01" for a in r.avisos) and r.aprovado


def test_a01_variacao_abaixo_do_limiar_nao_avisa():
    assert _avisos(cenario_com_valores_ne({2002: 100, 2003: 140}), "A01") == []


def test_a01_usa_variacao_absoluta_e_cita_exemplos():
    (a,) = _avisos(cenario_com_valores_ne({2002: 200, 2003: 90}), "A01")  # queda tambem avisa
    assert "amostra_per_capita" in a.mensagem and "scr_ref2010" in a.mensagem and "NE" in a.mensagem


def test_a01_ignora_ficha_auxiliar():
    # O PIB nominal (auxiliar) dobra junto com o per capita, mas so o per capita e citado.
    avisos = _avisos(cenario_com_valores_ne({2002: 100, 2003: 200}), "A01")
    assert len(avisos) == 1 and "pib_nominal" not in avisos[0].mensagem


def test_a01_respeita_limiar_da_ficha():
    c = cenario_com_valores_ne({2002: 100, 2003: 140})
    c["fichas"] = {**c["fichas"], "amostra_per_capita": dataclasses.replace(c["fichas"]["amostra_per_capita"], limiar_salto_pct=10.0)}
    assert len(_avisos(c, "A01")) == 1


def test_a01_limita_a_cinco_exemplos_por_serie():
    (a,) = _avisos(cenario_com_valores_ne({2002: 100, 2003: 200}), "A01")  # 16 territorios saltam
    assert a.mensagem.count("2002->2003") == 5 and a.mensagem.endswith("...")


def test_a01_ignora_valores_nulos_entre_observacoes():
    c = cenario_com_valores_ne({2002: 100, 2003: 200})
    base = c["base"].copy()
    base.loc[(base.indicador_id == "amostra_per_capita") & (base.ano == 2003), ["valor", "tipo_dado"]] = [np.nan, "indisponivel"]
    assert _avisos({**c, "base": base}, "A01") == []


def test_a01_sem_warning_com_valor_anterior_zero():
    c = cenario()
    base = c["base"].copy()
    base.loc[(base.indicador_id == "amostra_per_capita") & (base.territorio_id == "MA") & (base.ano == 2002), "valor"] = 0.0
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        r = validar(**{**c, "base": base})
    assert any(a.regra == "A01" and "MA" in a.mensagem for a in r.avisos)


def test_a02_alteracoes():
    c = cenario(); c["base_publicada"] = c["base"].assign(valor=c["base"].valor + 1)
    assert any(a.regra == "A02" and a.mensagem.startswith(f"{len(c['base'])} valores") for a in validar(**c).avisos)


def test_a02_nada_sem_base_publicada_ou_sem_alteracao():
    c = cenario()
    assert _avisos(c, "A02") == []
    assert _avisos({**c, "base_publicada": c["base"].copy()}, "A02") == []


def test_a02_conta_so_valores_alterados_e_trata_nan_como_igual():
    c = cenario()
    publicada = c["base"].copy()
    publicada.loc[0, "valor"] += 1.0                      # alterado
    publicada.loc[1, "valor"] = np.nan                    # numero -> nulo: alterado
    base = c["base"].copy()
    base.loc[2, ["valor", "tipo_dado"]] = [np.nan, "indisponivel"]
    publicada.loc[2, ["valor", "tipo_dado"]] = [np.nan, "indisponivel"]  # nulo nos dois: igual
    (a,) = _avisos({**c, "base": base, "base_publicada": publicada}, "A02")
    assert a.mensagem.startswith("2 valores alterados")


def test_a02_ignora_linhas_que_so_existem_de_um_lado():
    c = cenario()
    publicada = c["base"].iloc[1:].reset_index(drop=True)
    assert _avisos({**c, "base_publicada": publicada}, "A02") == []


def test_a03_atraso_so_em_serie_em_curso():
    assert any(a.regra == "A03" for a in validar(**cenario(fim=None, ultimo_ano=2020, hoje=date(2026, 11, 1))).avisos)
    assert not any(a.regra == "A03" for a in validar(**cenario(fim=2020, ultimo_ano=2020, hoje=date(2026, 11, 1))).avisos)


def test_a03_vence_depois_do_ultimo_dia_do_mes_previsto():
    # Proxima publicacao apos o ultimo ano 2020: dezembro de 2021 + 23 meses de defasagem = 2023-11.
    assert _avisos(cenario(fim=None, ultimo_ano=2020, hoje=date(2023, 11, 30)), "A03") == []
    assert len(_avisos(cenario(fim=None, ultimo_ano=2020, hoje=date(2023, 12, 1)), "A03")) == 3


def test_a03_usa_o_maior_ano_com_valor_do_ne():
    c = cenario(fim=None, ultimo_ano=2020, hoje=date(2023, 12, 1))
    base = c["base"].copy()
    base.loc[(base.territorio_id == "NE") & (base.ano == 2020), ["valor", "tipo_dado"]] = [np.nan, "indisponivel"]
    # Sem valor do NE em 2020, o ultimo ano passa a 2019 (proxima publicacao 2022-11, tambem vencida).
    mensagens = [a.mensagem for a in _avisos({**c, "base": base}, "A03")]
    assert mensagens and all("2019" in m for m in mensagens)


def test_avisos_nao_afetam_aprovado():
    c = cenario(fim=None, ultimo_ano=2020)
    r = validar(**c)
    assert r.avisos and r.aprovado
