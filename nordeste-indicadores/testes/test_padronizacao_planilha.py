import io
import zipfile
from dataclasses import replace

import pandas as pd
import pytest
from gerar_fixtures import xls_sintetico as montar_xls
from gerar_fixtures import xlsx_sintetico as montar_xlsx

from nordeste.coletores.registro import Coleta
from nordeste.esquema import COLUNAS_BASE
from nordeste.padronizacao import ErroLayout, padronizar
from nordeste.padronizacao.planilha import numero_br, padronizar_planilha

ABA = "Dados"
CABECALHO = ["Território", "IDEB 2019", "IDEB 2021", "IDEB 2023"]
LINHAS = [
    ["Piauí", 99999, 99998.5, "--"],
    ["Ceará*", "1.234,5", 7, 8],
    ["Bahia (1)", 3, "x", None],
    ["Total", 1, 1, 1],
    ["Brasil", 5, 6, 7],
]
COLUNAS = [
    {"coluna": "IDEB 2019", "ano": 2019, "subindicador": "ideb", "etapa": "anos_iniciais", "rede": "publica"},
    {"coluna": "IDEB 2021", "ano": 2021, "subindicador": "ideb", "etapa": "anos_iniciais", "rede": "publica"},
    {"coluna": "IDEB 2023", "ano": 2023, "subindicador": "ideb", "etapa": "anos_iniciais", "rede": "publica"},
]
PARAMETROS = {
    "formato": "xlsx", "aba": ABA, "linha_cabecalho": 3, "coluna_territorio": "Território",
    "colunas": COLUNAS,
}


def xlsx_sintetico(cabecalho=CABECALHO, linhas=LINHAS) -> bytes:
    """Planilha com título e linha em branco antes do cabeçalho (linha 3)."""
    posicoes = [CABECALHO.index(c) for c in cabecalho]
    corpo = [[linha[i] for i in posicoes] for linha in linhas]
    return montar_xlsx(ABA, [["Indicador sintético"], [], cabecalho, *corpo])


def xlsx_sem_coluna(coluna: str) -> bytes:
    return xlsx_sintetico([c for c in CABECALHO if c != coluna])


@pytest.fixture
def ficha_planilha(fichas):
    ficha = fichas["pib_nominal"]
    serie = replace(ficha.series[0], coletor="arquivo", parametros=dict(PARAMETROS))
    return replace(ficha, series=(serie,))


def com_parametros(ficha, **extra):
    serie = replace(ficha.series[0], parametros={**ficha.series[0].parametros, **extra})
    return replace(ficha, series=(serie,)), serie


@pytest.mark.parametrize("entrada,esperado", [
    ("1.234,5", 1234.5), ("12", 12.0), (3.5, 3.5), (7, 7.0), (" 1.000.000 ", 1000000.0),
    ("-", None), ("--", None), ("...", None), ("…", None), ("x", None), ("X", None),
    ("1.234", 1234.0), ("12.345.678", 12345678.0), ("-1.234,5", -1234.5), ("3,5", 3.5),
    ("", None), ("  ", None), ("n/d", None), ("N/D", None), (float("nan"), None), (None, None),
])
def test_numero_br(entrada, esperado):
    assert numero_br(entrada) == esperado


@pytest.mark.parametrize("entrada", ["abc", "12a", float("inf"), "1,2,3", True, "3.5", "1.23", "12.3456", "1.2345,6", ".5", "1.234.56"])
def test_numero_br_irreconhecivel(entrada):
    with pytest.raises(ValueError):
        numero_br(entrada)


def test_planilha_xlsx_por_nome_de_territorio(projeto, ficha_planilha, territorios):
    df = padronizar_planilha(xlsx_sintetico(), ficha_planilha, ficha_planilha.series[0], "c1", territorios)
    assert df.query("territorio_id == 'PI' and ano == 2019").valor.tolist() == [99999.0]
    assert df.query("valor.isna()").tipo_dado.unique().tolist() == ["indisponivel"]
    assert list(df.columns) == COLUNAS_BASE
    pi = df[(df.territorio_id == "PI") & (df.ano == 2019)].iloc[0]
    assert (pi.indicador_id, pi.subindicador, pi.etapa, pi.rede) == (
        "pib_nominal", "ideb", "anos_iniciais", "publica")
    assert (pi.serie_id, pi.coleta_id, pi.tipo_dado, pi.nota) == ("scr_ref2010", "c1", "observado", "")


