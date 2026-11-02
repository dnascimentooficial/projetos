"""Renderizacao das imagens do site (OpenGraph e cards) em PNG, com o Chromium sem tela pelo Playwright.

O Playwright e opcional (extra `site`) e so e importado ao renderizar: gerar o site sem imagens nao depende dele.
O navegador vem de `PLAYWRIGHT_CHROMIUM`, se definida; do contrario, o que o `playwright install` instalou.
"""

import os
import posixpath
import threading
from dataclasses import dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VARIAVEL_DO_NAVEGADOR = "PLAYWRIGHT_CHROMIUM"


class ErroImagens(OSError):
    """Nao foi possivel renderizar as imagens: Playwright ausente ou Chromium que nao abre."""


@dataclass(frozen=True)
class AlvoImagem:
    html: Path  # pagina a fotografar; usa /estilo.css e /fontes/... da raiz servida
    png: Path
    largura: int  # tamanho da janela e da imagem, em pixels
    altura: int


class _Silencioso(SimpleHTTPRequestHandler):
    def log_message(self, *_args) -> None:  # sem eco de cada GET no terminal
        pass


def _raiz_comum(alvos: list[AlvoImagem]) -> Path:
    return Path(os.path.commonpath([str(a.html.resolve().parent) for a in alvos]))


def renderizar(alvos: list[AlvoImagem], *, raiz: Path | None = None) -> None:
    """Grava o PNG de cada alvo, do tamanho pedido.

    As paginas sao servidas por HTTP local a partir de `raiz` (padrao: a pasta comum dos HTML), para que os caminhos
    absolutos do site (`/estilo.css`, `/fontes/...`) funcionem; nada sai da maquina. O movimento fica desligado e o
    tema e o claro, para a imagem nao depender do navegador de quem gera.
    """
    if not alvos:
        return
    try:
        from playwright.sync_api import Error as ErroPlaywright
        from playwright.sync_api import sync_playwright
    except ImportError as erro:
        raise ErroImagens("Falta o Playwright para gerar as imagens: python -m pip install '.[site]' (ou use --sem-imagens).") from erro

    raiz = (raiz or _raiz_comum(alvos)).resolve()
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Silencioso, directory=str(raiz)))
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as playwright:
            try:
                navegador = playwright.chromium.launch(executable_path=os.environ.get(VARIAVEL_DO_NAVEGADOR) or None)
            except ErroPlaywright as erro:
                raise ErroImagens(f"O Chromium não abriu (defina {VARIAVEL_DO_NAVEGADOR} ou rode 'playwright install chromium'): {erro}") from erro
            try:
                for alvo in alvos:
                    _fotografar(navegador, alvo, f"http://127.0.0.1:{servidor.server_port}/{_rota(alvo.html, raiz)}")
            finally:
                navegador.close()
    finally:
        servidor.shutdown()
        servidor.server_close()


def _rota(html: Path, raiz: Path) -> str:
    return posixpath.join(*html.resolve().relative_to(raiz).parts)


def _fotografar(navegador, alvo: AlvoImagem, url: str) -> None:
    from playwright.sync_api import Error as ErroPlaywright

    contexto = navegador.new_context(
        viewport={"width": alvo.largura, "height": alvo.altura}, reduced_motion="reduce", color_scheme="light",
    )
    try:
        pagina = contexto.new_page()
        faltas: list[str] = []
        pagina.on("response", lambda r: faltas.append(f"{r.status} {r.url}") if r.status >= 400 else None)
        try:
            pagina.goto(url, wait_until="networkidle")
            pagina.evaluate("document.fonts.ready.then(() => true)")  # o PNG sai depois das fontes locais, nunca com a de reserva
            if faltas:  # estilo ou fonte que nao carregou geraria uma imagem sem a identidade, e sem aviso
                raise ErroImagens(f"A página de {alvo.png.name} pediu o que não existe: {', '.join(faltas)}.")
            alvo.png.parent.mkdir(parents=True, exist_ok=True)
            pagina.screenshot(path=str(alvo.png), clip={"x": 0, "y": 0, "width": alvo.largura, "height": alvo.altura})
        except ErroPlaywright as erro:  # tempo esgotado, navegador que fechou: mensagem curta no CLI, sem traceback
            raise ErroImagens(f"Não consegui gerar {alvo.png.name}: {erro}") from erro
    finally:
        contexto.close()
