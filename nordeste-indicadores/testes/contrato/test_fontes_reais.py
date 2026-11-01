"""Contrato com as fontes oficiais reais: cada serie verificada e coletada da rede e padronizada.

Fora da execucao padrao (marcador `rede`): `python -m pytest -m rede -v`. Cada teste coleta com offline=False
em diretorio temporario, padroniza e confere que o Brasil e o Nordeste vieram e que a serie comeca no
`inicio` da ficha. As series de download enorme (varios arquivos do INEP, ~2 GB por serie) so rodam com
NORDESTE_CONTRATO_PESADO=1; sem ela, sao puladas com o motivo.
"""

import os
import shutil
from datetime import date
from pathlib import Path

import pytest

from nordeste.caminhos import Caminhos
from nordeste.coletores import coletar_serie
from nordeste.fichas import carregar_fichas
from nordeste.padronizacao import padronizar
from nordeste.territorios import UFS_NE, carregar_territorios

RAIZ_REPOSITORIO = Path(__file__).resolve().parents[2]
VARIAVEL_PESADO = "NORDESTE_CONTRATO_PESADO"
# Series com dezenas de arquivos grandes do INEP (~2 GB de download cada, uma hora sequencial a ~0,5 MB/s).
SERIES_PESADAS = {("matriculas_basica", "educacenso"), ("superior", "censup")}
# Series cuja fonte nao publica o Nordeste (o IDHM do Censo so tem Brasil e UFs, e o indice nao se recompoe das UFs):
# o contrato confere o Brasil e as nove UFs no lugar do Nordeste. A ficha declara a lacuna em `compatibilidade`.
SERIES_SEM_NORDESTE = {("idhm", "censo")}


def motivo_para_pular(indicador: str, serie: str, ambiente=os.environ) -> str | None:
    """Motivo de pular uma serie de download enorme, ou None quando ela deve rodar."""
    if (indicador, serie) in SERIES_PESADAS and ambiente.get(VARIAVEL_PESADO) != "1":
        return f"download enorme (~2 GB) em {indicador}/{serie}; defina {VARIAVEL_PESADO}=1 para rodar"
    return None


def territorios_esperados(indicador: str, serie: str) -> set[str]:
    """Territorios que a serie real precisa trazer: Brasil e Nordeste (Brasil e as UFs, se a fonte nao publica o NE)."""
    return {"BR", *UFS_NE} if (indicador, serie) in SERIES_SEM_NORDESTE else {"BR", "NE"}


def _series_verificadas() -> list:
    """(ficha, serie) de toda serie verificada que o coletor busca (o indicador calculado nao tem arquivo bruto)."""
    fichas = carregar_fichas(RAIZ_REPOSITORIO / "metadados" / "indicadores")
    return [
        pytest.param(ficha, serie, id=f"{ficha.id}/{serie.id}", marks=pytest.mark.rede)
        for ficha in fichas.values() if ficha.calculo is None
        for serie in ficha.series if serie.verificado
    ]


@pytest.mark.parametrize("ficha, serie", _series_verificadas())
def test_serie_real_coleta_e_padroniza(ficha, serie, tmp_path):
    motivo = motivo_para_pular(ficha.id, serie.id)
    if motivo:
        pytest.skip(motivo)
    shutil.copytree(RAIZ_REPOSITORIO / "metadados", tmp_path / "metadados")  # territorios e certificados (ca_extra)
    caminhos = Caminhos(tmp_path)

    coleta = coletar_serie(ficha, serie, caminhos, offline=False, hoje=date.today())
    df = padronizar(ficha, serie, coleta, caminhos, carregar_territorios(caminhos.territorios_csv))

    assert territorios_esperados(ficha.id, serie.id) <= set(df.territorio_id)
    assert df.ano.min() <= serie.inicio


# Mecanica do contrato (roda na execucao padrao, sem rede).

def test_series_pesadas_existem_na_ficha_e_sao_verificadas():
    fichas = carregar_fichas(RAIZ_REPOSITORIO / "metadados" / "indicadores")
    for indicador, serie in SERIES_PESADAS:
        assert any(s.id == serie and s.verificado for s in fichas[indicador].series), (indicador, serie)


@pytest.mark.parametrize("indicador, serie", sorted(SERIES_PESADAS))
def test_serie_pesada_e_pulada_com_motivo_sem_a_variavel(indicador, serie):
    motivo = motivo_para_pular(indicador, serie, ambiente={})
    assert VARIAVEL_PESADO in motivo and "2 GB" in motivo and f"{indicador}/{serie}" in motivo
    assert motivo_para_pular(indicador, serie, ambiente={VARIAVEL_PESADO: "0"}) == motivo
    assert motivo_para_pular(indicador, serie, ambiente={VARIAVEL_PESADO: "1"}) is None


def test_serie_leve_nunca_e_pulada():
    assert motivo_para_pular("pib_nominal", "scr_ref2010", ambiente={}) is None


def test_serie_que_a_fonte_publica_sem_o_nordeste_confere_brasil_e_as_ufs():
    fichas = carregar_fichas(RAIZ_REPOSITORIO / "metadados" / "indicadores")
    for indicador, serie in SERIES_SEM_NORDESTE:
        assert "sem o Nordeste" in fichas[indicador].serie(serie).compatibilidade  # a ficha declara a lacuna
        assert territorios_esperados(indicador, serie) == {"BR", *UFS_NE}
    assert territorios_esperados("pib_nominal", "scr_ref2010") == {"BR", "NE"}
