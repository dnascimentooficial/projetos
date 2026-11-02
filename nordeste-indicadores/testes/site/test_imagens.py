"""Imagens do site: contorno do Nordeste, PNG de compartilhamento (OpenGraph e cards) e foto da abertura.

Os testes com marcador `navegador` abrem o Chromium (Playwright) e ficam fora da suite padrao:
`python -m pytest -m navegador`. O navegador vem de `PLAYWRIGHT_CHROMIUM`, se definida.
"""

import importlib.util
import json
import os
import shutil
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

from nordeste.caminhos import Caminhos
from nordeste.site import gerar
from nordeste.site.conteudo import ErroConteudo, carregar_conteudo
from nordeste.site.gerar import gerar_site
from nordeste.site.imagens import AlvoImagem, renderizar

from auxiliares import RAIZ, Arvore, copiar_base

CONTORNO = RAIZ / "metadados" / "site" / "nordeste-contorno.svg"
FERRAMENTA = RAIZ / "ferramentas" / "gerar_contorno.py"
CHROMIUM_DO_AMBIENTE = Path("/opt/pw-browsers/chromium")
PAGINAS_COM_OG = ("index", "estados", "explorar", "cards", "sobre", "dados")
FOTO = {"arquivo": "foto-abertura.webp", "credito": "Fulana de Tal, CC BY-SA 4.0", "url": "https://commons.wikimedia.org/wiki/File:Exemplo.jpg"}


def _tamanho_do_png(arquivo: Path) -> tuple[int, int]:
    """Largura e altura lidas do cabecalho IHDR, sem biblioteca de imagem."""
    cabecalho = arquivo.read_bytes()[:24]
    assert cabecalho[:8] == b"\x89PNG\r\n\x1a\n", arquivo
    return struct.unpack(">II", cabecalho[16:24])


@pytest.fixture
def chromium(monkeypatch):
    """Aponta o Playwright para o Chromium do ambiente quando `PLAYWRIGHT_CHROMIUM` nao esta definida."""
    if "PLAYWRIGHT_CHROMIUM" not in os.environ and CHROMIUM_DO_AMBIENTE.exists():
        monkeypatch.setenv("PLAYWRIGHT_CHROMIUM", str(CHROMIUM_DO_AMBIENTE))


@pytest.fixture(scope="module")
def com_imagens(tmp_path_factory):
    if "PLAYWRIGHT_CHROMIUM" not in os.environ and CHROMIUM_DO_AMBIENTE.exists():
        os.environ["PLAYWRIGHT_CHROMIUM"] = str(CHROMIUM_DO_AMBIENTE)
    saida = tmp_path_factory.mktemp("site") / "saida"
    return saida, gerar_site(Caminhos(raiz=RAIZ), saida, imagens=True)


# --- contorno do Nordeste ---


def test_contorno_e_um_path_unico_e_pequeno():
    texto = CONTORNO.read_text(encoding="utf-8")
    assert len(texto.encode("utf-8")) < 30_000
    raiz = ET.fromstring(texto)
    paths = [e for e in raiz.iter() if e.tag.endswith("}path")]
    assert len(paths) == 1 and texto.count("<path") == 1
    assert [e for e in raiz.iter() if e is not raiz and e not in paths] == []  # so o <svg> e o <path>
    assert len(raiz.attrib["viewBox"].split()) == 4
    assert paths[0].attrib["d"].startswith("M") and paths[0].attrib["d"].endswith("Z")
    assert "IBGE" in texto and "2026-11-02" in texto  # a origem e a data ficam no topo (README tambem)


def _ferramenta():
    pytest.importorskip("shapely")
    spec = importlib.util.spec_from_file_location("gerar_contorno", FERRAMENTA)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _quadrado(x: float, y: float, lado: float = 1.0) -> dict:
    anel = [[x, y], [x + lado, y], [x + lado, y + lado], [x, y + lado], [x, y]]
    return {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [anel]}}


