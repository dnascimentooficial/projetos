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
FICHAS_PARTE_B = {
    "renda_dom_pc", "massa_renda_dom_pc", "populacao_pnadc", "pobreza", "extrema_pobreza", "gini",
    "desocupacao", "desocupados", "forca_trabalho", "informalidade", "informais", "ocupados",
    "rendimento_trabalho",
}
FICHAS_COMPLETAS = FICHAS_PARTE_A | FICHAS_PARTE_B | {"pib_volume"}  # as que trazem os 15 territorios em todo ano
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
    assert FICHAS_PARTE_A | {"pib_volume"} <= set(fichas)


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


# ---------------------------------------------------------------------------
# Bloco IBGE, parte B: PNAD antiga (`pnad`) e PNAD Continua (`pnadc`)
# ---------------------------------------------------------------------------

ANOS_PNADC = list(range(2012, 2026))
ANOS_SEM_CONTAGEM_REGIONAL = {2020, 2021, 2022}  # as contagens anuais de desocupados e forca de trabalho so saem para o Brasil


def _valores(base, indicador, serie, territorio):
    linhas = base[(base.indicador_id == indicador) & (base.serie_id == serie) & (base.territorio_id == territorio)]
    return linhas.set_index("ano").valor


def test_fichas_da_parte_b_existem(fichas):
    assert FICHAS_PARTE_B <= set(fichas)


def test_series_da_parte_b_separam_pnad_e_pnadc(fichas):
    esperado = {
        "renda_dom_pc": ["pnadc"], "pobreza": ["pnadc"], "extrema_pobreza": ["pnadc"],
        "gini": ["pnad", "pnadc"], "desocupacao": ["pnad", "pnadc"], "informalidade": ["pnadc"],
        "rendimento_trabalho": ["pnadc"],
    }
    for indicador, series in esperado.items():
        assert [s.id for s in fichas[indicador].series] == series, indicador
    for auxiliar in ("massa_renda_dom_pc", "populacao_pnadc", "desocupados", "forca_trabalho", "informais", "ocupados"):
        f = fichas[auxiliar]  # o auxiliar usa o mesmo id de serie do indicador que o consome
        assert f.auxiliar and [s.id for s in f.series] == ["pnadc"], auxiliar


def test_parametros_sidra_da_pnadc(fichas):
    esperado = {
        ("renda_dom_pc", "7533", "10816", ()), ("massa_renda_dom_pc", "7427", "10495", ()),
        ("populacao_pnadc", "7436", "606", ()), ("gini", "7435", "10681", ()),
        ("desocupacao", "4562", "4099", ()), ("desocupados", "10364", "4092", (("c2", "6794"),)),
        ("forca_trabalho", "10364", "4088", (("c2", "6794"),)), ("informalidade", "4708", "12466", ()),
        ("informais", "4680", "4090", (("c1350", "57303"),)), ("ocupados", "4680", "4090", (("c1350", "57302"),)),
        ("rendimento_trabalho", "4566", "5935", ()), ("pobreza", "5877", "9948", ()),
        ("extrema_pobreza", "5817", "9617", ()),
    }
    obtido = set()
    for indicador in FICHAS_PARTE_B:
        s = fichas[indicador].serie("pnadc")
        assert s.coletor == "sidra", indicador
        classificacoes = tuple(sorted((s.parametros.get("classificacoes") or {}).items()))
        obtido.add((indicador, s.parametros["tabela"], s.parametros["variavel"], classificacoes))
    assert obtido == esperado


def test_gini_da_pnad_antiga_vem_do_ipeadata_e_declara_o_ano_sem_pesquisa(fichas, base):
    s = fichas["gini"].serie("pnad")
    assert (s.coletor, s.parametros, s.inicio, s.fim) == (
        "ipeadata", {"codigo": "PGINI", "periodos": "2001-2014"}, 2001, 2014)
    assert s.anos_sem_publicacao == (2010,)
    linhas = base[(base.indicador_id == "gini") & (base.serie_id == "pnad")]  # o Ipeadata traz desde 1976: `periodos` corta
    assert set(linhas.ano) == set(range(2001, 2015))
    sem_pesquisa = linhas[linhas.ano == 2010]  # a PNAD nao foi a campo em 2010: linha indisponivel, sem interpolacao
    assert set(sem_pesquisa.territorio_id) == TERRITORIOS_COMPLETOS
    assert set(sem_pesquisa.tipo_dado) == {"indisponivel"} and sem_pesquisa.valor.isna().all()
    assert set(linhas[linhas.ano != 2010].tipo_dado) == {"observado"}


def test_desocupacao_da_pnad_antiga_declara_o_ano_sem_pesquisa(fichas, base):
    assert fichas["desocupacao"].serie("pnad").anos_sem_publicacao == (2010,)
    linhas = base[(base.indicador_id == "desocupacao") & (base.serie_id == "pnad") & (base.ano == 2010)]
    assert set(linhas.tipo_dado) == {"indisponivel"} and len(linhas) == 15


