import math

import pandas as pd
import pytest

from nordeste.derivados import brasil_fora_ne
from nordeste.esquema import CHAVE_BASE, COLUNAS_BASE
from nordeste.fichas import Comparacao, Ficha, Serie


def _serie(inicio=2000, fim=2030, serie_id="s"):
    return Serie(
        id=serie_id, inicio=inicio, fim=fim, fonte="f", base_origem="b", url="u",
        coletor="c", parametros={}, compatibilidade="c", verificado=True,
    )


def ficha(id, metodo=None, numerador=None, denominador=None, fator=1.0,
          referencia="brasil_fora_ne", inicio=2000, fim=2030, series=None, auxiliar=False):
    return Ficha(
        id=id, nome=id, descricao="d", eixo="e", categoria="c", unidade="u", orgao="o",
        periodicidade="anual", metodologia="m", observacoes="o", sentido="maior_melhor",
        limites={}, defasagem_meses=0,
        comparacao=Comparacao(referencia, metodo, numerador, denominador, fator),
        series=tuple(series) if series else (_serie(inicio, fim),), auxiliar=auxiliar,
    )


def aux(id):
    return ficha(id, referencia="nenhuma", auxiliar=True)


def _linha(indicador, territorio, ano, valor, coleta=None, serie="s", subindicador="", etapa="", rede=""):
    return {
        "indicador_id": indicador, "subindicador": subindicador, "etapa": etapa, "rede": rede,
        "territorio_id": territorio, "ano": ano, "valor": valor,
        "tipo_dado": "indisponivel" if valor is None else "observado",
        "serie_id": serie, "coleta_id": coleta or f"c.{indicador}.{territorio}", "nota": "",
    }


def _base(linhas):
    return pd.DataFrame(linhas, columns=COLUNAS_BASE)


def base_de(valores, coletas=None, ano=2002):
    return base_anos({i: {ano: t} for i, t in valores.items()}, coletas)


def base_anos(valores, coletas=None):
    coletas = coletas or {}
    return _base([
        _linha(i, t, ano, v, coletas.get(t))
        for i, anos in valores.items() for ano, terr in anos.items() for t, v in terr.items()
    ])


def test_soma():
    out, _ = brasil_fora_ne(base_de({"x": {"BR": 10, "NE": 4}}), {"x": ficha("x", "soma")})
    assert out.valor.tolist() == [6.0] and out.tipo_dado.tolist() == ["derivado"]


def test_razao_com_fator():
    b = base_de({"num": {"BR": 100, "NE": 30}, "den": {"BR": 50, "NE": 10}, "pc": {"BR": 2, "NE": 3}})
    out, _ = brasil_fora_ne(b, {"pc": ficha("pc", "razao", "num", "den", fator=1000), "num": aux("num"), "den": aux("den")})
    assert out[out.indicador_id == "pc"].valor.tolist() == [1750.0]


def test_razao_encadeada():
    b = base_anos({"num": {2003: {"BR": 108, "NE": 20}}, "den": {2002: {"BR": 100, "NE": 20}}, "vol": {}})
    fichas = {
        "vol": ficha("vol", "razao_encadeada", "num", "den", inicio=2002),
        "num": aux("num"), "den": aux("den"),
    }
    out, _ = brasil_fora_ne(b, fichas)
    assert out.set_index("ano").valor.to_dict() == {2002: 100.0, 2003: 110.0}


def test_sem_metodo_exato_nao_gera():
    out, _ = brasil_fora_ne(base_de({"ideb": {"BR": 5, "NE": 4}}), {"ideb": ficha("ideb", referencia="brasil")})
    assert out.empty


def test_registro_lista_insumos():
    _, reg = brasil_fora_ne(base_de({"x": {"BR": 10, "NE": 4}}, coletas={"BR": "cA", "NE": "cB"}), {"x": ficha("x", "soma")})
    assert reg.insumos.tolist() == ["cA;cB"] and reg.coleta_id.iloc[0].startswith("deriv.x.s.")


