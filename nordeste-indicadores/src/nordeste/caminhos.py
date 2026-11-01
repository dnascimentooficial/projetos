"""Caminhos do projeto, todos derivados de uma unica raiz."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Caminhos:
    raiz: Path

    @property
    def metadados(self) -> Path:
        return self.raiz / "metadados"

    @property
    def fichas(self) -> Path:
        return self.metadados / "indicadores"

    @property
    def territorios_csv(self) -> Path:
        return self.metadados / "territorios.csv"

    @property
    def governos_csv(self) -> Path:
        return self.metadados / "governos.csv"

    @property
    def _dados(self) -> Path:
        return self.raiz / "dados"

    @property
    def brutos(self) -> Path:
        return self._dados / "brutos"

    @property
    def trabalho(self) -> Path:
        return self._dados / "trabalho"

    @property
    def base(self) -> Path:
        return self._dados / "base"

    @property
    def relatorios(self) -> Path:
        return self._dados / "relatorios"

    @property
    def fixtures(self) -> Path:
        return self.raiz / "testes" / "fixtures"

    @property
    def registro_coletas(self) -> Path:
        return self.relatorios / "coletas.csv"

    @property
    def registro_derivacoes(self) -> Path:
        return self.relatorios / "derivacoes.csv"