def test_desocupacao_declara_a_precisao_da_taxa_oficial(fichas):
    assert fichas["desocupacao"].comparacao.precisao_oficial == 0.1  # a tabela 4562 traz uma casa decimal
    assert "0,47%" not in fichas["desocupacao"].metodologia


def test_desocupacao_da_pnad_antiga_vem_do_ipeadata(fichas):
    s = fichas["desocupacao"].serie("pnad")
    assert (s.coletor, s.parametros, s.inicio, s.fim) == (
        "ipeadata", {"codigo": "Dese_Pnad", "periodos": "2001-2014"}, 2001, 2014)


def test_comparacoes_da_parte_b(fichas):
    for indicador in ("gini", "pobreza", "extrema_pobreza", "rendimento_trabalho"):
        c = fichas[indicador].comparacao
        assert (c.referencia, c.metodo) == ("brasil", None), indicador  # sem contagens por UF: nao ha Brasil fora do NE
    esperado = {
        "renda_dom_pc": ("massa_renda_dom_pc", "populacao_pnadc", 1000.0),
        "desocupacao": ("desocupados", "forca_trabalho", 100.0),
        "informalidade": ("informais", "ocupados", 100.0),
    }
    for indicador, (numerador, denominador, fator) in esperado.items():
        c = fichas[indicador].comparacao
        assert (c.referencia, c.metodo, c.numerador, c.denominador, c.fator) == (
            "brasil_fora_ne", "razao", numerador, denominador, fator), indicador
    for auxiliar in ("massa_renda_dom_pc", "populacao_pnadc", "desocupados", "forca_trabalho", "informais", "ocupados"):
        assert fichas[auxiliar].comparacao.metodo == "soma", auxiliar


def test_valores_monetarios_da_pnadc_declaram_deflator_e_ano_base(fichas):
    for indicador in ("renda_dom_pc", "massa_renda_dom_pc", "rendimento_trabalho"):
        t = fichas[indicador].tratamento_monetario
        assert t["modo"] == "reais_constantes" and t["ano_base"] == 2025 and t["deflator"], indicador
    for indicador in FICHAS_PARTE_B - {"renda_dom_pc", "massa_renda_dom_pc", "rendimento_trabalho"}:
        assert fichas[indicador].tratamento_monetario is None, indicador


def test_pobreza_registra_a_linha_e_so_vira_verificada_com_a_linha_confirmada(fichas):
    for indicador in ("pobreza", "extrema_pobreza"):
        f = fichas[indicador]
        (s,) = f.series
        assert (s.id, s.inicio, s.fim, s.verificado) == ("pnadc", 2012, None, False), indicador
        assert "linha" in (f.metodologia + s.compatibilidade).lower(), indicador
        assert f.sentido == "menor_melhor" and f.limites == {"min": 0, "max": 100}, indicador


def test_cobertura_das_series_da_pnadc(fichas):
    for indicador in ("renda_dom_pc", "gini", "desocupacao", "rendimento_trabalho", "massa_renda_dom_pc", "populacao_pnadc",
                      "desocupados", "forca_trabalho"):
        s = fichas[indicador].serie("pnadc")
        assert (s.inicio, s.fim) == (2012, None), indicador
    for indicador in ("informalidade", "informais", "ocupados"):
        s = fichas[indicador].serie("pnadc")
        assert (s.inicio, s.fim) == (2016, None), indicador


def test_desocupacao_pnadc_offline_tem_brasil_fora_ne_exceto_onde_faltam_as_contagens(base):
    br_fora = _valores(base, "desocupacao", "pnadc", "BR_FORA_NE")
    assert set(br_fora.index) == set(ANOS_PNADC) - ANOS_SEM_CONTAGEM_REGIONAL
    assert set(br_fora) == {10.0}  # desocupados / forca de trabalho x 100, coerente com os insumos da fixture
    contagem = base[(base.indicador_id == "desocupados") & (base.ano.isin(ANOS_SEM_CONTAGEM_REGIONAL))]
    assert set(contagem[contagem.territorio_id != "BR"].tipo_dado) == {"indisponivel"}
    assert set(contagem[contagem.territorio_id == "BR"].tipo_dado) == {"observado"}
    taxa = base[(base.indicador_id == "desocupacao") & (base.serie_id == "pnadc") & (base.territorio_id != "BR_FORA_NE")]
    assert set(taxa.ano) == set(ANOS_PNADC) and set(taxa.tipo_dado) == {"observado"}  # a taxa oficial existe em todos os anos


def test_informalidade_e_renda_offline_tem_brasil_fora_ne_calculado_dos_insumos(base):
    inf = base[(base.indicador_id == "informalidade") & (base.territorio_id == "BR_FORA_NE")]
    assert set(inf.ano) == set(range(2016, 2026)) and set(inf.valor) == {50.0} and set(inf.serie_id) == {"pnadc"}
    renda = base[(base.indicador_id == "renda_dom_pc") & (base.territorio_id == "BR_FORA_NE")]
    assert set(renda.ano) == set(ANOS_PNADC) and set(renda.valor) == {1000.0}


