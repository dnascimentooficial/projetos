"""O site gerado, aberto no Chromium: acessibilidade (axe-core), largura no celular, sem JavaScript, movimento reduzido,
peso da primeira tela, o Explorar e o desenho que o site.js refaz no navegador.

Marcador `navegador`: `python -m pytest -m navegador testes/navegador`. As paginas sao servidas com a
Content-Security-Policy do .htaccess, entao script ou estilo inline apareceria como erro de console.
"""

import io
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from nordeste.caminhos import Caminhos
from nordeste.site.conteudo import carregar_conteudo
from nordeste.site.dados import DadosSite
from nordeste.site.explorar import INDICADORES_EXPLORAR, TERRITORIOS
from nordeste.site.gerar import vista_explorar_em_html

pytestmark = pytest.mark.navegador
RAIZ = Path(__file__).resolve().parents[2]
AXE = (Path(__file__).parent / "axe.min.js").read_text(encoding="utf-8")
GRAVES = ("serious", "critical")
CELULAR, DESKTOP = 390, 1280
LIMITE_DA_INICIAL = 500_000  # bytes, sem a foto da abertura


def _violacoes_do_axe(pagina) -> list[str]:
    """`regra (impacto): alvo, ...` de cada violacao grave da pagina aberta (axe-core, todas as regras padrao)."""
    pagina.evaluate(AXE)  # evaluate nao esta sujeito a CSP; o script tag estaria
    achadas = pagina.evaluate("axe.run(document).then(r => r.violations)")
    return [
        f"{v['id']} ({v['impact']}): " + ", ".join(" ".join(n["target"][0:1]) for n in v["nodes"][:4])
        for v in achadas if v["impact"] in GRAVES
    ]


# --- acessibilidade ---


@pytest.mark.parametrize("esquema", ["light", "dark"])
def test_axe_sem_violacao_grave(abrir, rotas, esquema):
    graves = {}
    for rota in rotas:
        with abrir(rota, color_scheme=esquema) as pagina:
            achadas = _violacoes_do_axe(pagina)
            if achadas:
                graves[rota] = achadas
    assert graves == {}


def test_axe_com_o_modal_aberto_e_com_o_explorar_trocado(abrir):
    with abrir("/") as pagina:
        pagina.locator("button.nn-ampliar").first.click()
        assert pagina.locator("dialog.nn-modal").evaluate("d => d.open")
        # a entrada do modal acabou: o contraste vale o do estado final, nao o de um quadro da animacao
        pagina.wait_for_function(
            "() => document.querySelector('dialog.nn-modal').getAnimations({ subtree: true }).every((a) => a.playState === 'finished')"
        )
        assert _violacoes_do_axe(pagina) == []
    with abrir("/explorar/") as pagina:
        pagina.select_option("#sel-expl-ind", "gini")
        pagina.select_option("#sel-expl-terr2", "BR")
        pagina.wait_for_function("() => document.getElementById('explorar-titulo').textContent.includes('×')")
        assert _violacoes_do_axe(pagina) == []


# --- largura no celular e no desktop (Foco 3) ---

_ESTOUROS = """() => {
  const largura = window.innerWidth;
  const fora = [];
  for (const e of document.body.querySelectorAll('*')) {
    const caixa = e.getBoundingClientRect();
    if (caixa.width === 0 || caixa.right <= largura + 1) continue;
    let contido = false;  // dentro de uma caixa que rola ou corta, o que passa dela nao alarga a pagina
    for (let p = e.parentElement; p && p !== document.body; p = p.parentElement) {
      if (getComputedStyle(p).overflowX !== 'visible') { contido = true; break; }
    }
    if (!contido) fora.push(`${e.tagName.toLowerCase()}${e.id ? '#' + e.id : ''}.${e.className && e.className.baseVal === undefined ? e.className : ''} ate ${Math.round(caixa.right)}`);
  }
  return { largura, rolagem: document.documentElement.scrollWidth, fora: fora.slice(0, 6) };
}"""


def _estouro(pagina) -> dict:
    medidas = pagina.evaluate(_ESTOUROS)
    return {} if medidas["rolagem"] <= medidas["largura"] and not medidas["fora"] else medidas


