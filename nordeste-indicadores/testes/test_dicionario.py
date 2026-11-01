"""Dicionario de indicadores do repositorio: fichas, parametros de coleta e fixtures coerentes."""

from pathlib import Path

import pandas as pd
import pytest

from nordeste.cli import main
from nordeste.coletores.arquivo import url_arquivo
from nordeste.coletores.ipeadata import url_ipeadata
from nordeste.coletores.sidra import url_sidra
from nordeste.fichas import carregar_fichas
from nordeste.tabela import cobertura_efetiva

TERRITORIOS_COMPLETOS = {
    "BR", "N", "NE", "SE", "S", "CO", "MA", "PI", "CE", "RN", "PB", "PE", "AL", "SE_UF", "BA",
}
FICHAS_PARTE_A = {"populacao", "pib_participacao", "pib_nominal", "pib_per_capita"}
FICHAS_PARTE_B = {
    "renda_dom_pc", "massa_renda_dom_pc", "populacao_pnadc", "pobreza", "extrema_pobreza", "gini",
    "desocupacao", "desocupados", "forca_trabalho", "informalidade", "informais", "ocupados",
    "rendimento_trabalho",
}
FICHAS_INEP = {"ideb", "abandono_em", "matriculas_basica", "superior"}
FICHAS_COMPLETAS = FICHAS_PARTE_A | FICHAS_PARTE_B | {"pib_volume"} | FICHAS_INEP  # as que trazem os 15 territorios em todo ano
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


