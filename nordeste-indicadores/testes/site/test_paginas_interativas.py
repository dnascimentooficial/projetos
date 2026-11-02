"""Estados, Explorar e Cards: as paginas com seletores, ja com a primeira vista pronta no HTML."""

import json
import re
from pathlib import Path

import pytest

from nordeste.caminhos import Caminhos
from nordeste.site.conteudo import calcular_destaques, carregar_conteudo, preencher
from nordeste.site.dados import DadosSite
from nordeste.site.explorar import (
    INDICADORES_ESTADOS, INDICADORES_EXPLORAR, POR_CHAVE, TERRITORIOS, dados_explorar, vista_estados,
)
from nordeste.site.formatacao import numero
from nordeste.site.gerar import RelatorioSite, gerar_site, vista_explorar_em_html

from auxiliares import RAIZ, Arvore, alterar_base, copiar_base

SITE = "https://nordeste.dnascimento.com.br"
AVISO = "Este indicador não tem dados para este território"
CHAVES_DO_EXPLORAR = [
    "pib_pc", "pib_vol", "pib_part", "renda", "rend_trab", "desoc", "informal", "pobreza", "extrema", "gini", "idhm",
    "ideb_ai", "ideb_af", "ideb_em", "aband", "matric", "superior", "pop",
]
CHAVES_DOS_ESTADOS = ["pib_pc", "renda", "pobreza", "desoc", "ideb_ai", "idhm", "aband"]
UFS = ["MA", "PI", "CE", "RN", "PB", "PE", "AL", "SE", "BA"]


def _ler(saida: Path, pagina: str) -> str:
    return (saida / pagina).read_text(encoding="utf-8")


def _meta(arvore: Arvore, **attrs) -> str:
    achados = arvore.achar("meta", **attrs)
    assert len(achados) == 1, attrs
    return achados[0]["attrs"]["content"]


@pytest.fixture(scope="module")
def dados() -> DadosSite:
    return DadosSite.carregar(Caminhos(raiz=RAIZ))


@pytest.fixture(scope="module")
def conteudo():
    return carregar_conteudo(RAIZ / "metadados" / "site")


@pytest.fixture(scope="module")
def gerado(tmp_path_factory) -> tuple[Path, RelatorioSite]:
    saida = tmp_path_factory.mktemp("site") / "saida"
    return saida, gerar_site(Caminhos(raiz=RAIZ), saida, imagens=False)


# --- Explorar ---


def test_json_do_explorar_tem_18_indicadores_e_separa_series(gerado, dados):
    saida, _ = gerado
    completo = dados_explorar(dados)
    assert list(completo) == CHAVES_DO_EXPLORAR and len(completo) == 18
    assert [i.chave for i in INDICADORES_EXPLORAR] == CHAVES_DO_EXPLORAR
    arquivos = sorted(p.name for p in (saida / "explorar" / "dados").iterdir())
    assert arquivos == sorted(f"{c}.json" for c in CHAVES_DO_EXPLORAR)
    territorios = [t[0] for t in TERRITORIOS]
    assert len(territorios) == 16
    for chave in CHAVES_DO_EXPLORAR:
        do_arquivo = json.loads(_ler(saida, f"explorar/dados/{chave}.json"))
        assert do_arquivo == completo[chave], chave
        assert list(do_arquivo) == territorios, chave  # os 16, mesmo os sem dado (lista vazia)
        for territorio, pontos in do_arquivo.items():
            chaves = [(ano, serie) for ano, _, serie in pontos]
            assert chaves == sorted(set(chaves)), (chave, territorio)  # em ordem e sem repetir ano na mesma serie

    # series de pesquisas diferentes seguem separadas: a desocupacao do Nordeste tem duas, cada ponto com a sua
    desoc = completo["desoc"]["NE"]
    series = {serie for _, _, serie in desoc}
    assert len(series) >= 2
    for serie in series:
        esperado = [[p.ano, p.valor, p.serie] for p in dados.serie("desocupacao", "NE", serie=serie)]
        assert [p for p in desoc if p[2] == serie] == esperado