@pytest.mark.parametrize("largura", [CELULAR, DESKTOP])
def test_sem_estouro_de_largura(abrir, rotas, largura):
    estourou = {}
    for rota in rotas:  # as seis paginas e cada card, inclusive /cards/renda_rs/ (R$ 2.554)
        with abrir(rota, largura=largura) as pagina:
            if medidas := _estouro(pagina):
                estourou[rota] = medidas
            if rota == "/estados/":  # cada vista do seletor, com os nomes e valores mais longos do ranking
                for opcao in pagina.locator("#sel-estado-ind option").evaluate_all("os => os.map(o => o.value)"):
                    pagina.select_option("#sel-estado-ind", opcao)
                    if medidas := _estouro(pagina):
                        estourou[f"{rota}?indicador={opcao}"] = medidas
    assert estourou == {}


@pytest.mark.parametrize("largura", [CELULAR, DESKTOP])
@pytest.mark.parametrize(
    "indicador, comparar",
    [("pib_pc", ""), ("renda", ""), ("renda", "CO"), ("matric", "SE_UF"), ("pop", "CO")],
)
def test_explorar_com_brasil_fora_do_nordeste_cabe_na_largura(abrir, largura, indicador, comparar):
    with abrir("/explorar/", largura=largura) as pagina:
        pagina.select_option("#sel-expl-ind", indicador)
        pagina.select_option("#sel-expl-terr", "BR_FORA_NE")
        if comparar:
            pagina.select_option("#sel-expl-terr2", comparar)
        pagina.wait_for_function("() => document.getElementById('explorar-titulo').textContent.includes('Brasil fora do Nordeste')")
        assert pagina.locator("#explorar-vista svg:visible").count() == 1
        assert _estouro(pagina) == {}
        pagina.locator("#explorar-vista svg:visible").hover(position={"x": largura / 2, "y": 60})  # a dica de valor tambem
        assert _estouro(pagina) == {}


# --- sem JavaScript, movimento reduzido e peso ---


def test_sem_javascript_mostra_numeros_e_graficos(abrir, relatorio_site):
    with abrir("/", java_script_enabled=False) as pagina:
        lide = pagina.locator("#resumo .nn-frase").first.inner_text()
        assert re.search(r"\d", lide) and "{" not in lide and "}" not in lide  # preenchido pela base, nunca o marcador
        assert pagina.locator("#resumo .nn-graf-largo svg").first.is_visible()
        assert pagina.locator("svg").count() >= 6
        # a faixa de numeros depende da condicao abertura_numeros na base viva: os dois estados sao corretos
        if "abertura_numeros" in relatorio_site.fechos_suprimidos:
            assert pagina.locator(".nn-numero-valor").count() == 0  # suprimida: sai inteira, sem numero solto
        else:
            assert pagina.locator(".nn-numero-valor").count() == 3 and pagina.locator(".nn-numero-valor:visible").count() == 3
        assert re.search(r"\d", pagina.locator(".nn-hero-intro").first.inner_text())  # o 1o paragrafo cita 2000 e nao tem condicao


_ANIMADOS = """() => {
  const achados = [];
  for (const e of document.querySelectorAll('*')) {
    for (const pseudo of [null, '::before', '::after']) {
      const estilo = getComputedStyle(e, pseudo);
      const duracoes = estilo.transitionDuration.split(',').map((d) => parseFloat(d));
      if (estilo.animationName !== 'none' || duracoes.some((d) => d > 0)) {
        achados.push(`${e.tagName.toLowerCase()}.${e.getAttribute('class') || ''}${pseudo || ''}`);
      }
    }
  }
  return achados;
}"""


def test_reduced_motion_sem_animacao(abrir, rotas):
    animados = {}
    for rota in rotas:
        with abrir(rota, reduced_motion="reduce") as pagina:
            if achados := pagina.evaluate(_ANIMADOS):
                animados[rota] = achados[:5]
    with abrir("/", reduced_motion="reduce") as pagina:  # o modal tem entrada animada: tambem sem animacao
        pagina.locator("button.nn-ampliar").first.click()
        assert pagina.evaluate(_ANIMADOS) == []
    assert animados == {}


def test_o_teste_de_movimento_enxerga_animacao_quando_ela_existe(abrir):
    with abrir("/", reduced_motion="no-preference") as pagina:  # controle: sem preferencia, a abertura anima
        assert any(a.startswith("span.") for a in pagina.evaluate(_ANIMADOS))