def test_formato_da_base_e_coleta_da_derivacao():
    b = base_de({"x": {"BR": 10, "NE": 4}}, coletas={"BR": "cA", "NE": "cB"})
    out, reg = brasil_fora_ne(b, {"x": ficha("x", "soma")})
    assert list(out.columns) == COLUNAS_BASE
    assert list(reg.columns) == ["coleta_id", "indicador_id", "serie_id", "insumos"]
    linha = out.iloc[0]
    assert (linha.territorio_id, linha.serie_id, linha.nota) == ("BR_FORA_NE", "s", "")
    assert linha.coleta_id == reg.coleta_id.iloc[0]
    assert len(linha.coleta_id.rsplit(".", 1)[1]) == 8


def test_coleta_id_muda_quando_os_insumos_mudam():
    fichas = {"x": ficha("x", "soma")}
    _, r1 = brasil_fora_ne(base_de({"x": {"BR": 10, "NE": 4}}, coletas={"BR": "cA", "NE": "cB"}), fichas)
    _, r2 = brasil_fora_ne(base_de({"x": {"BR": 10, "NE": 4}}, coletas={"BR": "cA", "NE": "cC"}), fichas)
    assert r1.coleta_id.iloc[0] != r2.coleta_id.iloc[0]


def test_soma_herda_grupo_e_so_com_os_dois_valores():
    b = _base([
        _linha("x", "BR", 2002, 10, subindicador="a", etapa="e1", rede="publica"),
        _linha("x", "NE", 2002, 4, subindicador="a", etapa="e1", rede="publica"),
        _linha("x", "BR", 2002, 9, subindicador="b"),
        _linha("x", "NE", 2002, None, subindicador="b"),
        _linha("x", "BR", 2003, 7),
        _linha("x", "SE", 2003, 1),
    ])
    out, _ = brasil_fora_ne(b, {"x": ficha("x", "soma")})
    assert len(out) == 1
    linha = out.iloc[0]
    assert (linha.subindicador, linha.etapa, linha.rede, linha.valor) == ("a", "e1", "publica", 6.0)


def test_soma_nao_atravessa_serie():
    b = _base([_linha("x", "BR", 2002, 10, serie="a"), _linha("x", "NE", 2002, 4, serie="b")])
    series = [_serie(serie_id="a"), _serie(serie_id="b")]
    out, reg = brasil_fora_ne(b, {"x": ficha("x", "soma", series=series)})
    assert out.empty and reg.empty


def test_soma_uma_linha_de_registro_por_serie():
    b = _base([
        _linha("x", "BR", 2002, 10, serie="a"), _linha("x", "NE", 2002, 4, serie="a"),
        _linha("x", "BR", 2003, 12, serie="a"), _linha("x", "NE", 2003, 5, serie="a"),
        _linha("x", "BR", 2010, 20, serie="b"), _linha("x", "NE", 2010, 8, serie="b"),
    ])
    series = [_serie(2000, 2005, "a"), _serie(2006, 2030, "b")]
    out, reg = brasil_fora_ne(b, {"x": ficha("x", "soma", series=series)})
    assert len(out) == 3
    assert sorted(reg.serie_id) == ["a", "b"]
    assert reg.coleta_id.nunique() == 2
    assert set(out.coleta_id) == set(reg.coleta_id)


def test_razao_ano_sem_serie_nao_gera_linha():
    b = base_de({"num": {"BR": 100, "NE": 30}, "den": {"BR": 50, "NE": 10}}, ano=2002)
    fichas = {"pc": ficha("pc", "razao", "num", "den", inicio=2010), "num": aux("num"), "den": aux("den")}
    out, reg = brasil_fora_ne(b, fichas)
    assert out.empty and reg.empty


def test_razao_insumos_sao_os_quatro_coletas_ordenados():
    b = base_de(
        {"num": {"BR": 100, "NE": 30}, "den": {"BR": 50, "NE": 10}},
        coletas={"BR": "cZ", "NE": "cA"},
    )
    fichas = {"pc": ficha("pc", "razao", "num", "den"), "num": aux("num"), "den": aux("den")}
    out, reg = brasil_fora_ne(b, fichas)
    assert out.valor.tolist() == [1.75]
    assert reg.insumos.tolist() == ["cA;cZ"]


