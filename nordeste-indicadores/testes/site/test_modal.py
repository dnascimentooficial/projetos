"""Modal "Ampliar" do Inicio no navegador: abre, mostra o grafico grande, fecha de tres jeitos, devolve o foco e cabe na
tela do celular. Marcador `navegador`: `python -m pytest -m navegador testes/site/test_modal.py`."""

import os
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from nordeste.caminhos import Caminhos
from nordeste.site.conteudo import calcular_destaques, carregar_conteudo, preencher
from nordeste.site.dados import DadosSite
from nordeste.site.gerar import gerar_site

from auxiliares import RAIZ

pytestmark = pytest.mark.navegador
CHROMIUM_DO_AMBIENTE = Path("/opt/pw-browsers/chromium")


class _Silencioso(SimpleHTTPRequestHandler):
    def log_message(self, *_args) -> None:
        pass


@pytest.fixture(scope="module")
def endereco(tmp_path_factory):
    """O site gerado, servido por HTTP local: os caminhos absolutos (/estilo.css, /site.js) so funcionam assim."""
    saida = tmp_path_factory.mktemp("site") / "saida"
    gerar_site(Caminhos(raiz=RAIZ), saida, imagens=False)
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Silencioso, directory=str(saida)))
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{servidor.server_port}"
    servidor.shutdown()
    servidor.server_close()


