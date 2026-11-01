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


def test_carrega_amostra_per_capita(projeto):
    f = carregar_fichas(projeto.fichas)["amostra_per_capita"]
    assert f.comparacao == Comparacao("brasil_fora_ne", "razao", "pib_nominal", "amostra_populacao", 1000.0)
    assert f.serie("scr_ref2010").inicio == 2002
    assert f.serie_do_ano(2001) is None


def test_fichas_do_repositorio_sao_validas_e_auxiliares(projeto_completo):
    assert verificar_fichas(projeto_completo.fichas) == []
    fichas = carregar_fichas(projeto_completo.fichas)
    assert {"pib_per_capita", "pib_nominal", "populacao"} <= set(fichas)
    assert {i for i, f in fichas.items() if f.auxiliar} == {
        "pib_nominal", "massa_renda_dom_pc", "populacao_pnadc", "desocupados", "forca_trabalho", "informais", "ocupados",
    }
    assert not fichas["pib_per_capita"].auxiliar
    assert fichas["pib_per_capita"].defasagem_meses == 23
    assert fichas["pib_nominal"].unidade == "R$ mil"
    assert fichas["pib_nominal"].tratamento_monetario == {"modo": "razao"}
    assert {i for i, f in fichas.items() if f.calculo is not None} == {"pib_per_capita"}
    assert all(s.parametros for f in fichas.values() for s in f.series if s.verificado and f.calculo is None)


def test_serie_inexistente_levanta_keyerror(fichas):
    with pytest.raises(KeyError):
        fichas["amostra_per_capita"].serie("nao_existe")


def test_serie_do_ano_respeita_inicio_e_fim(fichas):
    f = fichas["amostra_per_capita"]
    assert f.serie_do_ano(2002).id == "scr_ref2010"
    assert f.serie_do_ano(2023).id == "scr_ref2010"
    assert f.serie_do_ano(2024) is None


def test_padroes_dos_campos_opcionais(tmp_path, ficha_minima):
    f = carregar_ficha(_gravar(tmp_path, ficha_minima))
    assert (f.tratamento_monetario, f.auxiliar, f.limiar_salto_pct) == (None, False, 50.0)
    assert f.comparacao.fator == 1.0
    assert f.comparacao.precisao_oficial is None and f.series[0].anos_sem_publicacao == ()


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


# ---------------------------------------------------------------------------
# calculo: indicador calculado pelo projeto (razao_por_ano)
# ---------------------------------------------------------------------------

def _insumo(ficha_minima, id, series):
    insumo = copy.deepcopy(ficha_minima)
    insumo["id"], insumo["auxiliar"] = id, True
    insumo["series"] = [{**ficha_minima["series"][0], "id": s} for s in series]
    return insumo


@pytest.fixture
def pasta_com_calculo(tmp_path, ficha_minima):
    """Tres fichas: numerador `num` (serie_a), denominador `den` (est e censo) e o indicador calculado."""
    _gravar(tmp_path, _insumo(ficha_minima, "num", ["serie_a"]), "num.yaml")
    _gravar(tmp_path, _insumo(ficha_minima, "den", ["est", "censo"]), "den.yaml")
    calculada = copy.deepcopy(ficha_minima)
    calculada["comparacao"] = {"referencia": "brasil_fora_ne"}
    calculada["series"][0].update(coletor="calculo", verificado=True)
    calculada["calculo"] = {
        "metodo": "razao_por_ano",
        "numerador": {"indicador": "num", "serie": "serie_a"},
        "denominador": {"indicador": "den", "series_por_ano": {
            "2002-2006": "est", 2010: "censo", "2011": {"serie": "censo", "ano": 2010},
        }},
        "fator": 1000,
    }
    _gravar(tmp_path, calculada, "calculada.yaml")
    return tmp_path, calculada


def test_calculo_e_lido_com_faixas_e_ano_fixo(pasta_com_calculo):
    pasta, _ = pasta_com_calculo
    calc = carregar_fichas(pasta)["indicador_teste"].calculo
    assert (calc.metodo, calc.numerador, calc.serie_numerador, calc.denominador, calc.fator) == (
        "razao_por_ano", "num", "serie_a", "den", 1000.0)
    assert calc.denominador_do_ano(2002) == ("est", 2002)
    assert calc.denominador_do_ano(2006) == ("est", 2006)
    assert calc.denominador_do_ano(2010) == ("censo", 2010)
    assert calc.denominador_do_ano(2011) == ("censo", 2010)  # ano fixo: a populacao de 2010 serve a 2011
    assert calc.denominador_do_ano(2007) is None  # ano sem denominador mapeado
    assert carregar_fichas(pasta)["num"].calculo is None