@pytest.fixture(scope="module")
def base(projeto_consolidado):
    """Base de trabalho do dicionario inteiro, coletada offline e consolidada uma vez (nao alterar)."""
    return pd.read_csv(projeto_consolidado.trabalho / "base.csv", keep_default_na=False,
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


def test_ensaio_do_dicionario_inteiro_so_e_barrado_pela_r01(copia_consolidada, capsys):
    projeto_completo = copia_consolidada  # dicionario inteiro ja coletado offline e consolidado
    raiz = ["--raiz", str(projeto_completo.raiz), *HOJE]
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


def test_pib_per_capita_offline_vem_do_calculo_sobre_as_fixtures(base, projeto_consolidado):
    pc = base[base.indicador_id == "pib_per_capita"]
    assert set(pc.tipo_dado) == {"derivado"} and set(pc.serie_id) == {"scr_ref2010"}
    assert set(pc.ano) == set(range(2002, 2024)) - {2007}  # 2007 sem denominador: sem linha
    assert set(pc.territorio_id) == TERRITORIOS_COMPLETOS | {"BR_FORA_NE"}
    assert len(pc) == 16 * 21
    assert set(pc.valor) == {1000.0}  # 99999 x m / (99999 x m) x 1000, inclusive (13 - 9) / (13 - 9) x 1000
    (coleta_id,) = set(pc.coleta_id)
    derivacoes = pd.read_csv(projeto_consolidado.registro_derivacoes, dtype=str, keep_default_na=False)
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
def test_mapeamento_invalido_na_ficha_barra_a_publicacao_pela_r10(copia_consolidada, trecho, troca, mensagem):
    projeto_completo = copia_consolidada  # dicionario inteiro ja coletado offline e consolidado
    raiz = ["--raiz", str(projeto_completo.raiz), *HOJE]
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
        f = fichas[indicador]
        t = f.tratamento_monetario
        # o IBGE reapresenta a serie inteira a precos do ultimo ano a cada divulgacao: nada de ano fixo no texto
        assert t["modo"] == "reais_constantes" and t["ano_base"] == "ultimo_ano" and t["deflator"], indicador
        assert "do último ano da série" in f.unidade and "2025" not in f.unidade + f.descricao, indicador
        assert f.unidade_resolvida(2026).endswith("a preços médios de 2026"), indicador
    for indicador in FICHAS_PARTE_B - {"renda_dom_pc", "massa_renda_dom_pc", "rendimento_trabalho"}:
        assert fichas[indicador].tratamento_monetario is None, indicador


def test_pobreza_registra_a_linha_e_a_origem_da_confirmacao(fichas):
    for indicador in ("pobreza", "extrema_pobreza"):
        f = fichas[indicador]
        (s,) = f.series
        assert (s.id, s.inicio, s.fim, s.verificado) == ("pnadc", 2012, 2024, True), indicador  # 2012 a 2024: o download real
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


# ---------------------------------------------------------------------------
# INEP: IDEB (planilhas de divulgacao de 2025; Brasil e regioes/UFs em arquivos distintos, partes da mesma serie)
# ---------------------------------------------------------------------------

SUBINDICADORES_IDEB = ["anos_finais", "anos_iniciais", "ensino_medio"]
ORDEM_UFS = ["MA", "PI", "CE", "RN", "PB", "PE", "AL", "SE_UF", "BA"]
ANOS_IDEB = list(range(2005, 2026, 2))


def test_ideb_tem_uma_serie_com_seis_partes_de_dois_arquivos(fichas):
    f = fichas["ideb"]
    (s,) = f.series
    assert (s.id, s.inicio, s.fim, s.coletor, s.verificado) == ("ideb", 2005, 2025, "arquivo", True)
    p = s.parametros
    assert p["padronizador"] == "planilha"
    assert p["ca_extra"] == "metadados/certificados/rnp-icpedu-gr46-ov-tls-ca-2025.pem"
    assert url_arquivo(p) == (
        "https://download.inep.gov.br/ideb/resultados/divulgacao_regioes_ufs_ideb_2025.zip "
        "https://download.inep.gov.br/ideb/resultados/divulgacao_brasil_ideb_2025.zip")
    partes = p["partes"]
    assert len(partes) == 6
    for parte in partes:
        assert parte["filtro_linhas"] == {"Rede": "Total"} and parte["linha_cabecalho"] == 7
        esperados = ["BR"] if "brasil" in parte["url"] else ["N", "NE", "SE", "S", "CO", *ORDEM_UFS]
        assert parte["territorios_esperados"] == esperados
        assert [c["ano"] for c in parte["colunas"]] == ANOS_IDEB
        (subindicador,) = {c["subindicador"] for c in parte["colunas"]}
        assert {c["rede"] for c in parte["colunas"]} == {"total"} and not any("etapa" in c for c in parte["colunas"])
        assert all(c["coluna"].startswith("IDEB\n") for c in parte["colunas"])
    assert sorted(c["subindicador"] for parte in partes for c in parte["colunas"][:1]) == sorted(SUBINDICADORES_IDEB * 2)
    assert (f.sentido, f.limites, f.unidade) == ("maior_melhor", {"min": 0, "max": 10}, "índice (0 a 10)")
    assert f.comparacao.referencia == "brasil" and f.comparacao.metodo is None and f.tratamento_monetario is None


def test_ideb_declara_os_rotulos_de_2021_com_chamada_de_nota_e_a_nota_da_pandemia(fichas):
    f = fichas["ideb"]
    rotulos = {(parte["aba"], parte["colunas"][8]["coluna"]) for parte in f.serie("ideb").parametros["partes"]}
    assert rotulos == {
        ("UF e Regiões (AI)", "IDEB\n20215\n(N x P)"), ("UF e Regiões (AF)", "IDEB\n20215\n(N x P)"),
        ("UF e Regiões (EM)", "IDEB\n20215\n(N x P)"), ("Brasil (Anos Iniciais)", "IDEB\n20212\n(N x P)"),
        ("Brasil (Anos Finais)", "IDEB\n20211\n(N x P)"), ("Brasil (EM)", "IDEB\n20211\n(N x P)")}
    assert "2021" in f.observacoes and "pandemia" in f.observacoes


def test_ideb_offline_tem_tres_etapas_15_territorios_e_so_anos_de_edicao(base):
    from gerar_fixtures import VALORES_IDEB
    ideb = base[base.indicador_id == "ideb"]
    assert sorted(set(ideb.ano)) == ANOS_IDEB  # anos pares sem edicao nao tem linha
    for (subindicador, ano), grupo in ideb.groupby(["subindicador", "ano"]):
        assert set(grupo.territorio_id) == TERRITORIOS_COMPLETOS and len(grupo) == 15, (subindicador, ano)
    assert sorted(set(ideb.subindicador)) == SUBINDICADORES_IDEB
    # so a linha "Total" de cada etapa (as demais redes valem 1 na fixture)
    assert ideb.groupby("subindicador").valor.agg(lambda v: set(v)).to_dict() == {
        s: {v} for s, v in VALORES_IDEB.items()}
    assert set(ideb.tipo_dado) == {"observado"} and set(ideb.rede) == {"total"} and set(ideb.etapa) == {""}
    assert "BR_FORA_NE" not in set(ideb.territorio_id)


def test_ideb_coleta_offline_registra_um_pacote_por_serie(projeto_completo):
    raiz = ["--raiz", str(projeto_completo.raiz), *HOJE]
    assert main(raiz + ["coletar", "--offline", "--indicador", "ideb"]) == 0
    coletas = pd.read_csv(projeto_completo.registro_coletas)
    assert coletas.serie_id.tolist() == ["ideb"] and coletas.origem.tolist() == ["fixture"]
    assert coletas.arquivo[0].endswith(".zip")


# ---------------------------------------------------------------------------
# INEP: abandono no ensino medio, matriculas da educacao basica e ensino superior (Tarefa 15B).
# Cada ano e um arquivo de layout proprio: uma parte por arquivo (ou por aba), todas da mesma serie.
# ---------------------------------------------------------------------------

REDES_DO_INEP = ["federal", "estadual", "municipal", "privada"]


def _partes(fichas, indicador, serie):
    return fichas[indicador].serie(serie).parametros["partes"]


def url_sinopse_superior(ano):
    return ("https://download.inep.gov.br/informacoes_estatisticas/sinopses_estatisticas/sinopses_educacao_superior/"
            f"sinopse_educacao_superior_{ano}.zip")


def _anos_das_partes(partes):
    return sorted({c["ano"] for parte in partes for c in parte["colunas"]})


def _urls_das_partes(partes):
    return list(dict.fromkeys(parte["url"] for parte in partes))


def _territorios_por_ano(partes):
    por_ano = {}
    for parte in partes:
        for c in parte["colunas"]:
            por_ano.setdefault(c["ano"], set()).update(parte["territorios_esperados"])
    return por_ano


def test_abandono_em_tem_uma_parte_por_arquivo_de_cada_ano(fichas):
    f = fichas["abandono_em"]
    (s,) = f.series
    assert (s.id, s.inicio, s.fim, s.coletor, s.verificado) == ("indicadores_inep", 2007, 2025, "arquivo", True)
    assert s.parametros["padronizador"] == "planilha"
    assert s.parametros["ca_extra"] == "metadados/certificados/rnp-icpedu-gr46-ov-tls-ca-2025.pem"
    partes = s.parametros["partes"]
    assert _anos_das_partes(partes) == list(range(2007, 2026))
    assert len(_urls_das_partes(partes)) == 19 and url_arquivo(s.parametros) == " ".join(_urls_das_partes(partes))
    for ano in range(2007, 2026):
        do_ano = [p for p in partes if p["colunas"][0]["ano"] == ano]
        assert len(do_ano) == (3 if ano <= 2016 else 1), ano  # Brasil, regioes e UFs em arquivos separados ate 2016
        assert len({p["url"] for p in do_ano}) == 1 and str(ano) in do_ano[0]["url"], ano
    assert _territorios_por_ano(partes) == {ano: TERRITORIOS_COMPLETOS for ano in range(2007, 2026)}


def test_abandono_em_confere_o_ano_do_arquivo_e_so_le_o_total_de_localizacao_e_rede(fichas):
    for parte in _partes(fichas, "abandono_em", "indicadores_inep"):
        (coluna,) = parte["colunas"]
        anos_no_filtro = [v for v in parte["filtro_linhas"].values() if isinstance(v, int)]
        assert anos_no_filtro == [coluna["ano"]], parte["arquivo_no_zip"]  # o ano do arquivo e conferido na planilha
        assert sorted(v for v in parte["filtro_linhas"].values() if isinstance(v, str)) == ["Total", "Total"]
        assert coluna["rede"] == "total" and set(coluna) == {"coluna", "ano", "rede"}
        assert parte["formato"] in {"xls", "xlsx"} and parte["linha_cabecalho"] in {7, 8, 9}


def test_abandono_em_menor_e_melhor_e_compara_com_o_brasil(fichas):
    f = fichas["abandono_em"]
    assert (f.sentido, f.unidade, f.limites, f.defasagem_meses) == ("menor_melhor", "%", {"min": 0, "max": 100}, 8)
    assert f.comparacao.referencia == "brasil" and f.comparacao.metodo is None and f.tratamento_monetario is None
    assert "2020" in f.observacoes and "pandemia" in f.observacoes


def test_abandono_em_offline_tem_15_territorios_so_na_rede_total_e_sem_brasil_fora_ne(base):
    from gerar_fixtures import VALOR_ABANDONO
    a = base[base.indicador_id == "abandono_em"]
    assert sorted(set(a.ano)) == list(range(2007, 2026)) and len(a) == 19 * 15
    assert set(a.serie_id) == {"indicadores_inep"} and set(a.rede) == {"total"} and set(a.tipo_dado) == {"observado"}
    assert set(a.subindicador) == {""} and set(a.etapa) == {""}
    assert set(a.valor) == {VALOR_ABANDONO}  # as linhas-isca (outra localizacao ou rede) valem 1 e ficam de fora
    assert "BR_FORA_NE" not in set(a.territorio_id)


def test_abandono_em_coleta_offline_registra_um_pacote_por_serie(projeto_completo):
    raiz = ["--raiz", str(projeto_completo.raiz), *HOJE]
    assert main(raiz + ["coletar", "--offline", "--indicador", "abandono_em"]) == 0
    coletas = pd.read_csv(projeto_completo.registro_coletas)
    assert coletas.serie_id.tolist() == ["indicadores_inep"] and coletas.origem.tolist() == ["fixture"]
    assert coletas.arquivo[0].endswith(".zip")


def test_matriculas_basica_tem_tres_series_com_partes_por_ano(fichas):
    f = fichas["matriculas_basica"]
    assert [(s.id, s.inicio, s.fim, s.coletor, s.verificado) for s in f.series] == [
        ("censo_escolar_2000_2002", 2000, 2002, "arquivo", True), ("censo_escolar_pre2007", 2005, 2006, "arquivo", True),
        ("educacenso", 2007, 2025, "arquivo", True)]
    assert f.comparacao.referencia == "brasil_fora_ne" and f.comparacao.metodo == "soma"
    assert (f.unidade, f.limites, f.tratamento_monetario) == ("matrículas", {"min": 0}, None)
    antigas, pre, educacenso = (
        f.serie(i).parametros["partes"] for i in ("censo_escolar_2000_2002", "censo_escolar_pre2007", "educacenso"))
    assert _anos_das_partes(antigas) == [2000, 2001, 2002] and _anos_das_partes(pre) == [2005, 2006]
    assert _anos_das_partes(educacenso) == list(range(2007, 2026))
    assert [p["aba"] for p in antigas[:4]] == ["1.1", "1.5", "1.13", "1.36"]
    assert [p["aba"] for p in pre[:5]] == ["1.1", "1.6", "1.12", "1.18", "1.43"]
    assert len(antigas) == 3 * 4 and len(pre) == 2 * 5 and len(educacenso) == 19 * 6  # educacenso: tres abas, cada uma em duas partes
    assert len(_urls_das_partes(antigas)) == 3 and len(_urls_das_partes(pre)) == 2 and len(_urls_das_partes(educacenso)) == 19
    assert _territorios_por_ano(antigas) == {ano: TERRITORIOS_COMPLETOS for ano in (2000, 2001, 2002)}
    assert _territorios_por_ano(pre) == {2005: TERRITORIOS_COMPLETOS, 2006: TERRITORIOS_COMPLETOS}
    assert _territorios_por_ano(educacenso) == {ano: TERRITORIOS_COMPLETOS for ano in range(2007, 2026)}
    for parte in educacenso:  # Brasil e regioes (UF em branco) ou UFs (municipio em branco): as linhas de municipio ficam de fora
        assert parte["filtro_linhas"] in ({"Unnamed: 1": ""}, {"Unnamed: 2": ""})
        assert all(set(c) == {"coluna", "ano", "etapa", "rede"} for c in parte["colunas"])


def test_matriculas_basica_nao_tem_buraco_silencioso_em_2003_e_2004(fichas):
    """2003 e 2004 so existem em PDF: nenhuma serie as cobre, e a cobertura efetiva mostra o corte."""
    f = fichas["matriculas_basica"]
    cobertos = {a for s in f.series if s.verificado for a in range(s.inicio, s.fim + 1)}
    assert cobertos == {2000, 2001, 2002, *range(2005, 2026)}
    assert cobertura_efetiva(f) == "2000–2002; 2005–2025"
    assert all(not s.anos_sem_publicacao for s in f.series)  # os anos de PDF tiveram Censo: nao sao "sem pesquisa"


def test_matriculas_basica_2022_a_2025_seguem_o_layout_de_cada_sinopse(fichas):
    """2022 a 2024 repetem as tabelas 1.1, 1.5 e 1.14 (com uma linha a mais no cabecalho da 1.1); 2025 renumera para 1.1, 1.8 e 1.20."""
    partes = _partes(fichas, "matriculas_basica", "educacenso")
    esperado = {
        2022: (("Educação Básica 1.1", 11), ("Educação Infantil 1.5", 10), ("Ensino Fundamental 1.14", 10)),
        # 2023 e 2024: a linha em branco acima do Brasil tem celulas com espacos (nomes de coluna repetidos); o cabecalho
        # vai para a linha 5, inteiramente vazia, e as linhas de rotulos abaixo dela nao casam nenhum territorio
        2023: (("Educação Básica 1.1", 5), ("Educação Infantil 1.5", 10), ("Ensino Fundamental 1.14", 10)),
        2024: (("Educação Básica 1.1", 5), ("Educação Infantil 1.5", 10), ("Ensino Fundamental 1.14", 10)),
        2025: (("Educação Básica 1.1", 13), ("Educação Infantil 1.8", 12), ("Ensino Fundamental 1.20", 12)),
    }
    for ano, abas in esperado.items():
        do_ano = [p for p in partes if p["colunas"][0]["ano"] == ano]
        assert [(p["aba"], p["linha_cabecalho"]) for p in do_ano] == [x for aba in abas for x in (aba, aba)], ano
        assert len({p["url"] for p in do_ano}) == 1 and str(ano) in do_ano[0]["url"], ano
        assert len({p["arquivo_no_zip"] for p in do_ano}) == 1 and str(ano) in do_ano[0]["arquivo_no_zip"], ano
        redes_por_etapa = {}
        for p in do_ano:
            for c in p["colunas"]:
                redes_por_etapa.setdefault(c["etapa"], []).append(c["rede"])
        assert {e: sorted(set(r)) for e, r in redes_por_etapa.items()} == {
            "educacao_basica": ["total"], "educacao_infantil": ["total"], "ensino_fundamental": ["total"], "ensino_medio": ["total"],
            "creche": sorted(["total", *REDES_DO_INEP]), "pre_escola": sorted(["total", *REDES_DO_INEP]),
            "anos_iniciais": sorted(["total", *REDES_DO_INEP]), "anos_finais": sorted(["total", *REDES_DO_INEP])}, ano
    # 2025: as colunas das redes ficaram mais a direita (rede publica e categorias da rede privada entraram na tabela)
    colunas_2025 = {(p["aba"], c["etapa"], c["rede"]): c["coluna"] for p in partes for c in p["colunas"] if c["ano"] == 2025}
    assert colunas_2025["Educação Infantil 1.8", "creche", "federal"] == "Unnamed: 16"
    assert colunas_2025["Educação Infantil 1.8", "pre_escola", "privada"] == "Unnamed: 29"
    assert colunas_2025["Ensino Fundamental 1.20", "anos_iniciais", "estadual"] == "Unnamed: 17"
    assert colunas_2025["Ensino Fundamental 1.20", "anos_finais", "municipal"] == "Unnamed: 28"


def test_matriculas_basica_2000_a_2002_leem_a_tabela_de_cada_etapa_com_a_rede_na_mesma_aba(fichas):
    """Nas sinopses de 2000 a 2002 cada etapa tem uma aba com total e redes; 2001 e 2002 leem o ensino medio pelo rotulo."""
    partes = _partes(fichas, "matriculas_basica", "censo_escolar_2000_2002")
    for ano in (2000, 2001, 2002):
        do_ano = [p for p in partes if p["colunas"][0]["ano"] == ano]
        assert [p["aba"] for p in do_ano] == ["1.1", "1.5", "1.13", "1.36"], ano
        assert [p["colunas"][0]["etapa"] for p in do_ano] == ["creche", "pre_escola", "ensino_fundamental", "ensino_medio"]
        assert all([c["rede"] for c in p["colunas"]] == ["total", *REDES_DO_INEP] for p in do_ano), ano
        assert all(p["nomes_territorio"] == {"R. G. do Norte": "RN"} for p in do_ano)
    medio = {p["colunas"][0]["ano"]: p for p in partes if p["aba"] == "1.36"}
    assert [c["coluna"] for c in medio[2000]["colunas"]] == [f"Unnamed: {i}" for i in range(1, 6)]
    for ano in (2001, 2002):  # nessas abas a linha de rotulos fica logo acima do Brasil: e ela o cabecalho
        assert [c["coluna"] for c in medio[ano]["colunas"]] == ["Total", "Federal", "Estadual", "Municipal", "Privada"], ano


def test_matriculas_basica_offline_etapas_e_redes_de_cada_serie(base):
    m = base[(base.indicador_id == "matriculas_basica") & (base.territorio_id != "BR_FORA_NE")]
    redes = {(serie, etapa): sorted(g.rede.unique()) for (serie, etapa), g in m.groupby(["serie_id", "etapa"])}
    todas = sorted(["total", *REDES_DO_INEP])
    assert redes == {
        ("censo_escolar_2000_2002", "creche"): todas, ("censo_escolar_2000_2002", "pre_escola"): todas,
        ("censo_escolar_2000_2002", "ensino_fundamental"): todas, ("censo_escolar_2000_2002", "ensino_medio"): todas,
        ("censo_escolar_pre2007", "educacao_basica"): ["total"], ("censo_escolar_pre2007", "educacao_infantil"): ["total"],
        ("censo_escolar_pre2007", "creche"): todas, ("censo_escolar_pre2007", "pre_escola"): todas,
        ("censo_escolar_pre2007", "ensino_fundamental"): todas, ("censo_escolar_pre2007", "ensino_medio"): todas,
        ("educacenso", "educacao_basica"): ["total"], ("educacenso", "educacao_infantil"): ["total"],
        ("educacenso", "creche"): todas, ("educacenso", "pre_escola"): todas,
        ("educacenso", "ensino_fundamental"): ["total"], ("educacenso", "ensino_medio"): ["total"],
        ("educacenso", "anos_iniciais"): todas, ("educacenso", "anos_finais"): todas,
    }
    assert set(m.subindicador) == {""} and set(m.tipo_dado) == {"observado"}
    assert {s: sorted(set(g.ano)) for s, g in m.groupby("serie_id")} == {
        "censo_escolar_2000_2002": [2000, 2001, 2002], "censo_escolar_pre2007": [2005, 2006],
        "educacenso": list(range(2007, 2026))}


def test_matriculas_basica_offline_so_le_a_linha_de_cada_territorio_e_deriva_o_brasil_fora_ne(base):
    from gerar_fixtures import valor_contagem
    m = base[base.indicador_id == "matriculas_basica"]
    assert m.groupby(["serie_id", "etapa", "rede"]).ngroups == 20 + 22 + 24  # grupos de cada serie (ver o teste das etapas)
    for (serie, etapa, rede), grupo in m.groupby(["serie_id", "etapa", "rede"]):
        spec = {"etapa": etapa, "rede": rede}
        valores = grupo[grupo.ano == grupo.ano.min()].set_index("territorio_id")
        assert valores.valor["BA"] == valores.valor["MA"] == valor_contagem("BA", spec), (serie, etapa, rede)
        assert valores.valor["NE"] == valor_contagem("NE", spec) == 9 * valor_contagem("MA", spec)
        assert valores.valor["BR_FORA_NE"] == valor_contagem("BR", spec) - valor_contagem("NE", spec)
        assert valores.tipo_dado["BR_FORA_NE"] == "derivado" and valores.valor["BR_FORA_NE"] == 4 * valor_contagem("CE", spec)


def test_matriculas_basica_coleta_offline_registra_um_pacote_por_serie(projeto_completo):
    raiz = ["--raiz", str(projeto_completo.raiz), *HOJE]
    assert main(raiz + ["coletar", "--offline", "--indicador", "matriculas_basica"]) == 0
    coletas = pd.read_csv(projeto_completo.registro_coletas)
    assert sorted(coletas.serie_id) == ["censo_escolar_2000_2002", "censo_escolar_pre2007", "educacenso"]
    assert set(coletas.origem) == {"fixture"}


def test_superior_tem_duas_series_com_partes_por_ano(fichas):
    f = fichas["superior"]
    assert [(s.id, s.inicio, s.fim, s.coletor, s.verificado) for s in f.series] == [
        ("censup_pre2009", 2001, 2008, "arquivo", True), ("censup", 2009, 2024, "arquivo", True)]
    assert f.comparacao.referencia == "brasil_fora_ne" and f.comparacao.metodo == "soma"
    assert (f.unidade, f.limites, f.tratamento_monetario) == ("número (matrículas ou instituições)", {"min": 0}, None)
    pre, censup = (f.serie(i).parametros["partes"] for i in ("censup_pre2009", "censup"))
    assert _anos_das_partes(pre) == list(range(2001, 2009)) and _anos_das_partes(censup) == list(range(2009, 2025))
    assert len(pre) == 8 * 2 and len(censup) == 16 * 4  # tabelas 1.1 e 5.1; no censup, cada uma em Brasil e regioes e em UFs
    assert len(_urls_das_partes(pre)) == 8 and len(_urls_das_partes(censup)) == 16
    assert {p["formato"] for p in pre} == {"xls"} and {p["formato"] for p in censup} == {"xlsx"}
    assert _territorios_por_ano(pre) == {ano: TERRITORIOS_COMPLETOS for ano in range(2001, 2009)}
    assert _territorios_por_ano(censup) == {ano: TERRITORIOS_COMPLETOS for ano in range(2009, 2025)}
    for parte in censup:  # nas linhas "Total <territorio>"; a 5.1 so le a graduacao (a tabela traz tambem os sequenciais)
        assert ("Graduação" in parte["filtro_linhas"].values()) == (parte["aba"] == "5.1")
        assert all(nome.strip().startswith("Total ") for nome in parte["nomes_territorio"])
    assert {p["aba"] for p in pre + censup} == {"1.1", "5.1"}
    assert [p["linha_cabecalho"] for p in censup[:1]] == [10]


def test_superior_2020_a_2024_seguem_o_layout_de_cada_sinopse(fichas):
    """2020 a 2024 repetem as abas 1.1 e 5.1 (cabecalho na linha 10, colunas por posicao); mudam so 3 detalhes."""
    partes = _partes(fichas, "superior", "censup")
    for ano in range(2020, 2025):
        do_ano = [p for p in partes if p["colunas"][0]["ano"] == ano]
        assert [p["aba"] for p in do_ano] == ["1.1", "1.1", "5.1", "5.1"], ano
        assert {p["linha_cabecalho"] for p in do_ano} == {10}, ano
        assert len({p["url"] for p in do_ano}) == 1 and url_sinopse_superior(ano) == do_ano[0]["url"], ano
        assert {p["arquivo_no_zip"] for p in do_ano} == {
            f"Sinopse_Educação_Superior_{ano}/Sinopse_Educação_Superior_Municipio_{ano}.xlsx"}, ano
        colunas = {(p["aba"], c["subindicador"], c["rede"]): c["coluna"] for p in do_ano for c in p["colunas"]}
        assert colunas == {
            ("1.1", "ies", "total"): "Unnamed: 4", ("1.1", "universidades", "total"): "Unnamed: 12",
            ("5.1", "matriculas", "total"): "Unnamed: 5", ("5.1", "matriculas", "publica"): "Unnamed: 6",
            ("5.1", "matriculas", "privada"): "Unnamed: 10"}, ano
    # 1) 2024 troca de lugar o municipio e o nivel academico da 5.1: o nivel passa para a coluna 4 e o municipio para a 2
    for ano in range(2020, 2025):
        br, ufs = [p for p in partes if p["colunas"][0]["ano"] == ano and p["aba"] == "5.1"]
        nivel, municipio = ("Unnamed: 4", "Unnamed: 2") if ano == 2024 else ("Unnamed: 2", "Unnamed: 3")
        assert br["filtro_linhas"] == {"Unnamed: 1": "", nivel: "Graduação"}, ano
        assert ufs["filtro_linhas"] == {municipio: "", nivel: "Graduação"} and ufs["coluna_territorio"] == "Unnamed: 1", ano
    # 2) a linha de total da UF vem com dois espacos ("Total  Maranhao") em 2021 (aba 1.1) e em 2022 (abas 1.1 e 5.1)
    com_dois_espacos = {(2021, "1.1"), (2022, "1.1"), (2022, "5.1")}
    for p in partes:
        ano = p["colunas"][0]["ano"]
        if ano >= 2020 and p["territorios_esperados"][0] == "MA":  # as partes de UFs
            assert all("  " in nome for nome in p["nomes_territorio"]) == ((ano, p["aba"]) in com_dois_espacos), (ano, p["aba"])
    # 3) 2024, aba 1.1: a linha de total do Acre esta rotulada "Total Rondonia" (erro da fonte); a ficha le so o Nordeste,
    #    e nenhum nome de territorio de nenhuma parte pode ser o de Rondonia, senao a linha errada do Acre seria lida
    assert not any("Rondônia" in nome for p in partes for nome in p["nomes_territorio"])


def test_superior_cobertura_efetiva_vai_ate_2024_e_2025_nao_foi_publicado(fichas):
    f = fichas["superior"]
    assert cobertura_efetiva(f) == "2001–2024"
    observacoes = " ".join(f.observacoes.split())
    assert "Educação Superior de 2025 ainda não foi publicado" in observacoes and "fim: 2024" in observacoes
    assert "pendência" not in observacoes and "2020 a 2024 ficam" not in observacoes
    assert "2020 a 2024" in " ".join(f.serie("censup").compatibilidade.split())
    # o Brasil das matrículas inclui a linha "Exterior" da tabela 5.1, que nenhuma regiao tem: o Brasil fora do NE herda
    assert '"Exterior"' in observacoes and "inclui essas matrículas do exterior" in observacoes


def test_superior_declara_que_a_serie_antiga_so_tem_matriculas_totais_e_presenciais(fichas):
    f = fichas["superior"]
    assert "presenciais" in f.observacoes and "PDF" in f.observacoes
    assert "não é comparável" in f.serie("censup_pre2009").compatibilidade


def test_superior_offline_subindicadores_e_redes_de_cada_serie(base):
    s = base[(base.indicador_id == "superior") & (base.territorio_id != "BR_FORA_NE")]
    grupos = {(serie, sub): sorted(g.rede.unique()) for (serie, sub), g in s.groupby(["serie_id", "subindicador"])}
    assert grupos == {
        ("censup_pre2009", "ies"): ["total"], ("censup_pre2009", "universidades"): ["total"],
        ("censup_pre2009", "matriculas"): ["total"],
        ("censup", "ies"): ["total"], ("censup", "universidades"): ["total"],
        ("censup", "matriculas"): ["privada", "publica", "total"],
    }
    assert set(s.etapa) == {""} and set(s.tipo_dado) == {"observado"}
    assert {x: sorted(set(g.ano)) for x, g in s.groupby("serie_id")} == {
        "censup_pre2009": list(range(2001, 2009)), "censup": list(range(2009, 2025))}


def test_superior_offline_so_le_a_linha_de_cada_territorio_e_deriva_o_brasil_fora_ne(base):
    from gerar_fixtures import valor_contagem
    s = base[base.indicador_id == "superior"]
    for (serie, sub, rede), grupo in s.groupby(["serie_id", "subindicador", "rede"]):
        spec = {"subindicador": sub, "rede": rede}
        valores = grupo[grupo.ano == grupo.ano.min()].set_index("territorio_id")
        assert valores.valor["PE"] == valor_contagem("PE", spec), (serie, sub, rede)  # a linha-isca vale 1
        assert valores.valor["NE"] == 9 * valores.valor["PE"] and valores.valor["BR"] == 13 * valores.valor["PE"]
        assert valores.valor["BR_FORA_NE"] == 4 * valores.valor["PE"] and valores.tipo_dado["BR_FORA_NE"] == "derivado"
    censup = s[(s.serie_id == "censup") & (s.territorio_id == "BR") & (s.ano == 2009)].set_index(["subindicador", "rede"]).valor
    assert censup[("matriculas", "total")] == censup[("matriculas", "publica")] + censup[("matriculas", "privada")]
    assert censup[("ies", "total")] > censup[("universidades", "total")]


def test_superior_coleta_offline_registra_um_pacote_por_serie(projeto_completo):
    raiz = ["--raiz", str(projeto_completo.raiz), *HOJE]
    assert main(raiz + ["coletar", "--offline", "--indicador", "superior"]) == 0
    coletas = pd.read_csv(projeto_completo.registro_coletas)
    assert sorted(coletas.serie_id) == ["censup", "censup_pre2009"] and set(coletas.origem) == {"fixture"}


@pytest.mark.parametrize("indicador, serie, tamanho, pacote, duracao", [
    ("matriculas_basica", "educacenso", "~2,7 GB", "~37 MB", "~49 minutos"),
    ("superior", "censup", "~3,7 GB", "~38 MB", "~72 minutos")])
def test_series_grandes_do_inep_declaram_o_custo_operacional_medido(fichas, indicador, serie, tamanho, pacote, duracao):
    """Custos medidos com o pacote reduzido (Tarefas C2, C4 e C5), nao os da coleta antiga com zips inteiros."""
    texto = " ".join(fichas[indicador].observacoes.split())
    assert f"`{serie}`" in texto and tamanho in texto and f"pacote bruto guardado tem {pacote}" in texto
    assert "MB de RAM" in texto and duracao in texto and "MB/s" in texto
    assert "exercitada de ponta a ponta" in texto and "isoladamente" in texto
    for antigo in ("~1,9 GB", "~2 GB", "~25 MB", "35 a 60 minutos", "~4 GB de RAM", "não foi exercitada", "~28 MB",
                   "15 arquivos", "11 arquivos", "não foi repetida"):
        assert antigo not in texto, antigo


NOTA_DA_LINHA_DO_IPEADATA = (
    "Linha declarada segundo o Ipeadata (metadados da série); não conferida contra publicação do IBGE, que recusa "
    "acesso automatizado; aceita como confirmação por decisão do usuário em 2026-11-01."
)


def _normalizado(texto: str) -> str:
    return " ".join(texto.split())


def test_fichas_de_pobreza_verificadas_declaram_a_linha_a_nota_de_origem_e_a_quebra_de_consolidacao(fichas):
    """Verificada pela decisao do usuario (Ipeadata como confirmacao): a linha, a origem e a quebra ficam nas fichas."""
    for ficha_id, linha in (("pobreza", "8,30"), ("extrema_pobreza", "3,00")):
        f = fichas[ficha_id]
        serie = f.serie("pnadc")
        assert serie.verificado and (serie.inicio, serie.fim) == (2012, 2024), ficha_id
        for texto in (f.descricao, f.unidade, f.metodologia):  # a linha esta em tres campos
            assert f"US$ {linha} por dia (PPC 2021)" in _normalizado(texto), (ficha_id, texto)
        assert NOTA_DA_LINHA_DO_IPEADATA in _normalizado(f.metodologia), ficha_id
        assert NOTA_DA_LINHA_DO_IPEADATA in _normalizado(f.observacoes), ficha_id
        assert "Ipeadata" in serie.compatibilidade and "PPC 2021" in serie.compatibilidade, ficha_id
        assert "não foi confirmada" not in f.metodologia and "não verificada" not in f.observacoes, ficha_id
        # quebra de consolidacao: primeiras entrevistas 2012-2019 e 2023-2024, quintas entrevistas 2020-2022
        for texto in (f.metodologia, serie.compatibilidade):
            assert "primeiras entrevistas em 2012 a 2019 e 2023 a 2024" in _normalizado(texto), ficha_id
            assert "quintas entrevistas em 2020 a 2022" in _normalizado(texto), ficha_id


def test_dicionario_registra_a_confirmacao_da_pobreza_pelo_ipeadata_como_divergencia_e_risco():
    texto = _normalizado(DICIONARIO.read_text(encoding="utf-8"))
    divergencias = texto[texto.index("## Divergências em relação à seção 4 da spec"):texto.index("## Bloco PNUD")]
    item = divergencias.split(" 18. ")[1]  # nova entrada, depois da 17
    assert "`pobreza`" in item and "`extrema_pobreza`" in item and "Ipeadata" in item
    assert "decisão do usuário em 2026-11-01" in item and "publicação do IBGE" in item
    assert "reverificar a linha a cada atualização anual" in item and "foco de revisão 5" in item
    for secao in ("### pobreza / pnadc", "### extrema_pobreza / pnadc"):
        corpo = texto[texto.index(secao) + len(secao):]
        corpo = corpo[:corpo.index(" ### ")]
        assert "**Série verificada (`verificado: true`)" in corpo and "195 linhas" in corpo, secao
        assert NOTA_DA_LINHA_DO_IPEADATA in corpo, secao
