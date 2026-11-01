import dataclasses
import inspect
import warnings
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from nordeste.derivados import brasil_fora_ne, metricas_convergencia
from nordeste.esquema import normalizar_base
from nordeste.fichas import carregar_ficha
from nordeste.territorios import REGIOES, UFS_NE, carregar_territorios
from nordeste.validacao import Falha, ResultadoValidacao, _diverge, validar

METADADOS = Path(__file__).resolve().parent.parent / "metadados"
AMOSTRA = Path(__file__).resolve().parent / "amostra" / "indicadores"  # fichas de teste (ver conftest.py)
SERIE = "scr_ref2010"
ANOS = (2002, 2003)

# PIB nominal (R$ mil) e populacao por territorio em 2002; 2003 multiplica por 1,1 e 1,01.
_PIB_UF = {"MA": 30.0, "PI": 15.0, "CE": 50.0, "RN": 20.0, "PB": 22.0, "PE": 70.0, "AL": 18.0, "SE_UF": 16.0, "BA": 110.0}
_POP_UF = {"MA": 6.0, "PI": 3.0, "CE": 8.0, "RN": 3.0, "PB": 3.5, "PE": 8.5, "AL": 3.0, "SE_UF": 2.0, "BA": 13.5}
_PIB_REG = {"N": 80.0, "SE": 800.0, "S": 250.0, "CO": 120.0}
_POP_REG = {"N": 14.0, "SE": 75.0, "S": 26.0, "CO": 12.0}


_DA_FICHA = object()  # `fim` nao informado: mantem o da ficha (None significa serie em curso)


def _coleta_id(indicador):
    return f"sidra.{indicador}.{SERIE}.20261101"


def _valores(por_uf, por_regiao, fator):
    v = {t: x * fator for t, x in por_uf.items()}
    v["NE"] = sum(v[uf] for uf in UFS_NE)
    v.update({r: x * fator for r, x in por_regiao.items()})
    v["BR"] = sum(v[r] for r in REGIOES)
    return v


def _base_observada(anos=ANOS, fator_pib=None):
    """`fator_pib` (ano -> fator) multiplica o PIB nominal de todos os territorios, preservando as somas."""
    linhas = []
    for ano in anos:
        pib = _valores(_PIB_UF, _PIB_REG, 1.1 ** (ano - 2002) * (fator_pib or {}).get(ano, 1.0))
        pop = _valores(_POP_UF, _POP_REG, 1.01 ** (ano - 2002))
        per_capita = {t: pib[t] / pop[t] * 1000 for t in pib}
        for indicador, valores in (
            ("pib_nominal", pib), ("amostra_populacao", pop), ("amostra_per_capita", per_capita),
        ):
            linhas += [
                {"indicador_id": indicador, "territorio_id": t, "ano": ano, "valor": v,
                 "tipo_dado": "observado", "serie_id": SERIE, "coleta_id": _coleta_id(indicador)}
                for t, v in valores.items()
            ]
    return normalizar_base(pd.DataFrame(linhas))


def cenario(fim=_DA_FICHA, ultimo_ano=None, hoje=date(2026, 11, 1), per_capita_ne=None):
    """Base pequena e coerente do PIB per capita (uma ficha razao e seus dois insumos soma).

    `fim` troca o fim da serie nas tres fichas (None = em curso). `ultimo_ano` desloca os dois anos da
    base para (ultimo_ano - 1, ultimo_ano). `per_capita_ne` (ano -> valor) define o PIB per capita do NE
    por ano, escalando o PIB nominal de todos os territorios para manter somas e razao coerentes.
    """
    fichas = {
        "pib_nominal": carregar_ficha(METADADOS / "indicadores" / "pib_nominal.yaml"),
        **{i: carregar_ficha(AMOSTRA / f"{i}.yaml") for i in ("amostra_populacao", "amostra_per_capita")},
    }
    if fim is not _DA_FICHA:
        fichas = {i: dataclasses.replace(f, series=tuple(dataclasses.replace(s, fim=fim) for s in f.series))
                  for i, f in fichas.items()}
    territorios = carregar_territorios(METADADOS / "territorios.csv")
    anos = ANOS if ultimo_ano is None else (ultimo_ano - 1, ultimo_ano)
    fator_pib = None
    if per_capita_ne is not None:
        fator_pib = {
            ano: valor * sum(_POP_UF.values()) * 1.01 ** (ano - 2002) / 1000 / (sum(_PIB_UF.values()) * 1.1 ** (ano - 2002))
            for ano, valor in per_capita_ne.items()
        }
    observada = _base_observada(anos, fator_pib)
    fora_ne, derivacoes = brasil_fora_ne(observada, fichas)
    base = pd.concat([observada, fora_ne], ignore_index=True)
    coletas = pd.DataFrame([
        {"coleta_id": _coleta_id(i), "indicador_id": i, "serie_id": SERIE, "url": "https://sidra.ibge.gov.br",
         "data_coleta": "2026-11-01", "sha256": "0" * 64, "origem": "rede", "arquivo": f"dados/brutos/{i}.json"}
        for i in fichas
    ])
    return {
        "base": base, "derivados": metricas_convergencia(base, fichas, territorios), "fichas": fichas,
        "falhas_fichas": [], "territorios": territorios, "coletas": coletas, "derivacoes": derivacoes,
        "base_publicada": None, "hoje": hoje,
    }


