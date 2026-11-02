"""Graficos de linha em SVG, prontos no HTML: o JavaScript so acrescenta interacao.

O desenho segue o prototipo aprovado (`window.nnGrafico`): eixo de 2000 a 2027, pontos no meio do ano, faixas de
governo alternadas (interino hachurado), anos depois do ultimo dado hachurados, rotulo na ponta afastado de 14 px.
Cores que mudam com o tema ficam em classes CSS (`nn-*`); o SVG nao tem atributo `style=`.
"""

import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from html import escape

import pandas as pd

from nordeste.site.dados import Ponto
from nordeste.site.formatacao import numero

ANO_INICIAL = 2000
ANO_FINAL = 2027  # fim do eixo (exclusivo): 2026 e o ultimo ano desenhado
LARGURA_CARACTERE = 6.6  # px por caractere a 11 px; sem fonte medida no Python, so estima as margens
AFASTAMENTO_ROTULOS = 14  # distancia minima entre rotulos da ponta, em px
LARGURA_ESTREITA = 520  # abaixo disso: nomes de governo abreviados, menos anos no eixo, sem rotulo de quebra
DIAS_NO_ANO = 365.25


@dataclass(frozen=True)
class Linha:
    rotulo: str
    rotulo_curto: str
    pontos: list[Ponto]
    destaque: bool


@dataclass(frozen=True)
class ConfigGrafico:
    titulo: str
    casas: int
    sufixo: str = ""
    min0: bool = False
    ref100: bool = False
    quebras: tuple[tuple[int, str], ...] = ()


@dataclass(frozen=True)
class _Faixa:
    nome: str
    inicio: float
    fim: float
    interino: bool


Escala = Callable[[float], float]


def _escala(dominio: tuple[float, float], imagem: tuple[float, float]) -> Escala:
    d0, d1 = dominio
    i0, i1 = imagem
    return lambda v: i0 + (v - d0) * (i1 - i0) / (d1 - d0)


def _c(valor: float) -> str:
    """Coordenada com no maximo uma casa, sem `.0` e sem `-0`."""
    texto = f"{valor:.1f}"
    if texto.endswith(".0"):
        texto = texto[:-2]
    return "0" if texto == "-0" else texto


def _largura_texto(texto: str) -> float:
    return len(texto) * LARGURA_CARACTERE


# --- eixo y: ticks "bonitos" (mesmo algoritmo do d3: scaleLinear().nice(4) e ticks(4)) ---------------------------


def _unidade(inicio: float, fim: float, quantidade: int) -> tuple[float, bool]:
    """Passo bonito entre ticks: `(passo, fracionario)`. Fracionario: o tick e `i / passo`, evitando erro de ponto flutuante."""
    bruto = (fim - inicio) / quantidade
    potencia = math.floor(math.log10(bruto))
    erro = bruto / 10**potencia
    fator = 10 if erro >= math.sqrt(50) else 5 if erro >= math.sqrt(10) else 2 if erro >= math.sqrt(2) else 1
    if potencia >= 0:
        return fator * 10**potencia, False
    return 10**-potencia / fator, True


def _ticks(inicio: float, fim: float, quantidade: int) -> list[float]:
    passo, fracionario = _unidade(inicio, fim, quantidade)
    fator = passo if fracionario else 1 / passo
    primeiro, ultimo = math.ceil(round(inicio * fator, 9)), math.floor(round(fim * fator, 9))
    return [i / passo if fracionario else i * passo for i in range(primeiro, ultimo + 1)]


def _dominio_bonito(inicio: float, fim: float, quantidade: int) -> tuple[float, float]:
    anterior = None
    for _ in range(10):
        passo, fracionario = _unidade(inicio, fim, quantidade)
        if (passo, fracionario) == anterior:
            break
        if fracionario:
            inicio, fim = math.floor(round(inicio * passo, 9)) / passo, math.ceil(round(fim * passo, 9)) / passo
        else:
            inicio, fim = math.floor(round(inicio / passo, 9)) * passo, math.ceil(round(fim / passo, 9)) * passo
        anterior = (passo, fracionario)
    return inicio, fim


# --- governos ---------------------------------------------------------------------------------------------------


def _ano_fracionario(dia: date) -> float:
    return dia.year + (dia - date(dia.year, 1, 1)).days / DIAS_NO_ANO


