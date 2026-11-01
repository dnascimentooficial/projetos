import io
import zipfile
from dataclasses import replace

import pandas as pd
import pytest
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
    ("", None), ("  ", None), ("n/d", None), ("N/D", None), (float("nan"), None), (None, None),
])
def test_numero_br(entrada, esperado):
    assert numero_br(entrada) == esperado


@pytest.mark.parametrize("entrada", ["abc", "12a", float("inf"), "1,2,3", True])
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
