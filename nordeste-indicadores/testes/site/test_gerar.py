"""Gerador do site: Inicio, Sobre e Dados a partir da base publicada do repositorio."""

import hashlib
import json
import re
from pathlib import Path

import pandas as pd
import pytest
import yaml

from nordeste.caminhos import Caminhos
from nordeste.cli import main
from nordeste.site.conteudo import ErroConteudo, calcular_destaques, carregar_conteudo, preencher
from nordeste.site.dados import DadosSite
from nordeste.site.gerar import RelatorioSite, gerar_site

from auxiliares import RAIZ, Arvore, alterar_base, copiar_base

SITE = "https://nordeste.dnascimento.com.br"
PAGINAS = {
    "index.html": "/", "estados/index.html": "/estados/", "explorar/index.html": "/explorar/",
    "cards/index.html": "/cards/", "sobre/index.html": "/sobre/", "dados/index.html": "/dados/",
}
OG = {
    "index.html": "index", "estados/index.html": "estados", "explorar/index.html": "explorar",
    "cards/index.html": "cards", "sobre/index.html": "sobre", "dados/index.html": "dados",
}
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro"]


def _ler(saida: Path, pagina: str) -> str:
    return (saida / pagina).read_text(encoding="utf-8")


def _meta(arvore: Arvore, **attrs) -> str:
    achados = arvore.achar("meta", **attrs)
    assert len(achados) == 1, attrs
    return achados[0]["attrs"]["content"]


def _mes_extenso(aaaa_mm: str) -> str:
    ano, mes = aaaa_mm.split("-")
    return f"{MESES[int(mes) - 1]} de {ano}"


def _data_extenso(aaaa_mm_dd: str) -> str:
    ano, mes, dia = aaaa_mm_dd.split("-")
    return f"{int(dia)}{'º' if int(dia) == 1 else ''} de {MESES[int(mes) - 1]} de {ano}"


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


def test_gera_as_paginas_do_nucleo(gerado):
    saida, relatorio = gerado
    cards = sorted(f"cards/{c['id']}/index.html" for c in carregar_conteudo(RAIZ / "metadados" / "site").cards)
    assert sorted(relatorio.paginas) == sorted([*PAGINAS, *cards])
    for pagina in PAGINAS:
        assert (saida / pagina).is_file()
    assert (saida / "dados" / "base_nordeste.csv").read_bytes() == (RAIZ / "dados/base/base_nordeste.csv").read_bytes()
    assert (saida / "dados" / "derivados.csv").read_bytes() == (RAIZ / "dados/base/derivados.csv").read_bytes()
    assert relatorio.fechos_suprimidos == [] and relatorio.cards_suprimidos == []


def test_sem_nan_undefined_ou_marcador_cru(gerado):
    saida, _ = gerado
    for pagina in PAGINAS:
        html = _ler(saida, pagina)
        assert "{{" not in html and "{%" not in html, pagina
        visivel = Arvore(html).texto_visivel()
        assert not re.search(r"\b(nan|none|undefined|null)\b", visivel, flags=re.IGNORECASE), pagina
        assert "{" not in visivel and "}" not in visivel, pagina
        assert html.startswith("<!doctype html>") and '<html lang="pt-BR">' in html


def test_numeros_das_frases_conferem_com_a_base(gerado, dados, conteudo):
    saida, _ = gerado
    destaques = calcular_destaques(dados, conteudo)
    arvore = Arvore(_ler(saida, "index.html"))
    assert len(conteudo.perguntas) == 6
    for pergunta in conteudo.perguntas:
        artigo = arvore.achar("article", id=f"q-{pergunta['id']}")
        assert len(artigo) == 1, pergunta["id"]
    frases = arvore.achar("p", classe="nn-frase")
    esperadas = [" ".join(preencher(p["lide"], destaques).split()) for p in conteudo.perguntas]
    assert [Arvore.texto(f) for f in frases] == esperadas


