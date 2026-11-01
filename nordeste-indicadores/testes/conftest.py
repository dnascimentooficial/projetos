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


@pytest.fixture
def projeto(tmp_path) -> Caminhos:
    """Projeto temporario com copia de metadados/ e testes/fixtures/ do repositorio, se existirem."""
    caminhos = Caminhos(tmp_path)
    for relativo in (Path("metadados"), Path("testes") / "fixtures"):
        origem = RAIZ_REPOSITORIO / relativo
        if origem.is_dir():
            shutil.copytree(origem, tmp_path / relativo)
    return caminhos


@pytest.fixture
def territorios(projeto):
    return carregar_territorios(projeto.territorios_csv)


@pytest.fixture
def fichas(projeto):
    return carregar_fichas(projeto.fichas)
