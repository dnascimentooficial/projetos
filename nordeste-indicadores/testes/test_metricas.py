import pandas as pd
import pytest

from nordeste.derivados import ErroSerie, crescimento_relativo, metricas_convergencia, variacao_acumulada
from nordeste.esquema import COLUNAS_BASE, COLUNAS_DERIVADOS, METRICAS
from nordeste.fichas import Comparacao, Ficha, Serie
from nordeste.territorios import UFS_NE


def ficha(id, referencia="nenhuma", sentido="maior_melhor", inicio=2000, fim=2030, auxiliar=False,
          tratamento_monetario=None):
    serie = Serie(
        id="s", inicio=inicio, fim=fim, fonte="f", base_origem="b", url="u",
        coletor="c", parametros={}, compatibilidade="c", verificado=True,
    )
    return Ficha(
        id=id, nome=id, descricao="d", eixo="e", categoria="c", unidade="u", orgao="o",
        periodicidade="anual", metodologia="m", observacoes="o", sentido=sentido,
        limites={}, defasagem_meses=0, comparacao=Comparacao(referencia),
        series=(serie,), auxiliar=auxiliar, tratamento_monetario=tratamento_monetario,
    )


def _linha(indicador, territorio, ano, valor, serie="s"):
    return {
        "indicador_id": indicador, "subindicador": "", "etapa": "", "rede": "",
        "territorio_id": territorio, "ano": ano, "valor": valor,
        "tipo_dado": "indisponivel" if valor is None else "observado",
        "serie_id": serie, "coleta_id": f"c.{indicador}.{territorio}", "nota": "",
    }


def base_anos(valores):
    """valores: {indicador: {ano: {territorio: valor}}}."""
    return pd.DataFrame(
        [
            _linha(i, t, ano, v)
            for i, anos in valores.items() for ano, terr in anos.items() for t, v in terr.items()
        ],
        columns=COLUNAS_BASE,
    )


def base_de(valores, ano=2002):
    return base_anos({i: {ano: t} for i, t in valores.items()})


def serie_anos(valores, serie="s"):
    return pd.DataFrame({
        "ano": list(valores), "valor": [float(v) for v in valores.values()], "serie_id": serie,
    })


def test_razao_e_diferenca(territorios):
    m = metricas_convergencia(
        base_de({"x": {"NE": 40, "BR": 80}}), {"x": ficha("x", referencia="brasil")}, territorios,
    )
    ne = m[(m.territorio_id == "NE")].set_index("metrica").valor
    assert ne["razao"] == 50.0 and ne["diferenca"] == -40.0


def test_variacao_acumulada():
    assert variacao_acumulada(serie_anos({2002: 100, 2003: 150})).tolist() == [0.0, 50.0]


def test_crescimento_relativo_em_pontos():
    r = crescimento_relativo(serie_anos({2002: 100, 2003: 110}), serie_anos({2002: 100, 2003: 105}))
    assert r.round(6).tolist() == [5.0]


def test_recusa_series_misturadas():
    with pytest.raises(ErroSerie):
        variacao_acumulada(pd.concat([serie_anos({2012: 1}, serie="pnad"), serie_anos({2013: 2}, serie="pnadc")]))


def test_crescimento_relativo_recusa_series_diferentes():
    with pytest.raises(ErroSerie):
        crescimento_relativo(serie_anos({2012: 1, 2013: 2}, serie="pnad"), serie_anos({2012: 1, 2013: 2}, serie="pnadc"))


@pytest.mark.parametrize("sentido,pos", [("maior_melhor", 2), ("menor_melhor", 4)])
def test_posicao(sentido, pos, territorios):
    b = base_de({"x": {"N": 1, "NE": 4, "SE": 5, "S": 3, "CO": 2}})
    m = metricas_convergencia(b, {"x": ficha("x", sentido=sentido)}, territorios)
    assert m[m.metrica == "posicao_regioes"].valor.tolist() == [pos]


