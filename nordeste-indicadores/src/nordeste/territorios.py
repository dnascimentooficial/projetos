"""Tabela de territorios (Brasil, regioes, UFs do Nordeste e agregado derivado)."""

import unicodedata
from pathlib import Path

import pandas as pd

UFS_NE: tuple[str, ...] = ("MA", "PI", "CE", "RN", "PB", "PE", "AL", "SE_UF", "BA")
REGIOES: tuple[str, ...] = ("N", "NE", "SE", "S", "CO")

# Nivel territorial do IBGE (n1, n2, n3) -> valor de `tipo` na tabela.
_TIPO_POR_NIVEL = {"n1": "pais", "n2": "regiao", "n3": "uf"}


def carregar_territorios(path: Path) -> pd.DataFrame:
    """Le territorios.csv com todas as colunas como texto (vazio vira "")."""
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")


def territorio_por_codigo(territorios: pd.DataFrame, nivel: str, codigo: str) -> str | None:
    """Devolve o territorio_id do codigo IBGE no nivel dado, ou None se nao houver."""
    if nivel not in _TIPO_POR_NIVEL:
        raise ValueError(f"Nivel territorial desconhecido: {nivel!r}. Use n1, n2 ou n3.")
    achados = territorios[
        (territorios["tipo"] == _TIPO_POR_NIVEL[nivel]) & (territorios["codigo_ibge"] == str(codigo))
    ]
    return achados["territorio_id"].iloc[0] if len(achados) else None


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sem_acento.strip().casefold()


def territorio_por_nome(territorios: pd.DataFrame, nome: str) -> str | None:
    """Devolve o territorio_id pelo nome, sem diferenca de acento ou de maiusculas."""
    alvo = _normalizar(nome)
    for territorio_id, nome_tabela in zip(territorios["territorio_id"], territorios["nome"]):
        if _normalizar(nome_tabela) == alvo:
            return territorio_id
    return None