def test_peso_da_inicial(abrir):
    with abrir("/") as pagina:
        recursos = pagina.evaluate(
            """() => [performance.getEntriesByType('navigation')[0], ...performance.getEntriesByType('resource')]
                 .map((r) => ({ nome: r.name, bytes: r.transferSize }))"""
        )
    sem_a_foto = [r for r in recursos if "foto-abertura" not in r["nome"]]
    assert len(sem_a_foto) >= 5  # o HTML, o estilo, o script e as duas fontes
    assert all(r["bytes"] > 0 for r in sem_a_foto), sem_a_foto
    assert sum(r["bytes"] for r in sem_a_foto) <= LIMITE_DA_INICIAL, sorted(sem_a_foto, key=lambda r: -r["bytes"])[:3]


# --- abertura com foto: a foto aparece e o texto segue legivel sobre os pixels reais do fundo ---

_TEXTOS_DA_ABERTURA = """() => {
  const hero = document.querySelector('#topo');
  const alvos = [];
  for (const el of hero.querySelectorAll('.nn-eyebrow, .nn-hero-titulo > span, .nn-hero-intro')) {
    const intervalo = document.createRange();
    intervalo.selectNodeContents(el);
    alvos.push({
      nome: el.className || el.tagName.toLowerCase(),
      cor: getComputedStyle(el).color,
      caixas: [...intervalo.getClientRects()].map((c) => ({ x: c.left, y: c.top, w: c.width, h: c.height })),
    });
  }
  const c = hero.getBoundingClientRect();
  return { hero: { x: c.left, y: c.top, w: c.width, h: c.height }, alvos };
}"""
_LIMITE_DO_CONTRASTE = 4.5


def _luminancia_relativa(rgb: np.ndarray) -> np.ndarray:
    c = rgb / 255.0
    linear = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return linear @ np.array([0.2126, 0.7152, 0.0722])


def _contrastes(texto: np.ndarray, fundo: np.ndarray) -> np.ndarray:
    a, b = _luminancia_relativa(texto), _luminancia_relativa(fundo)
    return (np.maximum(a, b) + 0.05) / (np.minimum(a, b) + 0.05)


@pytest.mark.parametrize("largura", [CELULAR, 560, 561, 768, 900, 901, DESKTOP])  # os dois lados dos pontos de quebra do degradê (560 e 900 px)
def test_abertura_com_foto_aparece_e_o_texto_passa_de_4_5_sobre_os_pixels_do_fundo(abrir, largura):
    with abrir("/", largura=largura, altura=900, reduced_motion="reduce") as pagina:
        assert "nn-hero-com-foto" in pagina.locator("#topo").get_attribute("class").split()
        foto = pagina.evaluate(
            """async () => {
              const url = getComputedStyle(document.querySelector('#topo')).backgroundImage.match(/url\\("?([^")]+)"?\\)/)[1];
              const imagem = new Image();
              imagem.src = url;
              await imagem.decode();
              return { url, largura: imagem.naturalWidth, altura: imagem.naturalHeight };
            }"""
        )
        assert foto["url"].endswith("/foto-abertura.webp") and (foto["largura"], foto["altura"]) == (1024, 768)
        medidas = pagina.evaluate(_TEXTOS_DA_ABERTURA)
        pagina.evaluate("() => document.querySelectorAll('#topo > *').forEach((e) => { e.style.visibility = 'hidden'; })")
        caixa = medidas["hero"]
        recorte = {"x": 0, "y": caixa["y"], "width": largura, "height": caixa["h"]}
        fundo = np.array(Image.open(io.BytesIO(pagina.screenshot(clip=recorte))).convert("RGB"), dtype=float)

    # a foto esta la, sob a camada: bem mais variada que o preto liso (#080808) que a abertura tem sem foto
    x0, x1 = int(caixa["x"]) + 24, int(caixa["x"] + caixa["w"]) - 24
    miolo = fundo[24:-24, x0:x1].reshape(-1, 3)
    assert (np.abs(miolo - 8).max(axis=1) > 3).mean() > 0.5, "o fundo da abertura esta liso: a foto nao aparece"
    assert miolo.max() > 40  # a parte clara da foto (a espuma, o mar) atravessa o degradê

    reprovados, piores = [], {}
    for n, alvo in enumerate(medidas["alvos"]):
        canais = [float(v) for v in re.findall(r"[\d.]+", alvo["cor"])]
        cor, alfa = np.array(canais[:3]), canais[3] if len(canais) > 3 else 1.0
        assert alvo["caixas"], alvo["nome"]
        pior = 99.0
        for c in alvo["caixas"]:  # cada linha de texto, sobre os pixels que de fato ficam atras dela
            xa, xb = max(0, int(c["x"])), min(largura, int(np.ceil(c["x"] + c["w"])))
            ya, yb = max(0, int(c["y"] - caixa["y"])), min(fundo.shape[0], int(np.ceil(c["y"] + c["h"] - caixa["y"])))
            atras = fundo[ya:yb, xa:xb].reshape(-1, 3)
            pior = min(pior, _contrastes(alfa * cor + (1 - alfa) * atras, atras).min())
        piores[f"{n}:{alvo['nome']}"] = round(float(pior), 2)
        if pior < _LIMITE_DO_CONTRASTE:
            reprovados.append(f"{alvo['nome']} ({alvo['cor']}): {pior:.2f}:1")
    assert len(piores) >= 5  # o selo, as linhas do titulo (com o destaque) e o paragrafo
    assert reprovados == [], piores