def test_filtros_do_explorar_seguem_o_prototipo(dados):
    completo = dados_explorar(dados)
    esperado = {
        "ideb_ai": ("ideb", {"sub": "anos_iniciais", "rede": "total"}),
        "ideb_em": ("ideb", {"sub": "ensino_medio", "rede": "total"}),
        "matric": ("matriculas_basica", {"etapa": "educacao_basica", "rede": "total"}),
        "superior": ("superior", {"sub": "matriculas", "rede": "total"}),
        "idhm": ("idhm", {"sub": "idhm"}),
        "pib_pc": ("pib_per_capita", {}),
    }
    for chave, (indicador, filtros) in esperado.items():
        for territorio in ("NE", "BR", "BA"):
            do_site = [(a, v, s) for a, v, s in completo[chave][territorio]]
            da_base = [(p.ano, p.valor, p.serie) for p in dados.serie(indicador, territorio, **filtros)]
            assert do_site == da_base, (chave, territorio)
    assert completo["pib_pc"]["NE"] and completo["pop"]["NE"]


@pytest.fixture(scope="module")
def sem_idhm_do_brasil_fora_do_ne(tmp_path_factory) -> Path:
    raiz = copiar_base(tmp_path_factory.mktemp("repo") / "repo")
    alterar_base(raiz, lambda b: b[~((b["indicador_id"] == "idhm") & (b["territorio_id"] == "BR_FORA_NE"))])
    return raiz


def test_territorio_sem_dados_tem_mensagem(sem_idhm_do_brasil_fora_do_ne, conteudo):
    # Foco 1: indicador sem dado para o territorio escolhido: aviso no lugar do grafico, sem erro nem grafico vazio.
    dados = DadosSite.carregar(Caminhos(raiz=sem_idhm_do_brasil_fora_do_ne))
    assert dados_explorar(dados)["idhm"]["BR_FORA_NE"] == []
    html = vista_explorar_em_html(dados, conteudo.textos, "idhm", "BR_FORA_NE")
    arvore = Arvore(html)
    assert AVISO in arvore.texto_visivel()
    assert not arvore.achar("svg") and not arvore.achar("table")  # nem a referencia (Nordeste) aparece sozinha
    # o mesmo indicador com dado no territorio desenha o grafico e a tabela, sem aviso
    com_dado = Arvore(vista_explorar_em_html(dados, conteudo.textos, "idhm", "NE"))
    assert com_dado.achar("svg") and com_dado.achar("table")
    assert AVISO not in com_dado.texto_visivel()


def test_pagina_gera_com_territorio_sem_dados(sem_idhm_do_brasil_fora_do_ne, tmp_path):
    saida = tmp_path / "saida"
    gerar_site(Caminhos(raiz=sem_idhm_do_brasil_fora_do_ne), saida, imagens=False)
    assert (saida / "explorar" / "index.html").is_file()
    assert json.loads(_ler(saida, "explorar/dados/idhm.json"))["BR_FORA_NE"] == []


def test_explorar_traz_a_vista_inicial_desenhada(gerado, dados):
    saida, _ = gerado
    arvore = Arvore(_ler(saida, "explorar/index.html"))
    ind = POR_CHAVE["pib_pc"]
    titulo = f"{ind.nome}: Nordeste ({ind.unidade})"
    assert [Arvore.texto(h) for h in arvore.achar("h2")] == [titulo]
    assert AVISO not in arvore.texto_visivel()
    # nas duas larguras (Ruling S-O), com o Brasil como referencia e o Nordeste em destaque
    assert len(arvore.achar("div", classe="nn-graf-largo")) == len(arvore.achar("div", classe="nn-graf-estreito")) == 1
    svgs = arvore.achar("svg")
    assert [s["attrs"]["viewbox"] for s in svgs] == ["0 0 720 300", "0 0 360 240"]
    linhas = json.loads(svgs[0]["attrs"]["data-pontos"])
    assert [(l["rotulo"], l["destaque"]) for l in linhas] == [("Brasil", False), ("Nordeste", True)]
    assert svgs[0]["attrs"]["data-casas"] == "0"
    # a tabela traz os numeros do territorio escolhido, com a serie da fonte
    pontos = dados.serie("pib_per_capita", "NE")
    linhas_da_tabela = arvore.achar("tr")[1:]  # menos o cabecalho
    assert len(linhas_da_tabela) == len(pontos)
    primeira = [Arvore.texto(td) for td in arvore.achar("td")][:4]
    assert primeira == [str(pontos[0].ano), "Nordeste", numero(pontos[0].valor, 0), pontos[0].serie]


