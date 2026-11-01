import pandas as pd
import pytest

from nordeste.derivados import ErroSerie, crescimento_relativo, metricas_convergencia, variacao_acumulada
from nordeste.esquema import COLUNAS_BASE, COLUNAS_DERIVADOS, METRICAS
from nordeste.fichas import Comparacao, Ficha, Serie
from nordeste.territorios import UFS_NE


def ficha(id, referencia="nenhuma", sentido="maior_melhor", inicio=2000, fim=2030, auxiliar=False):
    serie = Serie(
        id="s", inicio=inicio, fim=fim, fonte="f", base_origem="b", url="u",
        coletor="c", parametros={}, compatibilidade="c", verificado=True,
    )
    return Ficha(
        id=id, nome=id, descricao="d", eixo="e", categoria="c", unidade="u", orgao="o",
        periodicidade="anual", metodologia="m", observacoes="o", sentido=sentido,
        limites={}, defasagem_meses=0, comparacao=Comparacao(referencia),
        series=(serie,), auxiliar=auxiliar,
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
    assert m[m.metrica == "variacao_acumulada"].valor.tolist() == [0.0, 100.0]
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
    assert set(m[m.metrica == "razao"].territorio_id) == {"NE", *UFS_NE}
    assert "BR" not in set(m.territorio_id) and "SE" not in set(m.territorio_id)


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


def test_crescimento_relativo_so_entre_observacoes_consecutivas_comuns():
    # serie bienal: a variacao e entre edicoes (2002 -> 2004), nao entre anos do calendario
    t = serie_anos({2002: 100, 2004: 120})
    r = crescimento_relativo(t, serie_anos({2002: 100, 2003: 90, 2004: 110}))
    assert r.index.tolist() == [2004] and r.round(6).tolist() == [10.0]


def test_exige_territorios_conhecidos(territorios):
    with pytest.raises(ValueError, match="BR_FORA_NE"):
        metricas_convergencia(base_de({"x": {"NE": 1}}), {"x": ficha("x")}, territorios[territorios.territorio_id != "BR_FORA_NE"])
