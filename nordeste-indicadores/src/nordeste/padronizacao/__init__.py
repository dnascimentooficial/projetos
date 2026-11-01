"""Padronizadores: convertem o arquivo bruto de uma coleta para o formato da base."""

import pandas as pd

from nordeste.caminhos import Caminhos
from nordeste.coletores.registro import Coleta
from nordeste.fichas import Ficha, Serie
from nordeste.padronizacao.erros import ErroLayout
from nordeste.padronizacao.ipeadata import padronizar_ipeadata
from nordeste.padronizacao.planilha import padronizar_planilha
from nordeste.padronizacao.sidra import padronizar_sidra

__all__ = ["ErroLayout", "padronizar"]

_PADRONIZADORES = {
    "sidra": padronizar_sidra,
    "planilha": padronizar_planilha,
    "ipeadata": padronizar_ipeadata,
}


def padronizar(
    ficha: Ficha, serie: Serie, coleta: Coleta, caminhos: Caminhos, territorios: pd.DataFrame,
) -> pd.DataFrame:
    """Padroniza o arquivo bruto da coleta e marca os anos de estimativa oficial.

    O padronizador vem de parametros["padronizador"] ou, na falta, do coletor da serie.
    Anos de parametros["anos_estimativa"] viram estimativa_oficial; linhas indisponiveis
    continuam indisponiveis (valor nulo <=> indisponivel).
    """
    nome = serie.parametros.get("padronizador", serie.coletor)
    if nome not in _PADRONIZADORES:
        raise ErroLayout(f"padronizador desconhecido em {ficha.id}/{serie.id}: {nome}")
    conteudo = (caminhos.raiz / coleta.arquivo).read_bytes()
    df = _PADRONIZADORES[nome](conteudo, ficha, serie, coleta.coleta_id, territorios)
    estimados = df["ano"].isin(serie.parametros.get("anos_estimativa", [])) & (
        df["tipo_dado"] != "indisponivel")
    df.loc[estimados, "tipo_dado"] = "estimativa_oficial"
    return df
