import copy

import pytest
import yaml

from nordeste.fichas import (
    Comparacao, ErroFicha, carregar_ficha, carregar_fichas, verificar_fichas,
)


@pytest.fixture
def ficha_minima():
    return {
        "id": "indicador_teste",
        "nome": "Indicador de teste",
        "descricao": "Descricao de teste.",
        "eixo": "economia",
        "categoria": "renda",
        "unidade": "pessoas",
        "orgao": "Orgao de teste",
        "periodicidade": "anual",
        "metodologia": "Metodologia de teste.",
        "observacoes": "Sem observacoes.",
        "sentido": "maior_melhor",
        "limites": {"min": 0},
        "comparacao": {"referencia": "brasil"},
        "defasagem_meses": 12,
        "series": [{
            "id": "serie_a", "inicio": 2002, "fim": 2023,
            "fonte": "Fonte de teste", "base_origem": "Base de teste",
            "url": "https://exemplo.invalid/serie_a", "coletor": "sidra",
            "parametros": {}, "compatibilidade": "Unica serie.", "verificado": False,
        }],
    }


def _gravar(pasta, dados, nome="x.yaml"):
    (pasta / nome).write_text(yaml.safe_dump(dados, allow_unicode=True), encoding="utf-8")
    return pasta / nome


def test_carrega_pib_per_capita(projeto):
    f = carregar_fichas(projeto.fichas)["pib_per_capita"]
    assert f.comparacao == Comparacao("brasil_fora_ne", "razao", "pib_nominal", "populacao_contas_regionais", 1000.0)
    assert f.serie("scr_ref2010").inicio == 2002
    assert f.serie_do_ano(2001) is None


def test_fichas_do_repositorio_sao_validas_e_auxiliares(projeto, fichas):
    assert verificar_fichas(projeto.fichas) == []
    assert set(fichas) == {"pib_per_capita", "pib_nominal", "populacao_contas_regionais"}
    assert {i for i, f in fichas.items() if f.auxiliar} == {"pib_nominal", "populacao_contas_regionais"}
    assert not fichas["pib_per_capita"].auxiliar
    assert fichas["pib_per_capita"].defasagem_meses == 23
    assert fichas["pib_nominal"].unidade == "R$ mil"
    assert fichas["pib_nominal"].tratamento_monetario == {"modo": "razao"}
    assert all(not s.verificado and s.parametros == {} for f in fichas.values() for s in f.series)


def test_serie_inexistente_levanta_keyerror(fichas):
    with pytest.raises(KeyError):
        fichas["pib_per_capita"].serie("nao_existe")


def test_serie_do_ano_respeita_inicio_e_fim(fichas):
    f = fichas["pib_per_capita"]
    assert f.serie_do_ano(2002).id == "scr_ref2010"
    assert f.serie_do_ano(2023).id == "scr_ref2010"
    assert f.serie_do_ano(2024) is None


def test_padroes_dos_campos_opcionais(tmp_path, ficha_minima):
    f = carregar_ficha(_gravar(tmp_path, ficha_minima))
    assert (f.tratamento_monetario, f.auxiliar, f.limiar_salto_pct) == (None, False, 50.0)
    assert f.comparacao.fator == 1.0


def test_campo_ausente_nomeia_o_campo(tmp_path, ficha_minima):
    del ficha_minima["sentido"]
    with pytest.raises(ErroFicha, match="sentido"):
        carregar_ficha(_gravar(tmp_path, ficha_minima))


def test_campo_de_serie_ausente_nomeia_o_campo(tmp_path, ficha_minima):
    del ficha_minima["series"][0]["verificado"]
    with pytest.raises(ErroFicha, match="verificado"):
        carregar_ficha(_gravar(tmp_path, ficha_minima))


def test_unidade_monetaria_exige_tratamento(tmp_path, ficha_minima):
    ficha_minima["unidade"] = "R$ correntes"; ficha_minima.pop("tratamento_monetario", None)
    _gravar(tmp_path, ficha_minima)
    assert any("tratamento_monetario" in m for m in verificar_fichas(tmp_path))


