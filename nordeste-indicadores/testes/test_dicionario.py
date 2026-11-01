"""Dicionario de indicadores do repositorio: fichas, parametros de coleta e fixtures coerentes."""

from pathlib import Path

import pandas as pd
import pytest

from nordeste.cli import main
from nordeste.coletores.arquivo import url_arquivo
from nordeste.coletores.ipeadata import url_ipeadata
from nordeste.coletores.sidra import url_sidra
from nordeste.fichas import carregar_fichas

TERRITORIOS_COMPLETOS = {
    "BR", "N", "NE", "SE", "S", "CO", "MA", "PI", "CE", "RN", "PB", "PE", "AL", "SE_UF", "BA",
}
FICHAS_PARTE_A = {"populacao", "pib_participacao", "pib_nominal", "pib_per_capita"}
FICHAS_COMPLETAS = FICHAS_PARTE_A | {"pib_volume"}  # as que trazem os 15 territorios em todo ano
HOJE = ["--hoje", "2026-11-01"]
DICIONARIO = Path(__file__).resolve().parent.parent / "docs" / "dicionario-verificacao.md"
URL_DO_COLETOR = {"sidra": url_sidra, "ipeadata": url_ipeadata, "arquivo": url_arquivo}


@pytest.fixture
def fichas(projeto_completo):
    return carregar_fichas(projeto_completo.fichas)


def _series(fichas):
    return [(f, s) for f in fichas.values() for s in f.series]


def _coletaveis(fichas):
    """Series que o coletor busca: as de fichas sem `calculo`."""
    return [(f, s) for f, s in _series(fichas) if f.calculo is None]


@pytest.fixture
def base(projeto_completo):
    raiz = ["--raiz", str(projeto_completo.raiz), *HOJE]
    assert main(raiz + ["coletar", "--offline"]) == 0
    assert main(raiz + ["consolidar"]) == 0
    return pd.read_csv(projeto_completo.trabalho / "base.csv", keep_default_na=False,
                       na_values={"valor": [""]})


def test_fichas_da_parte_a_existem(fichas):
    assert FICHAS_COMPLETAS <= set(fichas)


def test_toda_serie_tem_exatamente_uma_fixture(projeto_completo, fichas):
    for f, s in _series(fichas):
        achadas = sorted((projeto_completo.fixtures / f.id).glob(f"{s.id}.*"))
        esperadas = 0 if f.calculo is not None else 1  # indicador calculado nao e coletado: sem fixture
        assert len(achadas) == esperadas, f"{f.id}/{s.id}: {achadas}"


def test_serie_verificada_tem_parametros_de_coleta_completos(fichas):
    verificadas = [(f, s) for f, s in _coletaveis(fichas) if s.verificado]
    assert verificadas, "esperava ao menos uma serie verificada"
    for f, s in verificadas:
        assert s.coletor in URL_DO_COLETOR, f"{f.id}/{s.id}: coletor inesperado {s.coletor}"
        url = URL_DO_COLETOR[s.coletor](s.parametros)  # KeyError/ErroColeta se faltar parametro
        assert url.startswith("https://")


def test_dicionario_tem_uma_secao_por_serie_e_a_url_das_verificadas(fichas):
    texto = DICIONARIO.read_text(encoding="utf-8")
    titulos = [linha for linha in texto.splitlines() if linha.startswith("#")]
    for f, s in _series(fichas):
        assert any(f"{f.id} / {s.id}" in titulo for titulo in titulos), f"{f.id}/{s.id} sem secao"
        if s.verificado and f.calculo is None:  # a evidencia citada e a URL exata que o coletor monta
            assert f"`{URL_DO_COLETOR[s.coletor](s.parametros)}`" in texto, f"{f.id}/{s.id}"


def test_series_do_pib_nominal_e_participacao_usam_a_mesma_tabela_das_contas_regionais(fichas):
    nominal = fichas["pib_nominal"].serie("scr_ref2010").parametros
    participacao = fichas["pib_participacao"].serie("scr_ref2010").parametros
    assert nominal["tabela"] == participacao["tabela"] == "5938"
    assert nominal["variavel"] == "37" and participacao["variavel"] == "496"


