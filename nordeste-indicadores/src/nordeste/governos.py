"""Tabela de governos e atribuicao anual do presidente."""

from datetime import date
from pathlib import Path

import pandas as pd


def carregar_governos(path: Path) -> pd.DataFrame:
    """Le governos.csv: texto nas colunas descritivas e datetime.date em inicio e fim."""
    governos = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")
    for coluna in ("inicio", "fim"):
        governos[coluna] = [date.fromisoformat(valor) for valor in governos[coluna]]
    return governos


def atribuir_governo(ano: int, governos: pd.DataFrame) -> tuple[str, str]:
    """Devolve (presidente, mandato) do governo que cobre o ano inteiro.

    Sem governo cobrindo de 1o/jan a 31/dez, devolve o rotulo de transicao
    `transicao_<apelidos em ordem>` com mandato vazio.
    """
    inicio_ano, fim_ano = date(ano, 1, 1), date(ano, 12, 31)
    for g in governos.itertuples():
        if g.inicio <= inicio_ano and g.fim >= fim_ano:
            return g.presidente, g.mandato
    apelidos: list[str] = []
    for g in governos.sort_values("inicio").itertuples():
        if g.inicio <= fim_ano and g.fim >= inicio_ano and g.apelido.lower() not in apelidos:
            apelidos.append(g.apelido.lower())
    if not apelidos:
        raise ValueError(f"Nenhum governo cobre o ano {ano}.")
    return "transicao_" + "_".join(apelidos), ""