def test_posicao_exige_as_cinco_regioes(territorios):
    b = base_de({"x": {"N": 1, "NE": 4, "SE": 5, "S": 3}})
    m = metricas_convergencia(b, {"x": ficha("x")}, territorios)
    assert m[m.metrica == "posicao_regioes"].empty


def test_dispersao_exige_as_nove_ufs(territorios):
    nove = dict(zip(UFS_NE, range(1, 10)))
    m = metricas_convergencia(base_de({"x": nove}), {"x": ficha("x")}, territorios)
    assert m[m.metrica == "dispersao_ufs"].valor.round(2).tolist() == [51.64]
    assert m[m.metrica == "dispersao_ufs"].territorio_id.tolist() == ["NE"]
    oito = {k: v for k, v in nove.items() if k != "BA"}
    assert metricas_convergencia(base_de({"x": oito}), {"x": ficha("x")}, territorios).query("metrica == 'dispersao_ufs'").empty


def test_sem_referencia_so_saem_tres_metricas(territorios):
    b = base_anos({"x": {2002: {"NE": 1, "BR": 2}, 2003: {"NE": 2, "BR": 2}}})
    m = metricas_convergencia(b, {"x": ficha("x", referencia="nenhuma")}, territorios)
    assert set(m.metrica) <= {"variacao_acumulada", "posicao_regioes", "dispersao_ufs"}
    assert m[(m.metrica == "variacao_acumulada") & (m.territorio_id == "NE")].valor.tolist() == [0.0, 100.0]
    assert (m.referencia == "").all()


def test_referencia_brasil_fora_ne_e_registrada(territorios):
    m = metricas_convergencia(
        base_de({"x": {"NE": 30, "BR_FORA_NE": 60}}), {"x": ficha("x", referencia="brasil_fora_ne")}, territorios,
    )
    razao = m[m.metrica == "razao"]
    assert razao.valor.tolist() == [50.0] and razao.referencia.tolist() == ["BR_FORA_NE"]


def test_razao_e_diferenca_saem_para_ne_e_ufs(territorios):
    valores = {"BR": 10, "NE": 5, **{uf: 2 for uf in UFS_NE}}
    m = metricas_convergencia(base_de({"x": valores}), {"x": ficha("x", referencia="brasil")}, territorios)
    for metrica in ("razao", "diferenca", "crescimento_relativo"):
        assert set(m[m.metrica == metrica].territorio_id) <= {"NE", *UFS_NE}
    assert set(m[m.metrica == "razao"].territorio_id) == {"NE", *UFS_NE}


def test_razao_nao_atravessa_serie(territorios):
    b = pd.concat([
        base_de({"x": {"NE": 40}}),
        pd.DataFrame([_linha("x", "BR", 2002, 80, serie="outra")], columns=COLUNAS_BASE),
    ], ignore_index=True)
    m = metricas_convergencia(b, {"x": ficha("x", referencia="brasil")}, territorios)
    assert m[m.metrica.isin(["razao", "diferenca"])].empty


def test_crescimento_relativo_na_base(territorios):
    b = base_anos({"x": {2002: {"NE": 100, "BR": 100}, 2003: {"NE": 110, "BR": 105}}})
    m = metricas_convergencia(b, {"x": ficha("x", referencia="brasil")}, territorios)
    c = m[(m.metrica == "crescimento_relativo") & (m.territorio_id == "NE")]
    assert c.ano.tolist() == [2003] and c.valor.round(6).tolist() == [5.0]


def test_ignora_auxiliar_e_indisponivel(territorios):
    b = base_anos({
        "x": {2002: {"NE": 40, "BR": 80}, 2003: {"NE": None, "BR": 90}},
        "aux": {2002: {"NE": 1, "BR": 2}},
    })
    fichas = {"x": ficha("x", referencia="brasil"), "aux": ficha("aux", referencia="brasil", auxiliar=True)}
    m = metricas_convergencia(b, fichas, territorios)
    assert set(m.indicador_id) == {"x"}
    assert m[m.metrica == "razao"].ano.tolist() == [2002]


