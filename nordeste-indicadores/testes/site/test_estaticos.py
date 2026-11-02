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
