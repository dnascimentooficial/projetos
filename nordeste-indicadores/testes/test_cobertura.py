import pandas as pd

from nordeste.cobertura import proxima_publicacao, relatorio_cobertura
from nordeste.esquema import COLUNAS_BASE
from nordeste.fichas import Comparacao, Ficha, Serie


def ficha(id, inicio=2000, fim=2030, defasagem_meses=0):
    serie = Serie(
        id="s", inicio=inicio, fim=fim, fonte="f", base_origem="b", url="u",
        coletor="c", parametros={}, compatibilidade="c", verificado=True,
    )
    return Ficha(
        id=id, nome=id, descricao="d", eixo="e", categoria="c", unidade="u", orgao="o",
        periodicidade="anual", metodologia="m", observacoes="o", sentido="maior_melhor",
        limites={}, defasagem_meses=defasagem_meses, comparacao=Comparacao("nenhuma"),
        series=(serie,),
    )


def base_anos_ne(valores, indisponivel=(), territorio="NE", indicador="x"):
    linhas = [(a, v, "observado") for a, v in valores.items()] + [(a, None, "indisponivel") for a in indisponivel]
    return pd.DataFrame(
        [
            {
                "indicador_id": indicador, "subindicador": "", "etapa": "", "rede": "",
                "territorio_id": territorio, "ano": ano, "valor": valor, "tipo_dado": tipo,
                "serie_id": "s", "coleta_id": "c", "nota": "",
            }
            for ano, valor, tipo in linhas
        ],
        columns=COLUNAS_BASE,
    )


def test_proxima_publicacao():
    assert proxima_publicacao(2023, 23) == "2026-11"


def test_proxima_publicacao_sem_defasagem_e_dezembro_do_ano_seguinte():
    assert proxima_publicacao(2023, 0) == "2024-12"
    assert proxima_publicacao(2023, 1) == "2025-01"


def test_anos_faltantes():
    c = relatorio_cobertura(base_anos_ne({2002: 1, 2004: 1}, indisponivel=[2003]), {"x": ficha("x", inicio=2002, fim=2004)})
    assert c.iloc[0].anos_faltantes == "2003"


def test_colunas_e_primeiro_ultimo_ano():
    c = relatorio_cobertura(
        base_anos_ne({2002: 1, 2004: 1}, indisponivel=[2003]),
        {"x": ficha("x", inicio=2002, fim=2004, defasagem_meses=23)},
    )
    assert c.columns.tolist() == [
        "indicador_id", "serie_id", "territorio_id", "primeiro_ano", "ultimo_ano",
        "anos_faltantes", "proxima_publicacao",
    ]
    linha = c.iloc[0]
    assert (linha.indicador_id, linha.serie_id, linha.territorio_id) == ("x", "s", "NE")
    # serie com fim declarado esta encerrada: nao ha proxima publicacao a prever
    assert (linha.primeiro_ano, linha.ultimo_ano, linha.proxima_publicacao) == (2002, 2004, "")


def test_so_serie_em_curso_tem_proxima_publicacao():
    base = base_anos_ne({2002: 1, 2004: 1})
    em_curso = relatorio_cobertura(base, {"x": ficha("x", inicio=2002, fim=None, defasagem_meses=23)}).iloc[0]
    assert em_curso.proxima_publicacao == "2007-11"
    encerrada = relatorio_cobertura(base, {"x": ficha("x", inicio=2002, fim=2030, defasagem_meses=23)}).iloc[0]
    assert encerrada.proxima_publicacao == ""


def test_fim_nulo_usa_ultimo_ano_disponivel_da_serie():
    b = pd.concat([base_anos_ne({2002: 1, 2005: 1}, territorio="NE"), base_anos_ne({2002: 1, 2003: 1, 2004: 1}, territorio="BA")], ignore_index=True)
    c = relatorio_cobertura(b, {"x": ficha("x", inicio=2002, fim=None)}).set_index("territorio_id")
    assert c.loc["NE", "anos_faltantes"] == "2003;2004" and c.loc["BA", "anos_faltantes"] == "2005"


def test_anos_faltantes_ignora_anos_que_a_serie_nao_publica():
    b = pd.concat([base_anos_ne({2005: 1, 2007: 1}, territorio="NE"), base_anos_ne({2005: 1}, territorio="BA")], ignore_index=True)
    c = relatorio_cobertura(b, {"x": ficha("x", inicio=2005, fim=2007)}).set_index("territorio_id")
    assert c.loc["BA", "anos_faltantes"] == "2007" and c.loc["NE", "anos_faltantes"] == ""


def test_ano_do_inicio_que_ninguem_publica_nao_e_faltante():
    c = relatorio_cobertura(base_anos_ne({2003: 1, 2004: 1}), {"x": ficha("x", inicio=2002, fim=2004)})
    assert c.iloc[0].anos_faltantes == ""


def test_um_registro_por_territorio_presente():
    b = pd.concat([base_anos_ne({2002: 1}, territorio="NE"), base_anos_ne({2002: 1, 2003: 1}, territorio="BA")], ignore_index=True)
    c = relatorio_cobertura(b, {"x": ficha("x", inicio=2002, fim=2003)}).set_index("territorio_id")
    assert c.index.tolist() == ["BA", "NE"]
    assert c.loc["BA", "anos_faltantes"] == "" and c.loc["NE", "anos_faltantes"] == "2003"


def test_territorio_so_com_indisponivel_aparece_sem_anos():
    c = relatorio_cobertura(base_anos_ne({}, indisponivel=[2002]), {"x": ficha("x", inicio=2002, fim=2003)})
    linha = c.iloc[0]
    assert pd.isna(linha.primeiro_ano) and pd.isna(linha.ultimo_ano)
    assert linha.anos_faltantes == "2002" and linha.proxima_publicacao == ""


def test_base_vazia_devolve_colunas():
    c = relatorio_cobertura(pd.DataFrame(columns=COLUNAS_BASE), {})
    assert c.empty and "anos_faltantes" in c.columns