def test_explorar_tem_os_seletores_com_os_dados_de_cada_opcao(gerado):
    saida, _ = gerado
    arvore = Arvore(_ler(saida, "explorar/index.html"))
    selects = {s["attrs"]["id"]: s for s in arvore.achar("select")}
    assert set(selects) == {"sel-expl-ind", "sel-expl-terr", "sel-expl-terr2"}
    indicadores = [o for o in arvore.achar("option") if o["attrs"].get("value") in CHAVES_DO_EXPLORAR]
    assert [o["attrs"]["value"] for o in indicadores] == CHAVES_DO_EXPLORAR
    for opcao, ind in zip(indicadores, INDICADORES_EXPLORAR):
        assert opcao["attrs"]["data-casas"] == str(ind.casas) and opcao["attrs"]["data-sufixo"] == ind.sufixo
        assert Arvore.texto(opcao) == ind.rotulo
    inicial = [o["attrs"]["value"] for o in arvore.achar("option") if "selected" in o["attrs"]]
    assert inicial == ["pib_pc", "NE", ""]
    territorios = [o["attrs"]["value"] for o in arvore.achar("option") if o["attrs"].get("value") not in CHAVES_DO_EXPLORAR]
    assert territorios == [t[0] for t in TERRITORIOS] + [""] + [t[0] for t in TERRITORIOS]
    container = arvore.achar("article", id="explorar-grafico")[0]["attrs"]
    assert container["data-dados"] == "/explorar/dados/" and AVISO in container["data-sem-dados"]


# --- Estados ---


def _numero(texto: str) -> float:
    """`1.234,5` -> 1234.5."""
    return float(texto.replace(".", "").replace(",", "."))


def _vistas(html: str) -> list[Arvore]:
    return [Arvore(trecho) for trecho in html.split('<div class="nn-vista"')[1:]]


def test_estados_tem_os_7_indicadores_e_9_ufs(gerado):
    saida, _ = gerado
    html = _ler(saida, "estados/index.html")
    arvore = Arvore(html)
    opcoes = arvore.achar("option")
    assert [o["attrs"]["value"] for o in opcoes] == CHAVES_DOS_ESTADOS and len(opcoes) == 7
    assert [i.chave for i in INDICADORES_ESTADOS] == CHAVES_DOS_ESTADOS
    vistas = arvore.achar("div", classe="nn-vista")
    assert [v["attrs"]["data-vista"] for v in vistas] == CHAVES_DOS_ESTADOS
    assert ["hidden" in v["attrs"] for v in vistas] == [False] + [True] * 6  # a primeira vista visivel, o resto escondido
    for trecho in _vistas(html):
        assert [Arvore.texto(e) for e in trecho.achar("th", classe="nn-uf")] == UFS
        celulas = trecho.achar("td", classe="nn-cel")
        assert celulas and all(
            re.fullmatch(r"nn-cel (nn-f\d|nn-vazia)", c["attrs"]["class"]) for c in celulas
        )
        assert len(celulas) % 9 == 0
        assert trecho.achar("div", classe="nn-ranking") and len(trecho.achar("div", classe="nn-rk")) <= 9
        assert trecho.achar("details")


def test_estados_sem_style_e_com_faixas_por_classe(gerado):
    saida, _ = gerado
    arvore = Arvore(_ler(saida, "estados/index.html"))
    assert not any("style" in e["attrs"] for e in arvore.elementos)  # Ruling S-D
    classes = {c for e in arvore.achar("td", classe="nn-cel") for c in e["attrs"]["class"].split()}
    assert classes <= {"nn-cel", "nn-vazia"} | {f"nn-f{i}" for i in range(10)}
    assert {"nn-f0", "nn-f9"} <= classes


@pytest.mark.parametrize("chave, maior_melhor", [("pobreza", False), ("pib_pc", True), ("desoc", False), ("idhm", True)])
def test_mapa_de_calor_escurece_o_melhor(dados, chave, maior_melhor):
    # "Melhor = mais escuro": a faixa 9 e a situacao mais favoravel do indicador (a menor, quando menor e melhor).
    ind = next(i for i in INDICADORES_ESTADOS if i.chave == chave)
    assert ind.maior_melhor is maior_melhor
    vista = vista_estados(dados, ind)
    valores = {}
    for linha in vista["linhas"]:
        for celula in linha["celulas"]:
            if celula["classe"] != "nn-vazia":
                valores[linha["estado"], celula["ano"]] = (celula["classe"], celula["titulo"])
    numeros = {k: _numero(re.search(r": ([\d.,]+)", t).group(1)) for k, (_, t) in valores.items()}
    melhor = max(numeros, key=numeros.get) if maior_melhor else min(numeros, key=numeros.get)
    pior = min(numeros, key=numeros.get) if maior_melhor else max(numeros, key=numeros.get)
    assert valores[melhor][0] == "nn-f9" and valores[pior][0] == "nn-f0"