def test_ferramenta_dissolve_as_partes_num_unico_contorno(tmp_path):
    ferramenta = _ferramenta()
    # dois estados vizinhos (compartilham a aresta x=1), uma ilha minuscula ao largo e o buraco de um municipio
    vazado = _quadrado(0, 0)
    vazado["geometry"]["coordinates"].append([[0.4, 0.4], [0.6, 0.4], [0.6, 0.6], [0.4, 0.6], [0.4, 0.4]])
    entrada = tmp_path / "ufs.json"
    entrada.write_text(
        json.dumps({"type": "FeatureCollection", "features": [vazado, _quadrado(1, 0), _quadrado(3, 3, 0.01)]}),
        encoding="utf-8",
    )
    svg = ferramenta.gerar_svg([entrada], "malha de teste")
    raiz = ET.fromstring(svg)
    caminho = next(e for e in raiz.iter() if e.tag.endswith("}path"))
    assert svg.count("<path") == 1 and caminho.attrib["d"].count("M") == 1  # uma so parte, sem buraco nem ilha
    assert "malha de teste" in svg
    largura, altura = (float(v) for v in raiz.attrib["viewBox"].split()[2:])
    assert largura == 1000 and altura == pytest.approx(500, abs=1)  # dois quadrados lado a lado: 2 por 1
    with pytest.raises(ValueError, match="--"):
        ferramenta.gerar_svg([entrada], "origem -- invalida")


# --- foto da abertura (Ruling S-Q) ---


@pytest.fixture
def base_com_foto(tmp_path, monkeypatch):
    """Copia da base com `foto` em textos.yaml e uma pasta de estaticos que tem o arquivo da foto."""
    raiz = copiar_base(tmp_path / "repo")
    estaticos = tmp_path / "estaticos"
    shutil.copytree(gerar.PASTA_ESTATICOS, estaticos)
    (estaticos / FOTO["arquivo"]).write_bytes(b"RIFFxxxxWEBP")
    monkeypatch.setattr(gerar, "PASTA_ESTATICOS", estaticos)
    return raiz


def _com_foto(raiz: Path, foto: dict | None) -> None:
    arquivo = raiz / "metadados" / "site" / "textos.yaml"
    textos = yaml.safe_load(arquivo.read_text(encoding="utf-8"))
    textos.pop("foto", None)
    if foto is not None:
        textos["foto"] = foto
    arquivo.write_text(yaml.safe_dump(textos, allow_unicode=True), encoding="utf-8")


def test_sem_foto_nao_ha_imagem_nem_credito(tmp_path):
    raiz = copiar_base(tmp_path / "repo")
    _com_foto(raiz, None)
    saida = tmp_path / "saida"
    gerar_site(Caminhos(raiz=raiz), saida, imagens=False)
    for pagina in ("index.html", "sobre/index.html"):
        html = (saida / pagina).read_text(encoding="utf-8")
        assert Arvore(html).achar("img") == [] and "Foto" not in Arvore(html).texto_visivel(), pagina
    assert not (saida / FOTO["arquivo"]).exists()


def test_foto_aparece_na_abertura_e_o_credito_no_rodape_e_em_sobre(tmp_path, base_com_foto):
    _com_foto(base_com_foto, FOTO)
    saida = tmp_path / "saida"
    gerar_site(Caminhos(raiz=base_com_foto), saida, imagens=False)
    inicio = Arvore((saida / "index.html").read_text(encoding="utf-8"))
    fotos = inicio.achar("img")
    assert [f["attrs"]["src"] for f in fotos] == ["/foto-abertura.webp"]
    assert fotos[0]["attrs"]["alt"] == ""  # decorativa: o crédito diz de quem é
    assert (saida / "foto-abertura.webp").is_file()
    for pagina in ("index.html", "sobre/index.html", "dados/index.html"):
        arvore = Arvore((saida / pagina).read_text(encoding="utf-8"))
        links = [e for e in arvore.achar("a") if e["attrs"].get("href") == FOTO["url"]]
        assert [Arvore.texto(e) for e in links] == [FOTO["credito"]] * (2 if pagina == "sobre/index.html" else 1), pagina


@pytest.mark.parametrize("faltando", ["arquivo", "credito", "url"])
def test_foto_incompleta_e_erro_de_conteudo(tmp_path, base_com_foto, faltando):
    _com_foto(base_com_foto, {k: v for k, v in FOTO.items() if k != faltando})
    with pytest.raises(ErroConteudo, match=f"foto.{faltando}"):
        gerar_site(Caminhos(raiz=base_com_foto), tmp_path / "saida", imagens=False)


def test_foto_cujo_arquivo_nao_existe_e_erro_de_conteudo(tmp_path):
    raiz = copiar_base(tmp_path / "repo")
    _com_foto(raiz, FOTO)
    with pytest.raises(ErroConteudo, match="foto-abertura.webp"):
        gerar_site(Caminhos(raiz=raiz), tmp_path / "saida", imagens=False)