def test_razao_ignora_denominador_zero_e_valor_indisponivel():
    b = _base([
        _linha("num", "BR", 2002, 100), _linha("num", "NE", 2002, 30),
        _linha("den", "BR", 2002, 10), _linha("den", "NE", 2002, 10),
        _linha("num", "BR", 2003, 100), _linha("num", "NE", 2003, 30),
        _linha("den", "BR", 2003, 50), _linha("den", "NE", 2003, None),
    ])
    fichas = {"pc": ficha("pc", "razao", "num", "den"), "num": aux("num"), "den": aux("den")}
    out, _ = brasil_fora_ne(b, fichas)
    assert out.empty


def _duas_series():
    return [_serie(2000, 2030, "a"), _serie(2000, 2030, "b")]


def test_razao_com_series_sobrepostas_gera_uma_linha_por_serie():
    b = _base([
        _linha("num", "BR", 2002, 100, serie="a"), _linha("num", "NE", 2002, 30, serie="a"),
        _linha("den", "BR", 2002, 50, serie="a"), _linha("den", "NE", 2002, 10, serie="a"),
        _linha("num", "BR", 2002, 200, serie="b"), _linha("num", "NE", 2002, 40, serie="b"),
        _linha("den", "BR", 2002, 60, serie="b"), _linha("den", "NE", 2002, 20, serie="b"),
    ])
    fichas = {
        "pc": ficha("pc", "razao", "num", "den", series=_duas_series()),
        "num": aux("num"), "den": aux("den"),
    }
    out, reg = brasil_fora_ne(b, fichas)
    assert out.set_index("serie_id").valor.to_dict() == {"a": 1.75, "b": 4.0}
    assert sorted(reg.serie_id) == ["a", "b"]
    assert reg.coleta_id.nunique() == 2


def test_razao_ignora_serie_do_termo_que_a_ficha_nao_declara_ou_nao_cobre():
    b = _base([
        _linha("num", "BR", 2002, 100, serie="a"), _linha("num", "NE", 2002, 30, serie="a"),
        _linha("den", "BR", 2002, 50, serie="a"), _linha("den", "NE", 2002, 10, serie="a"),
        _linha("num", "BR", 2002, 200, serie="b"), _linha("num", "NE", 2002, 40, serie="b"),
        _linha("den", "BR", 2002, 60, serie="b"), _linha("den", "NE", 2002, 20, serie="b"),
        _linha("num", "BR", 2002, 200, serie="c"), _linha("num", "NE", 2002, 40, serie="c"),
        _linha("den", "BR", 2002, 60, serie="c"), _linha("den", "NE", 2002, 20, serie="c"),
    ])
    series = [_serie(2000, 2030, "a"), _serie(2010, None, "b")]
    fichas = {"pc": ficha("pc", "razao", "num", "den", series=series), "num": aux("num"), "den": aux("den")}
    out, _ = brasil_fora_ne(b, fichas)
    assert out.serie_id.tolist() == ["a"]


def test_razao_nao_junta_termos_de_series_diferentes():
    b = _base([
        _linha("num", "BR", 2002, 100, serie="a"), _linha("num", "NE", 2002, 30, serie="a"),
        _linha("den", "BR", 2002, 50, serie="b"), _linha("den", "NE", 2002, 10, serie="b"),
    ])
    fichas = {
        "pc": ficha("pc", "razao", "num", "den", series=_duas_series()),
        "num": aux("num"), "den": aux("den"),
    }
    out, _ = brasil_fora_ne(b, fichas)
    assert out.empty


def test_razao_junta_por_grupo():
    b = _base([
        _linha("num", "BR", 2002, 100, subindicador="u"), _linha("num", "NE", 2002, 30, subindicador="u"),
        _linha("den", "BR", 2002, 50, subindicador="u"), _linha("den", "NE", 2002, 10, subindicador="u"),
        _linha("num", "BR", 2002, 200, subindicador="v"), _linha("num", "NE", 2002, 40, subindicador="v"),
        _linha("den", "BR", 2002, 60, subindicador="v"), _linha("den", "NE", 2002, 20, subindicador="v"),
    ])
    fichas = {"pc": ficha("pc", "razao", "num", "den"), "num": aux("num"), "den": aux("den")}
    out, _ = brasil_fora_ne(b, fichas)
    assert out.set_index("subindicador").valor.to_dict() == {"u": 1.75, "v": 4.0}


