"""Relatorio de cobertura: anos disponiveis, anos faltantes e proxima publicacao esperada."""

import pandas as pd

from nordeste.fichas import Ficha

COLUNAS_COBERTURA: list[str] = [
    "indicador_id", "serie_id", "territorio_id", "primeiro_ano", "ultimo_ano",
    "anos_faltantes", "proxima_publicacao",
]


def proxima_publicacao(ultimo_ano: int, defasagem_meses: int) -> str:
    """"AAAA-MM" da proxima publicacao esperada.

    A proxima publicacao e a do ano seguinte ao ultimo disponivel: conta `defasagem_meses` a partir
    de dezembro de `ultimo_ano + 1`. (Dezembro de `ultimo_ano` mais a defasagem e a data em que o
    proprio `ultimo_ano` ja saiu.)
    """
    ano, mes_zero = divmod((ultimo_ano + 1) * 12 + 11 + defasagem_meses, 12)
    return f"{ano:04d}-{mes_zero + 1:02d}"


def relatorio_cobertura(base: pd.DataFrame, fichas: dict[str, Ficha]) -> pd.DataFrame:
    """Uma linha por indicador, serie e territorio presentes na base.

    `primeiro_ano` e `ultimo_ano` olham so os anos com valor do territorio. `anos_faltantes` lista,
    separados por ";", os anos entre `inicio` e `fim` da serie (ou o ultimo ano disponivel da serie,
    se `fim` for nulo) em que a serie tem valor em algum territorio mas este nao tem, mais os anos em
    que ele tem linha `indisponivel`. Anos que ninguem publica (serie bienal) nao sao faltantes.
    `proxima_publicacao` so e prevista para serie em curso (`fim` nulo); com `fim` declarado fica vazia.
    Series que a ficha nao declara ficam de fora: nao ha janela para medir.
    """
    linhas: list[dict] = []
    for (indicador_id, serie_id), serie_base in base.groupby(["indicador_id", "serie_id"], sort=True):
        ficha = fichas.get(indicador_id)
        serie = next((s for s in ficha.series if s.id == serie_id), None) if ficha else None
        if serie is None:
            continue
        publicados = set(serie_base.loc[serie_base.valor.notna(), "ano"].astype(int))
        limite = serie.fim if serie.fim is not None else max(publicados, default=serie.inicio - 1)
        janela = set(range(serie.inicio, limite + 1))
        em_curso = serie.fim is None  # serie com fim declarado esta encerrada: nao se preve proxima publicacao
        for territorio_id, grupo in serie_base.groupby("territorio_id", sort=True):
            anos = set(grupo.loc[grupo.valor.notna(), "ano"].astype(int))
            indisponiveis = set(grupo.loc[grupo.valor.isna(), "ano"].astype(int))
            faltantes = sorted(janela & ((publicados - anos) | indisponiveis))
            ultimo = max(anos) if anos else None
            linhas.append({
                "indicador_id": indicador_id, "serie_id": serie_id, "territorio_id": territorio_id,
                "primeiro_ano": min(anos) if anos else None, "ultimo_ano": ultimo,
                "anos_faltantes": ";".join(map(str, faltantes)),
                "proxima_publicacao": proxima_publicacao(ultimo, ficha.defasagem_meses) if anos and em_curso else "",
            })
    saida = pd.DataFrame(linhas, columns=COLUNAS_COBERTURA)
    for coluna in ("primeiro_ano", "ultimo_ano"):
        saida[coluna] = saida[coluna].astype("Int64")
    return saida
