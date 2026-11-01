from nordeste.caminhos import Caminhos


def test_caminhos(tmp_path):
    c = Caminhos(tmp_path)
    assert c.fichas == tmp_path / "metadados" / "indicadores"
    assert c.registro_coletas == tmp_path / "dados" / "relatorios" / "coletas.csv"
    assert c.trabalho == tmp_path / "dados" / "trabalho"
    assert c.partes_em_coleta == tmp_path / "dados" / "trabalho" / "partes"


def test_fixture_projeto_tolera_ausencia_de_metadados_e_fixtures(projeto):
    assert projeto.raiz.is_dir()
    assert isinstance(projeto, Caminhos)


def test_fixture_projeto_copia_metadados_do_repositorio(projeto):
    assert projeto.territorios_csv.exists()
    assert projeto.governos_csv.exists()
