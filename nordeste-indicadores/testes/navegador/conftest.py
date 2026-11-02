"""Apoio dos testes de navegador: o site gerado uma vez, servido por HTTP local, e o Chromium do Playwright.

Marcador `navegador`: `python -m pytest -m navegador`. O Chromium vem de `PLAYWRIGHT_CHROMIUM` ou, se existir, de
/opt/pw-browsers/chromium. O navegador vale por modulo (nao por sessao): a API sincrona do Playwright nao convive com
outra aberta na mesma thread, e testes/site/test_imagens.py abre a sua.
"""

import os
import threading
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from nordeste.caminhos import Caminhos
from nordeste.site.gerar import gerar_site

RAIZ = Path(__file__).resolve().parents[2]
CHROMIUM_DO_AMBIENTE = Path("/opt/pw-browsers/chromium")


class _Servidor(SimpleHTTPRequestHandler):
    """Serve o site com a Content-Security-Policy do proprio .htaccess: violacao de CSP vira erro de console."""

    csp = ""

    def log_message(self, *_args) -> None:
        pass

    def end_headers(self) -> None:
        if self.csp:
            self.send_header("Content-Security-Policy", self.csp)
        super().end_headers()


def _csp_do_htaccess(site: Path) -> str:
    linha = next(l for l in (site / ".htaccess").read_text(encoding="utf-8").splitlines() if "Content-Security-Policy" in l)
    return linha.split('"')[1]


@pytest.fixture(scope="session")
def site_gerado(tmp_path_factory) -> Path:
    """O site completo (sem as imagens PNG, que test_imagens.py cobre), gerado uma vez da base e dos metadados reais."""
    saida = tmp_path_factory.mktemp("site") / "saida"
    gerar_site(Caminhos(raiz=RAIZ), saida, imagens=False)
    return saida


@pytest.fixture(scope="session")
def endereco(site_gerado) -> str:
    """O site servido numa porta livre: os caminhos absolutos (/estilo.css, /site.js) so funcionam servidos."""
    manipulador = type("Manipulador", (_Servidor,), {"csp": _csp_do_htaccess(site_gerado)})
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), partial(manipulador, directory=str(site_gerado)))
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{servidor.server_port}"
    servidor.shutdown()
    servidor.server_close()


@pytest.fixture(scope="session")
def rotas(site_gerado) -> list[str]:
    """Rota de cada pagina gerada (as seis do menu e cada card), em ordem estavel."""
    return sorted(
        "/" if p.parent == site_gerado else f"/{p.parent.relative_to(site_gerado).as_posix()}/"
        for p in site_gerado.rglob("index.html")
    )


@pytest.fixture(scope="module")
def navegador():
    playwright = pytest.importorskip("playwright.sync_api")
    if "PLAYWRIGHT_CHROMIUM" not in os.environ and CHROMIUM_DO_AMBIENTE.exists():
        os.environ["PLAYWRIGHT_CHROMIUM"] = str(CHROMIUM_DO_AMBIENTE)
    with playwright.sync_playwright() as p:
        aberto = p.chromium.launch(executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM") or None)
        yield aberto
        aberto.close()


@pytest.fixture
def abrir(navegador, endereco):
    """`with abrir("/explorar/", largura=390) as pagina:` abre a rota num contexto novo e o fecha ao sair.

    Erros da pagina (excecao de script, resposta 4xx ou 5xx, erro no console) vao para `pagina.erros`. Opcoes extras
    (`java_script_enabled`, `reduced_motion`, `color_scheme`) vao ao contexto do Playwright.
    """

    @contextmanager
    def _abrir(rota: str = "/", largura: int = 1280, altura: int = 800, **opcoes):
        contexto = navegador.new_context(viewport={"width": largura, "height": altura}, **opcoes)
        try:
            pagina = contexto.new_page()
            erros: list[str] = []
            pagina.on("pageerror", lambda e: erros.append(str(e)))
            pagina.on("response", lambda r: erros.append(f"{r.status} {r.url}") if r.status >= 400 and "favicon" not in r.url else None)
            pagina.on("console", lambda m: erros.append(m.text) if m.type == "error" and "404" not in m.text else None)
            pagina.goto(endereco + rota, wait_until="networkidle")
            pagina.erros = erros
            yield pagina
        finally:
            contexto.close()

    return _abrir
