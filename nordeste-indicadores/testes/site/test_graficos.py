import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

from nordeste.governos import carregar_governos
from nordeste.site.dados import Ponto
from nordeste.site.graficos import ConfigGrafico, Linha, descricao_acessivel, grafico_linhas, minigrafico

BASE_MINI = Path(__file__).parent / "base_mini"
CFG = ConfigGrafico(titulo="Teste", casas=1, sufixo="%")


def _pontos(*pares: tuple[int, float], serie: str = "s") -> list[Ponto]:
    return [Ponto(ano, valor, serie) for ano, valor in pares]


def _linha(rotulo_curto="NE", pontos=None, destaque=True, rotulo="Nordeste") -> Linha:
    return Linha(rotulo, rotulo_curto, _pontos((2010, 10.0), (2011, 11.0), (2012, 12.0)) if pontos is None else pontos, destaque)


def _raiz(svg: str) -> ET.Element:
    return ET.fromstring(svg)


def _todos(raiz: ET.Element, tag: str) -> list[ET.Element]:
    return raiz.findall(f".//{{*}}{tag}")


def _classe(el: ET.Element) -> str:
    return el.get("class", "")


def _governos(tmp_path: Path, linhas: list[str]) -> pd.DataFrame:
    arquivo = tmp_path / "governos.csv"
    arquivo.write_text("presidente,inicio,fim,mandato,interino,partido,apelido\n" + "\n".join(linhas) + "\n", encoding="utf-8")
    return carregar_governos(arquivo)


GOVERNOS_MINI = carregar_governos(BASE_MINI / "metadados" / "governos.csv")


def _rotulos_da_ponta(raiz: ET.Element, *prefixos: str) -> dict[str, float]:
    achados = {}
    for texto in _todos(raiz, "text"):
        for prefixo in prefixos:
            if (texto.text or "").startswith(prefixo + " "):
                achados[prefixo] = float(texto.get("y"))
    return achados


def _y_da_grade(raiz: ET.Element) -> tuple[float, float]:
    ys = [float(g.get("y1")) for g in _todos(raiz, "line") if "nn-grade" in _classe(g)]
    return min(ys), max(ys)


def test_linha_quebra_na_troca_de_serie_e_no_ano_faltante():
    pontos = (
        _pontos((2010, 1.0), (2011, 2.0), (2012, 3.0), serie="a")
        + _pontos((2013, 4.0), (2014, 5.0), serie="b")  # ano seguinte, outra serie: quebra
        + _pontos((2016, 6.0), (2017, 7.0), serie="b")  # 2015 sem dado: quebra, sem emendar
        + _pontos((2019, 8.0), serie="b")  # ponto isolado: so o marcador
    )
    raiz = _raiz(grafico_linhas([_linha(pontos=pontos)], CFG, GOVERNOS_MINI))
    assert len(_todos(raiz, "path")) == 3
    assert len(_todos(raiz, "circle")) == 8
    # nenhum trecho cobre 2015 nem liga 2012 a 2013: cada path tem um M so
    assert all(p.get("d").count("M") == 1 for p in _todos(raiz, "path"))


def test_rotulos_da_ponta_nao_se_sobrepoem_nem_saem_do_quadro():
    ne = _linha("NE", _pontos((2010, 1.0), (2020, 1.9)))
    br = _linha("BR", _pontos((2010, 1.0), (2020, 2.2)), destaque=False, rotulo="Brasil")
    raiz = _raiz(grafico_linhas([ne, br], CFG, GOVERNOS_MINI))
    topo, eixo = _y_da_grade(raiz)
    y = _rotulos_da_ponta(raiz, "NE", "BR")
    assert abs(y["NE"] - y["BR"]) >= 14
    assert all(topo <= v <= eixo for v in y.values())