# --- Explorar ---


def _pontos_do_destaque(pagina) -> list[list]:
    return pagina.evaluate(
        """() => {
          const linhas = JSON.parse(document.querySelector('#explorar-vista .nn-graf-largo svg').getAttribute('data-pontos'));
          return linhas.find((l) => l.destaque).pontos;
        }"""
    )


def test_explorar_troca_indicador_e_territorio(abrir, site_gerado):
    with abrir("/explorar/") as pagina:
        titulo_antes = pagina.locator("#explorar-titulo").inner_text()
        svg_antes = pagina.locator("#explorar-vista .nn-graf-largo svg").evaluate("s => s.outerHTML")
        assert "PIB per capita" in titulo_antes and "Nordeste" in titulo_antes
        pagina.select_option("#sel-expl-ind", "gini")
        pagina.select_option("#sel-expl-terr", "BA")
        pagina.wait_for_function("() => document.getElementById('explorar-titulo').textContent.startsWith('Índice de Gini: Bahia')")
        titulo = pagina.locator("#explorar-titulo").inner_text()
        assert titulo != titulo_antes and "Gini" in titulo and "Bahia" in titulo and "PIB" not in titulo
        svg = pagina.locator("#explorar-vista .nn-graf-largo svg").evaluate("s => s.outerHTML")
        assert svg != svg_antes
        esperado = json.loads((site_gerado / "explorar" / "dados" / "gini.json").read_text(encoding="utf-8"))["BA"]
        assert esperado and _pontos_do_destaque(pagina) == esperado  # o desenho vem dos pontos da base, sem retoque
        assert pagina.url.endswith("?indicador=gini&territorio=BA")  # o endereco guarda a escolha


# --- cards ---


def test_card_tem_link_de_download(abrir, rotas):
    cards = [r for r in rotas if r.startswith("/cards/") and r != "/cards/"]
    assert "/cards/renda_rs/" in cards
    for rota in cards:
        with abrir(rota) as pagina:
            link = pagina.locator("a.nn-baixar")
            assert link.count() == 1 and link.is_visible(), rota
            assert link.get_attribute("href") == rota.rstrip("/") + ".png", rota
            assert link.get_attribute("download") is not None, rota
            assert link.inner_text().strip(), rota


# --- o desenho que o site.js refaz no navegador e o do Python (Ruling S-T) ---


def _arvore(svg: str) -> tuple:
    """O SVG como arvore comparavel, sem data-* e sem os ids em si: (tag, atributos ordenados, texto, filhos, resto).

    Os ids do Python vem de um hash e os do navegador de um contador, entao cada id vira a ordem em que aparece e as
    referencias a ele (aria-labelledby, url(#...)) apontam para essa ordem: quem aponta para quem continua conferido.
    """
    raiz = ET.fromstring(svg)
    ids = {no.attrib["id"]: f"#{i}" for i, no in enumerate(n for n in raiz.iter() if "id" in n.attrib)}
    trocar = re.compile("|".join(map(re.escape, ids)) or r"(?!)")

    def ler(no):
        atributos = tuple(sorted(
            (chave, trocar.sub(lambda m: ids[m[0]], valor))
            for chave, valor in no.attrib.items() if chave != "id" and not chave.startswith("data-")
        ))
        return (no.tag.split("}")[-1], atributos, (no.text or "").strip(), tuple(ler(f) for f in no), (no.tail or "").strip())

    return ler(raiz)


def _primeira_diferenca(a: tuple, b: tuple, caminho: str = "svg") -> str | None:
    if a[:3] != b[:3] or a[4] != b[4]:
        return f"{caminho}: {a[:3]} != {b[:3]}"
    if len(a[3]) != len(b[3]):
        return f"{caminho}: {len(a[3])} filhos != {len(b[3])}"
    for i, (x, y) in enumerate(zip(a[3], b[3])):
        if diferenca := _primeira_diferenca(x, y, f"{caminho}/{x[0]}[{i}]"):
            return diferenca
    return None