def test_calculo_dispensa_metodo_de_comparacao(pasta_com_calculo):
    pasta, _ = pasta_com_calculo
    assert verificar_fichas(pasta) == []


def test_calculo_recusa_metodo_de_comparacao(pasta_com_calculo):
    pasta, calculada = pasta_com_calculo
    calculada["comparacao"] = {"referencia": "brasil_fora_ne", "metodo": "soma"}
    _gravar(pasta, calculada, "calculada.yaml")
    assert any("comparacao.metodo" in m and "calculo" in m for m in verificar_fichas(pasta))


@pytest.mark.parametrize("series_por_ano, trecho", [
    ({"2002-2006": "est", "2006-2008": "censo"}, "sobrepoe"),
    ({"2002-2006": "est", "2004": "est"}, "sobrepoe"),
    ({"2006-2002": "est"}, "faixa"),
    ({"20x0": "est"}, "faixa"),
    ({}, "series_por_ano"),
    ({"2010": {"serie": "censo", "ano": "2010"}}, "ano"),
    ({"2010": ""}, "serie"),
    ({"2000-2003": "est"}, "fora da cobertura"),
])
def test_mapeamento_invalido_e_recusado(pasta_com_calculo, series_por_ano, trecho):
    pasta, calculada = pasta_com_calculo
    calculada["calculo"]["denominador"]["series_por_ano"] = series_por_ano
    _gravar(pasta, calculada, "calculada.yaml")
    mensagens = verificar_fichas(pasta)
    assert any("calculada.yaml" in m and trecho in m for m in mensagens), mensagens
    with pytest.raises(ErroFicha):
        carregar_fichas(pasta)


def test_serie_inexistente_no_mapeamento_e_recusada(pasta_com_calculo):
    pasta, calculada = pasta_com_calculo
    calculada["calculo"]["denominador"]["series_por_ano"]["2012"] = "fantasma"
    _gravar(pasta, calculada, "calculada.yaml")
    assert any("den/fantasma" in m for m in verificar_fichas(pasta))
    with pytest.raises(ErroFicha, match="fantasma"):
        carregar_fichas(pasta)


def test_insumo_inexistente_do_calculo_e_recusado(pasta_com_calculo):
    pasta, calculada = pasta_com_calculo
    calculada["calculo"]["numerador"] = {"indicador": "sumido", "serie": "serie_a"}
    _gravar(pasta, calculada, "calculada.yaml")
    assert any("calculo.numerador" in m and "sumido" in m for m in verificar_fichas(pasta))


def test_calculo_exige_metodo_conhecido_fator_positivo_e_uma_serie(pasta_com_calculo):
    pasta, calculada = pasta_com_calculo
    calculada["calculo"].update(metodo="media", fator=0)
    calculada["series"].append({**calculada["series"][0], "id": "serie_b"})
    _gravar(pasta, calculada, "calculada.yaml")
    mensagens = " | ".join(verificar_fichas(pasta))
    assert "calculo.metodo" in mensagens and "calculo.fator" in mensagens
    assert "uma unica serie" in mensagens


@pytest.mark.parametrize("destino, trecho", [
    ({"serie": "censo", "ano": 2012}, "posterior"),  # populacao de 2012 servindo a 2011: projecao silenciosa
    ({"serie": "censo", "ano": 1999}, "fora da cobertura da serie censo"),  # insumo cobre 2002 a 2023
])
def test_ano_fixo_do_denominador_nao_pode_ser_futuro_nem_fora_do_insumo(pasta_com_calculo, destino, trecho):
    pasta, calculada = pasta_com_calculo
    calculada["calculo"]["denominador"]["series_por_ano"]["2011"] = destino
    _gravar(pasta, calculada, "calculada.yaml")
    mensagens = verificar_fichas(pasta)
    assert any("calculada.yaml" in m and trecho in m for m in mensagens), mensagens
    with pytest.raises(ErroFicha):
        carregar_fichas(pasta)