def test_marcadores_de_ausencia_viram_indisponivel_com_nota(ficha_planilha, territorios):
    df = padronizar_planilha(xlsx_sintetico(), ficha_planilha, ficha_planilha.series[0], "c1", territorios)
    ausentes = df[df.valor.isna()].set_index(["territorio_id", "ano"])
    assert ausentes.nota.to_dict() == {
        ("PI", 2023): "Planilha: --", ("BA", 2021): "Planilha: x", ("BA", 2023): "Planilha: vazio"}
    assert (df[df.valor.notna()].tipo_dado == "observado").all()


def test_notas_de_rodape_e_linhas_sem_territorio(ficha_planilha, territorios):
    df = padronizar_planilha(xlsx_sintetico(), ficha_planilha, ficha_planilha.series[0], "c1", territorios)
    assert set(df.territorio_id) == {"PI", "CE", "BA", "BR"}  # "Ceará*" e "Bahia (1)" casam; "Total" cai
    assert df.query("territorio_id == 'CE' and ano == 2019").valor.tolist() == [1234.5]
    assert len(df) == 4 * 3


def test_planilha_dentro_de_zip(ficha_planilha, territorios):
    direto = padronizar_planilha(xlsx_sintetico(), ficha_planilha, ficha_planilha.series[0], "c1", territorios)
    pacote = io.BytesIO()
    with zipfile.ZipFile(pacote, "w") as z:
        z.writestr("leia-me.txt", "outro arquivo")
        z.writestr("dados/ideb.xlsx", xlsx_sintetico())
    ficha, serie = com_parametros(ficha_planilha, arquivo_no_zip="dados/ideb.xlsx")
    do_zip = padronizar_planilha(pacote.getvalue(), ficha, serie, "c1", territorios)
    pd.testing.assert_frame_equal(do_zip, direto)


def test_zip_sem_o_arquivo_citado(ficha_planilha, territorios):
    pacote = io.BytesIO()
    with zipfile.ZipFile(pacote, "w") as z:
        z.writestr("outro.xlsx", xlsx_sintetico())
    ficha, serie = com_parametros(ficha_planilha, arquivo_no_zip="dados/ideb.xlsx")
    with pytest.raises(ErroLayout, match="dados/ideb.xlsx"):
        padronizar_planilha(pacote.getvalue(), ficha, serie, "c1", territorios)
    with pytest.raises(ErroLayout, match="zip ilegível"):
        padronizar_planilha(b"nao e zip", ficha, serie, "c1", territorios)


def test_planilha_csv(ficha_planilha, territorios):
    texto = "Indicador sintético\n\nTerritório;IDEB 2019;IDEB 2021;IDEB 2023\nPiauí;99999;\"1.234,5\";...\nTotal;1;1;1\n"
    ficha, serie = com_parametros(ficha_planilha, formato="csv")
    df = padronizar_planilha(texto.encode("utf-8"), ficha, serie, "c1", territorios)
    assert df.set_index("ano").valor.dropna().to_dict() == {2019: 99999.0, 2021: 1234.5}
    assert df.query("ano == 2023").tipo_dado.tolist() == ["indisponivel"]
    ficha, serie = com_parametros(ficha_planilha, formato="csv", separador=",", codificacao="latin-1")
    latin1 = "x\n\nTerritório,IDEB 2019,IDEB 2021,IDEB 2023\nPiauí,5,6,7\n".encode("latin-1")
    assert padronizar_planilha(latin1, ficha, serie, "c1", territorios).valor.tolist() == [5.0, 6.0, 7.0]