def test_foto_acima_de_200_kb_e_erro_de_conteudo(tmp_path, base_com_foto):
    _com_foto(base_com_foto, FOTO)
    (gerar.PASTA_ESTATICOS / FOTO["arquivo"]).write_bytes(b"x" * 200_001)
    with pytest.raises(ErroConteudo, match="200 KB"):
        gerar_site(Caminhos(raiz=base_com_foto), tmp_path / "saida", imagens=False)


# --- renderizacao (Chromium) ---


@pytest.mark.navegador
def test_renderizar_grava_cada_png_no_tamanho_pedido(tmp_path, chromium):
    (tmp_path / "a.html").write_text("<!doctype html><body style='margin:0;background:#080808'>a</body>", encoding="utf-8")
    alvos = [AlvoImagem(tmp_path / "a.html", tmp_path / "saida" / "a.png", 300, 200)]
    alvos.append(AlvoImagem(tmp_path / "a.html", tmp_path / "saida" / "b.png", 120, 90))
    renderizar(alvos)
    assert _tamanho_do_png(tmp_path / "saida" / "a.png") == (300, 200)
    assert _tamanho_do_png(tmp_path / "saida" / "b.png") == (120, 90)


@pytest.mark.navegador
def test_og_1200x630_por_pagina(com_imagens):
    saida, _ = com_imagens
    for pagina in PAGINAS_COM_OG:
        assert _tamanho_do_png(saida / "og" / f"{pagina}.png") == (1200, 630), pagina
    # as paginas de card usam o proprio PNG do card (og:image aponta para /cards/<id>.png), nao uma imagem og/
    assert sorted(p.name for p in (saida / "og").iterdir()) == sorted(f"{p}.png" for p in PAGINAS_COM_OG)


@pytest.mark.navegador
def test_png_do_card_1080x1350(com_imagens):
    saida, relatorio = com_imagens
    ids = [p.split("/")[1] for p in relatorio.paginas if p.startswith("cards/") and p != "cards/index.html"]
    assert ids and len(ids) == len(set(ids))
    for id_ in ids:
        assert _tamanho_do_png(saida / "cards" / f"{id_}.png") == (1080, 1350), id_
    assert sorted(p.stem for p in (saida / "cards").glob("*.png")) == sorted(ids)


@pytest.mark.navegador
def test_png_do_card_e_so_o_card_e_og_tem_a_identidade(com_imagens):
    pil = pytest.importorskip("PIL.Image")
    saida, relatorio = com_imagens
    card = next(p.split("/")[1] for p in relatorio.paginas if p.startswith("cards/") and p != "cards/index.html")
    with pil.open(saida / "cards" / f"{card}.png") as imagem:
        rgb = imagem.convert("RGB")
        # o card e preto de ponta a ponta (sem o papel claro da pagina em volta, nem cantos arredondados)
        assert [rgb.getpixel(p) for p in ((0, 0), (1079, 0), (0, 1349), (1079, 1349))] == [(8, 8, 8)] * 4
        assert len(rgb.resize((54, 68)).getcolors(maxcolors=54 * 68)) > 20  # tem texto, numeros e grafico, nao so fundo
    with pil.open(saida / "og" / "index.png") as imagem:
        rgb = imagem.convert("RGB")
        assert rgb.getpixel((0, 0)) == (8, 8, 8)
        laranja = dict((cor, n) for n, cor in rgb.getcolors(maxcolors=1200 * 630)).get((234, 46, 0), 0)
        assert laranja > 500  # o destaque da abertura, em #ea2e00


@pytest.mark.navegador
def test_geracao_nao_deixa_html_de_apoio_e_as_paginas_apontam_para_imagens_que_existem(com_imagens):
    saida, relatorio = com_imagens
    assert sorted(p.name for p in saida.rglob("*.html")) == sorted(Path(p).name for p in relatorio.paginas)
    for pagina in relatorio.paginas:
        meta = [e for e in Arvore((saida / pagina).read_text(encoding="utf-8")).achar("meta", property="og:image")]
        imagem = meta[0]["attrs"]["content"].removeprefix("https://nordeste.dnascimento.com.br/")
        assert (saida / imagem).is_file(), (pagina, imagem)


@pytest.mark.navegador
def test_mesma_base_mesmas_imagens(com_imagens, tmp_path, chromium):
    saida, _ = com_imagens
    outra = tmp_path / "outra"
    gerar_site(Caminhos(raiz=RAIZ), outra, imagens=True)
    pngs = sorted(p.relative_to(saida) for p in saida.rglob("*.png"))
    assert pngs == sorted(p.relative_to(outra) for p in outra.rglob("*.png"))
    for png in pngs:
        assert (saida / png).read_bytes() == (outra / png).read_bytes(), png