def test_abertura_e_selo_vem_da_base(gerado, dados, conteudo):
    saida, _ = gerado
    arvore = Arvore(_ler(saida, "index.html"))
    anos = dados.base.loc[dados.base["valor"].notna() & (dados.base["tipo_dado"] != "indisponivel"), "ano"]
    selo = f"{conteudo.textos['abertura']['eyebrow']} · {anos.min()} a {anos.max()}"
    assert [Arvore.texto(e) for e in arvore.achar("p", classe="nn-eyebrow")][0] == selo
    destaques = calcular_destaques(dados, conteudo)
    intro = [Arvore.texto(e) for e in arvore.achar("p", classe="nn-hero-intro")]
    assert intro == [" ".join(preencher(p["texto"], destaques).split()) for p in conteudo.textos["abertura"]["intro"]]
    html = _ler(saida, "sobre/index.html")
    assert "na data desta publicação" not in html
    assert re.search(r"ainda não tinham sido divulgadas pelo IBGE em \d{1,2}º? de \w+ de \d{4}\.", Arvore(html).texto_visivel())


def test_ordem_dos_elementos_da_pergunta_segue_o_prototipo(gerado):
    saida, _ = gerado
    html = _ler(saida, "index.html")

    def artigo(id_):
        inicio = html.index(f'<article class="nn-card" id="q-{id_}">')
        return html[inicio:html.index("</article>", inicio)]

    for id_, marcas in (
        ("renda-per-capita", ['nn-eyebrow', '<h2', 'nn-muted', 'nn-frase', 'nn-graf"', 'nn-fecho', 'nn-fonte']),
        ("escola", ['nn-eyebrow', '<h2', 'nn-frase', 'nn-graf"', 'nn-fecho', 'nn-alerta', 'nn-fonte']),
    ):
        texto = artigo(id_)
        posicoes = [texto.index(m) for m in marcas]
        assert posicoes == sorted(posicoes), id_
    assert "<b>No frigir dos ovos:</b>" in artigo("escola")


def test_cada_grafico_sai_em_duas_larguras(gerado, conteudo):
    saida, _ = gerado
    arvore = Arvore(_ler(saida, "index.html"))
    graficos = sum(len(p["graficos"]) for p in conteudo.perguntas)
    largos = arvore.achar("div", classe="nn-graf-largo")
    estreitos = arvore.achar("div", classe="nn-graf-estreito")
    assert len(largos) == len(estreitos) == graficos
    svgs = arvore.achar("svg")
    assert len(svgs) == 2 * graficos
    assert [s["attrs"]["viewbox"] for s in svgs[:2]] == ["0 0 720 300", "0 0 360 240"]
    for contenedor in arvore.achar("div", classe="nn-graf"):
        assert contenedor["attrs"]["id"].startswith("g-")
    # cada grafico traz os numeros numa tabela, como a descricao acessivel promete
    assert len(arvore.achar("details")) == len(conteudo.perguntas)


def test_sem_style_nem_script_inline(gerado):
    saida, _ = gerado
    for pagina in PAGINAS:
        arvore = Arvore(_ler(saida, pagina))
        assert not any("style" in e["attrs"] for e in arvore.elementos), pagina
        assert not arvore.achar("style"), pagina
        for script in arvore.achar("script"):
            assert "src" in script["attrs"] or script["attrs"].get("type") == "application/ld+json", pagina


def test_metas_e_canonical_em_cada_pagina(gerado):
    saida, _ = gerado
    for pagina, rota in PAGINAS.items():
        arvore = Arvore(_ler(saida, pagina))
        url = SITE + rota
        assert [e["attrs"]["href"] for e in arvore.achar("link", rel="canonical")] == [url]
        assert _meta(arvore, property="og:url") == url
        assert _meta(arvore, property="og:image") == f"{SITE}/og/{OG[pagina]}.png"
        assert _meta(arvore, property="og:locale") == "pt_BR"
        assert _meta(arvore, name="twitter:card") == "summary_large_image"
        assert _meta(arvore, property="og:title") == Arvore.texto(arvore.achar("title")[0])
        assert _meta(arvore, property="og:description") == _meta(arvore, name="description") != ""
        assert arvore.achar("meta", charset="utf-8") and arvore.achar("meta", name="viewport")