def test_planilha_coluna_ausente(ficha_planilha, territorios):
    with pytest.raises(ErroLayout, match="IDEB 2023"):
        padronizar_planilha(xlsx_sem_coluna("IDEB 2023"), ficha_planilha, ficha_planilha.series[0], "c1", territorios)


def test_erro_de_layout_cita_arquivo_aba_e_coluna(ficha_planilha, territorios):
    ficha, serie = com_parametros(ficha_planilha, arquivo_no_zip="ideb.xlsx")
    pacote = io.BytesIO()
    with zipfile.ZipFile(pacote, "w") as z:
        z.writestr("ideb.xlsx", xlsx_sem_coluna("IDEB 2023"))
    with pytest.raises(ErroLayout, match=r"ideb\.xlsx.*aba Dados.*'IDEB 2023'"):
        padronizar_planilha(pacote.getvalue(), ficha, serie, "c1", territorios)


def test_planilha_sem_coluna_de_territorio(ficha_planilha, territorios):
    ficha, serie = com_parametros(ficha_planilha, coluna_territorio="Município")
    with pytest.raises(ErroLayout, match="Município"):
        padronizar_planilha(xlsx_sintetico(), ficha, serie, "c1", territorios)


def test_aba_inexistente_e_formato_desconhecido(ficha_planilha, territorios):
    ficha, serie = com_parametros(ficha_planilha, aba="Outra")
    with pytest.raises(ErroLayout, match="aba Outra"):
        padronizar_planilha(xlsx_sintetico(), ficha, serie, "c1", territorios)
    ficha, serie = com_parametros(ficha_planilha, formato="ods")
    with pytest.raises(ErroLayout, match="formato desconhecido"):
        padronizar_planilha(xlsx_sintetico(), ficha, serie, "c1", territorios)


def test_valor_irreconhecivel_e_erro_de_layout(ficha_planilha, territorios):
    conteudo = xlsx_sintetico(linhas=[["Piauí", "abc", 1, 1]])
    with pytest.raises(ErroLayout, match="'IDEB 2019'.*abc"):
        padronizar_planilha(conteudo, ficha_planilha, ficha_planilha.series[0], "c1", territorios)


def test_planilha_sem_linhas_de_territorio_devolve_base_vazia(ficha_planilha, territorios):
    conteudo = xlsx_sintetico(linhas=[["Total", 1, 1, 1]])
    df = padronizar_planilha(conteudo, ficha_planilha, ficha_planilha.series[0], "c1", territorios)
    assert df.empty and list(df.columns) == COLUNAS_BASE


def test_padronizar_despacha_para_planilha(projeto, ficha_planilha, territorios):
    serie = replace(ficha_planilha.series[0], parametros={**PARAMETROS, "padronizador": "planilha", "anos_estimativa": [2021]})
    relativo = "dados/brutos/x/y/abc.xlsx"
    (projeto.raiz / relativo).parent.mkdir(parents=True)
    (projeto.raiz / relativo).write_bytes(xlsx_sintetico())
    coleta = Coleta(
        coleta_id="c9", indicador_id="pib_nominal", serie_id=serie.id, url="x", data_coleta="2026-11-01",
        sha256="0" * 64, origem="fixture", arquivo=relativo,
    )
    df = padronizar(ficha_planilha, serie, coleta, projeto, territorios)
    assert set(df.coleta_id) == {"c9"}
    assert set(df[(df.ano == 2021) & df.valor.notna()].tipo_dado) == {"estimativa_oficial"}
    assert set(df[df.valor.isna()].tipo_dado) == {"indisponivel"}


def test_coluna_inteira_no_yaml_casa_cabecalho(ficha_planilha, territorios):
    conteudo = montar_xlsx(ABA, [["Indicador sintético"], [], ["Território", 2019, 2021], ["Piauí", 99999, "x"]])
    colunas = [{"coluna": 2019, "ano": 2019}, {"coluna": 2021, "ano": 2021}]
    ficha, serie = com_parametros(ficha_planilha, colunas=colunas)
    df = padronizar_planilha(conteudo, ficha, serie, "c1", territorios)
    assert df.set_index("ano").valor.dropna().to_dict() == {2019: 99999.0}
    assert df.query("ano == 2021").tipo_dado.tolist() == ["indisponivel"]
    ficha, serie = com_parametros(ficha_planilha, colunas=[{"coluna": 2030, "ano": 2030}])
    with pytest.raises(ErroLayout, match="'2030'"):
        padronizar_planilha(conteudo, ficha, serie, "c1", territorios)


