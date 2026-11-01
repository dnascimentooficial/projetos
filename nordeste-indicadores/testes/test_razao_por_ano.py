"""Calculo `razao_por_ano`: indicador calculado territorio a territorio (ex.: PIB per capita)."""

import pandas as pd
import pytest

from nordeste.derivados import COLUNAS_REGISTRO, aplicar_calculos
from nordeste.esquema import CHAVE_BASE, COLUNAS_BASE
from nordeste.fichas import Calculo, Comparacao, FaixaDenominador, Ficha, Serie


def _serie(serie_id, inicio=2000, fim=2030):
    return Serie(
        id=serie_id, inicio=inicio, fim=fim, fonte="f", base_origem="b", url="u",
        coletor="calculo", parametros={}, compatibilidade="c", verificado=True,
    )


def _ficha(id, series=("s",), calculo=None, referencia="brasil_fora_ne", inicio=2000, fim=2030):
    return Ficha(
        id=id, nome=id, descricao="d", eixo="e", categoria="c", unidade="u", orgao="o",
        periodicidade="anual", metodologia="m", observacoes="o", sentido="maior_melhor",
        limites={}, defasagem_meses=0, comparacao=Comparacao(referencia),
        series=tuple(_serie(s, inicio, fim) for s in series), calculo=calculo,
    )


# Numerador `pib` (serie "ref") e denominador `pop` em duas series: estimativas ("est") e censo ("censo").
# 2002-2003 usam a estimativa do proprio ano; 2004 usa o censo do proprio ano; 2005 usa o censo de 2004;
# 2006 nao tem denominador mapeado.
CALCULO = Calculo(
    metodo="razao_por_ano", numerador="pib", serie_numerador="ref", denominador="pop",
    faixas=(
        FaixaDenominador(2002, 2003, "est"),
        FaixaDenominador(2004, 2004, "censo"),
        FaixaDenominador(2005, 2005, "censo", ano=2004),
    ),
    fator=1000.0,
)


def fichas(referencia="brasil_fora_ne", calculo=CALCULO, inicio=2000, fim=2030):
    return {
        "pib": _ficha("pib", ("ref",), referencia="nenhuma"),
        "pop": _ficha("pop", ("est", "censo"), referencia="nenhuma"),
        "pc": _ficha("pc", ("ref2010",), calculo, referencia, inicio, fim),
    }


def _linha(indicador, serie, territorio, ano, valor, subindicador=""):
    return {
        "indicador_id": indicador, "subindicador": subindicador, "etapa": "", "rede": "",
        "territorio_id": territorio, "ano": ano, "valor": valor,
        "tipo_dado": "indisponivel" if valor is None else "observado",
        "serie_id": serie, "coleta_id": f"col.{indicador}.{serie}", "nota": "",
    }


def base(*linhas):
    return pd.DataFrame(list(linhas), columns=COLUNAS_BASE)


def _pib(territorio, ano, valor, **kw):
    return _linha("pib", "ref", territorio, ano, valor, **kw)


def _pop(serie, territorio, ano, valor, **kw):
    return _linha("pop", serie, territorio, ano, valor, **kw)


def _valores(saida):
    return {(r.territorio_id, r.ano): r.valor for r in saida.itertuples()}


def test_razao_por_territorio_com_fator_e_brasil_fora_ne():
    b = base(
        _pib("BR", 2002, 1000.0), _pib("NE", 2002, 300.0), _pib("MA", 2002, 50.0), _pib("SE", 2002, 450.0),
        _pop("est", "BR", 2002, 20.0), _pop("est", "NE", 2002, 12.0), _pop("est", "MA", 2002, 4.0),
        _pop("est", "SE", 2002, 5.0),
    )
    saida, _ = aplicar_calculos(b, fichas())
    assert _valores(saida) == pytest.approx({
        ("BR", 2002): 1000 / 20 * 1000,              # 50.000
        ("NE", 2002): 300 / 12 * 1000,               # 25.000
        ("MA", 2002): 50 / 4 * 1000,                 # 12.500
        ("SE", 2002): 450 / 5 * 1000,                # 90.000
        ("BR_FORA_NE", 2002): (1000 - 300) / (20 - 12) * 1000,  # 87.500: razao das diferencas
    })
    assert list(saida.columns) == COLUNAS_BASE
    assert set(saida.indicador_id) == {"pc"} and set(saida.serie_id) == {"ref2010"}
    assert set(saida.tipo_dado) == {"derivado"}
    assert saida.equals(saida.sort_values(CHAVE_BASE, kind="stable").reset_index(drop=True))


def test_mapeamento_por_intervalo_e_ano_fixo_do_denominador():
    b = base(
        *(_pib("BR", ano, 100.0 * ano) for ano in (2002, 2003, 2004, 2005)),
        _pop("est", "BR", 2002, 2.0), _pop("est", "BR", 2003, 4.0),
        _pop("est", "BR", 2004, 999.0),               # existe, mas 2004 esta mapeado para o censo
        _pop("censo", "BR", 2004, 5.0),
        _pop("censo", "BR", 2003, 999.0),             # existe, mas 2003 esta mapeado para a estimativa
    )
    saida, _ = aplicar_calculos(b, fichas())
    assert _valores(saida) == pytest.approx({
        ("BR", 2002): 200200 / 2 * 1000,
        ("BR", 2003): 200300 / 4 * 1000,
        ("BR", 2004): 200400 / 5 * 1000,
        ("BR", 2005): 200500 / 5 * 1000,              # censo de 2004 aplicado a 2005
    })