def test_razao_exige_numerador(tmp_path, ficha_minima):
    ficha_minima["comparacao"] = {"referencia": "brasil_fora_ne", "metodo": "razao"}
    _gravar(tmp_path, ficha_minima)
    assert any("numerador" in m for m in verificar_fichas(tmp_path))


def test_razao_encadeada_exige_denominador(tmp_path, ficha_minima):
    ficha_minima["comparacao"] = {"referencia": "brasil_fora_ne", "metodo": "razao_encadeada", "numerador": "a"}
    _gravar(tmp_path, ficha_minima)
    mensagens = verificar_fichas(tmp_path)
    assert any("denominador" in m for m in mensagens)
    assert not any("numerador" in m for m in mensagens)


def test_brasil_fora_ne_exige_metodo(tmp_path, ficha_minima):
    ficha_minima["comparacao"] = {"referencia": "brasil_fora_ne"}
    _gravar(tmp_path, ficha_minima)
    assert any("metodo" in m for m in verificar_fichas(tmp_path))


def test_exige_ao_menos_uma_serie(tmp_path, ficha_minima):
    ficha_minima["series"] = []
    _gravar(tmp_path, ficha_minima)
    assert any("series" in m for m in verificar_fichas(tmp_path))


def test_valores_fora_do_vocabulario_sao_recusados(tmp_path, ficha_minima):
    ficha_minima["sentido"] = "tanto_faz"
    ficha_minima["comparacao"] = {"referencia": "mundo"}
    mensagens = verificar_fichas(_gravar(tmp_path, ficha_minima).parent)
    assert any("sentido" in m for m in mensagens)
    assert any("referencia" in m for m in mensagens)


def test_serie_em_curso_aceita_fim_nulo(tmp_path, ficha_minima):
    ficha_minima["series"][0]["fim"] = None
    assert carregar_ficha(_gravar(tmp_path, ficha_minima)).series[0].fim is None


def test_serie_em_curso_cobre_anos_futuros(tmp_path, ficha_minima):
    ficha_minima["series"][0]["fim"] = None
    assert carregar_ficha(_gravar(tmp_path, ficha_minima)).serie_do_ano(2040).id == "serie_a"


def test_verificar_reporta_todos_os_problemas(tmp_path, ficha_minima):
    a = copy.deepcopy(ficha_minima); del a["nome"]
    b = copy.deepcopy(ficha_minima); b["id"] = "outro"; del b["orgao"]
    _gravar(tmp_path, a, "a.yaml"); _gravar(tmp_path, b, "b.yaml")
    mensagens = verificar_fichas(tmp_path)
    assert any("a.yaml" in m and "nome" in m for m in mensagens)
    assert any("b.yaml" in m and "orgao" in m for m in mensagens)


def test_verificar_ficha_ilegivel_nao_para_a_verificacao(tmp_path, ficha_minima):
    (tmp_path / "quebrada.yaml").write_text("id: [aberto", encoding="utf-8")
    _gravar(tmp_path, ficha_minima, "boa.yaml")
    mensagens = verificar_fichas(tmp_path)
    assert len(mensagens) == 1 and "quebrada.yaml" in mensagens[0]


def test_numerador_inexistente_e_recusado(tmp_path, ficha_minima):
    ficha_minima["comparacao"] = {
        "referencia": "brasil_fora_ne", "metodo": "razao",
        "numerador": "fantasma", "denominador": "indicador_teste",
    }
    _gravar(tmp_path, ficha_minima)
    assert any("fantasma" in m for m in verificar_fichas(tmp_path))
    with pytest.raises(ErroFicha, match="fantasma"):
        carregar_fichas(tmp_path)


def test_ids_duplicados_sao_recusados(tmp_path, ficha_minima):
    _gravar(tmp_path, ficha_minima, "a.yaml"); _gravar(tmp_path, ficha_minima, "b.yaml")
    assert any("duplicado" in m for m in verificar_fichas(tmp_path))
    with pytest.raises(ErroFicha, match="duplicado"):
        carregar_fichas(tmp_path)
