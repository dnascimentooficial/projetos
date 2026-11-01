"""Conferencias repetiveis com as fontes reais (marcador `rede`): PIB per capita e valores-ancora.

`python -m pytest -m rede -k "per_capita or ancora" -v`. Coletam da rede em diretorio temporario e:

- recalculam o PIB per capita (pib_nominal / populacao x 1000, mapeamento da ficha) e o comparam com os 7 pontos de
  fonte primaria do IBGE registrados em docs/dicionario-verificacao.md (2023 e Maranhao 2016), a ate 0,5%;
- conferem um valor estavel por serie leve (meia unidade da ultima casa publicada), para pegar coluna, ano ou
  territorio deslocado no padronizador.
"""

import shutil
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from nordeste.caminhos import Caminhos
from nordeste.coletores import coletar_serie
from nordeste.derivados import aplicar_calculos
from nordeste.fichas import carregar_fichas
from nordeste.padronizacao import padronizar
from nordeste.territorios import carregar_territorios

pytestmark = pytest.mark.rede

RAIZ_REPOSITORIO = Path(__file__).resolve().parents[2]
TOLERANCIA = 0.005  # relativa, como na R08

# Fonte primaria do IBGE (dicionario de verificacao, secao "Conferencia contra valores publicados"):
# os seis de 2023 sao da materia [10] da Agencia IBGE; Maranhao 2016, do release [4].
PER_CAPITA_IBGE = {
    ("BR", 2023): 53886.67, ("NE", 2023): 27681.97, ("CE", 2023): 26405.96, ("PE", 2023): 29857.27,
    ("BA", 2023): 30476.54, ("MA", 2023): 22020.63, ("MA", 2016): 12264.28,
}

# (indicador, serie, subindicador, territorio, ano): (valor, meia unidade da ultima casa publicada)
ANCORAS = {
    ("ideb", "ideb", "anos_iniciais", "NE", 2023): (5.6, 0.05),
    ("desocupacao", "pnadc", "", "NE", 2012): (9.6, 0.05),
    ("pib_participacao", "scr_ref2010", "", "NE", 2002): (13.09, 0.005),
}


@pytest.fixture(scope="module")
def caminhos(tmp_path_factory) -> Caminhos:
    raiz = tmp_path_factory.mktemp("ancoras")
    shutil.copytree(RAIZ_REPOSITORIO / "metadados", raiz / "metadados")  # fichas, territorios e certificados
    return Caminhos(raiz)


@pytest.fixture(scope="module")
def fichas(caminhos):
    return carregar_fichas(caminhos.fichas)


def _coletar_e_padronizar(caminhos: Caminhos, ficha, serie_id: str) -> pd.DataFrame:
    serie = ficha.serie(serie_id)
    coleta = coletar_serie(ficha, serie, caminhos, offline=False, hoje=date.today())
    return padronizar(ficha, serie, coleta, caminhos, carregar_territorios(caminhos.territorios_csv))


def test_pib_per_capita_calculado_confere_com_a_fonte_primaria_do_ibge(caminhos, fichas):
    ficha = fichas["pib_per_capita"]
    calculo = ficha.calculo
    insumos = [(calculo.numerador, calculo.serie_numerador)]
    insumos += sorted({(calculo.denominador, f.serie) for f in calculo.faixas})
    base = pd.concat(
        [_coletar_e_padronizar(caminhos, fichas[i], s) for i, s in insumos], ignore_index=True)

    calculada, _ = aplicar_calculos(base, {ficha.id: ficha, **{i: fichas[i] for i, _ in insumos}})
    valores = calculada.set_index(["territorio_id", "ano"]).valor
    divergentes = {
        ponto: (round(valores.get(ponto, float("nan")), 2), publicado)
        for ponto, publicado in PER_CAPITA_IBGE.items()
        if not abs(valores.get(ponto, float("nan")) - publicado) <= TOLERANCIA * publicado
    }
    assert not divergentes, f"(calculado, publicado) fora de 0,5%: {divergentes}"


@pytest.mark.parametrize("chave", list(ANCORAS), ids=lambda c: f"ancora-{c[0]}-{c[3]}-{c[4]}")
def test_ancora_de_serie_leve(caminhos, fichas, chave):
    indicador, serie_id, subindicador, territorio, ano = chave
    esperado, folga = ANCORAS[chave]
    df = _coletar_e_padronizar(caminhos, fichas[indicador], serie_id)
    achado = df[(df.subindicador == subindicador) & (df.territorio_id == territorio) & (df.ano == ano)
                & df.etapa.eq("") & df.rede.isin(["", "total"])]
    assert len(achado) == 1, achado
    assert achado.valor.iloc[0] == pytest.approx(esperado, abs=folga)