# Planilhas .xls (formato antigo do IBGE): mesma tabela de teste, gravada em BIFF8.
def xls_sintetico() -> bytes:
    posicoes = range(len(CABECALHO))
    corpo = [[linha[i] for i in posicoes] for linha in LINHAS]
    return montar_xls(ABA, [["Indicador sintético"], [], CABECALHO, *corpo])


def test_planilha_xls_equivale_ao_xlsx(ficha_planilha, territorios):
    xlsx = padronizar_planilha(xlsx_sintetico(), ficha_planilha, ficha_planilha.series[0], "c1", territorios)
    ficha, serie = com_parametros(ficha_planilha, formato="xls")
    xls = padronizar_planilha(xls_sintetico(), ficha, serie, "c1", territorios)
    pd.testing.assert_frame_equal(xls, xlsx)
    assert xls.query("territorio_id == 'CE' and ano == 2019").valor.tolist() == [1234.5]


def test_planilha_xls_dentro_de_zip(ficha_planilha, territorios):
    ficha, serie = com_parametros(ficha_planilha, formato="xls")
    direto = padronizar_planilha(xls_sintetico(), ficha, serie, "c1", territorios)
    pacote = io.BytesIO()
    with zipfile.ZipFile(pacote, "w") as z:
        z.writestr("tab03.xls", xls_sintetico())
    ficha, serie = com_parametros(ficha_planilha, formato="xls", arquivo_no_zip="tab03.xls")
    do_zip = padronizar_planilha(pacote.getvalue(), ficha, serie, "c1", territorios)
    pd.testing.assert_frame_equal(do_zip, direto)


def test_planilha_xls_com_layout_do_ibge(ficha_planilha, territorios):
    """Tabela 3 das Contas Regionais: canto do cabecalho vazio, anos numericos, nomes recuados."""
    conteudo = montar_xls("Tabela3", [
        ["Tabela 3 - Série encadeada do volume"], [], ["Brasil,\nGrandes Regiões", "Série encadeada"],
        [None, 2002, 2003],
        ["Brasil", 100, 99999],
        ["  Nordeste", 100, 101.5],
        ["    Sergipe", 100, "..."],
        ["Fonte: IBGE"],
    ])
    colunas = [{"coluna": 2002, "ano": 2002}, {"coluna": 2003, "ano": 2003}]
    ficha, serie = com_parametros(
        ficha_planilha, formato="xls", aba="Tabela3", linha_cabecalho=4,
        coluna_territorio="Unnamed: 0", colunas=colunas)
    df = padronizar_planilha(conteudo, ficha, serie, "c1", territorios)
    assert df.set_index(["territorio_id", "ano"]).valor.dropna().to_dict() == {
        ("BR", 2002): 100.0, ("BR", 2003): 99999.0, ("NE", 2002): 100.0, ("NE", 2003): 101.5,
        ("SE_UF", 2002): 100.0}
    assert df.query("territorio_id == 'SE_UF' and ano == 2003").tipo_dado.tolist() == ["indisponivel"]


def test_planilha_xls_ilegivel_e_erro_de_layout(ficha_planilha, territorios):
    ficha, serie = com_parametros(ficha_planilha, formato="xls")
    with pytest.raises(ErroLayout, match="não foi possível ler"):
        padronizar_planilha(b"isto nao e uma planilha", ficha, serie, "c1", territorios)
    ficha, serie = com_parametros(ficha_planilha, formato="xls", aba="Outra")
    with pytest.raises(ErroLayout, match="aba Outra"):
        padronizar_planilha(xls_sintetico(), ficha, serie, "c1", territorios)