def cenario_com_valores_ne(valores):
    """Cenario em que o PIB per capita do NE vale `valores[ano]` (ano -> valor), sem quebrar R07 nem R08."""
    return cenario(per_capita_ne=valores)


# ---------------------------------------------------------------------------
# Quebras: cada uma devolve um novo cenario, sem mutar o original
# ---------------------------------------------------------------------------

def _com_base(c, ajuste):
    base = c["base"].copy()
    ajuste(base)
    return {**c, "base": base}


def _linha(base, indicador, territorio, ano):
    return (base.indicador_id == indicador) & (base.territorio_id == territorio) & (base.ano == ano)


def marcar_coleta_como_fixture(c):
    coletas = c["coletas"].copy()
    coletas.loc[coletas.indicador_id == "pib_nominal", "origem"] = "fixture"
    return {**c, "coletas": coletas}


def marcar_insumo_de_derivacao_como_fixture(c):
    """Fixture que so aparece como insumo de uma derivacao (nenhuma linha da base a usa diretamente)."""
    fixture = {**c["coletas"].iloc[0].to_dict(), "coleta_id": "arquivo.pib_nominal.x.fixture", "origem": "fixture"}
    coletas = pd.concat([c["coletas"], pd.DataFrame([fixture])], ignore_index=True)
    derivacoes = c["derivacoes"].copy()
    derivacoes.loc[0, "insumos"] += ";" + fixture["coleta_id"]
    return {**c, "coletas": coletas, "derivacoes": derivacoes}


def trocar_territorio_por(territorio):
    def quebra(c):
        return _com_base(c, lambda b: b.__setitem__("territorio_id", b.territorio_id.where(b.index != 0, territorio)))
    return quebra


def duplicar_primeira_linha(c):
    return {**c, "base": pd.concat([c["base"], c["base"].iloc[[0]]], ignore_index=True)}


def valor_nulo_com_tipo_observado(c):
    return _com_base(c, lambda b: b.__setitem__("valor", b.valor.where(b.index != 0)))


def ano_antes_do_inicio(c):
    return _com_base(c, lambda b: b.__setitem__("ano", b.ano.where(~_linha(b, "amostra_per_capita", "MA", 2002), 2001)))


def valor_negativo_com_min_zero(c):
    return _com_base(c, lambda b: b.__setitem__("valor", b.valor.where(~_linha(b, "pib_nominal", "MA", 2002), -1.0)))


def ne_diferente_da_soma_das_ufs(c):
    return _com_base(c, lambda b: b.__setitem__("valor", b.valor.where(~_linha(b, "pib_nominal", "NE", 2003), b.valor * 1.01)))


def per_capita_ne_divergente(c):
    return _com_base(c, lambda b: b.__setitem__("valor", b.valor.where(~_linha(b, "amostra_per_capita", "NE", 2002), b.valor * 1.01)))


def valor_infinito(c):
    return _com_base(c, lambda b: b.__setitem__("valor", b.valor.where(~_linha(b, "amostra_per_capita", "NE", 2003), float("inf"))))


def coleta_id_inexistente(c):
    return _com_base(c, lambda b: b.__setitem__("coleta_id", b.coleta_id.where(b.index != 0, "sidra.nao_registrada")))


def falha_de_ficha(c):
    return {**c, "falhas_fichas": ["pib_nominal.yaml: campo obrigatorio ausente ou vazio: nome"]}