def _faixas(governos: pd.DataFrame) -> list[_Faixa]:
    """Uma faixa por governo; mandatos seguidos do mesmo apelido (nao interinos) viram uma faixa so."""
    faixas: list[_Faixa] = []
    for g in governos.sort_values("inicio", kind="stable").itertuples():
        interino = g.interino == "sim"
        inicio, fim = _ano_fracionario(g.inicio), _ano_fracionario(g.fim) + 1 / DIAS_NO_ANO
        anterior = faixas[-1] if faixas else None
        if anterior and not interino and not anterior.interino and anterior.nome == g.apelido:
            faixas[-1] = _Faixa(anterior.nome, anterior.inicio, fim, False)
        else:
            faixas.append(_Faixa(g.apelido, inicio, fim, interino))
    return faixas


def faixas_em_json(governos: pd.DataFrame) -> str:
    """As faixas de governo como `[[nome, inicio, fim, interino], ...]` (anos fracionarios), para o site.js redesenhar
    o grafico do Explorar com as mesmas faixas do Python."""
    return json.dumps(
        [[f.nome, f.inicio, f.fim, f.interino] for f in _faixas(governos)], separators=(",", ":"), ensure_ascii=False
    )


# --- linhas -----------------------------------------------------------------------------------------------------


def _visiveis(linhas: list[Linha]) -> list[Linha]:
    """Linhas so com os pontos dentro do eixo; linha sem ponto no eixo sai."""
    recortadas = [
        Linha(l.rotulo, l.rotulo_curto, [p for p in l.pontos if ANO_INICIAL <= p.ano < ANO_FINAL], l.destaque)
        for l in linhas
    ]
    return [l for l in recortadas if l.pontos]


def _trechos(pontos: list[Ponto]) -> list[list[Ponto]]:
    """Quebra a linha na troca de serie e no ano faltante: nunca emenda dois trechos."""
    trechos: list[list[Ponto]] = []
    for p in pontos:
        anterior = trechos[-1][-1] if trechos else None
        if anterior is not None and p.ano == anterior.ano + 1 and p.serie == anterior.serie:
            trechos[-1].append(p)
        else:
            trechos.append([p])
    return trechos


def _desenhar_linha(l: Linha, x: Callable[[Ponto], float], y: Escala) -> str:
    classe = "nn-linha-ne" if l.destaque else "nn-linha-ref"
    espessura = "2.6" if l.destaque else "2"
    partes = [f'<g class="{classe}">']
    for trecho in _trechos(l.pontos):
        if len(trecho) > 1:
            caminho = "".join(f"{'M' if i == 0 else 'L'}{_c(x(p))},{_c(y(p.valor))}" for i, p in enumerate(trecho))
            partes.append(
                f'<path d="{caminho}" fill="none" stroke-width="{espessura}" stroke-linejoin="round" stroke-linecap="round"/>'
            )
        raio = "2.2" if len(trecho) > 1 else "3.4"
        partes += [f'<circle cx="{_c(x(p))}" cy="{_c(y(p.valor))}" r="{raio}" stroke="none"/>' for p in trecho]
    partes.append("</g>")
    return "".join(partes)


def _rotulo_da_ponta(l: Linha, cfg: ConfigGrafico) -> str:
    return f"{l.rotulo_curto} {numero(l.pontos[-1].valor, cfg.casas)}{cfg.sufixo}"


def _y_dos_rotulos(alvos: list[float], topo: float, eixo: float) -> list[float]:
    """Posicao y de cada rotulo da ponta: empurra para baixo ate haver 14 px entre vizinhos e depois limita de baixo
    para cima ao quadro, entre o topo e o eixo."""
    ordem = sorted(range(len(alvos)), key=lambda i: alvos[i])  # estavel: empate mantem a ordem das linhas
    ys = {i: alvos[i] for i in ordem}
    if ordem:
        ys[ordem[0]] = max(topo + 10, ys[ordem[0]])
    for anterior, atual in zip(ordem, ordem[1:]):
        ys[atual] = max(ys[atual], ys[anterior] + AFASTAMENTO_ROTULOS)
    teto = eixo - 2
    for i in reversed(ordem):
        ys[i] = min(ys[i], teto)
        teto = ys[i] - AFASTAMENTO_ROTULOS
    return [ys[i] for i in range(len(alvos))]


# --- textos e acessibilidade ------------------------------------------------------------------------------------


def descricao_acessivel(linhas: list[Linha], cfg: ConfigGrafico) -> str:
    """Primeiro e ultimo valor de cada linha, como no prototipo (`window.nnAria`)."""
    partes = []
    for l in _visiveis(linhas):
        primeiro, ultimo = l.pontos[0], l.pontos[-1]
        partes.append(
            f"{l.rotulo}: {numero(primeiro.valor, cfg.casas)}{cfg.sufixo} em {primeiro.ano} "
            f"e {numero(ultimo.valor, cfg.casas)}{cfg.sufixo} em {ultimo.ano}"
        )
    return f"Gráfico de linhas, {cfg.titulo}. {'; '.join(partes)}. A tabela com todos os valores está logo abaixo."


