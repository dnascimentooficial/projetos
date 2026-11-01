"""Consolidacao: junta, numa unica base, a ultima coleta padronizada de cada serie."""

from dataclasses import dataclass

import pandas as pd

from nordeste.caminhos import Caminhos
from nordeste.coletores.registro import ler_registro, ultima_coleta
from nordeste.esquema import CHAVE_BASE, COLUNAS_BASE, normalizar_base
from nordeste.fichas import Ficha
from nordeste.padronizacao import ErroLayout, padronizar


@dataclass(frozen=True)
class Pendencia:
    indicador_id: str
    serie_id: str
    motivo: str


def _calculos_pendentes(fichas: dict[str, Ficha], pendencias: list[Pendencia]) -> list[Pendencia]:
    """Indicador calculado cuja serie de numerador ou de denominador ficou pendente."""
    pendentes = {(p.indicador_id, p.serie_id) for p in pendencias}
    novas: list[Pendencia] = []
    for ficha in fichas.values():
        calculo = ficha.calculo
        if calculo is None:
            continue
        insumos = [(calculo.numerador, calculo.serie_numerador)]
        insumos += sorted({(calculo.denominador, f.serie) for f in calculo.faixas})
        faltando = [f"{i}/{s}" for i, s in insumos if (i, s) in pendentes]
        if faltando:
            novas.append(Pendencia(ficha.id, ficha.series[0].id, f"insumo pendente: {', '.join(faltando)}"))
    return novas


def _comparacoes_pendentes(fichas: dict[str, Ficha], pendencias: list[Pendencia]) -> list[Pendencia]:
    """Serie de indicador cuja comparacao (razao ou razao_encadeada) usa numerador ou denominador pendente na serie.

    Sem a pendencia, as linhas BR_FORA_NE do indicador sumiriam da base publicada; com ela, a publicacao
    reaproveita as linhas ja publicadas da serie. Serie ja pendente nao ganha segunda pendencia.
    """
    pendentes = {(p.indicador_id, p.serie_id) for p in pendencias}
    novas: list[Pendencia] = []
    for ficha in fichas.values():
        comp = ficha.comparacao
        if comp.numerador is None or comp.denominador is None:
            continue
        for serie in ficha.series:
            if (ficha.id, serie.id) in pendentes:
                continue
            faltando = [f"{i}/{serie.id}" for i in (comp.numerador, comp.denominador) if (i, serie.id) in pendentes]
            if faltando:
                novas.append(Pendencia(ficha.id, serie.id, f"insumo da comparacao pendente: {', '.join(faltando)}"))
    return novas


def consolidar(
    caminhos: Caminhos, fichas: dict[str, Ficha], territorios: pd.DataFrame,
) -> tuple[pd.DataFrame, list[Pendencia]]:
    """Padroniza a ultima coleta de cada serie de cada ficha e devolve a base ordenada por CHAVE_BASE.

    Serie sem coleta, com arquivo bruto ausente (os brutos ficam fora do Git) ou com ErroLayout vira Pendencia e
    fica fora da base; outras excecoes propagam. Fichas com `calculo` nao tem coleta (sao calculadas depois, sobre
    esta base); so viram Pendencia quando uma serie de insumo do calculo esta pendente. Serie cuja comparacao
    (razao) tem insumo pendente tambem vira Pendencia.
    """
    registro = ler_registro(caminhos.registro_coletas)
    partes: list[pd.DataFrame] = []
    pendencias: list[Pendencia] = []
    for ficha in fichas.values():
        if ficha.calculo is not None:
            continue
        for serie in ficha.series:
            coleta = ultima_coleta(registro, ficha.id, serie.id)
            if coleta is None:
                pendencias.append(Pendencia(ficha.id, serie.id, "sem coleta"))
                continue
            if not (caminhos.raiz / coleta.arquivo).is_file():
                pendencias.append(Pendencia(
                    ficha.id, serie.id, f"arquivo bruto ausente; rode coletar ({coleta.arquivo})"))
                continue
            try:
                partes.append(padronizar(ficha, serie, coleta, caminhos, territorios))
            except ErroLayout as erro:
                pendencias.append(Pendencia(ficha.id, serie.id, str(erro)))
    pendencias += _comparacoes_pendentes(fichas, pendencias)
    pendencias += _calculos_pendentes(fichas, pendencias)
    if not partes:
        return normalizar_base(pd.DataFrame(columns=COLUNAS_BASE)), pendencias
    base = normalizar_base(pd.concat(partes, ignore_index=True))
    return base.sort_values(CHAVE_BASE, kind="stable").reset_index(drop=True), pendencias
