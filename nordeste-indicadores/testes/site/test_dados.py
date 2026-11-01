import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from nordeste.caminhos import Caminhos
from nordeste.fichas import Calculo
from nordeste.site.dados import DadosSite, Ponto

BASE_MINI = Path(__file__).parent / "base_mini"


@pytest.fixture(scope="module")
def dados() -> DadosSite:
    return DadosSite.carregar(Caminhos(raiz=BASE_MINI))


def test_carrega_as_tabelas_e_as_fichas(dados):
    assert set(dados.fichas) == {"alfa", "beta"}
    assert set(dados.base["territorio_id"]) == {"NE", "BR", "BA"}
    assert set(dados.base["ano"]) == {2011, 2012, 2013}
    assert not dados.governos.empty
    assert not dados.cobertura.empty and not dados.derivados.empty


def test_serie_quebra_por_serie_e_ignora_indisponivel(dados):
    assert dados.serie("alfa", "NE") == [
        Ponto(2011, 10.0, "s_antiga"),
        Ponto(2012, 11.0, "s_antiga"),
        Ponto(2012, 11.5, "s_nova"),
        Ponto(2013, 12.5, "s_nova"),
    ]
    # beta/NE/2012 e indisponivel: o ano nao aparece
    assert [p.ano for p in dados.serie("beta", "NE", sub="a")] == [2011, 2013]


def test_serie_filtra_so_o_que_foi_pedido(dados):
    assert [p.serie for p in dados.serie("alfa", "NE", serie="s_nova")] == ["s_nova", "s_nova"]
    assert [p.valor for p in dados.serie("beta", "NE", sub="b")] == [7.0, 8.0, 9.0]
    assert len(dados.serie("beta", "NE")) == 5  # sub=None nao filtra: a (2 pontos) + b (3 pontos)
    assert len(dados.serie("alfa", "NE", rede="total")) == 4
    assert dados.serie("alfa", "NE", rede="publica") == []
    assert dados.serie("alfa", "NE", etapa="creche") == []
    assert dados.serie("alfa", "XX") == []


def test_pontos_sao_congelados(dados):
    with pytest.raises(AttributeError):
        dados.serie("alfa", "NE")[0].valor = 0.0


def test_razao_le_derivados(dados):
    assert dados.razao("alfa", "NE", "BR") == [
        Ponto(2011, 0.5, "s_antiga"),
        Ponto(2012, 0.6, "s_antiga"),
        Ponto(2012, 0.65, "s_nova"),
        Ponto(2013, 0.75, "s_nova"),
    ]
    # outras metricas e outras referencias ficam de fora
    assert dados.razao("alfa", "NE", "BR_FORA_NE") == []
    assert dados.razao("alfa", "BA", "BR")[0] == Ponto(2011, 1.5, "s_antiga")


def test_sha256_e_data_base(dados):
    esperado = hashlib.sha256((BASE_MINI / "dados/base/base_nordeste.csv").read_bytes()).hexdigest()
    assert dados.sha256_base == esperado
    assert dados.data_base == "2026-10-25"


def test_atualizado_em_mostra_coleta_antiga_da_serie_que_nao_atualizou(dados):
    # beta nao foi recoletado desde maio; o site mostra a data velha e a base segue a data mais nova
    assert dados.atualizado_em("beta") == "2026-05-10"
    assert dados.atualizado_em("alfa") == "2026-10-25"
    assert dados.atualizado_em("beta") < dados.data_base


def test_atualizado_em_de_indicador_calculado_vem_dos_insumos(dados):
    calculado = replace(
        dados.fichas["alfa"], id="gama",
        calculo=Calculo(metodo="razao_por_ano", numerador="beta", serie_numerador="s_unica",
                        denominador="beta", faixas=()),
    )
    dados.fichas["gama"] = calculado
    try:
        assert dados.atualizado_em("gama") == "2026-05-10"
        dados.fichas["gama"] = replace(calculado, calculo=replace(calculado.calculo, denominador="alfa"))
        assert dados.atualizado_em("gama") == "2026-10-25"
    finally:
        del dados.fichas["gama"]


def test_atualizado_em_de_indicador_sem_coleta_levanta(dados):
    with pytest.raises(KeyError):
        dados.atualizado_em("inexistente")


def test_proxima_publicacao_vem_da_cobertura_do_ne(dados):
    assert dados.proxima_publicacao("alfa") == "2027-03"  # s_antiga (encerrada) nao tem previsao
    assert dados.proxima_publicacao("beta") == "2028-05"
    assert dados.proxima_publicacao("inexistente") is None