def _dados_para_o_script(linhas: list[Linha]) -> str:
    """JSON compacto e deterministico lido pelo site.js (Ruling S-C): pontos como [ano, valor, serie]."""
    return json.dumps(
        [
            {
                "rotulo": l.rotulo,
                "rotulo_curto": l.rotulo_curto,
                "destaque": l.destaque,
                "pontos": [[p.ano, p.valor, p.serie] for p in l.pontos],
            }
            for l in linhas
        ],
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _atributo(valor: str) -> str:
    return escape(valor, quote=True)


def _passo_dos_anos(estreito: bool) -> int:
    vao = ANO_FINAL - ANO_INICIAL
    if vao <= 8:
        return 2 if estreito else 1
    if vao <= 16:
        return 4 if estreito else 2
    return 8 if estreito else 4


# --- graficos ---------------------------------------------------------------------------------------------------


def grafico_linhas(
    linhas: list[Linha], cfg: ConfigGrafico, governos: pd.DataFrame, largura: int = 720, altura: int = 300
) -> str:
    """`<svg>` do grafico de linhas; vazio (`""`) quando nenhuma linha tem ponto dentro do eixo.

    Os atributos `data-pontos`, `data-casas` e `data-sufixo` levam os dados completos recebidos (inclusive fora do
    eixo) para o site.js redesenhar com zoom e comparacao.
    """
    visiveis = _visiveis(linhas)
    if not visiveis:
        return ""
    estreito = largura < LARGURA_ESTREITA

    valores = [p.valor for l in visiveis for p in l.pontos]
    if cfg.ref100:
        valores.append(100.0)
    baixo, alto = min(valores), max(valores)
    if cfg.min0:
        baixo = min(0.0, baixo)
    if baixo == alto:
        baixo, alto = baixo - 1, alto + 1
    dominio = _dominio_bonito(baixo, alto, 4)
    ticks = _ticks(*dominio, 4)
    amplitude = dominio[1] - dominio[0]
    casas_eixo = 2 if amplitude < 1 else 1 if amplitude < 10 else 0
    rotulos_y = [numero(t, casas_eixo) + cfg.sufixo for t in ticks]
    rotulos_fim = [_rotulo_da_ponta(l, cfg) for l in visiveis]

    topo, base = 26, 24
    esquerda = math.ceil(max((_largura_texto(r) for r in rotulos_y), default=30)) + 10
    direita = math.ceil(max(_largura_texto(r) for r in rotulos_fim)) + 12
    x_anos = _escala((ANO_INICIAL, ANO_FINAL), (esquerda, largura - direita))
    y = _escala(dominio, (altura - base, topo))
    x_ponto: Callable[[Ponto], float] = lambda p: x_anos(p.ano + 0.5)  # pontos no meio do ano
    eixo, alto_quadro = altura - base, altura - topo - base

    dados = _dados_para_o_script(linhas)
    id_base = "nn" + hashlib.sha1(f"{cfg.titulo}|{largura}|{altura}|{dados}".encode()).hexdigest()[:8]
    id_padrao, id_titulo, id_desc = f"{id_base}-h", f"{id_base}-t", f"{id_base}-d"

    partes = [
        f'<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="{id_titulo} {id_desc}" width="100%" '
        f'viewBox="0 0 {largura} {altura}" font-size="11" data-pontos="{_atributo(dados)}" '
        f'data-casas="{cfg.casas}" data-sufixo="{_atributo(cfg.sufixo)}">',
        f'<title id="{id_titulo}">{escape(cfg.titulo, quote=False)}</title>',
        f'<desc id="{id_desc}">{escape(descricao_acessivel(linhas, cfg), quote=False)}</desc>',
        f'<defs><pattern id="{id_padrao}" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
        '<line x1="0" y1="0" x2="0" y2="6" class="nn-hachura" stroke-width="2.5"/></pattern></defs>',
    ]

    # faixas de governo (interino hachurado) com o nome no topo
    for i, faixa in enumerate(_faixas(governos)):
        a, b = max(ANO_INICIAL, faixa.inicio), min(ANO_FINAL, faixa.fim)
        if b <= a:
            continue
        xa, xb = x_anos(a), x_anos(b)
        if faixa.interino:
            partes.append(
                f'<rect x="{_c(xa)}" y="{topo}" width="{_c(xb - xa)}" height="{_c(alto_quadro)}" fill="url(#{id_padrao})"/>'
            )
            continue
        classe = "nn-faixa-b" if i % 2 else "nn-faixa-a"
        partes.append(
            f'<rect class="{classe}" x="{_c(xa)}" y="{topo}" width="{_c(xb - xa)}" height="{_c(alto_quadro)}"/>'
        )
        if xb - xa >= 14:
            nome = faixa.nome[:1] if estreito or xb - xa < 58 else faixa.nome
            partes.append(
                f'<text class="nn-rotulo" x="{_c((xa + xb) / 2)}" y="{topo - 8}" text-anchor="middle">{escape(nome, quote=False)}</text>'
            )

    # anos depois do ultimo dado
    ultimo_ano = max(l.pontos[-1].ano for l in visiveis)
    if ultimo_ano + 1 < ANO_FINAL:
        xa, xb = x_anos(ultimo_ano + 1), x_anos(ANO_FINAL)
        partes.append(
            f'<rect x="{_c(xa)}" y="{topo}" width="{_c(xb - xa)}" height="{_c(alto_quadro)}" fill="url(#{id_padrao})"/>'
        )

    # grade e rotulos do eixo y
    for tick, rotulo in zip(ticks, rotulos_y):
        partes.append(
            f'<line class="nn-grade" x1="{esquerda}" x2="{_c(largura - direita)}" y1="{_c(y(tick))}" y2="{_c(y(tick))}" stroke-width="1"/>'
        )
        partes.append(f'<text class="nn-eixo" x="{esquerda - 6}" y="{_c(y(tick) + 4)}" text-anchor="end">{escape(rotulo, quote=False)}</text>')

    if cfg.ref100 and dominio[0] <= 100 <= dominio[1]:
        partes.append(
            f'<line class="nn-ref100" x1="{esquerda}" x2="{_c(largura - direita)}" y1="{_c(y(100))}" y2="{_c(y(100))}" '
            'stroke-width="1.5" stroke-dasharray="5 4"/>'
        )

    # anos no eixo x
    passo = _passo_dos_anos(estreito)
    for ano in range(math.ceil(ANO_INICIAL / passo) * passo, ANO_FINAL, passo):
        partes.append(f'<text class="nn-eixo" x="{_c(x_anos(ano + 0.5))}" y="{altura - 6}" text-anchor="middle">{ano}</text>')

    # quebras de serie
    quebras = [(ano, rotulo) for ano, rotulo in cfg.quebras if ANO_INICIAL < ano < ANO_FINAL]
    for i, (ano, rotulo) in enumerate(quebras):
        partes.append(
            f'<line class="nn-quebra" x1="{_c(x_anos(ano))}" x2="{_c(x_anos(ano))}" y1="{topo}" y2="{eixo}" '
            'stroke-width="1" stroke-dasharray="2 3"/>'
        )
        if not estreito:
            partes.append(
                f'<text class="nn-rotulo" x="{_c(x_anos(ano) + 4)}" y="{topo + 12 + i * 13}">{escape(rotulo, quote=False)}</text>'
            )

    for l in visiveis:
        partes.append(_desenhar_linha(l, x_ponto, y))

    # rotulos da ponta
    alvos = [y(l.pontos[-1].valor) + 4 for l in visiveis]
    for l, rotulo, y_rotulo in zip(visiveis, rotulos_fim, _y_dos_rotulos(alvos, topo, eixo)):
        classe = "nn-rotulo-forte" if l.destaque else "nn-rotulo"
        partes.append(
            f'<text class="{classe}" x="{_c(x_ponto(l.pontos[-1]) + 7)}" y="{_c(y_rotulo)}">{escape(rotulo, quote=False)}</text>'
        )

    partes.append("</svg>")
    return "".join(partes)


def minigrafico(linhas: list[Linha], largura: int = 480, altura: int = 120) -> str:
    """Versao pequena e decorativa (`aria-hidden`): so as linhas, sem eixos, faixas nem rotulos; vazio sem pontos."""
    com_pontos = [l for l in linhas if l.pontos]
    if not com_pontos:
        return ""
    margem = 8
    anos = [p.ano for l in com_pontos for p in l.pontos]
    valores = [p.valor for l in com_pontos for p in l.pontos]
    ano0, ano1 = min(anos), max(anos)
    baixo, alto = min(valores), max(valores)
    if ano0 == ano1:
        ano1 += 1
    if baixo == alto:
        baixo, alto = baixo - 1, alto + 1
    x_anos = _escala((ano0, ano1), (margem, largura - margem))
    y = _escala((baixo, alto), (altura - margem, margem))
    x_ponto: Callable[[Ponto], float] = lambda p: x_anos(p.ano)
    corpo = "".join(_desenhar_linha(l, x_ponto, y) for l in com_pontos)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false" width="100%" '
        f'viewBox="0 0 {largura} {altura}">{corpo}</svg>'
    )