def test_json_ld_valido(gerado, dados):
    saida, _ = gerado
    anos = dados.base.loc[dados.base["valor"].notna() & (dados.base["tipo_dado"] != "indisponivel"), "ano"]
    for pagina in ("index.html", "dados/index.html"):
        scripts = Arvore(_ler(saida, pagina)).achar("script", type="application/ld+json")
        assert len(scripts) == 1, pagina
        ld = json.loads("".join(scripts[0]["texto"]))
        assert ld["@type"] == "Dataset" and ld["@context"] == "https://schema.org"
        assert ld["name"] and ld["description"]
        assert ld["creator"]["name"] == "Júlio Diógenes"
        assert ld["license"] == "https://creativecommons.org/licenses/by/4.0/"
        assert ld["temporalCoverage"] == f"{anos.min()}/{anos.max()}"
        assert ld["spatialCoverage"] == "Nordeste, Brasil"
        assert ld["dateModified"] == dados.data_base
        assert [d["contentUrl"] for d in ld["distribution"]] == [
            f"{SITE}/dados/base_nordeste.csv", f"{SITE}/dados/derivados.csv"
        ]
        assert {d["encodingFormat"] for d in ld["distribution"]} == {"text/csv"}
    assert not Arvore(_ler(saida, "sobre/index.html")).achar("script", type="application/ld+json")


def test_pergunta_mostra_atualizado_em_e_proximo_dado(gerado, dados, conteudo):
    saida, _ = gerado
    arvore = Arvore(_ler(saida, "index.html"))
    previstos = 0
    for pergunta in conteudo.perguntas:
        indicadores = {l["indicador"] for g in pergunta["graficos"] for l in g["linhas"]}
        artigo = next(a for a in arvore.achar("article", id=f"q-{pergunta['id']}"))
        # o texto do artigo inteiro: contamos as frases de atualizacao dentro dele
        texto = Arvore.texto(artigo)
        assert texto.count("Atualizado em ") == len(indicadores), pergunta["id"]
        com_previsao = [i for i in indicadores if dados.proxima_publicacao(i)]
        assert texto.count("Próximo dado esperado: ") == len(com_previsao), pergunta["id"]
        for i in com_previsao:
            assert f"Próximo dado esperado: {_mes_extenso(dados.proxima_publicacao(i))}" in texto
            previstos += 1
        for i in indicadores:
            assert f"Atualizado em {_data_extenso(dados.atualizado_em(i))}" in texto
    assert previstos > 0  # a base publicada tem previsao (ex.: desocupacao), entao a regra foi exercitada


def test_rodape_tem_data_sha256_e_links(gerado, dados):
    saida, _ = gerado
    for pagina in PAGINAS:
        arvore = Arvore(_ler(saida, pagina))
        rodape = Arvore.texto(arvore.achar("footer")[0])
        assert "Júlio Diógenes · Nordeste em Números" in rodape
        assert dados.sha256_base in rodape
        assert re.search(r"publicados em \d{1,2}º? de \w+ de \d{4}", rodape)
        assert "https://dnascimento.com.br" in [e["attrs"].get("href") for e in arvore.achar("a")]


def test_sobre_tem_fontes_por_serie_formulas_e_lacunas(gerado, dados, conteudo):
    saida, _ = gerado
    arvore = Arvore(_ler(saida, "sobre/index.html"))
    linhas = [r for r in arvore.achar("tr") if r["tag"] == "tr"]
    assert len(linhas) - 1 == sum(len(f.series) for f in dados.fichas.values())  # menos o cabecalho
    links = {e["attrs"]["href"] for e in arvore.achar("a")}
    for ficha in dados.fichas.values():
        for serie in ficha.series:
            assert serie.url in links
    visivel = arvore.texto_visivel()
    for item in conteudo.textos["como_ler"]["itens"]:
        assert item in visivel
    for bloco in conteudo.textos["formulas"]["blocos"]:
        assert bloco["titulo"] in visivel
        for item in bloco["itens"]:
            assert item in visivel
    assert len(conteudo.textos["o_que_falta"]["itens"]) == len(arvore.achar("li", classe="nn-lacuna"))
    assert "/dados/" in links


