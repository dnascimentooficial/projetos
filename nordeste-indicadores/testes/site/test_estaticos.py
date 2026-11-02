"""Estilo, script, fontes e .htaccess do site: identidade visual, Content-Security-Policy e movimento opcional."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from nordeste.caminhos import Caminhos
from nordeste.site import graficos
from nordeste.site.dados import DadosSite
from nordeste.site.formatacao import numero
from nordeste.site.gerar import gerar_site

from auxiliares import RAIZ, Arvore

SITE = "https://nordeste.dnascimento.com.br"
HTACCESS = [
    "RewriteEngine On",
    r"RewriteCond %{HTTP_HOST} !^nordeste\.dnascimento\.com\.br$ [NC]",
    "RewriteRule ^(.*)$ https://nordeste.dnascimento.com.br/$1 [R=301,L]",
    "RewriteCond %{HTTPS} off",
    "RewriteRule ^(.*)$ https://nordeste.dnascimento.com.br/$1 [R=301,L]",
    "Header always set Content-Security-Policy \"default-src 'self'; img-src 'self' data:; style-src 'self'; "
    "script-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'self'\"",
    'Header always set X-Content-Type-Options "nosniff"',
    'Header always set Referrer-Policy "strict-origin-when-cross-origin"',
    'Header always set X-Frame-Options "DENY"',
    'Header always set Strict-Transport-Security "max-age=31536000"',
]
CORES = ("#ea2e00", "#c42600", "#080808", "#f5f4ef", "#ffffff")
# elementos que carregam um recurso pela URL; <a> e so link (as fontes oficiais sao links e podem ser externos)
CARREGAM = {"link": "href", "script": "src", "img": "src", "source": "src", "iframe": "src", "video": "src",
            "audio": "src", "embed": "src", "object": "data", "image": "href", "use": "href"}
NAMESPACE_SVG = "http://www.w3.org/2000/svg"  # nome, nao recurso: o site.js cria elementos SVG com ele
MOVIMENTO = re.compile(r"^(animation|transition)(-[a-z-]+)?$|^view-transition-name$|^scroll-behavior$")
SEM_REDUCAO = "@media (prefers-reduced-motion: no-preference)"


@pytest.fixture(scope="module")
def saida(tmp_path_factory) -> Path:
    destino = tmp_path_factory.mktemp("site") / "saida"
    gerar_site(Caminhos(raiz=RAIZ), destino, imagens=False)
    return destino


def _arquivos(saida: Path, extensao: str) -> list[Path]:
    return sorted(saida.rglob(f"*{extensao}"))


def _sem_comentarios(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _regras(css: str) -> list[tuple[tuple[str, ...], str]]:
    """(cabecalhos dos blocos que envolvem, declaracao) de cada declaracao do CSS; at-rules vazias como `@x { }`
    entram com declaracao vazia, para o teste ver onde ficam."""
    achadas, pilha, atual = [], [], ""
    for caractere in _sem_comentarios(css):
        if caractere == "{":
            pilha.append(" ".join(atual.split()))
            atual = ""
            achadas.append((tuple(pilha), ""))
        elif caractere == "}":
            if atual.strip():
                achadas.append((tuple(pilha), atual.strip()))
            pilha.pop()
            atual = ""
        elif caractere == ";":
            achadas.append((tuple(pilha), atual.strip()))
            atual = ""
        else:
            atual += caractere
    assert not pilha, "chaves desbalanceadas no CSS"
    return achadas


def _proprio(url: str) -> bool:
    return not re.match(r"^(?:[a-z][a-z0-9+.-]*:|//)", url, re.I) or url.startswith(SITE + "/")


# --- .htaccess ---


def test_htaccess_redireciona_e_tem_cabecalhos(saida):
    linhas = [l for l in (saida / ".htaccess").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert linhas == HTACCESS


# --- Content-Security-Policy: nada de fora e nada inline ---


def test_nenhum_recurso_externo(saida):
    paginas = _arquivos(saida, ".html")
    assert len(paginas) > 6
    for pagina in paginas:
        arvore = Arvore(pagina.read_text(encoding="utf-8"))
        for elemento in arvore.elementos:
            if elemento["tag"] == "a":
                continue
            for nome in {CARREGAM.get(elemento["tag"]), "src", "srcset", "poster"} - {None}:
                valor = elemento["attrs"].get(nome)
                if valor is None:
                    continue
                urls = [v.split()[0] for v in valor.split(",") if v.strip()] if nome == "srcset" else [valor]
                for url in urls:
                    assert _proprio(url), (pagina.name, elemento["tag"], url)
        for estilo in arvore.achar("link", rel="stylesheet"):
            assert estilo["attrs"]["href"].startswith("/"), pagina
    for css in _arquivos(saida, ".css"):
        texto = _sem_comentarios(css.read_text(encoding="utf-8"))
        assert "@import" not in texto, css
        for url in re.findall(r"url\(\s*['\"]?([^'\")]+)", texto):
            assert url.startswith("/") or url.startswith("#"), (css.name, url)
    for js in _arquivos(saida, ".js"):
        texto = js.read_text(encoding="utf-8").replace(NAMESPACE_SVG, "")
        assert not re.search(r"https?://|//[a-z0-9-]+\.[a-z]", texto, re.I), js.name
        assert "import(" not in texto and "importScripts" not in texto, js.name


def test_sem_style_ou_script_inline(saida):
    for pagina in _arquivos(saida, ".html"):
        texto = pagina.read_text(encoding="utf-8")
        arvore = Arvore(texto)
        assert not arvore.achar("style"), pagina
        for elemento in arvore.elementos:
            assert "style" not in elemento["attrs"], (pagina, elemento["tag"])
            assert not [a for a in elemento["attrs"] if a.startswith("on")], (pagina, elemento["tag"])
            assert not (elemento["attrs"].get("href") or "").lower().startswith("javascript:"), pagina
        for script in arvore.achar("script"):
            if script["attrs"].get("type") == "application/ld+json":  # dado, nao e executado (Ruling S-D)
                continue
            assert script["attrs"].get("src", "").startswith("/") and not Arvore.texto(script), pagina
    js = (saida / "site.js").read_text(encoding="utf-8")
    for proibido in (".style", "setAttribute('style'", 'setAttribute("style"', "cssText", "innerHTML", "outerHTML",
                     "insertAdjacentHTML", "document.write", "eval(", "new Function", "setTimeout('", 'setTimeout("'):
        assert proibido not in js, proibido


def test_paginas_usam_os_estaticos_gerados(saida):
    for pagina in _arquivos(saida, ".html"):
        arvore = Arvore(pagina.read_text(encoding="utf-8"))
        locais = [e["attrs"]["href"] for e in arvore.achar("link", rel="stylesheet")]
        locais += [e["attrs"]["src"] for e in arvore.achar("script") if "src" in e["attrs"]]
        assert locais == ["/estilo.css", "/site.js"], pagina
        for local in locais:
            assert (saida / local.lstrip("/")).is_file(), local


# --- identidade visual ---


def test_cores_e_fontes_da_identidade(saida):
    css = (saida / "estilo.css").read_text(encoding="utf-8")
    for cor in CORES:
        assert cor in css.lower(), cor
    faces = re.findall(r"@font-face\s*\{([^}]*)\}", _sem_comentarios(css))
    familias = {}
    for face in faces:
        familia = re.search(r"font-family:\s*['\"]?([^;'\"]+)", face).group(1)
        familias[familia] = face
        assert re.search(r"font-display:\s*swap", face), familia
        urls = re.findall(r"url\(\s*['\"]?([^'\")]+)", face)
        assert urls and all(u.endswith(".woff2") for u in urls), familia
        for url in urls:
            fonte = saida / url.lstrip("/")
            assert fonte.read_bytes()[:4] == b"wOF2", url
            licenca = fonte.parent / "OFL.txt"
            assert "SIL Open Font License" in licenca.read_text(encoding="utf-8"), url
    assert set(familias) == {"Manrope", "DM Sans"}


def test_movimento_so_sem_reduced_motion(saida):
    css = (saida / "estilo.css").read_text(encoding="utf-8")
    regras = _regras(css)
    animadas = 0
    for cabecalhos, declaracao in regras:
        dentro = SEM_REDUCAO in cabecalhos
        bloco = cabecalhos[-1] if cabecalhos else ""
        if bloco.startswith(("@keyframes", "@view-transition")) or bloco.startswith("::view-transition"):
            assert dentro, bloco
        propriedade = declaracao.split(":", 1)[0].strip().lower() if ":" in declaracao else ""
        if MOVIMENTO.match(propriedade):
            assert dentro, (cabecalhos, declaracao)
            animadas += 1
    assert animadas, "o site tem movimento (com prefers-reduced-motion: no-preference)"
    assert any(c[-1] == "@view-transition" and d.replace(" ", "") == "navigation:auto" for c, d in regras)
    js = (saida / "site.js").read_text(encoding="utf-8")
    assert "matchMedia('(prefers-reduced-motion: no-preference)')" in js
    assert "IntersectionObserver" in js


# --- foto da abertura (Ruling S-U) e modal Ampliar (Ruling S-W) ---


def _luminancia(rgb: tuple[float, float, float]) -> float:
    canais = [c / 255 for c in rgb]
    lineares = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canais]
    return 0.2126 * lineares[0] + 0.7152 * lineares[1] + 0.0722 * lineares[2]


def _contraste(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    claro, escuro = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (claro + 0.05) / (escuro + 0.05)


def _declaracoes(css: str, seletor: str) -> dict[str, str]:
    """propriedade -> valor das regras cujo seletor e exatamente `seletor` (sem at-rule em volta)."""
    achadas = {}
    for cabecalhos, declaracao in _regras(css):
        if cabecalhos == (seletor,) and ":" in declaracao:
            propriedade, valor = declaracao.split(":", 1)
            achadas[propriedade.strip()] = " ".join(valor.split())
    return achadas


def test_css_da_foto_e_da_camada(saida):
    css = (saida / "estilo.css").read_text(encoding="utf-8")
    foto = _declaracoes(css, ".nn-hero-com-foto")
    assert foto["background-image"] == 'url("/foto-abertura.webp")'  # local: a CSP e default-src 'self'
    assert foto["background-size"] == "cover"
    camada = _declaracoes(css, ".nn-hero-com-foto::before")
    cor = re.fullmatch(r"rgba\((\d+), (\d+), (\d+), ([0-9.]+)\)", camada["background"])
    assert cor, camada
    r, g, b, alfa = int(cor[1]), int(cor[2]), int(cor[3]), float(cor[4])
    assert (r, g, b) == (8, 8, 8)  # o #080808 da identidade
    assert 0.85 <= alfa <= 0.90 and alfa == 0.88
    # pior caso: a foto toda branca por baixo; o texto branco da abertura segue com >= 4,5:1 sobre a camada
    fundo = tuple(255 * (1 - alfa) + c * alfa for c in (r, g, b))
    assert _contraste((255, 255, 255), fundo) >= 4.5
    for seletor in (".nn-hero-intro", ".nn-hero .nn-eyebrow", ".nn-hero-com-foto .nn-hero-titulo .nn-destaque"):
        texto = _declaracoes(css, seletor).get("color")
        if texto and texto.startswith("rgba(255, 255, 255,"):
            a = float(texto.rsplit(",", 1)[1].strip(" )"))
            sobre = tuple(255 * a + c * (1 - a) for c in fundo)
            assert _contraste(sobre, fundo) >= 4.5, seletor
    # o laranja puro (#ea2e00) nao chega a 4,5:1 nem sobre a camada sem foto nenhuma por baixo: com foto, o destaque
    # do titulo da abertura e branco translúcido (medido nos pixels reais em testes/navegador)
    assert _contraste((234, 46, 0), fundo) < 4.5
    destaque = _declaracoes(css, ".nn-hero-com-foto .nn-hero-titulo .nn-destaque").get("color", "")
    assert destaque.startswith("rgba(255, 255, 255,"), destaque
    # a foto so existe por CSS: nem <img> nem style= nas paginas (test_sem_style_ou_script_inline) e movimento so sem reducao
    assert not any(c == (".nn-hero-com-foto",) and "animation" in d for c, d in _regras(css))


def test_modal_do_css_e_as_cores_da_faixa(saida):
    css = (saida / "estilo.css").read_text(encoding="utf-8")
    modal = _declaracoes(css, ".nn-modal")
    assert modal["padding"] == "0" and modal["background"] == "var(--nn-painel)"
    cheia = [(c, d) for c, d in _regras(css) if "max-width: 560px" in c[0] and c[-1] == ".nn-modal" and d.startswith("width")]
    assert cheia and cheia[0][1] == "width: 100vw"  # no celular o modal ocupa a tela toda
    assert any(c[-1] == ".nn-modal-gire" and d == "display: block" and "orientation: portrait" in c[0] for c, d in _regras(css))
    assert _declaracoes(css, ".nn-faixa-abertura")["background"] == "var(--nn-papel)"
    # a abertura do modal anima so sem reducao de movimento (test_movimento_so_sem_reduced_motion confere o resto)
    assert any(SEM_REDUCAO in c and c[-1].startswith(".nn-modal") and d.startswith("animation") for c, d in _regras(css))


def test_texto_branco_pequeno_so_sobre_o_laranja_escuro(saida):
    """Ruling S-S: #ea2e00 com texto branco da 4,3:1; aba ativa, botao pressionado e Baixar usam #c42600 (>= 4,5:1)."""
    css = (saida / "estilo.css").read_text(encoding="utf-8")
    assert _contraste((255, 255, 255), (0xEA, 0x2E, 0x00)) < 4.5 <= _contraste((255, 255, 255), (0xC4, 0x26, 0x00))
    assert re.search(r"--nn-laranja-escuro:\s*#c42600", css)
    for seletor in ('.nn .nn-menu a[aria-current="page"]', '.nn-botao[aria-pressed="true"]', ".nn .nn-baixar"):
        assert _declaracoes(css, seletor)["background"] == "var(--nn-laranja-escuro)", seletor
    grupos: dict[tuple, dict[str, str]] = {}
    for cabecalhos, declaracao in _regras(css):
        if ":" in declaracao:
            propriedade, valor = declaracao.split(":", 1)
            grupos.setdefault(cabecalhos, {})[propriedade.strip()] = " ".join(valor.split())
    vivos = ("var(--nn-laranja)", "#ea2e00")
    assert [c[-1] for c, g in grupos.items() if g.get("background") in vivos and g.get("color") == "var(--nn-branco)"] == []