def test_rotulos_da_ponta_ficam_entre_o_topo_e_o_eixo_nos_extremos():
    alto = _linha("A", _pontos((2010, 0.0), (2020, 100.0)))
    baixo = _linha("B", _pontos((2010, 100.0), (2020, 0.0)), destaque=False)
    meio = _linha("C", _pontos((2010, 50.0), (2020, 1.0)), destaque=False)
    raiz = _raiz(grafico_linhas([alto, baixo, meio], ConfigGrafico("Extremos", 0), GOVERNOS_MINI))
    topo, eixo = _y_da_grade(raiz)
    y = _rotulos_da_ponta(raiz, "A", "B", "C")
    assert all(topo <= v <= eixo for v in y.values())
    ordenados = sorted(y.values())
    assert all(b - a >= 14 for a, b in zip(ordenados, ordenados[1:]))


def test_rotulo_da_ponta_leva_rotulo_curto_valor_e_sufixo():
    raiz = _raiz(grafico_linhas([_linha("NE", _pontos((2010, 40.0), (2020, 43.64)))], CFG, GOVERNOS_MINI))
    assert "NE 43,6%" in [t.text for t in _todos(raiz, "text")]


def test_faixas_de_governo_vem_do_csv(tmp_path):
    governos = _governos(tmp_path, [
        "Gov Antigo,1990-01-01,1999-12-31,1,não,,Antigo",  # fora do eixo 2000-2027
        "Ana,2000-01-01,2003-12-31,1,não,,Ana",
        "Ana,2004-01-01,2007-12-31,2,não,,Ana",  # mesmo apelido em sequencia: uma faixa so
        "Bia,2008-01-01,2010-05-12,1,não,,Bia",
        "Caio,2010-05-12,2010-08-31,,sim,,Caio",  # interino: hachurado
        "Caio,2010-08-31,2013-12-31,,não,,Caio",
    ])
    raiz = _raiz(grafico_linhas([_linha(pontos=_pontos((2000, 1.0), (2026, 2.0)))], CFG, governos))
    retangulos = _todos(raiz, "rect")
    assert len(retangulos) == 4  # Ana, Bia, Caio interino, Caio
    comuns = [r for r in retangulos if "nn-faixa" in _classe(r)]
    hachurados = [r for r in retangulos if r.get("fill", "").startswith("url(#")]
    assert len(comuns) == 3 and len(hachurados) == 1
    assert {_classe(r) for r in comuns} == {"nn-faixa-a", "nn-faixa-b"}
    padrao = _todos(raiz, "pattern")
    assert [f"url(#{p.get('id')})" for p in padrao] == [hachurados[0].get("fill")]
    nomes = [t.text for t in _todos(raiz, "text")]
    assert "Ana" in nomes and "Caio" in nomes and "Antigo" not in nomes
    # Ana (2000 a 2007) comeca no inicio do eixo e e a mais larga delas
    larguras = {r: float(r.get("width")) for r in comuns}
    assert float(max(larguras, key=larguras.get).get("x")) == min(float(r.get("x")) for r in comuns)


def test_faixas_alternam_as_duas_classes(tmp_path):
    governos = _governos(tmp_path, [
        "Ana,2000-01-01,2003-12-31,1,não,,Ana",
        "Bia,2004-01-01,2007-12-31,1,não,,Bia",
        "Caio,2008-01-01,2011-12-31,1,não,,Caio",
    ])
    raiz = _raiz(grafico_linhas([_linha(pontos=_pontos((2000, 1.0), (2026, 2.0)))], CFG, governos))
    classes = [_classe(r) for r in _todos(raiz, "rect")]
    assert classes == ["nn-faixa-a", "nn-faixa-b", "nn-faixa-a"]