def test_pib_participacao_nao_tem_comparacao_nem_deflator(fichas):
    f = fichas["pib_participacao"]
    assert f.comparacao.referencia == "nenhuma" and f.comparacao.metodo is None
    assert f.unidade == "%" and f.tratamento_monetario is None
    assert f.limites == {"min": 0, "max": 100}


def test_populacao_separa_estimativas_e_censos_em_series_proprias(fichas):
    f = fichas["populacao"]
    assert [s.id for s in f.series] == [
        "estimativa_pre_censo2022", "estimativa_pos_censo2022", "censo_2000_2010", "censo_2022",
    ]
    assert f.comparacao.referencia == "brasil_fora_ne" and f.comparacao.metodo == "soma"
    assert f.serie("estimativa_pos_censo2022").fim is None  # serie em curso


def test_series_de_populacao_nao_se_sobrepoem(fichas):
    anos = [
        set(range(s.inicio, (s.fim or 2026) + 1)) for s in fichas["populacao"].series
        if s.id.startswith("estimativa")
    ]
    assert not anos[0] & anos[1]


def test_base_offline_tem_os_15_territorios_em_cada_ano_de_cada_serie(base, fichas):
    for f, s in _series(fichas):
        if f.id not in FICHAS_COMPLETAS:
            continue
        linhas = base[(base.indicador_id == f.id) & (base.serie_id == s.id)
                      & (base.territorio_id != "BR_FORA_NE")]
        assert not linhas.empty, f"{f.id}/{s.id} sem linhas"
        for ano, grupo in linhas.groupby("ano"):
            assert set(grupo.territorio_id) == TERRITORIOS_COMPLETOS, f"{f.id}/{s.id} {ano}"
        assert linhas.ano.min() == s.inicio, f"{f.id}/{s.id}"
        if s.fim is not None:
            assert linhas.ano.max() == s.fim, f"{f.id}/{s.id}"


def test_anos_de_estimativa_viram_estimativa_oficial(base, fichas):
    for s in fichas["populacao"].series:
        linhas = base[(base.indicador_id == "populacao") & (base.serie_id == s.id)
                      & (base.territorio_id != "BR_FORA_NE")]
        esperado = "estimativa_oficial" if s.id.startswith("estimativa") else "observado"
        assert set(linhas.tipo_dado) == {esperado}, s.id
        if s.id.startswith("estimativa"):
            assert set(linhas.ano) == set(s.parametros["anos_estimativa"]), s.id


def test_anos_sem_estimativa_sao_lacunas_e_nao_valores_inventados(base):
    pre = base[(base.indicador_id == "populacao") & (base.serie_id == "estimativa_pre_censo2022")]
    assert not pre.empty and not {2007, 2010} & set(pre.ano)  # anos de contagem e de censo ficam fora das estimativas


def test_populacao_tem_brasil_fora_ne_por_serie(base):
    derivados = base[(base.indicador_id == "populacao") & (base.territorio_id == "BR_FORA_NE")]
    assert set(derivados.serie_id) == {
        "estimativa_pre_censo2022", "estimativa_pos_censo2022", "censo_2000_2010", "censo_2022",
    }
    assert set(derivados.tipo_dado) == {"derivado"}


def test_pib_participacao_do_brasil_e_100_e_nao_gera_brasil_fora_ne(base):
    p = base[base.indicador_id == "pib_participacao"]
    assert set(p[p.territorio_id == "BR"].valor) == {100.0}
    assert "BR_FORA_NE" not in set(p.territorio_id)