def test_ano_sem_denominador_mapeado_ou_sem_valor_fica_sem_linha():
    b = base(
        _pib("BR", 2006, 100.0), _pop("est", "BR", 2006, 2.0),   # 2006 nao esta mapeado: nada de interpolar
        _pib("BR", 2003, 100.0),                                 # mapeado, mas a estimativa de 2003 nao veio
        _pib("BR", 2002, 100.0), _pop("est", "BR", 2002, None),  # denominador indisponivel
        _pib("NE", 2002, 100.0), _pop("est", "NE", 2002, 0.0),   # denominador zero
        _pib("MA", 2002, None), _pop("est", "MA", 2002, 3.0),    # numerador indisponivel
    )
    saida, registro = aplicar_calculos(b, fichas())
    assert saida.empty and list(saida.columns) == COLUNAS_BASE
    assert registro.empty and list(registro.columns) == COLUNAS_REGISTRO


def test_brasil_fora_ne_exige_br_e_ne_nos_dois_termos():
    b = base(
        _pib("BR", 2002, 1000.0), _pib("NE", 2002, 300.0), _pop("est", "BR", 2002, 20.0),
    )
    saida, _ = aplicar_calculos(b, fichas())
    assert set(saida.territorio_id) == {"BR"}


def test_brasil_fora_ne_com_denominador_igual_fica_sem_linha():
    b = base(
        _pib("BR", 2002, 1000.0), _pib("NE", 2002, 300.0),
        _pop("est", "BR", 2002, 20.0), _pop("est", "NE", 2002, 20.0),
    )
    saida, _ = aplicar_calculos(b, fichas())
    assert set(saida.territorio_id) == {"BR", "NE"}


def test_referencia_brasil_nao_gera_brasil_fora_ne():
    b = base(
        _pib("BR", 2002, 1000.0), _pib("NE", 2002, 300.0),
        _pop("est", "BR", 2002, 20.0), _pop("est", "NE", 2002, 12.0),
    )
    saida, _ = aplicar_calculos(b, fichas(referencia="brasil"))
    assert set(saida.territorio_id) == {"BR", "NE"}


def test_so_anos_dentro_da_cobertura_da_serie_da_ficha():
    b = base(
        _pib("BR", 2002, 100.0), _pib("BR", 2003, 100.0),
        _pop("est", "BR", 2002, 2.0), _pop("est", "BR", 2003, 2.0),
    )
    saida, _ = aplicar_calculos(b, fichas(inicio=2003, fim=2003))
    assert set(saida.ano) == {2003}


def test_grupo_do_numerador_casa_com_o_do_denominador():
    b = base(
        _pib("BR", 2002, 100.0, subindicador="a"), _pop("est", "BR", 2002, 2.0, subindicador="a"),
        _pib("BR", 2002, 100.0, subindicador="b"), _pop("est", "BR", 2002, 4.0, subindicador="c"),
    )
    saida, _ = aplicar_calculos(b, fichas())
    assert [(r.subindicador, r.valor) for r in saida.itertuples()] == [("a", pytest.approx(50000.0))]


def test_registro_de_derivacao_lista_so_os_insumos_usados():
    b = base(
        _pib("BR", 2002, 1000.0), _pib("NE", 2002, 300.0), _pib("BR", 2004, 1000.0),
        _pop("est", "BR", 2002, 20.0), _pop("est", "NE", 2002, 12.0),
        _pop("censo", "BR", 2004, 25.0),
        _linha("pop", "outra", "BR", 2002, 7.0),   # serie do denominador que o mapeamento nao usa
    )
    saida, registro = aplicar_calculos(b, fichas())
    assert list(registro.columns) == COLUNAS_REGISTRO and len(registro) == 1
    r = registro.iloc[0]
    assert (r.indicador_id, r.serie_id) == ("pc", "ref2010")
    assert r.insumos == "col.pib.ref;col.pop.censo;col.pop.est"
    assert r.coleta_id.startswith("deriv.pc.ref2010.")
    assert set(saida.coleta_id) == {r.coleta_id}  # todas as linhas, inclusive BR_FORA_NE, apontam para o registro


def test_coleta_id_muda_quando_os_insumos_mudam():
    linhas = [_pib("BR", 2002, 1000.0), _pop("est", "BR", 2002, 20.0)]
    _, antes = aplicar_calculos(base(*linhas), fichas())
    linhas[0] = {**linhas[0], "coleta_id": "col.pib.ref.nova"}
    _, depois = aplicar_calculos(base(*linhas), fichas())
    assert antes.coleta_id[0] != depois.coleta_id[0]


def test_fichas_sem_calculo_nao_geram_linhas():
    b = base(_pib("BR", 2002, 1000.0), _pop("est", "BR", 2002, 20.0))
    saida, registro = aplicar_calculos(b, {k: v for k, v in fichas().items() if k != "pc"})
    assert saida.empty and registro.empty


def test_linhas_brasil_fora_ne_da_base_nao_entram_no_calculo():
    b = base(_pib("BR_FORA_NE", 2002, 700.0), _pop("est", "BR_FORA_NE", 2002, 8.0))
    saida, _ = aplicar_calculos(b, fichas())
    assert saida.empty