_SERIALIZAR = """() => [...document.querySelectorAll('#explorar-vista .nn-graf-largo svg, #explorar-vista .nn-graf-estreito svg')]
  .map((s) => new XMLSerializer().serializeToString(s))"""


def test_explorar_redesenhado_no_navegador_igual_ao_do_python(abrir):
    dados = DadosSite.carregar(Caminhos(raiz=RAIZ))
    textos = carregar_conteudo(RAIZ / "metadados" / "site").textos
    diferentes, comparados, sem_grafico = [], 0, 0
    with abrir("/explorar/") as pagina:
        pagina.select_option("#sel-expl-ind", "gini")  # sai da vista inicial, que ja vem desenhada no HTML
        pagina.select_option("#sel-expl-terr", "BA")
        for indicador in INDICADORES_EXPLORAR:
            for territorio, _, _ in TERRITORIOS:
                pagina.select_option("#sel-expl-ind", indicador.chave)
                pagina.select_option("#sel-expl-terr", territorio)
                esperado_html = vista_explorar_em_html(dados, textos, indicador.chave, territorio)
                esperados = re.findall(r"<svg\b.*?</svg>", esperado_html, flags=re.S)
                pagina.wait_for_function(
                    "(t) => document.getElementById('explorar-titulo').textContent.includes(t) && !document.getElementById('explorar-vista').hasAttribute('aria-busy')",
                    arg=f"{indicador.nome}: {next(n for i, n, _ in TERRITORIOS if i == territorio)} (",
                )
                obtidos = pagina.evaluate(_SERIALIZAR)
                if not esperados:  # territorio sem dado: a vista e so o aviso, nos dois lados
                    sem_grafico += 1
                    if obtidos:
                        diferentes.append(f"{indicador.chave}/{territorio}: o Python nao desenha e o navegador desenhou")
                    continue
                comparados += 1
                if len(esperados) != 2 or len(obtidos) != 2:  # a vista tem sempre dois graficos: o largo e o estreito
                    diferentes.append(f"{indicador.chave}/{territorio}: {len(esperados)} graficos no Python e {len(obtidos)} no navegador")
                    continue
                for largura, (no_navegador, do_python) in zip(("largo", "estreito"), zip(obtidos, esperados)):
                    if diferenca := _primeira_diferenca(_arvore(no_navegador), _arvore(do_python)):
                        diferentes.append(f"{indicador.chave}/{territorio} ({largura}): {diferenca}")
    assert comparados >= 6 * 3 and sem_grafico >= 1  # a amostra e grande e inclui territorio sem dado
    assert diferentes == []


# --- pista de rolagem do mapa de calor no celular (Ruling S-T) ---


def test_mapa_de_calor_no_celular_avisa_que_rola_de_lado(abrir):
    frase = carregar_conteudo(RAIZ / "metadados" / "site").textos["estados"]["rolagem"]
    with abrir("/estados/", largura=CELULAR) as pagina:
        caixa = pagina.locator(".nn-vista:visible .nn-mapa-caixa")
        assert caixa.evaluate("c => c.scrollWidth > c.clientWidth")  # rola de verdade
        assert pagina.locator(".nn-vista:visible .nn-rolagem").inner_text().strip() == frase
        assert caixa.evaluate("c => getComputedStyle(c).maskImage") != "none"  # esmaece na borda direita
        caixa.evaluate("c => { c.scrollLeft = c.scrollWidth; }")
        pagina.wait_for_function("() => document.querySelector('.nn-vista:not([hidden]) .nn-mapa-caixa').classList.contains('nn-no-fim')")
        assert caixa.evaluate("c => getComputedStyle(c).maskImage") == "none"  # no fim, nada a esmaecer
        caixa.evaluate("c => { c.scrollLeft = 0; }")
        pagina.wait_for_function("() => !document.querySelector('.nn-vista:not([hidden]) .nn-mapa-caixa').classList.contains('nn-no-fim')")
    with abrir("/estados/", largura=DESKTOP) as pagina:  # no desktop o mapa cabe: sem frase e sem esmaecimento
        assert not pagina.locator(".nn-vista:visible .nn-rolagem").is_visible()
        assert pagina.locator(".nn-vista:visible .nn-mapa-caixa").evaluate("c => getComputedStyle(c).maskImage") == "none"