def test_ensaio_do_dicionario_inteiro_so_e_barrado_pela_r01(projeto_completo, capsys):
    raiz = ["--raiz", str(projeto_completo.raiz), *HOJE]
    assert main(raiz + ["coletar", "--offline"]) == 0
    assert main(raiz + ["consolidar"]) == 0
    capsys.readouterr()
    assert main(raiz + ["publicar", "--ensaio"]) == 1
    assert "R01" in capsys.readouterr().err
    validacao = pd.read_csv(projeto_completo.relatorios / "validacao.csv")
    assert set(validacao.query("nivel == 'erro'").regra) == {"R01"}
    assert not projeto_completo.base.exists()
    pendencias = pd.read_csv(projeto_completo.trabalho / "pendencias.csv", keep_default_na=False)
    assert pendencias.empty


def test_pib_volume_le_a_tabela3_do_zip_de_xls_do_ibge(fichas):
    f = fichas["pib_volume"]
    s = f.serie("scr_ref2010")
    assert (s.inicio, s.fim, s.coletor, s.verificado) == (2002, 2023, "arquivo", True)
    p = s.parametros
    assert p["url"].endswith("/Contas_Regionais/2023/xls/Especiais_2002_2023_xls.zip")
    assert (p["padronizador"], p["formato"], p["arquivo_no_zip"], p["aba"]) == (
        "planilha", "xls", "tab03.xls", "Tabela3")
    assert p["linha_cabecalho"] == 4
    assert [c["ano"] for c in p["colunas"]] == list(range(2002, 2024))
    assert all(c["coluna"] == c["ano"] for c in p["colunas"])


def test_pib_volume_compara_com_o_brasil_porque_nao_ha_pib_a_precos_do_ano_anterior(fichas):
    f = fichas["pib_volume"]
    assert f.comparacao.referencia == "brasil" and f.comparacao.metodo is None
    assert f.tratamento_monetario is None and not f.auxiliar


def test_pib_volume_offline_vem_do_xls_sintetico_sem_brasil_fora_ne(base):
    v = base[base.indicador_id == "pib_volume"]
    assert set(v.tipo_dado) == {"observado"} and set(v.valor) == {99999.0}
    assert "BR_FORA_NE" not in set(v.territorio_id)
    assert len(v) == 15 * 22  # as 27 UFs do arquivo ficam so as 9 do Nordeste, mais BR e as 5 regioes


def test_populacao_contas_regionais_saiu_do_dicionario(fichas):
    assert "populacao_contas_regionais" not in fichas


# Populacao que o IBGE usou como denominador do PIB per capita das Contas Regionais, por ano
# (conferida contra valores publicados; ver docs/dicionario-verificacao.md).
DENOMINADOR_ESPERADO = {
    **{ano: ("estimativa_pre_censo2022", ano) for ano in [*range(2002, 2007), 2008, 2009, *range(2011, 2022)]},
    2010: ("censo_2000_2010", 2010),
    2022: ("censo_2022", 2022),
    2023: ("censo_2022", 2022),  # o IBGE dividiu o PIB de 2023 pela populacao do Censo 2022
}


def test_pib_per_capita_e_calculado_pelo_projeto(fichas):
    f = fichas["pib_per_capita"]
    calc = f.calculo
    assert (calc.metodo, calc.numerador, calc.serie_numerador, calc.denominador, calc.fator) == (
        "razao_por_ano", "pib_nominal", "scr_ref2010", "populacao", 1000.0)
    for ano in range(2002, 2024):
        assert calc.denominador_do_ano(ano) == DENOMINADOR_ESPERADO.get(ano), ano
    assert calc.denominador_do_ano(2007) is None  # sem populacao conferida para 2007
    assert f.comparacao.referencia == "brasil_fora_ne" and f.comparacao.metodo is None
    assert f.tratamento_monetario == {"modo": "razao"} and not f.auxiliar
    (s,) = f.series
    assert (s.id, s.inicio, s.fim, s.coletor, s.parametros, s.verificado) == (
        "scr_ref2010", 2002, 2023, "calculo", {}, True)
    assert s.fonte.startswith("Cálculo do projeto com dados do IBGE")
    for trecho in ("5938", "6579", "202", "4709"):
        assert trecho in s.fonte
    assert "populacao_contas_regionais" not in f.metodologia + f.observacoes