def test_indicadores_sem_brasil_fora_ne_na_parte_b(base):
    for indicador in ("gini", "pobreza", "extrema_pobreza", "rendimento_trabalho"):
        assert "BR_FORA_NE" not in set(base[base.indicador_id == indicador].territorio_id), indicador


def test_series_da_parte_b_offline_sao_observadas(base):
    for indicador in FICHAS_PARTE_B:
        linhas = base[(base.indicador_id == indicador) & (base.territorio_id != "BR_FORA_NE")
                      & (base.tipo_dado != "indisponivel")]
        assert set(linhas.tipo_dado) == {"observado"}, indicador


# ---------------------------------------------------------------------------
# PNUD: IDHM e componentes (Ipeadata, series encadeadas do Ipea a partir do Atlas)
# ---------------------------------------------------------------------------

SUBINDICADORES_IDHM = ["educacao", "idhm", "longevidade", "renda"]
UFS_NE = TERRITORIOS_COMPLETOS - {"BR", "N", "NE", "SE", "S", "CO"}


def test_idhm_tem_quatro_subindicadores_em_duas_series_do_ipeadata(fichas):
    f = fichas["idhm"]
    assert [s.id for s in f.series] == ["censo", "pnadc"] and not f.auxiliar
    codigos = {"idhm": "IDHM", "renda": "IDHMRE", "educacao": "IDHMED", "longevidade": "IDHMLO"}
    for s, janela, (inicio, fim) in ((f.serie("censo"), "2000-2010", (2000, 2010)),
                                     (f.serie("pnadc"), "2012-2024", (2012, 2024))):
        assert (s.coletor, s.verificado, s.inicio, s.fim) == ("ipeadata", True, inicio, fim)
        assert s.parametros == {"codigos": codigos, "periodos": janela}
    assert (f.sentido, f.limites, f.unidade) == ("maior_melhor", {"min": 0, "max": 1}, "índice (0 a 1)")
    assert f.comparacao.referencia == "brasil" and f.comparacao.metodo is None
    assert f.tratamento_monetario is None and f.limiar_salto_pct == 100


def test_idhm_declara_o_que_a_serie_nao_cobre(fichas):
    f = fichas["idhm"]
    texto = " ".join((f.observacoes, f.serie("censo").compatibilidade, f.serie("pnadc").compatibilidade))
    for trecho in ("Nordeste fica sem valor", "não se recompõe", "não foi cotejada", "não são comparáveis"):
        assert trecho in texto, trecho


def test_idhm_offline_censo_so_tem_brasil_e_ufs_sem_nordeste_nem_regioes(base):
    censo = base[(base.indicador_id == "idhm") & (base.serie_id == "censo")]
    assert set(censo.ano) == {2000, 2010}  # nem 1991 (fora da janela) nem anos entre censos
    assert set(censo.territorio_id) == {"BR", *UFS_NE}
    assert set(censo.tipo_dado) == {"observado"}
    for _, grupo in censo.groupby(["subindicador", "ano"]):
        assert len(grupo) == 10
    assert sorted(set(censo.subindicador)) == SUBINDICADORES_IDHM


def test_idhm_offline_pnadc_tem_os_15_territorios_em_cada_ano(base):
    pnadc = base[(base.indicador_id == "idhm") & (base.serie_id == "pnadc")]
    assert set(pnadc.ano) == set(range(2012, 2025))
    for (subindicador, ano), grupo in pnadc.groupby(["subindicador", "ano"]):
        assert set(grupo.territorio_id) == TERRITORIOS_COMPLETOS, (subindicador, ano)
    assert sorted(set(pnadc.subindicador)) == SUBINDICADORES_IDHM


def test_idhm_offline_cada_subindicador_vem_do_seu_codigo_e_nao_ha_brasil_fora_ne(base):
    idhm = base[base.indicador_id == "idhm"]
    assert idhm.groupby("subindicador").valor.agg(lambda v: set(v)).to_dict() == {
        "idhm": {0.5}, "renda": {0.6}, "educacao": {0.4}, "longevidade": {0.7}}
    assert "BR_FORA_NE" not in set(idhm.territorio_id)
    assert set(idhm.etapa) == {""} and set(idhm.rede) == {""}


def test_idhm_coleta_offline_registra_um_arquivo_por_serie(projeto_completo):
    raiz = ["--raiz", str(projeto_completo.raiz), *HOJE]
    assert main(raiz + ["coletar", "--offline", "--indicador", "idhm"]) == 0
    coletas = pd.read_csv(projeto_completo.registro_coletas)
    assert sorted(coletas.serie_id) == ["censo", "pnadc"] and set(coletas.origem) == {"fixture"}
