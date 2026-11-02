"""Gera `metadados/site/nordeste-contorno.svg`, o contorno do Nordeste (as 9 UFs dissolvidas) das imagens de
compartilhamento.

Uso (precisa de `shapely`: `python -m pip install shapely`):

    python ferramentas/gerar_contorno.py geojs-21-mun.json ... geojs-29-mun.json \\
        --origem "descricao da origem e data do download" --saida metadados/site/nordeste-contorno.svg

As entradas sao GeoJSON em graus (lon, lat) com os poligonos das UFs ou dos municipios do Nordeste. O contorno e a uniao
de tudo, sem buracos, sem baias e frestas estreitas (a malha tem falhas), sem ilhas menores que 0,1% da area (so enfeite: Fernando de Noronha nao cabe no desenho),
simplificado e projetado com a escala de longitude da latitude media. Sai um unico `<path>`; a origem e a data ficam
num comentario no topo do arquivo.
"""

import argparse
import json
import math
import sys
from pathlib import Path

from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.ops import unary_union

LARGURA = 1000  # largura do viewBox; a altura segue a proporcao do Nordeste
TOLERANCIA = 0.015  # graus (cerca de 1,5 km) na simplificacao
ILHA_MINIMA = 0.001  # fracao da area total abaixo da qual a parte e descartada
FECHAMENTO = 0.12  # graus (cerca de 13 km): frestas e baias mais estreitas que o dobro disso sao fechadas (falhas da malha)
LIMITE_BYTES = 30_000


def _poligonos(arquivos: list[Path]) -> list[Polygon]:
    partes = []
    for arquivo in arquivos:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        itens = dados["features"] if dados.get("type") == "FeatureCollection" else [dados]
        for item in itens:
            partes.append(shape(item.get("geometry", item)).buffer(0))  # buffer(0) conserta aneis invalidos
    return partes


def dissolver(arquivos: list[Path], tolerancia: float = TOLERANCIA) -> list[Polygon]:
    """Uniao das geometrias, sem buracos nem ilhas minusculas, simplificada; em graus."""
    uniao = unary_union(_poligonos(arquivos)).buffer(FECHAMENTO).buffer(-FECHAMENTO)
    partes = list(uniao.geoms) if isinstance(uniao, MultiPolygon) else [uniao]
    total = sum(p.area for p in partes)
    inteiros = [Polygon(p.exterior) for p in partes if p.area >= ILHA_MINIMA * total]
    simples = [p.simplify(tolerancia, preserve_topology=True) for p in inteiros]
    return sorted((p for p in simples if not p.is_empty), key=lambda p: -p.area)


def caminho_svg(poligonos: list[Polygon]) -> tuple[str, float, float]:
    """O atributo `d` e o tamanho (largura, altura) do viewBox, com Norte para cima."""
    x_min, y_min, x_max, y_max = unary_union(poligonos).bounds
    escala_x = math.cos(math.radians((y_min + y_max) / 2))  # um grau de longitude vale menos longe do Equador
    passo = LARGURA / ((x_max - x_min) * escala_x)

    def ponto(lon: float, lat: float) -> str:
        return f"{(lon - x_min) * escala_x * passo:.1f} {(y_max - lat) * passo:.1f}"

    trechos = []
    for poligono in poligonos:
        coordenadas = list(poligono.exterior.coords)[:-1]  # o fecho vai no Z
        trechos.append("M" + " ".join(ponto(*c[:2]) for c in coordenadas) + "Z")
    return "".join(trechos), float(LARGURA), round((y_max - y_min) * passo, 1)


def gerar_svg(arquivos: list[Path], origem: str) -> str:
    if "--" in origem:
        raise ValueError("A origem vai num comentario XML e nao pode conter '--'.")
    d, largura, altura = caminho_svg(dissolver(arquivos))
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {largura:g} {altura:g}">\n'
        f"<!-- Contorno do Nordeste (9 UFs dissolvidas e simplificadas). Origem: {origem} -->\n"
        f'<path fill-rule="evenodd" d="{d}"/>\n</svg>\n'
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("entradas", nargs="+", type=Path, help="GeoJSON das UFs ou dos municipios do Nordeste")
    ap.add_argument("--origem", required=True, help="de onde vieram as malhas e quando (vai no topo do SVG)")
    ap.add_argument("--saida", type=Path, required=True)
    args = ap.parse_args(argv)
    svg = gerar_svg(args.entradas, args.origem)
    if len(svg.encode("utf-8")) > LIMITE_BYTES:
        print(f"contorno com {len(svg)} bytes: acima de {LIMITE_BYTES}; aumente a tolerancia.", file=sys.stderr)
        return 1
    args.saida.write_text(svg, encoding="utf-8")
    print(f"{args.saida}: {len(svg.encode('utf-8'))} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
