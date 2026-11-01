"""Tabela de indicadores do README: gerada das fichas, com a situacao de verificacao e a cobertura efetiva."""

from dataclasses import replace
from pathlib import Path

from nordeste.fichas import carregar_fichas
from nordeste.tabela import cobertura_efetiva, main, tabela_markdown

RAIZ = Path(__file__).resolve().parent.parent


def _linha(tabela: str, indicador: str) -> list[str]:
    (linha,) = [l for l in tabela.splitlines() if l.startswith(f"| `{indicador}` ")]
    return [c.strip() for c in linha.strip("|").split("|")]


def test_tem_uma_linha_por_ficha_e_cabecalho_de_markdown():
    fichas = carregar_fichas(RAIZ / "metadados" / "indicadores")
    linhas = tabela_markdown(fichas).splitlines()
    assert linhas[0].startswith("| Indicador |") and set(linhas[1]) <= set("|- ")
    assert len(linhas) == 2 + len(fichas)


def test_cobertura_junta_series_e_deixa_o_buraco_entre_elas():
    fichas = carregar_fichas(RAIZ / "metadados" / "indicadores")
    # censo 2000-2010, estimativa 2001-2021, censo 2022; a estimativa pos-censo comeca em 2024 e segue em curso.
    assert cobertura_efetiva(fichas["populacao"]) == "2000–2022; 2024–"
    assert cobertura_efetiva(fichas["pib_volume"]) == "2002–2023"


def test_cobertura_tira_o_ano_sem_pesquisa_que_nenhuma_outra_serie_cobre():
    fichas = carregar_fichas(RAIZ / "metadados" / "indicadores")
    # PNAD 2001-2014 sem 2010 e PNAD Continua desde 2012: o buraco de 2010 aparece.
    assert cobertura_efetiva(fichas["desocupacao"]) == "2001–2009; 2011–"


def test_cobertura_de_indicador_calculado_so_tem_os_anos_com_denominador_mapeado():
    fichas = carregar_fichas(RAIZ / "metadados" / "indicadores")
    # 2007 nao tem populacao no mapeamento do calculo (ano da Contagem): sai da cobertura, gerado da ficha
    assert cobertura_efetiva(fichas["pib_per_capita"]) == "2002–2006; 2008–2023"


def test_serie_nao_verificada_fica_fora_da_cobertura_e_da_situacao_verificada():
    fichas = carregar_fichas(RAIZ / "metadados" / "indicadores")
    tabela = tabela_markdown(fichas)
    assert cobertura_efetiva(fichas["pobreza"]) == "2012–2024"  # verificada pelo Ipeadata (C3b), fim no ultimo ano baixado
    assert _linha(tabela, "pobreza")[-1] == "verificada" and _linha(tabela, "extrema_pobreza")[-1] == "verificada"
    # nenhuma ficha real e nao verificada hoje: o caso vem de uma ficha com a serie desmarcada
    (serie,) = fichas["pobreza"].series
    nao_verificada = replace(fichas["pobreza"], series=(replace(serie, verificado=False),))
    assert cobertura_efetiva(nao_verificada) == "—"
    assert "não verificada" in _linha(tabela_markdown({**fichas, "pobreza": nao_verificada}), "pobreza")[-1]
    assert "verificada" == _linha(tabela, "ideb")[-1]


def test_papel_do_indicador_e_a_origem_calculada():
    tabela = tabela_markdown(carregar_fichas(RAIZ / "metadados" / "indicadores"))
    assert _linha(tabela, "pib_nominal")[3] == "auxiliar"
    assert _linha(tabela, "ideb")[3] == "exibido"
    assert "calculada" in _linha(tabela, "pib_per_capita")[-1]


def test_comando_imprime_a_tabela(capsys):
    assert main(["--raiz", str(RAIZ)]) == 0
    saida = capsys.readouterr().out
    assert "| `populacao` |" in saida and saida.endswith("\n")