@pytest.fixture(scope="module")
def navegador():
    playwright = pytest.importorskip("playwright.sync_api")
    if "PLAYWRIGHT_CHROMIUM" not in os.environ and CHROMIUM_DO_AMBIENTE.exists():
        os.environ["PLAYWRIGHT_CHROMIUM"] = str(CHROMIUM_DO_AMBIENTE)
    with playwright.sync_playwright() as p:
        aberto = p.chromium.launch(executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM") or None)
        yield aberto
        aberto.close()


@pytest.fixture(scope="module")
def primeira_frase() -> str:
    conteudo = carregar_conteudo(RAIZ / "metadados" / "site")
    destaques = calcular_destaques(DadosSite.carregar(Caminhos(raiz=RAIZ)), conteudo)
    return preencher(conteudo.perguntas[0]["frase_feita"], destaques)


def _abrir(navegador, endereco, largura=1280, altura=800, **opcoes):
    contexto = navegador.new_context(viewport={"width": largura, "height": altura}, **opcoes)
    pagina = contexto.new_page()
    erros: list[str] = []
    pagina.on("pageerror", lambda e: erros.append(str(e)))
    pagina.on(
        "response", lambda r: erros.append(f"{r.status} {r.url}") if r.status >= 400 and "favicon" not in r.url else None
    )
    pagina.on("console", lambda m: erros.append(m.text) if m.type == "error" and "404" not in m.text else None)
    pagina.goto(endereco + "/", wait_until="networkidle")
    pagina.erros = erros
    return contexto, pagina


def _botao(pagina, indice=0):
    return pagina.locator("button.nn-ampliar").nth(indice)


def test_abre_pelo_botao_com_o_grafico_grande_e_o_titulo(navegador, endereco, primeira_frase):
    contexto, pagina = _abrir(navegador, endereco)
    try:
        assert pagina.locator("dialog.nn-modal").evaluate("d => d.open") is False
        botao = _botao(pagina)
        assert botao.is_visible() and botao.get_attribute("hidden") is None  # o JS tirou o hidden
        botao.click()
        assert pagina.locator("dialog.nn-modal").evaluate("d => d.open") is True
        assert pagina.locator("dialog svg[viewBox='0 0 1100 520']").count() == 1
        assert pagina.locator("dialog h2.nn-modal-titulo").inner_text().strip() == primeira_frase
        rotulado = pagina.locator("dialog").get_attribute("aria-labelledby")
        assert pagina.locator(f"#{rotulado}").inner_text().strip() == primeira_frase
        for classe in (".nn-legenda", ".nn-fonte", ".nn-atualizacao"):
            assert pagina.locator(f"dialog {classe}").first.is_visible(), classe
        grande = pagina.locator("dialog svg").bounding_box()
        assert grande["width"] > 800  # o grafico ocupa o modal, bem maior que os 720 px da pagina
        assert pagina.erros == []
    finally:
        contexto.close()


def test_esc_fecha_e_o_foco_volta_ao_botao_que_abriu(navegador, endereco):
    contexto, pagina = _abrir(navegador, endereco)
    try:
        botao = _botao(pagina, 2)
        botao.focus()
        botao.press("Enter")  # pelo teclado
        assert pagina.locator("dialog.nn-modal").evaluate("d => d.open") is True
        assert pagina.evaluate("document.activeElement.closest('dialog') !== null")  # o foco entrou no modal
        pagina.keyboard.press("Escape")
        assert pagina.locator("dialog.nn-modal").evaluate("d => d.open") is False
        assert pagina.evaluate("document.querySelectorAll('button.nn-ampliar')[2] === document.activeElement")
        assert pagina.locator("dialog .nn-ampliado-conteudo").count() == 0  # o clone saiu
    finally:
        contexto.close()


def test_fecha_pelo_x_e_por_clique_fora_e_reabre_em_outro_grafico(navegador, endereco):
    contexto, pagina = _abrir(navegador, endereco)
    try:
        _botao(pagina, 1).click()
        pagina.locator("dialog button.nn-modal-fechar").click()
        assert pagina.locator("dialog.nn-modal").evaluate("d => d.open") is False
        assert pagina.evaluate("document.querySelectorAll('button.nn-ampliar')[1] === document.activeElement")
        _botao(pagina, 0).click()
        assert pagina.locator("dialog.nn-modal").evaluate("d => d.open") is True
        pagina.mouse.click(4, 4)  # fora da caixa: no fundo escurecido
        assert pagina.locator("dialog.nn-modal").evaluate("d => d.open") is False
        _botao(pagina, 3).click()
        assert pagina.locator("dialog svg").count() == 1  # nunca dois graficos no modal
        pagina.locator("dialog .nn-modal-corpo").click(position={"x": 5, "y": 5})  # dentro da caixa: nao fecha
        assert pagina.locator("dialog.nn-modal").evaluate("d => d.open") is True
    finally:
        contexto.close()


def test_o_proprio_grafico_tambem_abre_o_modal_com_o_mouse(navegador, endereco):
    contexto, pagina = _abrir(navegador, endereco)
    try:
        grafico = pagina.locator("#resumo .nn-graf-largo svg").first
        grafico.scroll_into_view_if_needed()
        assert pagina.locator("#resumo .nn-graf").first.evaluate("e => getComputedStyle(e).cursor") == "zoom-in"
        caixa = grafico.bounding_box()
        pagina.mouse.click(caixa["x"] + caixa["width"] / 2, caixa["y"] + caixa["height"] / 2)
        assert pagina.locator("dialog.nn-modal").evaluate("d => d.open") is True
        assert pagina.locator("dialog svg[viewBox='0 0 1100 520']").count() == 1
    finally:
        contexto.close()


def test_a_dica_de_valor_funciona_no_grafico_grande(navegador, endereco):
    contexto, pagina = _abrir(navegador, endereco)
    try:
        _botao(pagina).click()
        ponto = pagina.locator("dialog svg g.nn-linha-ne circle").nth(3).bounding_box()
        pagina.mouse.move(ponto["x"] + ponto["width"] / 2, ponto["y"] + ponto["height"] / 2)
        assert pagina.locator("dialog svg .nn-dica").count() == 1
        assert pagina.locator("dialog svg .nn-dica-valor").first.text_content().strip() != ""
    finally:
        contexto.close()


def test_no_celular_o_modal_ocupa_a_tela_e_nao_estoura(navegador, endereco):
    contexto, pagina = _abrir(navegador, endereco, 390, 844, has_touch=True, is_mobile=True, reduced_motion="reduce")
    try:
        # toque no grafico mostra o valor (nao abre o modal): so o botao abre no celular
        grafico = pagina.locator("#resumo .nn-graf-estreito svg").first
        grafico.scroll_into_view_if_needed()
        caixa = grafico.bounding_box()
        pagina.touchscreen.tap(caixa["x"] + caixa["width"] / 2, caixa["y"] + caixa["height"] / 2)
        assert pagina.locator("dialog.nn-modal").evaluate("d => d.open") is False
        botao = _botao(pagina)
        botao.scroll_into_view_if_needed()
        botao.tap()
        assert pagina.locator("dialog.nn-modal").evaluate("d => d.open") is True
        caixa_modal = pagina.locator("dialog.nn-modal").bounding_box()
        assert (caixa_modal["x"], caixa_modal["y"], caixa_modal["width"], caixa_modal["height"]) == (0, 0, 390, 844)
        assert pagina.locator("dialog p.nn-modal-gire").is_visible()  # retrato: pede para girar
        assert pagina.evaluate("document.documentElement.scrollWidth") <= 390
        assert pagina.locator("dialog.nn-modal").evaluate("d => d.scrollWidth <= d.clientWidth")
        assert pagina.locator("dialog svg").bounding_box()["width"] <= 390
        pagina.locator("dialog button.nn-modal-fechar").tap()
        assert pagina.locator("dialog.nn-modal").evaluate("d => d.open") is False
    finally:
        contexto.close()


def test_em_paisagem_no_celular_o_aviso_de_girar_some(navegador, endereco):
    contexto, pagina = _abrir(navegador, endereco, 844, 390, has_touch=True, is_mobile=True, reduced_motion="reduce")
    try:
        botao = _botao(pagina)
        botao.scroll_into_view_if_needed()
        botao.tap()
        assert pagina.locator("dialog.nn-modal").evaluate("d => d.open") is True
        assert not pagina.locator("dialog p.nn-modal-gire").is_visible()
        caixa_modal = pagina.locator("dialog.nn-modal").bounding_box()
        assert (caixa_modal["width"], caixa_modal["height"]) == (844, 390)  # tela cheia tambem em paisagem
        assert pagina.evaluate("document.documentElement.scrollWidth") <= 844
    finally:
        contexto.close()


def test_sem_javascript_os_botoes_ficam_escondidos(navegador, endereco):
    contexto, pagina = _abrir(navegador, endereco, java_script_enabled=False)
    try:
        assert pagina.locator("button.nn-ampliar").count() > 6
        assert pagina.locator("button.nn-ampliar:visible").count() == 0
        assert pagina.locator("#resumo .nn-graf-largo svg").first.is_visible()  # o grafico da pagina segue la
    finally:
        contexto.close()