def test_dados_mostra_sha256_de_cada_csv(gerado, dados):
    saida, _ = gerado
    arvore = Arvore(_ler(saida, "dados/index.html"))
    codigos = [Arvore.texto(c) for c in arvore.achar("code", classe="nn-sha-arquivo")]
    assert codigos == [
        dados.sha256_base, hashlib.sha256((saida / "dados" / "derivados.csv").read_bytes()).hexdigest()
    ]
    links = [e["attrs"]["href"] for e in arvore.achar("a", classe="nn-baixar")]
    assert links == ["/dados/base_nordeste.csv", "/dados/derivados.csv"]


def test_mesma_base_mesmo_site(gerado, tmp_path):
    saida, _ = gerado
    outra = tmp_path / "outra"
    gerar_site(Caminhos(raiz=RAIZ), outra, imagens=False)
    arquivos = sorted(p.relative_to(saida) for p in saida.rglob("*") if p.is_file())
    assert arquivos == sorted(p.relative_to(outra) for p in outra.rglob("*") if p.is_file())
    for arquivo in arquivos:
        assert (saida / arquivo).read_bytes() == (outra / arquivo).read_bytes(), arquivo


def test_gerar_apaga_e_recria_a_saida(tmp_path):
    saida = tmp_path / "saida"
    saida.mkdir()
    (saida / "velho.txt").write_text("sobra", encoding="utf-8")
    gerar_site(Caminhos(raiz=RAIZ), saida, imagens=False)
    assert not (saida / "velho.txt").exists() and (saida / "index.html").is_file()


# --- supressao de fecho e card (Ruling S-N) ---


def _fechos(saida: Path) -> list[str]:
    return [Arvore.texto(e) for e in Arvore(_ler(saida, "index.html")).achar("p", classe="nn-fecho")]


def test_fecho_com_condicao_falsa_some_e_vai_ao_relatorio(tmp_path, gerado, conteudo):
    _, normal = gerado
    raiz = copiar_base(tmp_path / "repo")

    def inverter(base):
        # a pobreza do Nordeste termina acima do que comecou: "pob_ne.ultimo < pob_ne.primeiro" fica falsa
        pobreza = base[(base["indicador_id"] == "pobreza") & (base["territorio_id"] == "NE") & (base["valor"] != "")]
        base.loc[pobreza["ano"].astype(int).idxmax(), "valor"] = "99.0"
        return base

    alterar_base(raiz, inverter)
    saida = tmp_path / "saida"
    relatorio = gerar_site(Caminhos(raiz=raiz), saida, imagens=False)
    pobreza = next(p for p in conteudo.perguntas if p["id"] == "pobreza")
    arvore = Arvore(_ler(saida, "index.html"))
    assert arvore.achar("article", id="q-pobreza")  # a pergunta fica, so o fecho sai
    # o paragrafo da abertura que diz "a pobreza caiu" tem a mesma condicao e sai junto (Ruling S-P)
    assert relatorio.fechos_suprimidos == ["abertura_numeros", "pobreza"]
    assert "pobreza" in relatorio.cards_suprimidos
    assert not any(pobreza["fecho"]["texto"] in f for f in _fechos(saida))
    assert len(_fechos(saida)) == len(conteudo.perguntas) - 1
    assert normal.fechos_suprimidos == []


def test_destaque_sumido_da_base_tira_a_pergunta_e_nao_quebra(tmp_path, conteudo):
    raiz = copiar_base(tmp_path / "repo")
    alterar_base(raiz, lambda b: b[~((b["indicador_id"] == "pobreza") & (b["territorio_id"] == "NE"))])
    saida = tmp_path / "saida"
    relatorio = gerar_site(Caminhos(raiz=raiz), saida, imagens=False)
    arvore = Arvore(_ler(saida, "index.html"))
    assert not arvore.achar("article", id="q-pobreza")  # o lide cita o destaque ausente: a pergunta toda sai
    assert len(arvore.achar("article")) == len(conteudo.perguntas) - 1
    assert relatorio.fechos_suprimidos == ["abertura_numeros", "pobreza"]  # o paragrafo da abertura cita o destaque
    assert relatorio.cards_suprimidos == ["pobreza"]  # o card cuja frase cita o destaque ausente; os outros ficam
    assert (saida / "sobre" / "index.html").is_file()