# ---------------------------------------------------------------------------
# Series com partes: varias planilhas (arquivos ou abas) lidas uma a uma e concatenadas
# ---------------------------------------------------------------------------

URL_UFS = "https://download.inep.gov.br/ideb/ufs.zip"
URL_BRASIL = "https://download.inep.gov.br/ideb/brasil.xlsx"
TERRITORIO_UF = "Região/\nUnidade da Federação"
CABECALHO_IDEB = [TERRITORIO_UF, "Rede", "IDEB\n2019", "IDEB\n20215"]  # rotulo de 2021 com chamada de nota


def _linhas_ufs(base: float) -> list[list]:
    return [
        ["Ensino Fundamental (sintético)"], [], CABECALHO_IDEB,
        ["Nordeste", "Total", base, base + 1],
        ["Nordeste", "Pública", 1, 1],
        ["Bahia", "Total (3)(4)", base + 2, "-"],
        ["Bahia", "Privada (1)", 9, 9],
        ["R. G. do Norte", "Total (4)", base + 3, base + 4],
        ["Ceará (2)", "Total (4)", base + 5, base + 6],
        ["(1) Nota de rodapé sem território."],
    ]


def _pacote_ideb() -> bytes:
    from gerar_fixtures import xlsx_abas

    from nordeste.coletores.arquivo import empacotar_partes
    ufs = xlsx_abas({"AI": _linhas_ufs(4.0), "AF": _linhas_ufs(3.0)})
    brasil = xlsx_abas({"Brasil": [
        ["Brasil (sintético)"], [], ["Brasil", "Rede", "IDEB\n2019", "IDEB\n20212"],
        ["BRASIL", "rede", "VL_OBSERVADO_2019", "VL_OBSERVADO_2021"],  # linha de codigos: o filtro descarta
        ["Brasil", "Total", 5.5, 5.6], ["Brasil", "Privada (1)", 7, 7],
    ]})
    return empacotar_partes({URL_UFS: pacote_zip("ideb/ufs.xlsx", ufs), URL_BRASIL: brasil})


def pacote_zip(nome: str, conteudo: bytes) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr(nome, conteudo)
    return saida.getvalue()


def _parte_uf(aba: str, subindicador: str, **extra) -> dict:
    return {
        "url": URL_UFS, "formato": "xlsx", "arquivo_no_zip": "ideb/ufs.xlsx", "aba": aba, "linha_cabecalho": 3,
        "coluna_territorio": TERRITORIO_UF, "filtro_linhas": {"Rede": "Total"},
        "nomes_territorio": {"R. G. do Norte": "RN"},
        "colunas": [
            {"coluna": "IDEB\n2019", "ano": 2019, "subindicador": subindicador, "rede": "total"},
            {"coluna": "IDEB\n20215", "ano": 2021, "subindicador": subindicador, "rede": "total"},
        ], **extra,
    }


PARTE_BRASIL = {
    "url": URL_BRASIL, "formato": "xlsx", "aba": "Brasil", "linha_cabecalho": 3, "coluna_territorio": "Brasil",
    "filtro_linhas": {"Rede": "total"},
    "colunas": [
        {"coluna": "IDEB\n2019", "ano": 2019, "subindicador": "anos_iniciais", "rede": "total"},
        {"coluna": "IDEB\n20212", "ano": 2021, "subindicador": "anos_iniciais", "rede": "total"},
    ],
}


def _com_partes(ficha, partes):
    serie = replace(ficha.series[0], parametros={"padronizador": "planilha", "partes": partes})
    return replace(ficha, series=(serie,)), serie


