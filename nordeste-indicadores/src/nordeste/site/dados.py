"""Dados do site: a base publicada, seus derivados e relatorios, lidos de dados/base, dados/relatorios e metadados."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from nordeste.caminhos import Caminhos
from nordeste.coletores.registro import ler_registro
from nordeste.esquema import COLUNAS_DERIVADOS, normalizar_base
from nordeste.fichas import Ficha, carregar_fichas
from nordeste.governos import carregar_governos


@dataclass(frozen=True)
class Ponto:
    ano: int
    valor: float
    serie: str


def _ler_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")


def _ler_derivados(path: Path) -> pd.DataFrame:
    derivados = _ler_csv(path)
    derivados["ano"] = derivados["ano"].astype(int)
    derivados["valor"] = pd.to_numeric(derivados["valor"]).astype(float)
    return derivados[COLUNAS_DERIVADOS]


@dataclass
class DadosSite:
    base: pd.DataFrame
    derivados: pd.DataFrame
    cobertura: pd.DataFrame
    coletas: pd.DataFrame
    fichas: dict[str, Ficha]
    governos: pd.DataFrame
    sha256_base: str
    data_base: str

    @classmethod
    def carregar(cls, caminhos: Caminhos) -> "DadosSite":
        arquivo_base = caminhos.base / "base_nordeste.csv"
        coletas = ler_registro(caminhos.registro_coletas)
        if coletas.empty:
            raise ValueError(f"Sem coletas em {caminhos.registro_coletas}: nao ha data da base.")
        return cls(
            base=normalizar_base(_ler_csv(arquivo_base)),
            derivados=_ler_derivados(caminhos.base / "derivados.csv"),
            cobertura=_ler_csv(caminhos.relatorios / "cobertura.csv"),
            coletas=coletas,
            fichas=carregar_fichas(caminhos.fichas),
            governos=carregar_governos(caminhos.governos_csv),
            sha256_base=hashlib.sha256(arquivo_base.read_bytes()).hexdigest(),
            data_base=max(coletas["data_coleta"]),
        )

    def serie(
        self, indicador: str, territorio: str, *,
        sub: str | None = None, etapa: str | None = None, rede: str | None = None, serie: str | None = None,
    ) -> list[Ponto]:
        """Pontos com valor do territorio, por (ano, serie). Argumento `None` nao filtra; `indisponivel` fica de fora."""
        base = self.base
        selecao = (
            (base["indicador_id"] == indicador) & (base["territorio_id"] == territorio)
            & (base["tipo_dado"] != "indisponivel") & base["valor"].notna()
        )
        for coluna, filtro in (("subindicador", sub), ("etapa", etapa), ("rede", rede), ("serie_id", serie)):
            if filtro is not None:
                selecao &= base[coluna] == filtro
        return _pontos(base[selecao])

    def razao(self, indicador: str, territorio: str, referencia: str) -> list[Ponto]:
        """Razao do territorio sobre a referencia (metrica `razao` de derivados.csv), por (ano, serie)."""
        d = self.derivados
        selecao = (
            (d["indicador_id"] == indicador) & (d["territorio_id"] == territorio)
            & (d["referencia"] == referencia) & (d["metrica"] == "razao") & d["valor"].notna()
        )
        return _pontos(d[selecao])

    def atualizado_em(self, indicador: str) -> str:
        """Maior data de coleta do indicador (`AAAA-MM-DD`); no calculado, a de seus insumos.

        Serie que nao atualizou mostra a data da coleta antiga: nada aqui a troca pela data da base.
        """
        ficha = self.fichas.get(indicador)
        origem = [indicador]
        if ficha is not None and ficha.calculo is not None:
            origem = [ficha.calculo.numerador, ficha.calculo.denominador]
        datas = self.coletas.loc[self.coletas["indicador_id"].isin(origem), "data_coleta"]
        if datas.empty:
            raise KeyError(f"Sem coleta registrada para {indicador!r}.")
        return max(datas)

    def proxima_publicacao(self, indicador: str) -> str | None:
        """`AAAA-MM` da proxima publicacao esperada, pela cobertura do Nordeste; None se nao ha previsao."""
        c = self.cobertura
        previsoes = c.loc[(c["indicador_id"] == indicador) & (c["territorio_id"] == "NE"), "proxima_publicacao"]
        previsoes = [p for p in previsoes if p]
        return max(previsoes) if previsoes else None


def _pontos(linhas: pd.DataFrame) -> list[Ponto]:
    ordenadas = linhas.sort_values(["ano", "serie_id"], kind="stable")
    return [Ponto(int(a), float(v), s) for a, v, s in zip(ordenadas["ano"], ordenadas["valor"], ordenadas["serie_id"])]