def test_modal_reserva_o_espaco_da_barra_e_o_zoom_so_com_ponteiro_fino(saida):
    """Ruling S-Z: com o modal aberto a barra de rolagem some e o espaco dela fica; cursor zoom-in so com mouse."""
    css = (saida / "estilo.css").read_text(encoding="utf-8")
    aberto = _declaracoes(css, "html:has(.nn-modal[open])")
    assert aberto["overflow"] == "hidden" and aberto["scrollbar-gutter"] == "stable"
    cursores = [c for c, d in _regras(css) if d.startswith("cursor: zoom-in")]
    assert cursores and all("@media (pointer: fine)" in c[0] and c[-1] == ".nn-clicavel" for c in cursores)


def test_mapa_de_calor_avisa_a_rolagem_so_onde_ele_rola(saida):
    css = (saida / "estilo.css").read_text(encoding="utf-8")
    assert _declaracoes(css, ".nn-rolagem")["display"] == "none"
    estreito = [(c, d) for c, d in _regras(css) if c[0] == "@media (max-width: 640px)"]
    assert (("@media (max-width: 640px)", ".nn-rolagem"), "display: block") in estreito
    assert any(c[-1] == ".nn-mapa-caixa" and d.startswith("mask-image: linear-gradient(to right") for c, d in estreito)
    assert any(c[-1] == ".nn-mapa-caixa.nn-no-fim" and d == "mask-image: none" for c, d in estreito)
    assert _declaracoes(css, ".nn-mapa")["min-width"] == "560px"  # abaixo de ~640 px ele rola