def test_pib_per_capita_offline_vem_do_calculo_sobre_as_fixtures(base, projeto_completo):
    pc = base[base.indicador_id == "pib_per_capita"]
    assert set(pc.tipo_dado) == {"derivado"} and set(pc.serie_id) == {"scr_ref2010"}
    assert set(pc.ano) == set(range(2002, 2024)) - {2007}  # 2007 sem denominador: sem linha
    assert set(pc.territorio_id) == TERRITORIOS_COMPLETOS | {"BR_FORA_NE"}
    assert len(pc) == 16 * 21
    assert set(pc.valor) == {1000.0}  # 99999 x m / (99999 x m) x 1000, inclusive (13 - 9) / (13 - 9) x 1000
    (coleta_id,) = set(pc.coleta_id)
    derivacoes = pd.read_csv(projeto_completo.registro_derivacoes, dtype=str, keep_default_na=False)
    (insumos,) = derivacoes.loc[derivacoes.coleta_id == coleta_id, "insumos"]
    origem = {c.split(".")[0] + "/" + c.split(".")[1] for c in insumos.split(";")}
    assert origem == {
        "pib_nominal/scr_ref2010", "populacao/estimativa_pre_censo2022",
        "populacao/censo_2000_2010", "populacao/censo_2022",
    }


def test_indicador_calculado_nao_e_coletado(projeto_completo):
    raiz = ["--raiz", str(projeto_completo.raiz), *HOJE]
    assert main(raiz + ["coletar", "--offline", "--indicador", "pib_per_capita"]) == 0
    assert not projeto_completo.registro_coletas.exists()
    assert main(raiz + ["coletar", "--offline"]) == 0
    coletas = pd.read_csv(projeto_completo.registro_coletas)
    assert "pib_per_capita" not in set(coletas.indicador_id)


def test_insumo_pendente_deixa_o_indicador_calculado_pendente(projeto_completo, capsys):
    raiz = ["--raiz", str(projeto_completo.raiz), *HOJE]
    assert main(raiz + ["coletar", "--offline", "--indicador", "pib_nominal"]) == 0
    assert main(raiz + ["consolidar"]) == 0
    pendencias = pd.read_csv(projeto_completo.trabalho / "pendencias.csv", keep_default_na=False)
    pc = pendencias[pendencias.indicador_id == "pib_per_capita"]
    assert pc.serie_id.tolist() == ["scr_ref2010"]
    assert pc.motivo.iloc[0].startswith("insumo pendente: populacao/")
    assert "pib_per_capita/scr_ref2010: insumo pendente" in capsys.readouterr().out


@pytest.mark.parametrize("trecho, troca, mensagem", [
    ('"2010": censo_2000_2010', '"2009-2010": censo_2000_2010', "sobrepoe"),
    ('"2022": censo_2022', '"2022": {serie: censo_2022, ano: 2023}', "posterior"),  # populacao futura
    ('"2023": {serie: censo_2022, ano: 2022}', '"2023": {serie: censo_2000_2010, ano: 2021}', "fora da cobertura"),
])
def test_mapeamento_invalido_na_ficha_barra_a_publicacao_pela_r10(projeto_completo, trecho, troca, mensagem):
    raiz = ["--raiz", str(projeto_completo.raiz), *HOJE]
    assert main(raiz + ["coletar", "--offline"]) == 0
    assert main(raiz + ["consolidar"]) == 0
    ficha = projeto_completo.fichas / "pib_per_capita.yaml"
    texto = ficha.read_text(encoding="utf-8")
    assert trecho in texto
    ficha.write_text(texto.replace(trecho, troca), encoding="utf-8")
    assert main(raiz + ["validar"]) == 1
    validacao = pd.read_csv(projeto_completo.relatorios / "validacao.csv")
    r10 = validacao.query("regra == 'R10'").mensagem
    assert any(mensagem in m for m in r10), r10.tolist()