def remover_uf_de_um_ano(c, uf, ano):
    base = c["base"]
    return {**c, "base": base[~((base.territorio_id == uf) & (base.ano == ano))].reset_index(drop=True)}


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------

def test_base_valida_aprova():
    r = validar(**cenario())
    assert r.erros == [] and r.avisos == [] and r.aprovado


@pytest.mark.parametrize("regra,quebra", [
    ("R01", marcar_coleta_como_fixture), ("R01", marcar_insumo_de_derivacao_como_fixture),
    ("R02", trocar_territorio_por("XX")), ("R03", duplicar_primeira_linha),
    ("R04", valor_nulo_com_tipo_observado), ("R05", ano_antes_do_inicio),
    ("R06", valor_negativo_com_min_zero), ("R07", ne_diferente_da_soma_das_ufs),
    ("R08", per_capita_ne_divergente), ("R09", coleta_id_inexistente), ("R10", falha_de_ficha),
    ("R02", valor_infinito)])
def test_regra_bloqueia(regra, quebra):
    r = validar(**quebra(cenario()))
    assert not r.aprovado and regra in {f.regra for f in r.erros}


def test_r02_rede_fora_do_dominio_bloqueia_e_rede_vazia_passa():
    c = cenario()
    assert (c["base"].rede == "").all() and validar(**c).aprovado
    base = c["base"].copy()
    base.loc[base.index[0], "rede"] = "particular"
    r = validar(**{**c, "base": base})
    assert any(f.regra == "R02" and "rede fora do dominio" in f.mensagem for f in r.erros)
    base.loc[base.index[0], "rede"] = "publica"
    assert "R02" not in {f.regra for f in validar(**{**c, "base": base}).erros}


def test_quebras_nao_mutam_o_cenario():
    c = cenario()
    copia = {k: (v.copy() if isinstance(v, pd.DataFrame) else v) for k, v in c.items()}
    for quebra in (marcar_coleta_como_fixture, marcar_insumo_de_derivacao_como_fixture, valor_nulo_com_tipo_observado,
                   duplicar_primeira_linha, ne_diferente_da_soma_das_ufs, falha_de_ficha):
        quebra(c)
    for chave in ("base", "coletas", "derivacoes"):
        pd.testing.assert_frame_equal(c[chave], copia[chave])
    assert c["falhas_fichas"] == []


def test_r07_ignora_ano_com_uf_faltando():
    r = validar(**remover_uf_de_um_ano(cenario(), "BA", 2003))
    assert "R07" not in {f.regra for f in r.erros}


def test_r01_nao_tem_como_desligar():
    assert set(inspect.signature(validar).parameters) == {
        "base", "derivados", "fichas", "falhas_fichas", "territorios", "coletas", "derivacoes", "base_publicada", "hoje"}


def test_r01_uma_falha_por_coleta_envolvida():
    # A coleta do PIB nominal alimenta as linhas do PIB nominal e duas derivacoes (PIB nominal e PIB per capita).
    r = validar(**marcar_coleta_como_fixture(cenario()))
    r01 = [f for f in r.erros if f.regra == "R01"]
    assert len(r01) == 3
    assert any(_coleta_id("pib_nominal") in f.mensagem for f in r01)


def test_mensagem_cita_indicador_territorio_e_ano():
    r = validar(**valor_negativo_com_min_zero(cenario()))
    (r06,) = [f for f in r.erros if f.regra == "R06"]
    assert "pib_nominal" in r06.mensagem and "MA" in r06.mensagem and "2002" in r06.mensagem


def test_falhas_agregadas_por_indicador_e_serie():
    def todos_negativos(c):
        return _com_base(c, lambda b: b.__setitem__("valor", b.valor.where(b.indicador_id != "pib_nominal", -1.0)))
    r = validar(**todos_negativos(cenario()))
    assert len([f for f in r.erros if f.regra == "R06"]) == 1


def test_para_dataframe():
    r = ResultadoValidacao(erros=[Falha("R03", "duplicada")], avisos=[Falha("A01", "salto")])
    df = r.para_dataframe()
    assert list(df.columns) == ["nivel", "regra", "mensagem"]
    assert df.values.tolist() == [["erro", "R03", "duplicada"], ["aviso", "A01", "salto"]]
    assert not r.aprovado and ResultadoValidacao(erros=[], avisos=[Falha("A01", "x")]).aprovado