def test_razao_nao_junta_termos_de_grupos_diferentes():
    b = _base([
        _linha("num", "BR", 2002, 100, subindicador="u"), _linha("num", "NE", 2002, 30, subindicador="u"),
        _linha("den", "BR", 2002, 50, subindicador="v"), _linha("den", "NE", 2002, 10, subindicador="v"),
    ])
    fichas = {"pc": ficha("pc", "razao", "num", "den"), "num": aux("num"), "den": aux("den")}
    out, _ = brasil_fora_ne(b, fichas)
    assert out.empty


def _fichas_vol(inicio=2002, fim=2030):
    return {
        "vol": ficha("vol", "razao_encadeada", "num", "den", inicio=inicio, fim=fim),
        "num": aux("num"), "den": aux("den"),
    }


def _termos(num, den):
    return base_anos({
        "num": {a: {"BR": b, "NE": n} for a, (b, n) in num.items()},
        "den": {a: {"BR": b, "NE": n} for a, (b, n) in den.items()},
    })


def test_encadeada_tres_anos_acumula_fatores():
    b = _termos(
        num={2003: (108, 20), 2004: (150, 30)},
        den={2002: (100, 20), 2003: (110, 22)},
    )
    out, _ = brasil_fora_ne(b, _fichas_vol())
    esperado = {2002: 100.0, 2003: 110.0, 2004: 110.0 * 120 / 88}
    obtido = out.set_index("ano").valor.to_dict()
    assert obtido.keys() == esperado.keys()
    for ano, valor in esperado.items():
        assert math.isclose(obtido[ano], valor)


def test_encadeada_para_no_primeiro_ano_sem_fator():
    b = _termos(
        num={2003: (108, 20), 2005: (200, 40)},
        den={2002: (100, 20), 2003: (110, 22), 2004: (120, 24)},
    )
    out, _ = brasil_fora_ne(b, _fichas_vol())
    assert out.ano.tolist() == [2002, 2003]


def test_encadeada_comeca_no_primeiro_ano_com_denominador():
    b = _termos(
        num={2004: (108, 20)},
        den={2003: (100, 20), 2004: (110, 22)},
    )
    out, _ = brasil_fora_ne(b, _fichas_vol(inicio=2002))
    assert out.set_index("ano").valor.to_dict() == {2003: 100.0, 2004: pytest.approx(110.0)}


def test_encadeada_sem_denominador_nao_gera():
    b = _termos(num={2003: (108, 20)}, den={})
    out, reg = brasil_fora_ne(b, _fichas_vol())
    assert out.empty and reg.empty


def test_encadeada_respeita_o_fim_da_serie():
    b = _termos(
        num={2003: (108, 20), 2004: (150, 30)},
        den={2002: (100, 20), 2003: (110, 22)},
    )
    out, _ = brasil_fora_ne(b, _fichas_vol(fim=2003))
    assert out.ano.tolist() == [2002, 2003]


def test_encadeada_reinicia_em_cada_serie():
    b = _base([
        _linha("den", "BR", 2002, 100, serie="a"), _linha("den", "NE", 2002, 20, serie="a"),
        _linha("num", "BR", 2003, 108, serie="a"), _linha("num", "NE", 2003, 20, serie="a"),
        _linha("den", "BR", 2010, 100, serie="b"), _linha("den", "NE", 2010, 20, serie="b"),
        _linha("num", "BR", 2011, 130, serie="b"), _linha("num", "NE", 2011, 30, serie="b"),
    ])
    series = [_serie(2002, 2009, "a"), _serie(2010, 2030, "b")]
    fichas = {
        "vol": ficha("vol", "razao_encadeada", "num", "den", series=series),
        "num": aux("num"), "den": aux("den"),
    }
    out, reg = brasil_fora_ne(b, fichas)
    por_serie = {s: g.set_index("ano").valor.to_dict() for s, g in out.groupby("serie_id")}
    assert por_serie == {"a": {2002: 100.0, 2003: pytest.approx(110.0)}, "b": {2010: 100.0, 2011: pytest.approx(125.0)}}
    assert sorted(reg.serie_id) == ["a", "b"]