def test_planilha_com_partes_concatena_as_partes_filtradas(ficha_planilha, territorios):
    ficha, serie = _com_partes(ficha_planilha, [
        _parte_uf("AI", "anos_iniciais"), _parte_uf("AF", "anos_finais"), PARTE_BRASIL])
    df = padronizar_planilha(_pacote_ideb(), ficha, serie, "c1", territorios)
    assert list(df.columns) == COLUNAS_BASE
    valores = df.set_index(["subindicador", "territorio_id", "ano"]).valor
    assert valores.dropna().to_dict() == {
        ("anos_iniciais", "NE", 2019): 4.0, ("anos_iniciais", "NE", 2021): 5.0,
        ("anos_iniciais", "BA", 2019): 6.0,
        ("anos_iniciais", "RN", 2019): 7.0, ("anos_iniciais", "RN", 2021): 8.0,
        ("anos_iniciais", "CE", 2019): 9.0, ("anos_iniciais", "CE", 2021): 10.0,
        ("anos_finais", "NE", 2019): 3.0, ("anos_finais", "NE", 2021): 4.0,
        ("anos_finais", "BA", 2019): 5.0,
        ("anos_finais", "RN", 2019): 6.0, ("anos_finais", "RN", 2021): 7.0,
        ("anos_finais", "CE", 2019): 8.0, ("anos_finais", "CE", 2021): 9.0,
        ("anos_iniciais", "BR", 2019): 5.5, ("anos_iniciais", "BR", 2021): 5.6,
    }
    bahia_2021 = df[(df.territorio_id == "BA") & (df.ano == 2021)]
    assert set(bahia_2021.tipo_dado) == {"indisponivel"} and set(bahia_2021.nota) == {"Planilha: -"}
    assert set(df.rede) == {"total"} and set(df.etapa) == {""} and set(df.coleta_id) == {"c1"}
    assert len(df) == 2 * 4 * 2 + 2  # 2 abas x 4 territorios x 2 anos, mais o Brasil


def test_filtro_de_linhas_compara_sem_acento_maiusculas_nem_marcas_de_nota(ficha_planilha, territorios):
    ficha, serie = _com_partes(ficha_planilha, [_parte_uf("AI", "anos_iniciais", filtro_linhas={"Rede": "PUBLICA"})])
    df = padronizar_planilha(_pacote_ideb(), ficha, serie, "c1", territorios)
    assert df.set_index(["territorio_id", "ano"]).valor.to_dict() == {("NE", 2019): 1.0, ("NE", 2021): 1.0}
    ficha, serie = _com_partes(ficha_planilha, [_parte_uf("AI", "anos_iniciais", filtro_linhas={"Rede": "privada"})])
    df = padronizar_planilha(_pacote_ideb(), ficha, serie, "c1", territorios)
    assert set(df.territorio_id) == {"BA"} and set(df.valor) == {9.0}  # "Privada (1)" casa com "privada"


def test_filtro_de_linhas_com_coluna_inexistente_e_erro_de_layout(ficha_planilha, territorios):
    ficha, serie = _com_partes(ficha_planilha, [
        _parte_uf("AI", "anos_iniciais"), _parte_uf("AF", "anos_finais", filtro_linhas={"Dependência": "Total"})])
    with pytest.raises(ErroLayout, match=r"parte 2.*aba AF.*'Dependência'"):
        padronizar_planilha(_pacote_ideb(), ficha, serie, "c1", territorios)


def test_nomes_territorio_aponta_para_territorio_conhecido(ficha_planilha, territorios):
    ficha, serie = _com_partes(ficha_planilha, [
        _parte_uf("AI", "anos_iniciais", nomes_territorio={"R. G. do Norte": "XX"})])
    with pytest.raises(ErroLayout, match="XX"):
        padronizar_planilha(_pacote_ideb(), ficha, serie, "c1", territorios)


def test_sem_filtro_linhas_repetidas_do_mesmo_territorio_sao_erro_de_layout(ficha_planilha, territorios):
    parte = {k: v for k, v in _parte_uf("AI", "anos_iniciais").items() if k != "filtro_linhas"}
    ficha, serie = _com_partes(ficha_planilha, [parte])
    with pytest.raises(ErroLayout, match="repetid"):
        padronizar_planilha(_pacote_ideb(), ficha, serie, "c1", territorios)


def test_partes_que_repetem_a_mesma_linha_sao_erro_de_layout(ficha_planilha, territorios):
    ficha, serie = _com_partes(ficha_planilha, [_parte_uf("AI", "anos_iniciais"), _parte_uf("AF", "anos_iniciais")])
    with pytest.raises(ErroLayout, match="repetid"):
        padronizar_planilha(_pacote_ideb(), ficha, serie, "c1", territorios)


