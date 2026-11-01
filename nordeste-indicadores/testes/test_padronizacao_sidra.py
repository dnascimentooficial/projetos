import json
from dataclasses import replace

import pandas as pd
import pytest

from nordeste.coletores.registro import Coleta
from nordeste.esquema import COLUNAS_BASE
from nordeste.padronizacao import ErroLayout, padronizar
from nordeste.padronizacao.sidra import padronizar_sidra

CABECALHO = {
    "NC": "Nível Territorial (Código)", "NN": "Nível Territorial",
    "MC": "Unidade de Medida (Código)", "MN": "Unidade de Medida", "V": "Valor",
    "D1C": "Brasil, Grande Região e Unidade da Federação (Código)",
    "D1N": "Brasil, Grande Região e Unidade da Federação",
    "D2C": "Ano (Código)", "D2N": "Ano", "D3C": "Variável (Código)", "D3N": "Variável",
}


def ler(projeto, indicador, serie="scr_ref2010"):
    return (projeto.fixtures / indicador / f"{serie}.json").read_bytes()


def json_sidra(linhas, rotulo_periodo="Ano (Código)"):
    """Monta um JSON SIDRA com cabeçalho; `linhas` são tuplas (NC, D1C, ano, V)."""
    cabecalho = {**CABECALHO, "D2C": rotulo_periodo}
    corpo = [{"NC": nc, "D1C": codigo, "D2C": ano, "V": valor} for nc, codigo, ano, valor in linhas]
    return json.dumps([cabecalho, *corpo]).encode("utf-8")


def test_mapeia_niveis_e_valores(projeto, fichas, territorios):
    f = fichas["amostra_per_capita"]
    df = padronizar_sidra(ler(projeto, "amostra_per_capita"), f, f.serie("scr_ref2010"), "c1", territorios)
    ne_2002 = df[(df.territorio_id == "NE") & (df.ano == 2002)].iloc[0]
    assert ne_2002.valor == 1000.0 and ne_2002.tipo_dado == "observado" and ne_2002.coleta_id == "c1"
    assert set(df.territorio_id) == {"BR", "N", "NE", "SE", "S", "CO", "MA", "PI", "CE", "RN", "PB", "PE", "AL", "SE_UF", "BA"}
    assert list(df.columns) == COLUNAS_BASE
    assert set(df.indicador_id) == {"amostra_per_capita"} and set(df.serie_id) == {"scr_ref2010"}
    assert df.ano.min() == 2002 and df.ano.max() == 2023
    assert not df.duplicated(["territorio_id", "ano"]).any()


def test_codigo_um_depende_do_nivel(fichas, territorios):
    f = fichas["pib_nominal"]
    conteudo = json_sidra([("1", "1", "2002", "7"), ("2", "1", "2002", "8")])
    df = padronizar_sidra(conteudo, f, f.serie("scr_ref2010"), "c1", territorios)
    assert dict(zip(df.territorio_id, df.valor)) == {"BR": 7.0, "N": 8.0}


def test_reticencias_viram_indisponivel(projeto, fichas, territorios):
    f = fichas["amostra_per_capita"]
    df = padronizar_sidra(ler(projeto, "amostra_per_capita"), f, f.serie("scr_ref2010"), "c1", territorios)
    al = df[(df.territorio_id == "AL") & (df.ano == 2010)].iloc[0]
    assert pd.isna(al.valor) and al.tipo_dado == "indisponivel" and al.nota == "SIDRA: ..."
    assert (df[df.tipo_dado != "indisponivel"].nota == "").all()


@pytest.mark.parametrize("simbolo", ["..", "...", "X"])
def test_simbolos_de_indisponibilidade(fichas, territorios, simbolo):
    f = fichas["pib_nominal"]
    df = padronizar_sidra(json_sidra([("3", "26", "2002", simbolo)]), f, f.serie("scr_ref2010"), "c1", territorios)
    assert pd.isna(df.valor.iloc[0]) and df.tipo_dado.iloc[0] == "indisponivel"
    assert df.nota.iloc[0] == f"SIDRA: {simbolo}"


def test_traco_e_zero_e_uf_fora_do_ne_descartada(fichas, territorios):
    conteudo = json_sidra([("3", "26", "2002", "-"), ("3", "35", "2002", "5")])
    f = fichas["pib_nominal"]
    df = padronizar_sidra(conteudo, f, f.serie("scr_ref2010"), "c1", territorios)
    assert df.valor.tolist() == [0.0] and df.territorio_id.tolist() == ["PE"]
    assert df.tipo_dado.tolist() == ["observado"] and df.nota.tolist() == [""]