def test_anos_depois_do_ultimo_dado_ficam_hachurados():
    linha = _linha(pontos=_pontos((2010, 1.0), (2020, 2.0)))
    raiz = _raiz(grafico_linhas([linha], CFG, GOVERNOS_MINI))
    padrao = _todos(raiz, "pattern")[0].get("id")
    depois = [r for r in _todos(raiz, "rect") if r.get("fill") == f"url(#{padrao})" and "nn-faixa" not in _classe(r)]
    ultima = max(float(c.get("cx")) for c in _todos(raiz, "circle"))
    # o retangulo vai do fim do ano 2020 (meio do ano do ultimo ponto, mais meio ano) ate o fim do eixo
    assert any(float(r.get("x")) > ultima for r in depois)
    cheio = _raiz(grafico_linhas([_linha(pontos=_pontos((2010, 1.0), (2026, 2.0)))], CFG, GOVERNOS_MINI))
    assert not [r for r in _todos(cheio, "rect") if r.get("fill", "").startswith("url(#") and float(r.get("x")) > 600]


def test_ref100_so_quando_100_esta_no_dominio():
    baixo = _linha(pontos=_pontos((2010, 40.0), (2020, 60.0)))
    sem_flag = _raiz(grafico_linhas([baixo], ConfigGrafico("R", 1), GOVERNOS_MINI))
    assert not [l for l in _todos(sem_flag, "line") if "nn-ref100" in _classe(l)]
    # mesmo com 100 dentro dos valores, sem o ajuste nao ha linha de referencia
    em_volta = _linha(pontos=_pontos((2010, 90.0), (2020, 110.0)))
    sem_flag2 = _raiz(grafico_linhas([em_volta], ConfigGrafico("R", 1), GOVERNOS_MINI))
    assert not [l for l in _todos(sem_flag2, "line") if "nn-ref100" in _classe(l)]
    # com o ajuste, o 100 entra no dominio e a linha cai entre o topo e o eixo
    com_flag = _raiz(grafico_linhas([baixo], ConfigGrafico("R", 1, ref100=True), GOVERNOS_MINI))
    refs = [l for l in _todos(com_flag, "line") if "nn-ref100" in _classe(l)]
    assert len(refs) == 1
    topo, eixo = _y_da_grade(com_flag)
    assert topo <= float(refs[0].get("y1")) <= eixo
    assert refs[0].get("stroke-dasharray")
    assert "100" in [t.text for t in _todos(com_flag, "text")]


def test_min0_leva_o_eixo_ate_zero():
    linha = _linha(pontos=_pontos((2010, 40.0), (2020, 60.0)))
    sem = [t.text for t in _todos(_raiz(grafico_linhas([linha], ConfigGrafico("M", 0), GOVERNOS_MINI)), "text")]
    com = [t.text for t in _todos(_raiz(grafico_linhas([linha], ConfigGrafico("M", 0, min0=True), GOVERNOS_MINI)), "text")]
    assert "0" not in sem and "0" in com


def test_quebras_de_serie_viram_linhas_verticais_com_rotulo():
    cfg = ConfigGrafico("Q", 1, quebras=((2012, "Nova pesquisa"), (1990, "fora do eixo")))
    raiz = _raiz(grafico_linhas([_linha()], cfg, GOVERNOS_MINI))
    quebras = [l for l in _todos(raiz, "line") if "nn-quebra" in _classe(l)]
    assert len(quebras) == 1 and quebras[0].get("x1") == quebras[0].get("x2")
    textos = [t.text for t in _todos(raiz, "text")]
    assert "Nova pesquisa" in textos and "fora do eixo" not in textos


def test_svg_tem_title_desc_e_viewbox():
    linha = _linha("NE", _pontos((2010, 40.0), (2020, 43.64)))
    svg = grafico_linhas([linha], ConfigGrafico("Pobreza no Nordeste", 1, "%"), GOVERNOS_MINI, largura=640, altura=260)
    raiz = _raiz(svg)
    assert raiz.tag.endswith("svg")
    assert raiz.get("role") == "img"
    assert raiz.get("viewBox") == "0 0 640 260"
    assert raiz.get("width") == "100%"
    titulo, desc = _todos(raiz, "title")[0], _todos(raiz, "desc")[0]
    assert titulo.text == "Pobreza no Nordeste"
    assert desc.text == descricao_acessivel([linha], ConfigGrafico("Pobreza no Nordeste", 1, "%"))
    assert raiz.get("aria-labelledby") == f"{titulo.get('id')} {desc.get('id')}"
    assert svg.startswith("<svg ") and svg.endswith("</svg>")