def test_nao_apaga_a_pasta_que_contem_o_projeto(tmp_path):
    raiz = copiar_base(tmp_path / "repo")
    for perigosa in (tmp_path, raiz):
        with pytest.raises(ValueError, match="saída"):
            gerar_site(Caminhos(raiz=raiz), perigosa, imagens=False)
    assert (raiz / "metadados").is_dir()


def test_nao_apaga_a_base_publicada_nem_os_metadados(tmp_path):
    # Ruling S-P: apagar dados/base, dados/relatorios ou metadados (ou uma pasta que os contenha) e irreversivel no robo.
    raiz = copiar_base(tmp_path / "repo")
    antes = sorted(p.relative_to(raiz) for p in raiz.rglob("*"))
    dentro = (raiz / "dados" / "base" / "x", raiz / "dados" / "relatorios" / "x", raiz / "metadados" / "site" / "x")
    for perigosa in (raiz / "dados", raiz / "dados" / "base", raiz / "dados" / "relatorios", raiz / "metadados", *dentro):
        with pytest.raises(ValueError, match="saída"):
            gerar_site(Caminhos(raiz=raiz), perigosa, imagens=False)
    assert sorted(p.relative_to(raiz) for p in raiz.rglob("*")) == antes
    # uma pasta qualquer dentro do projeto, fora da base e dos metadados, pode ser a saida
    gerar_site(Caminhos(raiz=raiz), raiz / "saida-do-site", imagens=False)
    assert (raiz / "saida-do-site" / "index.html").is_file()


# --- textos.yaml incompleto ---


def _sem_chave_de_texto(raiz: Path, caminho: tuple[str, ...]) -> None:
    arquivo = raiz / "metadados" / "site" / "textos.yaml"
    textos = yaml.safe_load(arquivo.read_text(encoding="utf-8"))
    pai = textos
    for chave in caminho[:-1]:
        pai = pai[chave]
    del pai[caminho[-1]]
    arquivo.write_text(yaml.safe_dump(textos, allow_unicode=True, sort_keys=False), encoding="utf-8")


@pytest.mark.parametrize(
    "caminho",
    [("abertura",), ("abertura", "intro"), ("estados", "sem_dados"), ("paginas", "cards"), ("dados", "arquivos", "derivados.csv")],
)
def test_textos_incompleto_e_erro_de_conteudo(tmp_path, caminho):
    raiz = copiar_base(tmp_path / "repo")
    _sem_chave_de_texto(raiz, caminho)
    with pytest.raises(ErroConteudo, match=r"textos\.yaml: falta .*" + re.escape(caminho[-1])):
        gerar_site(Caminhos(raiz=raiz), tmp_path / "saida", imagens=False)


def test_cli_com_chave_de_texto_faltando_sai_com_um_sem_traceback(tmp_path, capsys):
    raiz = copiar_base(tmp_path / "repo")
    _sem_chave_de_texto(raiz, ("abertura", "intro"))
    assert main(["--raiz", str(raiz), "site", "--saida", str(tmp_path / "saida"), "--sem-imagens"]) == 1
    erro = capsys.readouterr().err
    assert "abertura.intro" in erro and "Traceback" not in erro


# --- condicao nos paragrafos da abertura (Ruling S-P) ---


def test_paragrafo_da_abertura_com_condicao_falsa_some_e_vai_ao_relatorio(tmp_path, gerado, conteudo):
    saida_normal, normal = gerado
    assert normal.fechos_suprimidos == []
    raiz = copiar_base(tmp_path / "repo")

    def subir_a_pobreza(base):
        # "A pobreza caiu": a base inverte a direcao e o paragrafo deixa de valer
        pobreza = base[(base["indicador_id"] == "pobreza") & (base["territorio_id"] == "NE") & (base["valor"] != "")]
        base.loc[pobreza["ano"].astype(int).idxmax(), "valor"] = "99.0"
        return base

    alterar_base(raiz, subir_a_pobreza)
    saida = tmp_path / "saida"
    relatorio = gerar_site(Caminhos(raiz=raiz), saida, imagens=False)
    assert "abertura_numeros" in relatorio.fechos_suprimidos
    normais = [Arvore.texto(e) for e in Arvore(_ler(saida_normal, "index.html")).achar("p", classe="nn-hero-intro")]
    sem = [Arvore.texto(e) for e in Arvore(_ler(saida, "index.html")).achar("p", classe="nn-hero-intro")]
    assert len(normais) == 2 and sem == normais[:1]  # o paragrafo sem afirmacao de direcao continua