def test_saida_no_esquema_e_ordenada(territorios):
    b = base_anos({"x": {2003: {"NE": 2, "BR": 2, "MA": 1}, 2002: {"NE": 1, "BR": 2, "MA": 1}}})
    m = metricas_convergencia(b, {"x": ficha("x", referencia="brasil")}, territorios)
    assert m.columns.tolist() == COLUNAS_DERIVADOS and set(m.metrica) <= set(METRICAS)
    chave = ["indicador_id", "subindicador", "etapa", "rede", "metrica", "referencia", "territorio_id", "ano", "serie_id"]
    assert m[chave].equals(m[chave].sort_values(chave).reset_index(drop=True))


def test_base_vazia_devolve_esquema(territorios):
    m = metricas_convergencia(pd.DataFrame(columns=COLUNAS_BASE), {}, territorios)
    assert m.empty and m.columns.tolist() == COLUNAS_DERIVADOS


def test_referencia_zero_nao_gera_razao(territorios):
    m = metricas_convergencia(
        base_de({"x": {"NE": 4, "BR": 0}}), {"x": ficha("x", referencia="brasil")}, territorios,
    )
    assert m[m.metrica == "razao"].empty
    assert m[m.metrica == "diferenca"].valor.tolist() == [4.0]


def test_crescimento_relativo_entre_edicoes_de_serie_bienal():
    # serie bienal: a variacao e entre edicoes (2002 -> 2004), porque 2003 nao e ano publicado da serie
    t = serie_anos({2002: 100, 2004: 120})
    r = crescimento_relativo(t, serie_anos({2002: 100, 2004: 110}))
    assert r.index.tolist() == [2004] and r.round(6).tolist() == [10.0]


def test_crescimento_relativo_nao_pula_ano_publicado_da_serie():
    # 2003 e ano publicado (a referencia tem valor); sem o territorio em 2003, nao ha par 2002 -> 2004
    t = serie_anos({2002: 100, 2004: 120})
    assert crescimento_relativo(t, serie_anos({2002: 100, 2003: 90, 2004: 110})).empty
    # o calendario da serie pode vir de fora: lacuna da referencia num ano publicado tambem corta o par
    r = crescimento_relativo(
        serie_anos({2019: 100, 2020: 110, 2021: 121}), serie_anos({2019: 100, 2021: 110}),
        calendario=[2019, 2020, 2021],
    )
    assert r.empty


def test_exige_territorios_conhecidos(territorios):
    with pytest.raises(ValueError, match="BR_FORA_NE"):
        metricas_convergencia(base_de({"x": {"NE": 1}}), {"x": ficha("x")}, territorios[territorios.territorio_id != "BR_FORA_NE"])


def test_variacao_acumulada_sai_para_referencias(territorios):
    b = base_anos({"x": {
        2002: {"NE": 100, "BR": 100, "BR_FORA_NE": 100, "SE": 100},
        2003: {"NE": 110, "BR": 105, "BR_FORA_NE": 102, "SE": 90},
    }})
    m = metricas_convergencia(b, {"x": ficha("x", referencia="brasil_fora_ne")}, territorios)
    v = m[m.metrica == "variacao_acumulada"].set_index(["territorio_id", "ano"]).valor
    assert v[("BR", 2003)] == pytest.approx(5.0) and v[("BR_FORA_NE", 2003)] == pytest.approx(2.0)
    assert v[("NE", 2003)] == pytest.approx(10.0) and v[("SE", 2003)] == pytest.approx(-10.0)
    assert (m[m.metrica == "variacao_acumulada"].referencia == "").all()


def test_crescimento_relativo_com_tres_observacoes():
    r = crescimento_relativo(serie_anos({2002: 100, 2003: 110, 2004: 121}), serie_anos({2002: 100, 2003: 105, 2004: 110.25}))
    assert r.round(6).tolist() == [5.0, 5.0] and r.index.tolist() == [2003, 2004]