def test_title_desc_escapam_caracteres_especiais():
    linha = _linha("NE", rotulo="Norte & <Nordeste>")
    raiz = _raiz(grafico_linhas([linha], ConfigGrafico("A & B <c>", 1), GOVERNOS_MINI))
    assert _todos(raiz, "title")[0].text == "A & B <c>"
    assert "Norte & <Nordeste>" in _todos(raiz, "desc")[0].text


def test_descricao_acessivel_traz_primeiro_e_ultimo_valor_de_cada_linha():
    ne = _linha("NE", _pontos((2012, 58.8), (2018, 50.0), (2024, 44.7)), rotulo="Nordeste")
    br = _linha("BR", _pontos((2012, 30.0), (2024, 25.5)), destaque=False, rotulo="Brasil")
    vazia = _linha("XX", [], destaque=False, rotulo="Vazia")
    texto = descricao_acessivel([ne, br, vazia], ConfigGrafico("Pobreza", 1, "%"))
    assert texto == (
        "Gráfico de linhas, Pobreza. Nordeste: 58,8% em 2012 e 44,7% em 2024; "
        "Brasil: 30,0% em 2012 e 25,5% em 2024. A tabela com todos os valores está logo abaixo."
    )


def test_pontos_fora_do_eixo_nao_entram_no_desenho_nem_na_descricao():
    linha = _linha("NE", _pontos((1995, 5.0), (2010, 10.0), (2012, 12.0), (2031, 99.0)))
    texto = descricao_acessivel([linha], CFG)
    assert "2010" in texto and "2012" in texto and "1995" not in texto and "2031" not in texto
    raiz = _raiz(grafico_linhas([linha], CFG, GOVERNOS_MINI))
    assert len(_todos(raiz, "circle")) == 2


def test_data_pontos_data_casas_e_data_sufixo_para_o_script():
    ne = _linha("NE", _pontos((2011, 10.5), (2012, 11.0)), rotulo="Nordeste")
    br = Linha("Brasil", "BR", [Ponto(2012, 9.0, "pnad")], False)
    raiz = _raiz(grafico_linhas([ne, br], ConfigGrafico("D", 2, " mi"), GOVERNOS_MINI))
    assert raiz.get("data-casas") == "2"
    assert raiz.get("data-sufixo") == " mi"
    assert raiz.get("data-pontos") == (
        '[{"rotulo":"Nordeste","rotulo_curto":"NE","destaque":true,"pontos":[[2011,10.5,"s"],[2012,11.0,"s"]]},'
        '{"rotulo":"Brasil","rotulo_curto":"BR","destaque":false,"pontos":[[2012,9.0,"pnad"]]}]'
    )
    assert json.loads(raiz.get("data-pontos"))[1]["pontos"] == [[2012, 9.0, "pnad"]]


def test_data_pontos_mantem_acentos():
    linha = Linha("Maranhão", "MA", _pontos((2010, 1.0)), True)
    assert 'data-pontos="[{&quot;rotulo&quot;:&quot;Maranhão&quot;' in grafico_linhas([linha], CFG, GOVERNOS_MINI)


def test_sem_atributo_style_nem_cor_literal_de_tema():
    svg = grafico_linhas([_linha(), _linha("BR", destaque=False)], ConfigGrafico("S", 1, ref100=True), GOVERNOS_MINI)
    assert "style=" not in svg and "<style" not in svg and "<script" not in svg
    assert "#ea2e00" not in svg.lower()
    classes = set(re.findall(r'class="([^"]+)"', svg))
    assert {"nn-linha-ne", "nn-linha-ref", "nn-grade", "nn-eixo", "nn-rotulo-forte", "nn-ref100", "nn-hachura"} <= classes