def test_parte_cuja_url_nao_esta_no_pacote_e_pacote_ilegivel(ficha_planilha, territorios):
    ficha, serie = _com_partes(ficha_planilha, [_parte_uf("AI", "anos_iniciais", url="https://outra/x.zip")])
    with pytest.raises(ErroLayout, match=r"parte 1.*https://outra/x\.zip"):
        padronizar_planilha(_pacote_ideb(), ficha, serie, "c1", territorios)
    ficha, serie = _com_partes(ficha_planilha, [_parte_uf("AI", "anos_iniciais")])
    with pytest.raises(ErroLayout, match="pacote"):
        padronizar_planilha(b"nao e zip", ficha, serie, "c1", territorios)


def test_parte_sem_nenhuma_linha_aceita_e_erro_de_layout(ficha_planilha, territorios):
    """Se a fonte renomear "Total", o subindicador inteiro sumiria em silencio: a parte vazia barra."""
    ficha, serie = _com_partes(ficha_planilha, [
        _parte_uf("AI", "anos_iniciais"), _parte_uf("AF", "anos_finais", filtro_linhas={"Rede": "Federal"})])
    with pytest.raises(ErroLayout, match=r"parte 2.*aba AF.*nenhuma linha"):
        padronizar_planilha(_pacote_ideb(), ficha, serie, "c1", territorios)


def test_territorios_esperados_ausentes_na_parte_sao_erro_de_layout(ficha_planilha, territorios):
    esperados = ["NE", "BA", "RN", "CE", "PE", "PI"]
    ficha, serie = _com_partes(ficha_planilha, [_parte_uf("AI", "anos_iniciais", territorios_esperados=esperados)])
    with pytest.raises(ErroLayout, match=r"parte 1.*aba AI.*PE, PI"):
        padronizar_planilha(_pacote_ideb(), ficha, serie, "c1", territorios)
    ficha, serie = _com_partes(ficha_planilha, [
        _parte_uf("AI", "anos_iniciais", territorios_esperados=["NE", "BA", "RN", "CE"]),
        {**PARTE_BRASIL, "territorios_esperados": ["BR"]}])
    df = padronizar_planilha(_pacote_ideb(), ficha, serie, "c1", territorios)
    assert set(df.territorio_id) == {"NE", "BA", "RN", "CE", "BR"}


def test_territorios_esperados_valem_tambem_sem_partes(ficha_planilha, territorios):
    ficha, serie = com_parametros(ficha_planilha, territorios_esperados=["PI", "NE"])
    with pytest.raises(ErroLayout, match="NE"):
        padronizar_planilha(xlsx_sintetico(), ficha, serie, "c1", territorios)


def test_partes_invalidas_sao_erro(ficha_planilha, territorios):
    for partes in ([], ["https://x/1.zip"], {"url": URL_UFS}):
        ficha, serie = _com_partes(ficha_planilha, partes)
        with pytest.raises(ErroLayout, match="partes deve ser"):
            padronizar_planilha(_pacote_ideb(), ficha, serie, "c1", territorios)


def test_padronizar_despacha_series_com_partes(projeto, ficha_planilha, territorios):
    ficha, serie = _com_partes(ficha_planilha, [_parte_uf("AI", "anos_iniciais"), PARTE_BRASIL])
    relativo = "dados/brutos/x/y/abc.zip"
    (projeto.raiz / relativo).parent.mkdir(parents=True)
    (projeto.raiz / relativo).write_bytes(_pacote_ideb())
    coleta = Coleta(
        coleta_id="c9", indicador_id="pib_nominal", serie_id=serie.id, url="x", data_coleta="2026-11-01",
        sha256="0" * 64, origem="fixture", arquivo=relativo,
    )
    df = padronizar(ficha, serie, coleta, projeto, territorios)
    assert set(df.territorio_id) == {"BR", "NE", "BA", "RN", "CE"} and set(df.coleta_id) == {"c9"}
