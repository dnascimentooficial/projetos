from datetime import date

import pytest

from nordeste.governos import atribuir_governo, carregar_governos


@pytest.mark.parametrize("ano,esperado", [
    (2000, ("Fernando Henrique Cardoso", "2")), (2003, ("Luiz Inácio Lula da Silva", "1")),
    (2015, ("Dilma Rousseff", "2")), (2016, ("transicao_dilma_temer", "")),
    (2017, ("Michel Temer", "")), (2026, ("Luiz Inácio Lula da Silva", "3"))])
def test_atribuicao_anual(projeto, ano, esperado):
    assert atribuir_governo(ano, carregar_governos(projeto.governos_csv)) == esperado


def test_todo_ano_tem_um_rotulo(projeto):
    g = carregar_governos(projeto.governos_csv)
    assert all(atribuir_governo(a, g)[0] for a in range(2000, 2027))


def test_interinidade_registrada(projeto):
    g = carregar_governos(projeto.governos_csv)
    interino = g[g.interino == "sim"].iloc[0]
    assert (interino.inicio, interino.fim) == (date(2016, 5, 12), date(2016, 8, 31))


def test_datas_sao_date_e_apelidos_presentes(projeto):
    g = carregar_governos(projeto.governos_csv)
    assert all(type(d) is date for d in list(g.inicio) + list(g.fim))
    assert set(g.apelido) == {"FHC", "Lula", "Dilma", "Temer", "Bolsonaro"}
    assert list(g.columns) == ["presidente", "inicio", "fim", "mandato", "interino", "partido", "apelido"]