def test_nordeste_e_referencia_usam_classes_diferentes():
    ne = _linha("NE", destaque=True)
    br = _linha("BR", destaque=False)
    raiz = _raiz(grafico_linhas([ne, br], CFG, GOVERNOS_MINI))
    grupos = [_classe(g) for g in _todos(raiz, "g")]
    assert grupos == ["nn-linha-ne", "nn-linha-ref"]


def test_mesma_entrada_mesmo_svg():
    linhas = [_linha(), _linha("BR", destaque=False)]
    cfg = ConfigGrafico("Igual", 1, "%", ref100=True, quebras=((2011, "x"),))
    assert grafico_linhas(linhas, cfg, GOVERNOS_MINI) == grafico_linhas(linhas, cfg, GOVERNOS_MINI)
    assert minigrafico(linhas) == minigrafico(linhas)


def test_ids_dos_padroes_nao_colidem_entre_graficos_diferentes():
    a = grafico_linhas([_linha()], ConfigGrafico("A", 1), GOVERNOS_MINI)
    b = grafico_linhas([_linha()], ConfigGrafico("B", 1), GOVERNOS_MINI)
    id_a = _todos(_raiz(a), "pattern")[0].get("id")
    id_b = _todos(_raiz(b), "pattern")[0].get("id")
    assert id_a != id_b


def test_sem_pontos_visiveis_nao_ha_grafico():
    assert grafico_linhas([], CFG, GOVERNOS_MINI) == ""
    assert grafico_linhas([_linha(pontos=[])], CFG, GOVERNOS_MINI) == ""
    assert grafico_linhas([_linha(pontos=_pontos((1990, 1.0)))], CFG, GOVERNOS_MINI) == ""


def test_valor_unico_nao_divide_por_zero():
    raiz = _raiz(grafico_linhas([_linha(pontos=_pontos((2010, 5.0), (2011, 5.0)))], CFG, GOVERNOS_MINI))
    assert len(_todos(raiz, "path")) == 1


def test_numeros_negativos_e_zero_no_eixo_sem_menos_zero():
    linha = _linha(pontos=_pontos((2010, -20.0), (2011, 30.0)))
    textos = [t.text for t in _todos(_raiz(grafico_linhas([linha], ConfigGrafico("N", 0), GOVERNOS_MINI)), "text")]
    assert "0" in textos and "-0" not in textos


def test_largura_estreita_abrevia_faixas_e_corta_rotulos_de_quebra(tmp_path):
    governos = _governos(tmp_path, ["Lula,2003-01-01,2006-12-31,1,não,,Lula", "Lula,2007-01-01,2010-12-31,2,não,,Lula"])
    cfg = ConfigGrafico("E", 1, quebras=((2012, "Nova pesquisa"),))
    largo = _raiz(grafico_linhas([_linha()], cfg, governos))
    assert "Lula" in [t.text for t in _todos(largo, "text")]
    estreito = _raiz(grafico_linhas([_linha()], cfg, governos, largura=360, altura=230))
    textos = [t.text for t in _todos(estreito, "text")]
    assert "Nova pesquisa" not in textos
    assert "Lula" not in textos and "L" in textos
    assert estreito.get("viewBox") == "0 0 360 230"


def test_minigrafico_e_decorativo_e_traz_um_path_por_trecho():
    pontos = _pontos((2010, 1.0), (2011, 2.0), (2013, 3.0), (2014, 4.0))
    svg = minigrafico([_linha(pontos=pontos), _linha("BR", destaque=False)], largura=300, altura=100)
    raiz = _raiz(svg)
    assert raiz.get("viewBox") == "0 0 300 100"
    assert raiz.get("width") == "100%"
    assert raiz.get("aria-hidden") == "true"
    assert len(_todos(raiz, "path")) == 3  # dois trechos da primeira linha, um da segunda
    assert "style=" not in svg
    assert [_classe(g) for g in _todos(raiz, "g")] == ["nn-linha-ne", "nn-linha-ref"]
    assert minigrafico([]) == "" and minigrafico([_linha(pontos=[])]) == ""
