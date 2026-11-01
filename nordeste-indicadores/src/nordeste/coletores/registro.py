"""Registro de coletas: um CSV append-only com uma linha por arquivo bruto."""

import csv
from dataclasses import asdict, dataclass, fields
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class Coleta:
    coleta_id: str
    indicador_id: str
    serie_id: str
    url: str
    data_coleta: str
    sha256: str
    origem: str  # "rede" ou "fixture"
    arquivo: str  # relativo a raiz do projeto, com "/"


COLUNAS: list[str] = [campo.name for campo in fields(Coleta)]


def ler_registro(path: Path) -> pd.DataFrame:
    """Le o registro; arquivo inexistente devolve DataFrame vazio com as colunas de Coleta."""
    if not path.exists():
        return pd.DataFrame(columns=COLUNAS)
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _coleta(linha) -> Coleta:
    return Coleta(**{coluna: linha[coluna] for coluna in COLUNAS})


def ultima_coleta(registro: pd.DataFrame, indicador_id: str, serie_id: str) -> Coleta | None:
    """Ultima linha gravada para o indicador e a serie (ordem de gravacao, nao de data)."""
    achadas = registro[(registro["indicador_id"] == indicador_id) & (registro["serie_id"] == serie_id)]
    return None if achadas.empty else _coleta(achadas.iloc[-1])


def registrar(path: Path, coleta: Coleta) -> Coleta:
    """Acrescenta a coleta; se ja ha linha com mesmo indicador, serie e sha256, devolve-a sem gravar."""
    registro = ler_registro(path)
    iguais = registro[
        (registro["indicador_id"] == coleta.indicador_id)
        & (registro["serie_id"] == coleta.serie_id)
        & (registro["sha256"] == coleta.sha256)
    ]
    if not iguais.empty:
        return _coleta(iguais.iloc[0])
    novo = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as saida:
        escritor = csv.DictWriter(saida, fieldnames=COLUNAS, lineterminator="\n")
        if novo:
            escritor.writeheader()
        escritor.writerow(asdict(coleta))
    return coleta
