import shutil
import sys
from pathlib import Path

import pytest

from nordeste.caminhos import Caminhos
from nordeste.fichas import carregar_fichas
from nordeste.territorios import carregar_territorios

RAIZ_REPOSITORIO = Path(__file__).resolve().parent.parent

# Os testes usam os montadores de xlsx e JSON sinteticos do gerador de fixtures.
sys.path.insert(0, str(RAIZ_REPOSITORIO / "testes" / "fixtures"))


# Amostra dos testes de mecanica (coleta, consolidacao, publicacao, CLI): as tres fichas do PIB per capita.
# O dicionario cresce a cada bloco de fontes; so test_dicionario.py olha o dicionario inteiro.
AMOSTRA = ("pib_nominal", "pib_per_capita", "populacao_contas_regionais")


def _copiar_do_repositorio(destino: Path, completo: bool) -> None:
    for relativo in (Path("metadados"), Path("testes") / "fixtures"):
        origem = RAIZ_REPOSITORIO / relativo
        if origem.is_dir():
            shutil.copytree(origem, destino / relativo)
    if completo:
        return
    for ficha in (destino / "metadados" / "indicadores").glob("*.yaml"):
        if ficha.stem not in AMOSTRA:
            ficha.unlink()
    for pasta in (destino / "testes" / "fixtures").iterdir():
        if pasta.is_dir() and pasta.name not in (*AMOSTRA, "__pycache__"):
            shutil.rmtree(pasta)


@pytest.fixture
def projeto(tmp_path) -> Caminhos:
    """Projeto temporario com as fichas e fixtures da AMOSTRA e os demais metadados do repositorio."""
    _copiar_do_repositorio(tmp_path, completo=False)
    return Caminhos(tmp_path)


@pytest.fixture
def projeto_completo(tmp_path) -> Caminhos:
    """Projeto temporario com o dicionario inteiro do repositorio (todas as fichas e fixtures)."""
    _copiar_do_repositorio(tmp_path, completo=True)
    return Caminhos(tmp_path)


@pytest.fixture
def territorios(projeto):
    return carregar_territorios(projeto.territorios_csv)


@pytest.fixture
def fichas(projeto):
    return carregar_fichas(projeto.fichas)