def test_ranking_do_ultimo_ano_na_ordem_do_indicador(dados):
    for chave in ("pobreza", "pib_pc"):
        ind = next(i for i in INDICADORES_ESTADOS if i.chave == chave)
        vista = vista_estados(dados, ind)
        ultimo = vista["ano_do_ranking"]
        assert ultimo == vista["anos"][-1]
        valores = [_numero(r["valor"].rstrip("%")) for r in vista["ranking"]]
        assert valores == sorted(valores, reverse=ind.maior_melhor)
        assert [r["posicao"][:2] for r in vista["ranking"]] == [f"{i}º" for i in range(1, len(valores) + 1)]
        assert len(valores) <= 9


def test_estados_vista_sem_dados_mostra_aviso_e_nao_quebra(tmp_path):
    raiz = copiar_base(tmp_path / "repo")
    alterar_base(raiz, lambda b: b[b["indicador_id"] != "abandono_em"])
    saida = tmp_path / "saida"
    gerar_site(Caminhos(raiz=raiz), saida, imagens=False)
    html = _ler(saida, "estados/index.html")
    vistas = _vistas(html)
    assert len(vistas) == 7
    assert "Este indicador não tem dados para os estados" in vistas[6].texto_visivel()  # o abandono e o ultimo
    assert all("não tem dados" not in v.texto_visivel() for v in vistas[:6])
    assert not vistas[6].achar("td", classe="nn-cel") and not vistas[6].achar("details")
    assert all(not v for v in json.loads(_ler(saida, "explorar/dados/aband.json")).values())


# --- Cards ---


def test_17_paginas_de_card_com_og_proprio(gerado, conteudo):
    saida, relatorio = gerado
    assert len(conteudo.cards) == 17 and relatorio.cards_suprimidos == []
    titulos = set()
    for card in conteudo.cards:
        pagina = f"cards/{card['id']}/index.html"
        assert pagina in relatorio.paginas
        arvore = Arvore(_ler(saida, pagina))
        url = f"{SITE}/cards/{card['id']}/"
        assert [e["attrs"]["href"] for e in arvore.achar("link", rel="canonical")] == [url]
        assert _meta(arvore, property="og:url") == url
        assert _meta(arvore, property="og:image") == f"{SITE}/cards/{card['id']}.png"
        assert _meta(arvore, property="og:title") == Arvore.texto(arvore.achar("title")[0])
        assert card["frase_feita"] in _meta(arvore, property="og:title")
        assert _meta(arvore, property="og:description") == _meta(arvore, name="description") != ""
        assert _meta(arvore, name="twitter:card") == "summary_large_image"
        titulos.add(_meta(arvore, property="og:title"))
        baixar = [a for a in arvore.achar("a") if Arvore.texto(a) == "Baixar imagem (PNG)"]
        assert [a["attrs"]["href"] for a in baixar] == [f"/cards/{card['id']}.png"]
        assert not arvore.achar("script", type="application/ld+json")
    assert len(titulos) == 17


def test_card_mostra_numeros_frase_e_fonte_da_base(gerado, dados, conteudo):
    saida, _ = gerado
    destaques = calcular_destaques(dados, conteudo)
    for card in conteudo.cards:
        arvore = Arvore(_ler(saida, f"cards/{card['id']}/index.html"))
        cartao = arvore.achar("article", classe="nn-cartao")
        assert len(cartao) == 1, card["id"]
        numeros = arvore.achar("p", classe="nn-c-numero")
        assert len(numeros) == 1
        assert ("nn-c-longo" in numeros[0]["attrs"]["class"].split()) == card.get("longo", False)
        assert Arvore.texto(numeros[0]) == f"{preencher(card['de'], destaques)} → {preencher(card['para'], destaques)}"
        assert [Arvore.texto(e) for e in arvore.achar("p", classe="nn-c-frase")] == [preencher(card["frase"], destaques)]
        assert [Arvore.texto(e) for e in arvore.achar("p", classe="nn-c-fecho")] == [preencher(card["fecho"], destaques)]
        assert [Arvore.texto(e) for e in arvore.achar("h1")] == [card["frase_feita"]]
        fonte = Arvore.texto(arvore.achar("p", classe="nn-c-fonte")[0])
        data = "/".join(reversed(dados.data_base.split("-")))
        assert fonte == f"Fonte: {card['fonte']} · dados de {data} · dnascimento.com.br"
        assert len(arvore.achar("svg")) == 1  # o minigrafico, decorativo
        assert arvore.achar("svg")[0]["attrs"]["aria-hidden"] == "true"