def test_r02_texto_nulo():
    def indicador_nulo(c):
        return _com_base(c, lambda b: b.__setitem__("indicador_id", b.indicador_id.where(b.index != 0, None)))
    r = validar(**indicador_nulo(cenario()))
    assert any(f.regra == "R02" and "indicador_id nulo" in f.mensagem for f in r.erros)


def test_r08_com_oficial_infinito_bloqueia_sem_warning():
    assert _diverge(float("inf"), 1.0) and _diverge(1.0, float("-inf")) and _diverge(float("nan"), 1.0)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        r = validar(**valor_infinito(cenario()))
    assert "R08" in {f.regra for f in r.erros}


def test_base_vazia_bloqueia():
    c = cenario()
    r = validar(**{**c, "base": c["base"].iloc[0:0]})
    assert not r.aprovado and any(f.regra == "R02" and "base sem linhas" in f.mensagem for f in r.erros)


def test_r08_denominador_zero_bloqueia():
    def populacao_ne_zero(c):
        return _com_base(c, lambda b: b.__setitem__(
            "valor", b.valor.where(~_linha(b, "amostra_populacao", "NE", 2002), 0.0)))
    r = validar(**populacao_ne_zero(cenario()))
    r08 = [f for f in r.erros if f.regra == "R08"]
    assert len(r08) == 1 and "NE 2002" in r08[0].mensagem


def test_infinitos_opostos_nas_ufs_bloqueiam_sem_warning():
    def ufs_infinitas(c):
        def ajuste(b):
            b.loc[_linha(b, "pib_nominal", "MA", 2002), "valor"] = float("inf")
            b.loc[_linha(b, "pib_nominal", "PI", 2002), "valor"] = float("-inf")
        return _com_base(c, ajuste)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        r = validar(**ufs_infinitas(cenario()))
    assert "R02" in {f.regra for f in r.erros}


def test_diverge_com_precisao_publicada():
    assert _diverge(7.9, 7.94) and not _diverge(7.9, 7.94, precisao=0.1)  # 0,04 > 0,5% de 7,9, mas < 0,05
    assert not _diverge(7.9, 7.95, precisao=0.1)  # a borda da meia casa decimal passa
    assert _diverge(7.9, 7.96, precisao=0.1)
    assert _diverge(7.9, 7.84, precisao=0.1) and not _diverge(7.9, 7.86, precisao=0.1)
    assert _diverge(100.0, 100.6, precisao=0.1)  # a tolerancia relativa de 0,5% continua valendo quando e maior
    assert not _diverge(100.0, 100.4, precisao=0.1)
    assert _diverge(float("inf"), 1.0, precisao=0.1) and _diverge(1.0, float("nan"), precisao=0.1)


def _cenario_r08_com_precisao(fator_oficial, precisao):
    """Per capita oficial do NE `fator_oficial` vezes o valor recalculado; a ficha declara `precisao_oficial`."""
    c = cenario()
    base = c["base"].copy()
    ne = _linha(base, "amostra_per_capita", "NE", 2002)
    recalculado = base.loc[ne, "valor"].iloc[0]
    base.loc[ne, "valor"] = recalculado * fator_oficial
    fichas = dict(c["fichas"])
    ficha = fichas["amostra_per_capita"]
    fichas["amostra_per_capita"] = dataclasses.replace(
        ficha, comparacao=dataclasses.replace(ficha.comparacao, precisao_oficial=precisao))
    return {**c, "base": base, "fichas": fichas}, recalculado


def test_r08_aceita_diferenca_dentro_da_meia_casa_do_valor_publicado():
    # oficial 0,6% acima do recalculado: falha pela regra antiga (0,5%), passa com precisao de 2% do valor (meia casa = 1%)
    c, recalculado = _cenario_r08_com_precisao(1.006, precisao=None)
    assert "R08" in {f.regra for f in validar(**c).erros}
    c, _ = _cenario_r08_com_precisao(1.006, precisao=recalculado * 0.02)
    assert "R08" not in {f.regra for f in validar(**c).erros}


def test_r08_reprova_diferenca_maior_que_a_meia_casa_do_valor_publicado():
    _, recalculado = _cenario_r08_com_precisao(1.0, precisao=None)
    c, _ = _cenario_r08_com_precisao(1.012, precisao=recalculado * 0.02)  # 1,2% acima, meia casa = 1%
    assert "R08" in {f.regra for f in validar(**c).erros}
