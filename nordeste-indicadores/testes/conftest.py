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


# Amostra dos testes de mecanica (coleta, consolidacao, publicacao, CLI): uma razao com valor oficial
# (pib_per_capita) e seus dois insumos soma (pib_nominal e populacao_contas_regionais). O pib_nominal e a
# ficha real do dicionario; as outras duas sao fichas de teste em testes/amostra/ (o pib_per_capita real
# e calculado pelo projeto e a populacao_contas_regionais saiu do dicionario), com as fixtures ao lado.
# O dicionario cresce a cada bloco de fontes; so test_dicionario.py olha o dicionario inteiro.
AMOSTRA_DO_DICIONARIO = ("pib_nominal",)
PASTA_AMOSTRA = RAIZ_REPOSITORIO / "testes" / "amostra"


def _copiar_do_repositorio(destino: Path, completo: bool) -> None:
    for relativo in (Path("metadados"), Path("testes") / "fixtures"):
        origem = RAIZ_REPOSITORIO / relativo
        if origem.is_dir():
            shutil.copytree(origem, destino / relativo)
    if completo:
        return
    for ficha in (destino / "metadados" / "indicadores").glob("*.yaml"):
        if ficha.stem not in AMOSTRA_DO_DICIONARIO:
            ficha.unlink()
    for pasta in (destino / "testes" / "fixtures").iterdir():
        if pasta.is_dir() and pasta.name not in (*AMOSTRA_DO_DICIONARIO, "__pycache__"):
            shutil.rmtree(pasta)
    shutil.copytree(PASTA_AMOSTRA / "indicadores", destino / "metadados" / "indicadores", dirs_exist_ok=True)
    shutil.copytree(PASTA_AMOSTRA / "fixtures", destino / "testes" / "fixtures", dirs_exist_ok=True)


@pytest.fixture
def projeto(tmp_path) -> Caminhos:
    """Projeto temporario com a amostra (pib_nominal e as fichas de testes/amostra), suas fixtures e os demais metadados."""
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