def test_sem_linhas_devolve_base_vazia(fichas, territorios):
    f = fichas["pib_nominal"]
    df = padronizar_sidra(json_sidra([]), f, f.serie("scr_ref2010"), "c1", territorios)
    assert df.empty and list(df.columns) == COLUNAS_BASE


def test_layout_sem_coluna_de_ano(fichas, territorios):
    f = fichas["pib_nominal"]
    with pytest.raises(ErroLayout, match="coluna de período"):
        padronizar_sidra(json_sidra([], rotulo_periodo="Mês (Código)"), f, f.serie("scr_ref2010"), "c1", territorios)


def test_layout_sem_coluna_de_territorio(fichas, territorios):
    f = fichas["pib_nominal"]
    cabecalho = {**CABECALHO, "D1C": "Município (Código)"}
    with pytest.raises(ErroLayout, match="coluna de território"):
        padronizar_sidra(json.dumps([cabecalho]).encode(), f, f.serie("scr_ref2010"), "c1", territorios)


def test_layout_que_nao_e_lista_sidra(fichas, territorios):
    f = fichas["pib_nominal"]
    for conteudo in (b'{"a": 1}', b"[]", b"nao e json"):
        with pytest.raises(ErroLayout, match="SIDRA"):
            padronizar_sidra(conteudo, f, f.serie("scr_ref2010"), "c1", territorios)


def test_valor_irreconhecivel_e_erro(fichas, territorios):
    f = fichas["pib_nominal"]
    with pytest.raises(ErroLayout, match="valor"):
        padronizar_sidra(json_sidra([("3", "26", "2002", "abc")]), f, f.serie("scr_ref2010"), "c1", territorios)


def test_colunas_sobrescritas_por_parametros(fichas, territorios):
    f = fichas["pib_nominal"]
    cabecalho = {**CABECALHO, "D2C": "Trimestre (Código)", "D4C": "Ano (Código)"}
    linha = {"NC": "3", "D1C": "26", "D2C": "999", "D4C": "2005", "V": "3"}
    conteudo = json.dumps([cabecalho, linha]).encode()
    serie = replace(f.serie("scr_ref2010"), parametros={"coluna_periodo": "D4C", "coluna_territorio": "D1C"})
    df = padronizar_sidra(conteudo, f, serie, "c1", territorios)
    assert df.ano.tolist() == [2005] and df.territorio_id.tolist() == ["PE"]


def test_padronizar_le_o_arquivo_da_coleta(projeto, fichas, territorios):
    f = fichas["amostra_per_capita"]
    s = f.serie("scr_ref2010")
    coleta = Coleta(
        coleta_id="c9", indicador_id=f.id, serie_id=s.id, url="x", data_coleta="2026-11-01",
        sha256="0" * 64, origem="fixture", arquivo="testes/fixtures/amostra_per_capita/scr_ref2010.json",
    )
    df = padronizar(f, s, coleta, projeto, territorios)
    assert set(df.coleta_id) == {"c9"} and len(df) == 15 * 22
    assert (df[df.tipo_dado == "observado"].valor == 1000.0).all()


def test_anos_estimativa(projeto, fichas, territorios):
    f = fichas["amostra_per_capita"]
    s = replace(f.serie("scr_ref2010"), parametros={"anos_estimativa": [2023, 2010]})
    coleta = Coleta(
        coleta_id="c9", indicador_id=f.id, serie_id=s.id, url="x", data_coleta="2026-11-01",
        sha256="0" * 64, origem="fixture", arquivo="testes/fixtures/amostra_per_capita/scr_ref2010.json",
    )
    df = padronizar(f, s, coleta, projeto, territorios)
    assert set(df[df.ano == 2023].tipo_dado) == {"estimativa_oficial"}
    assert set(df[df.ano == 2022].tipo_dado) == {"observado"}
    # indisponível continua indisponível: valor nulo ⇔ indisponivel
    al_2010 = df[(df.territorio_id == "AL") & (df.ano == 2010)].iloc[0]
    assert al_2010.tipo_dado == "indisponivel" and pd.isna(al_2010.valor)
    assert set(df[(df.ano == 2010) & (df.territorio_id != "AL")].tipo_dado) == {"estimativa_oficial"}


def test_padronizador_desconhecido(projeto, fichas, territorios):
    f = fichas["amostra_per_capita"]
    s = replace(f.serie("scr_ref2010"), parametros={"padronizador": "inventado"})
    coleta = Coleta(
        coleta_id="c9", indicador_id=f.id, serie_id=s.id, url="x", data_coleta="2026-11-01",
        sha256="0" * 64, origem="fixture", arquivo="testes/fixtures/amostra_per_capita/scr_ref2010.json",
    )
    with pytest.raises(ErroLayout, match="padronizador desconhecido.*inventado"):
        padronizar(f, s, coleta, projeto, territorios)