def test_linha_indisponivel_nao_vira_referencia_nem_gera_variacao(territorios):
    b = base_anos({"x": {
        2002: {"NE": 100, "BR": 100},
        2003: {"NE": 110, "BR": None},
        2004: {"NE": 121, "BR": 110},
    }})
    m = metricas_convergencia(b, {"x": ficha("x", referencia="brasil")}, territorios)
    br = m[(m.territorio_id == "BR") & (m.metrica == "variacao_acumulada")]
    assert br.ano.tolist() == [2002, 2004] and br.valor.round(6).tolist() == [0.0, 10.0]
    assert m[(m.metrica == "razao") & (m.territorio_id == "NE")].ano.tolist() == [2002, 2004]
    # 2003 e ano publicado da serie (o NE tem valor) e o BR nao: nem 2002 -> 2003 nem 2003 -> 2004 tem par
    assert m[m.metrica == "crescimento_relativo"].empty


def test_linha_indisponivel_e_ignorada_mesmo_com_valor_residual(territorios):
    b = base_anos({"x": {2002: {"NE": 100, "BR": 100}, 2003: {"NE": 110, "BR": 999}}})
    b.loc[(b.territorio_id == "BR") & (b.ano == 2003), "tipo_dado"] = "indisponivel"
    m = metricas_convergencia(b, {"x": ficha("x", referencia="brasil")}, territorios)
    assert m[(m.metrica == "razao") & (m.territorio_id == "NE")].ano.tolist() == [2002]
    assert m[(m.territorio_id == "BR")].ano.tolist() == [2002]


# ---------------------------------------------------------------------------
# Revisao final: I1 (R$ correntes), I3 (lacuna no crescimento), I6 (BR no lugar do BR_FORA_NE), M3 (ano-base)
# ---------------------------------------------------------------------------

def _completa(valor_ne, valor_ref=100.0):
    """Um ano com BR, 5 regioes e 9 UFs."""
    return {"BR": valor_ref, "N": 1.0, "NE": valor_ne, "SE": 3.0, "S": 4.0, "CO": 5.0,
            **{uf: float(i) for i, uf in enumerate(UFS_NE, start=1)}}


def test_ficha_em_reais_correntes_so_tem_metricas_do_mesmo_ano(territorios):
    b = base_anos({"x": {2002: _completa(40.0), 2003: _completa(50.0, 110.0)}})
    nominal = ficha("x", referencia="brasil", tratamento_monetario={"modo": "razao"})
    m = metricas_convergencia(b, {"x": nominal}, territorios)
    assert set(m.metrica) == {"razao", "posicao_regioes", "dispersao_ufs"}
    assert m[(m.metrica == "razao") & (m.territorio_id == "NE")].valor.round(6).tolist() == [40.0, 45.454545]


def test_ficha_em_reais_constantes_mantem_todas_as_metricas(territorios):
    b = base_anos({"x": {2002: _completa(40.0), 2003: _completa(50.0, 110.0)}})
    constante = ficha("x", referencia="brasil",
                      tratamento_monetario={"modo": "reais_constantes", "deflator": "d", "ano_base": 2025})
    m = metricas_convergencia(b, {"x": constante}, territorios)
    assert set(m.metrica) == set(METRICAS)


def test_crescimento_relativo_na_base_nao_atravessa_lacuna_da_referencia(territorios):
    # BR ausente de 2020 a 2022, anos publicados da serie (NE e SE tem valor): a linha 2023 seria 2019 -> 2023
    anos = {a: {"NE": 100.0 + a - 2019, "SE": 50.0} for a in range(2019, 2024)}
    anos[2019]["BR"], anos[2023]["BR"] = 200.0, 220.0
    m = metricas_convergencia(base_anos({"x": anos}), {"x": ficha("x", referencia="brasil")}, territorios)
    assert m[m.metrica == "crescimento_relativo"].empty
    assert m[(m.metrica == "razao") & (m.territorio_id == "NE")].ano.tolist() == [2019, 2023]