def test_abertura_sem_id_ou_texto_e_erro_de_conteudo(tmp_path):
    raiz = copiar_base(tmp_path / "repo")
    textos = raiz / "metadados" / "site" / "textos.yaml"
    textos.write_text(textos.read_text(encoding="utf-8").replace("    - id: abertura_inicio\n", "    -\n"), encoding="utf-8")
    with pytest.raises(ErroConteudo, match="abertura"):
        gerar_site(Caminhos(raiz=raiz), tmp_path / "saida", imagens=False)


# --- proximo dado, com cobertura sintetica (Ruling S-P) ---


def test_proximo_dado_aparece_so_onde_a_cobertura_preve(tmp_path, conteudo):
    raiz = copiar_base(tmp_path / "repo")
    cobertura = raiz / "dados" / "relatorios" / "cobertura.csv"
    tabela = pd.read_csv(cobertura, dtype=str, keep_default_na=False)
    tabela["proxima_publicacao"] = ""
    tabela.loc[(tabela["indicador_id"] == "pobreza") & (tabela["territorio_id"] == "NE"), "proxima_publicacao"] = "2031-02"
    # a previsao de outro territorio nao conta: a regra olha so o Nordeste
    tabela.loc[(tabela["indicador_id"] == "gini") & (tabela["territorio_id"] == "BA"), "proxima_publicacao"] = "2031-03"
    tabela.to_csv(cobertura, index=False)
    saida = tmp_path / "saida"
    gerar_site(Caminhos(raiz=raiz), saida, imagens=False)
    arvore = Arvore(_ler(saida, "index.html"))
    for pergunta in conteudo.perguntas:
        indicadores = {l["indicador"] for g in pergunta["graficos"] for l in g["linhas"]}
        texto = Arvore.texto(arvore.achar("article", id=f"q-{pergunta['id']}")[0])
        esperado = 1 if "pobreza" in indicadores else 0
        assert texto.count("Próximo dado esperado: ") == esperado, pergunta["id"]
        assert ("Próximo dado esperado: fevereiro de 2031." in texto) == bool(esperado), pergunta["id"]
        assert "março de 2031" not in texto
        assert texto.count("Atualizado em ") == len(indicadores)  # a data da coleta segue em todos


# --- linha de comando ---


def test_cli_site_sai_com_zero(tmp_path):
    saida, arquivo = tmp_path / "saida", tmp_path / "relatorio.json"
    codigo = main(["--raiz", str(RAIZ), "site", "--saida", str(saida), "--sem-imagens", "--relatorio", str(arquivo)])
    assert codigo == 0
    assert (saida / "index.html").is_file()
    relatorio = json.loads(arquivo.read_text(encoding="utf-8"))
    assert sorted(relatorio) == ["cards_suprimidos", "fechos_suprimidos", "paginas"]
    cards = [f"cards/{c['id']}/index.html" for c in carregar_conteudo(RAIZ / "metadados" / "site").cards]
    assert sorted(relatorio["paginas"]) == sorted([*PAGINAS, *cards])


def test_cli_site_com_conteudo_invalido_sai_com_um(tmp_path, capsys):
    raiz = copiar_base(tmp_path / "repo")
    (raiz / "metadados" / "site" / "textos.yaml").write_text("- nao e um mapa\n", encoding="utf-8")
    assert main(["--raiz", str(raiz), "site", "--saida", str(tmp_path / "saida"), "--sem-imagens"]) == 1
    assert "textos.yaml" in capsys.readouterr().err