def test_rotulo_dos_cards_e_neutro(gerado, conteudo):
    # Ruling S-R: "Os dados dizem outra coisa" contradiria os cards cujo fecho admite fundo de verdade.
    saida, _ = gerado
    for card in conteudo.cards:
        arvore = Arvore(_ler(saida, f"cards/{card['id']}/index.html"))
        assert [Arvore.texto(e) for e in arvore.achar("p", classe="nn-c-sera")] == ["O que os dados dizem"], card["id"]
        assert "Os dados dizem outra coisa" not in arvore.texto_visivel(), card["id"]
    assert "Os dados dizem outra coisa" not in _ler(saida, "cards/index.html")


def test_lista_de_cards_leva_a_cada_pagina(gerado, conteudo):
    saida, _ = gerado
    arvore = Arvore(_ler(saida, "cards/index.html"))
    links = [a["attrs"]["href"] for a in arvore.achar("a", classe="nn-cartao-link")]
    assert links == [f"/cards/{c['id']}/" for c in conteudo.cards]


def test_card_suprimido_nao_gera_pagina_e_vai_ao_relatorio(tmp_path, conteudo):
    raiz = copiar_base(tmp_path / "repo")

    def inverter(base):
        # a pobreza do Nordeste termina acima do que comecou: a condicao do card fica falsa
        pobreza = base[(base["indicador_id"] == "pobreza") & (base["territorio_id"] == "NE") & (base["valor"] != "")]
        base.loc[pobreza["ano"].astype(int).idxmax(), "valor"] = "99.0"
        return base

    alterar_base(raiz, inverter)
    saida = tmp_path / "saida"
    relatorio = gerar_site(Caminhos(raiz=raiz), saida, imagens=False)
    assert "pobreza" in relatorio.cards_suprimidos
    assert not (saida / "cards" / "pobreza").exists()
    assert "cards/pobreza/index.html" not in relatorio.paginas
    ids = [c["id"] for c in conteudo.cards]
    publicados = [i for i in ids if i not in relatorio.cards_suprimidos]
    assert len(publicados) >= 10
    for id_ in publicados:
        assert (saida / "cards" / id_ / "index.html").is_file()
    lista = Arvore(_ler(saida, "cards/index.html"))
    assert [a["attrs"]["href"] for a in lista.achar("a", classe="nn-cartao-link")] == [f"/cards/{i}/" for i in publicados]
    assert sorted(relatorio.paginas) == sorted(
        [p for p in relatorio.paginas if not p.startswith("cards/") or p == "cards/index.html"]
        + [f"cards/{i}/index.html" for i in publicados]
    )


# --- todas as paginas novas ---


def test_paginas_novas_sem_nan_style_ou_script_inline(gerado):
    saida, relatorio = gerado
    novas = ["estados/index.html", "explorar/index.html", "cards/index.html"] + [
        p for p in relatorio.paginas if p.startswith("cards/") and p != "cards/index.html"
    ]
    assert len(novas) == 3 + 17
    for pagina in novas:
        html = _ler(saida, pagina)
        assert "{{" not in html and "{%" not in html, pagina
        arvore = Arvore(html)
        visivel = arvore.texto_visivel()
        assert not re.search(r"\b(nan|none|undefined|null)\b", visivel, flags=re.IGNORECASE), pagina
        assert "{" not in visivel and "}" not in visivel, pagina
        assert not any("style" in e["attrs"] for e in arvore.elementos), pagina
        assert not arvore.achar("style"), pagina
        assert all("src" in s["attrs"] for s in arvore.achar("script")), pagina
        assert '<html lang="pt-BR">' in html
