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
FICHAS_PARTE_A = {
    "populacao", "pib_participacao", "pib_nominal", "pib_per_capita", "populacao_contas_regionais",
}
HOJE = ["--hoje", "2026-11-01"]
DICIONARIO = Path(__file__).resolve().parent.parent / "docs" / "dicionario-verificacao.md"
URL_DO_COLETOR = {"sidra": url_sidra, "ipeadata": url_ipeadata, "arquivo": url_arquivo}


@pytest.fixture
def fichas(projeto_completo):
    return carregar_fichas(projeto_completo.fichas)


def _series(fichas):
    return [(f, s) for f in fichas.values() for s in f.series]


@pytest.fixture
def base(projeto_completo):
    raiz = ["--raiz", str(projeto_completo.raiz), *HOJE]
    assert main(raiz + ["coletar", "--offline"]) == 0
    assert main(raiz + ["consolidar"]) == 0
    return pd.read_csv(projeto_completo.trabalho / "base.csv", keep_default_na=False,
                       na_values={"valor": [""]})


def test_fichas_da_parte_a_existem(fichas):
    assert FICHAS_PARTE_A <= set(fichas)


def test_toda_serie_tem_exatamente_uma_fixture(projeto_completo, fichas):
    for f, s in _series(fichas):
        achadas = sorted((projeto_completo.fixtures / f.id).glob(f"{s.id}.*"))
        assert len(achadas) == 1, f"{f.id}/{s.id}: {achadas}"


def test_serie_verificada_tem_parametros_de_coleta_completos(fichas):
    verificadas = [(f, s) for f, s in _series(fichas) if s.verificado]
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
        if s.verificado:  # a evidencia citada e a URL exata que o coletor monta a partir da ficha
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
        if f.id not in FICHAS_PARTE_A:
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