def test_encadeada_so_encadeia_dentro_da_mesma_serie():
    b = _base([
        _linha("den", "BR", 2002, 100, serie="a"), _linha("den", "NE", 2002, 20, serie="a"),
        _linha("num", "BR", 2003, 108, serie="b"), _linha("num", "NE", 2003, 20, serie="b"),
    ])
    fichas = {
        "vol": ficha("vol", "razao_encadeada", "num", "den", series=_duas_series()),
        "num": aux("num"), "den": aux("den"),
    }
    out, _ = brasil_fora_ne(b, fichas)
    assert out.set_index("serie_id").ano.to_dict() == {"a": 2002} and out.valor.tolist() == [100.0]


def test_encadeada_series_sobrepostas_geram_uma_cadeia_por_serie():
    b = _base([
        _linha("den", "BR", 2002, 100, serie="a"), _linha("den", "NE", 2002, 20, serie="a"),
        _linha("num", "BR", 2003, 108, serie="a"), _linha("num", "NE", 2003, 20, serie="a"),
        _linha("den", "BR", 2002, 200, serie="b"), _linha("den", "NE", 2002, 40, serie="b"),
        _linha("num", "BR", 2003, 340, serie="b"), _linha("num", "NE", 2003, 40, serie="b"),
    ])
    fichas = {
        "vol": ficha("vol", "razao_encadeada", "num", "den", series=_duas_series()),
        "num": aux("num"), "den": aux("den"),
    }
    out, _ = brasil_fora_ne(b, fichas)
    por_serie = {s: g.set_index("ano").valor.to_dict() for s, g in out.groupby("serie_id")}
    assert por_serie == {"a": {2002: 100.0, 2003: pytest.approx(110.0)}, "b": {2002: 100.0, 2003: pytest.approx(187.5)}}


def test_encadeada_junta_por_grupo():
    b = _base([
        _linha("den", "BR", 2002, 100, subindicador="u"), _linha("den", "NE", 2002, 20, subindicador="u"),
        _linha("num", "BR", 2003, 108, subindicador="u"), _linha("num", "NE", 2003, 20, subindicador="u"),
        _linha("den", "BR", 2002, 200, subindicador="v"), _linha("den", "NE", 2002, 40, subindicador="v"),
        _linha("num", "BR", 2003, 340, subindicador="v"), _linha("num", "NE", 2003, 40, subindicador="v"),
        _linha("num", "BR", 2003, 999, subindicador="w"), _linha("num", "NE", 2003, 1, subindicador="w"),
    ])
    out, _ = brasil_fora_ne(b, _fichas_vol())
    por_grupo = {s: g.set_index("ano").valor.to_dict() for s, g in out.groupby("subindicador")}
    assert por_grupo == {"u": {2002: 100.0, 2003: pytest.approx(110.0)}, "v": {2002: 100.0, 2003: pytest.approx(187.5)}}


def test_encadeada_insumos_da_cadeia():
    b = _termos(num={2003: (108, 20)}, den={2002: (100, 20), 2003: (110, 22)})
    b["coleta_id"] = b.indicador_id + "." + b.territorio_id + "." + b.ano.astype(str)
    _, reg = brasil_fora_ne(b, _fichas_vol())
    esperado = sorted({
        "den.BR.2002", "den.NE.2002", "num.BR.2003", "num.NE.2003",
    })
    assert reg.insumos.tolist() == [";".join(esperado)]
    assert len(reg) == 1


def test_saida_ordenada_pela_chave_e_sem_duplicidade():
    b = base_anos({"x": {2003: {"BR": 10, "NE": 4}, 2002: {"BR": 9, "NE": 3}}})
    out, _ = brasil_fora_ne(b, {"x": ficha("x", "soma")})
    assert out.ano.tolist() == [2002, 2003]
    assert not out.duplicated(CHAVE_BASE).any()


def test_sem_fichas_aplicaveis_devolve_vazio_com_colunas():
    out, reg = brasil_fora_ne(base_de({"x": {"BR": 10, "NE": 4}}), {})
    assert out.empty and list(out.columns) == COLUNAS_BASE
    assert reg.empty and list(reg.columns) == ["coleta_id", "indicador_id", "serie_id", "insumos"]
