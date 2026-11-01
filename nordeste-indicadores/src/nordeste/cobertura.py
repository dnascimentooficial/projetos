"""Relatorio de cobertura: anos disponiveis, anos faltantes e proxima publicacao esperada."""

import pandas as pd

from nordeste.fichas import Ficha

COLUNAS_COBERTURA: list[str] = [
    "indicador_id", "serie_id", "territorio_id", "primeiro_ano", "ultimo_ano",
    "anos_faltantes", "proxima_publicacao",
]


def proxima_publicacao(ultimo_ano: int, defasagem_meses: int) -> str:
    """"AAAA-MM" da proxima publicacao: conta `defasagem_meses` a partir de dezembro do ultimo ano."""
    ano, mes_zero = divmod(ultimo_ano * 12 + 11 + defasagem_meses, 12)
    return f"{ano:04d}-{mes_zero + 1:02d}"


def _anos_faltantes(inicio: int, fim: int | None, anos: set[int]) -> str:
    limite = fim if fim is not None else max(anos, default=inicio - 1)
    return ";".join(str(a) for a in range(inicio, limite + 1) if a not in anos)


def relatorio_cobertura(base: pd.DataFrame, fichas: dict[str, Ficha]) -> pd.DataFrame:
    """Uma linha por indicador, serie e territorio presentes na base.

    `primeiro_ano` e `ultimo_ano` olham so os anos com valor. `anos_faltantes` lista, separados por
    ";", os anos entre `inicio` e `fim` da serie (ou o ultimo ano disponivel, se `fim` for nulo) sem valor.
    Series que a ficha nao declara ficam de fora: nao ha janela para medir.
    """
    linhas: list[dict] = []
    for (indicador_id, serie_id, territorio_id), grupo in base.groupby(
        ["indicador_id", "serie_id", "territorio_id"], sort=True,
    ):
        ficha = fichas.get(indicador_id)
        serie = next((s for s in ficha.series if s.id == serie_id), None) if ficha else None
        if serie is None:
            continue
        anos = set(grupo.loc[grupo.valor.notna(), "ano"].astype(int))
        ultimo = max(anos) if anos else None
        linhas.append({
            "indicador_id": indicador_id, "serie_id": serie_id, "territorio_id": territorio_id,
            "primeiro_ano": min(anos) if anos else None, "ultimo_ano": ultimo,
            "anos_faltantes": _anos_faltantes(serie.inicio, serie.fim, anos),
            "proxima_publicacao": proxima_publicacao(ultimo, ficha.defasagem_meses) if anos else "",
        })
    saida = pd.DataFrame(linhas, columns=COLUNAS_COBERTURA)
    for coluna in ("primeiro_ano", "ultimo_ano"):
        saida[coluna] = saida[coluna].astype("Int64")
    return saida