def test_ano_fixo_igual_ao_inicio_da_faixa_e_aceito(pasta_com_calculo):
    pasta, calculada = pasta_com_calculo
    calculada["calculo"]["denominador"]["series_por_ano"]["2011"] = {"serie": "censo", "ano": 2011}
    _gravar(pasta, calculada, "calculada.yaml")
    assert verificar_fichas(pasta) == []


def test_precisao_oficial_e_lida(tmp_path, ficha_minima):
    ficha_minima["comparacao"] = {"referencia": "brasil", "precisao_oficial": 0.1}
    assert carregar_ficha(_gravar(tmp_path, ficha_minima)).comparacao.precisao_oficial == 0.1


@pytest.mark.parametrize("valor", [0, -0.1, "0.1", True, None])
def test_precisao_oficial_invalida_e_recusada(tmp_path, ficha_minima, valor):
    ficha_minima["comparacao"] = {"referencia": "brasil", "precisao_oficial": valor}
    _gravar(tmp_path, ficha_minima)
    assert any("precisao_oficial" in m for m in verificar_fichas(tmp_path))


def test_anos_sem_publicacao_sao_lidos(tmp_path, ficha_minima):
    ficha_minima["series"][0]["anos_sem_publicacao"] = [2010, 2005]
    f = carregar_ficha(_gravar(tmp_path, ficha_minima))
    assert f.series[0].anos_sem_publicacao == (2005, 2010)


@pytest.mark.parametrize("anos", [[2001], [2024], [2010, 2010], ["2010"], 2010, [True]])
def test_anos_sem_publicacao_invalidos_sao_recusados(tmp_path, ficha_minima, anos):
    ficha_minima["series"][0]["anos_sem_publicacao"] = anos  # cobertura 2002 a 2023
    _gravar(tmp_path, ficha_minima)
    assert any("anos_sem_publicacao" in m for m in verificar_fichas(tmp_path))


def test_anos_sem_publicacao_em_serie_em_curso_aceita_anos_depois_do_inicio(tmp_path, ficha_minima):
    ficha_minima["series"][0]["fim"] = None
    ficha_minima["series"][0]["anos_sem_publicacao"] = [2030]
    assert carregar_ficha(_gravar(tmp_path, ficha_minima)).series[0].anos_sem_publicacao == (2030,)


# Parametros de leitura de planilha validados na ficha: territorios_esperados e filtro_linhas (na serie ou em cada parte)
def _com_partes(ficha_minima, **parte):
    ficha_minima["series"][0]["coletor"] = "arquivo"
    ficha_minima["series"][0]["parametros"] = {
        "padronizador": "planilha", "partes": [{"url": "https://exemplo.invalid/a.zip", **parte}]}
    return ficha_minima


def test_territorios_esperados_e_filtro_validos_sao_aceitos(tmp_path, ficha_minima):
    _com_partes(ficha_minima, territorios_esperados=["BR", "NE", "SE_UF"], filtro_linhas={"Rede": "Total", "Ano": 2023})
    f = carregar_ficha(_gravar(tmp_path, ficha_minima))
    assert f.series[0].parametros["partes"][0]["territorios_esperados"] == ["BR", "NE", "SE_UF"]


@pytest.mark.parametrize("esperados", [["XX"], ["BR_FORA_NE"], [], "BR", [1], ["BR", "BR"]])
def test_territorios_esperados_invalidos_sao_recusados(tmp_path, ficha_minima, esperados):
    _gravar(tmp_path, _com_partes(ficha_minima, territorios_esperados=esperados))
    assert any("territorios_esperados" in m for m in verificar_fichas(tmp_path))


def test_territorios_esperados_na_serie_sem_partes_tambem_sao_validados(tmp_path, ficha_minima):
    ficha_minima["series"][0]["parametros"] = {"territorios_esperados": ["NE", "ZZ"]}
    _gravar(tmp_path, ficha_minima)
    assert any("territorios_esperados" in m and "ZZ" in m for m in verificar_fichas(tmp_path))


@pytest.mark.parametrize("filtro", [{"Rede": None}, {"Rede": True}, {"Rede": ["Total"]}, {"Rede": {"a": 1}}, ["Rede"]])
def test_filtro_linhas_aceita_so_texto_ou_numero(tmp_path, ficha_minima, filtro):
    _gravar(tmp_path, _com_partes(ficha_minima, filtro_linhas=filtro))
    assert any("filtro_linhas" in m for m in verificar_fichas(tmp_path))