# --- o desenho do site.js segue o do Python ---


def test_constantes_do_desenho_iguais_no_script(saida):
    js = (saida / "site.js").read_text(encoding="utf-8")
    for nome in ("ANO_INICIAL", "ANO_FINAL", "LARGURA_CARACTERE", "AFASTAMENTO_ROTULOS", "LARGURA_ESTREITA"):
        achado = re.search(rf"\b{nome} = ([0-9.]+)", js)
        assert achado and float(achado.group(1)) == getattr(graficos, nome), nome


def test_explorar_tem_os_ganchos_do_script(saida):
    arvore = Arvore((saida / "explorar" / "index.html").read_text(encoding="utf-8"))
    cartao = arvore.achar("article", id="explorar-grafico")[0]["attrs"]
    dados = DadosSite.carregar(Caminhos(raiz=RAIZ))
    faixas = json.loads(cartao["data-governos"])
    assert faixas == json.loads(graficos.faixas_em_json(dados.governos))
    assert faixas and all(isinstance(n, str) and i < f and isinstance(x, bool) for n, i, f, x in faixas)
    assert [i for _, i, _, _ in faixas] == sorted(i for _, i, _, _ in faixas)
    assert cartao["data-sem-periodo"] and cartao["data-erro"] and cartao["data-tabela"]
    zoom = arvore.achar("div", id="explorar-zoom")[0]["attrs"]
    assert "hidden" in zoom  # sem JavaScript o painel de zoom nao aparece; o site.js monta os controles
    for texto in ("data-de", "data-ate", "data-inicio", "data-fim", "data-ampliar", "data-todo", "aria-label"):
        assert zoom[texto], texto
    for id_ in ("sel-expl-terr", "sel-expl-terr2"):
        assert all(o["attrs"].get("data-etiqueta") for o in _opcoes(arvore, id_) if o["attrs"]["value"])


def _opcoes(arvore: Arvore, id_select: str) -> list[dict]:
    """As <option> do <select> de id dado, na ordem."""
    i = arvore.elementos.index(arvore.achar("select", id=id_select)[0])
    opcoes = []
    for elemento in arvore.elementos[i + 1:]:
        if elemento["tag"] != "option":
            break
        opcoes.append(elemento)
    return opcoes


@pytest.mark.skipif(shutil.which("node") is None, reason="sem Node.js para rodar o site.js")
def test_numeros_do_script_iguais_aos_do_python(saida):
    casos = [(43.25, 1), (2.5, 0), (3.5, 0), (-0.04, 1), (1234567.891, 2), (0.125, 2), (2.675, 2), (25000, 0),
             (0.7125, 3), (99.95, 1), (-12.25, 1), (1e-9, 0), (186521.5, 0)]
    programa = (
        "const NN = require(process.argv[1]);"
        f"const casos = {json.dumps(casos)};"
        "console.log(JSON.stringify(casos.map(([v, c]) => NN.numero(v, c))));"
    )
    feito = subprocess.run(["node", "-e", programa, str(saida / "site.js")], capture_output=True, text=True, check=True)
    assert json.loads(feito.stdout) == [numero(v, c) for v, c in casos]