def test_sem_brasil_fora_ne_no_ano_a_referencia_e_o_brasil(territorios):
    anos = {a: {"NE": 10.0 * (a - 2018), "BR": 100.0 + a - 2019, "BR_FORA_NE": 200.0 + a - 2019} for a in range(2019, 2024)}
    for a in (2020, 2021, 2022):
        del anos[a]["BR_FORA_NE"]
    m = metricas_convergencia(base_anos({"x": anos}), {"x": ficha("x", referencia="brasil_fora_ne")}, territorios)
    ne = m[m.territorio_id == "NE"]
    razao = ne[ne.metrica == "razao"].set_index("ano")
    assert razao.referencia.to_dict() == {
        2019: "BR_FORA_NE", 2020: "BR", 2021: "BR", 2022: "BR", 2023: "BR_FORA_NE"}
    assert razao.valor[2020] == pytest.approx(20.0 / 101.0 * 100)
    assert ne[ne.metrica == "diferenca"].set_index("ano").referencia.to_dict() == razao.referencia.to_dict()
    # cada par usa uma unica referencia, a do ano mais recente: 2022 -> 2023 seria BR -> BR_FORA_NE e nao sai
    cresc = ne[ne.metrica == "crescimento_relativo"].set_index("ano")
    assert cresc.referencia.to_dict() == {2020: "BR", 2021: "BR", 2022: "BR"}
    assert cresc.valor[2020] == pytest.approx((20.0 / 10.0 - 1) * 100 - (101.0 / 100.0 - 1) * 100)


def test_serie_inteira_sem_brasil_fora_ne_compara_com_o_brasil(territorios):
    b = base_anos({"x": {2002: {"NE": 40.0, "BR": 80.0}, 2003: {"NE": 44.0, "BR": 88.0}}})
    m = metricas_convergencia(b, {"x": ficha("x", referencia="brasil_fora_ne")}, territorios)
    comparadas = m[m.metrica.isin(["razao", "diferenca", "crescimento_relativo"])]
    assert set(comparadas.referencia) == {"BR"} and len(comparadas) == 5


def test_variacao_acumulada_usa_o_primeiro_ano_do_brasil_para_todos(territorios):
    b = base_anos({"x": {
        2002: {"NE": 100.0},
        2003: {"NE": 110.0, "BR": 200.0},
        2004: {"NE": 121.0, "BR": 220.0, "MA": 50.0},
    }})
    m = metricas_convergencia(b, {"x": ficha("x")}, territorios)
    v = m[m.metrica == "variacao_acumulada"]
    ne = v[v.territorio_id == "NE"].set_index("ano").valor
    assert ne.index.tolist() == [2003, 2004] and ne[2004] == pytest.approx(10.0)
    assert v[v.territorio_id == "MA"].empty  # sem valor no ano-base (2003): nao ha variacao acumulada


def test_variacao_acumulada_sem_brasil_usa_o_primeiro_ano_da_serie(territorios):
    b = base_anos({"x": {2010: {"NE": 100.0}, 2011: {"NE": 120.0, "MA": 10.0}, 2012: {"MA": 12.0}}})
    m = metricas_convergencia(b, {"x": ficha("x")}, territorios)
    v = m[m.metrica == "variacao_acumulada"]
    assert v[v.territorio_id == "NE"].valor.round(6).tolist() == [0.0, 20.0]
    assert v[v.territorio_id == "MA"].empty


def test_variacao_acumulada_com_ano_base_explicito():
    assert variacao_acumulada(serie_anos({2002: 100, 2003: 150, 2004: 300}), ano_base=2003).tolist() == [0.0, 100.0]
    assert variacao_acumulada(serie_anos({2003: 150, 2004: 300}), ano_base=2002).empty
