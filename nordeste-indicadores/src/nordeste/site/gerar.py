"""Gerador do site estatico a partir da base publicada, dos relatorios e dos metadados: Inicio, Estados, Explorar,
Cards, Sobre e Dados.

Nada aqui le o relogio nem a base de trabalho: a mesma base publicada gera o mesmo site, byte a byte. Todo numero de
texto vem de um marcador preenchido pela base (`conteudo.preencher`); fecho e card cuja condicao falha, ou cujo texto
cita um destaque que sumiu da base, nao saem e vao para o `RelatorioSite`.
"""

import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import NamedTuple

import pandas as pd
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from nordeste.caminhos import Caminhos
from nordeste.site.conteudo import (
    Conteudo, Destaque, ErroConteudo, avaliar_condicao, calcular_destaques, carregar_conteudo, destaques_citados,
    pontos_da_selecao, preencher,
)
from nordeste.site.dados import DadosSite
from nordeste.site.explorar import (
    ETIQUETA_DO_TERRITORIO, FAIXAS, INDICADORES_EXPLORAR, NOME_DO_TERRITORIO, POR_CHAVE, TERRITORIOS,
    IndicadorExplorar, dados_explorar, pontos, pontos_do_indicador, referencias, tabela_do_territorio, vistas_estados,
)
from nordeste.site.formatacao import numero
from nordeste.site.graficos import ConfigGrafico, Linha, faixas_em_json, grafico_linhas, minigrafico
from nordeste.site.imagens import AlvoImagem, renderizar

NOME_DO_SITE = "Nordeste em Números"
URL_DO_SITE = "https://nordeste.dnascimento.com.br"
URL_DO_AUTOR = "https://dnascimento.com.br"
LICENCA = "https://creativecommons.org/licenses/by/4.0/"
PASTA_MODELOS = Path(__file__).parent / "modelos"
PASTA_ESTATICOS = Path(__file__).parent / "estaticos"  # estilo, script, fontes, foto e .htaccess, copiados na raiz do site
CONTORNO = ("site", "nordeste-contorno.svg")  # em metadados/; ferramentas/gerar_contorno.py o gera
OG = (1200, 630)  # imagem de compartilhamento das paginas
CARD = (1080, 1350)  # PNG de cada card
FOTO_TAMANHO_MAXIMO = 200_000  # bytes: a foto pesa na primeira tela
FOTO_EXIGIDA = ("arquivo", "credito", "url")  # `foto` e opcional em textos.yaml; se existir, traz tudo isso
FOTO_ARQUIVO = "foto-abertura.webp"  # o estilo.css aponta para este nome (fundo da abertura, Ruling S-U)
LARGO = {"largura": 720}  # os dois tamanhos de cada grafico (Ruling S-O): o CSS mostra um conforme a largura da tela
ESTREITO = {"largura": 360, "altura": 240}
AMPLIADO = {"largura": 1100, "altura": 520}  # o terceiro, do modal "Ampliar" (Ruling S-W): guardado num <template>
ARQUIVOS_DE_DADOS = ("base_nordeste.csv", "derivados.csv")
EXPLORAR_INICIAL = ("pib_pc", "NE")  # a vista que ja vem desenhada no HTML: indicador e territorio
TEXTOS_EXIGIDOS = {  # seção de textos.yaml: chaves lidas pelo gerador e pelos modelos
    "abertura": {"eyebrow", "titulo", "destaque", "intro"},
    "faixa": {"rotulo", "id", "numeros", "texto", "nota"},  # + `condicao`, opcional (Ruling S-V)
    "ampliar": {"botao", "rotulo", "fechar", "gire", "quebra"},
    "por_que": {"titulo", "paragrafos"}, "como_ler": {"titulo", "itens"}, "o_que_falta": {"titulo", "itens"},
    "dataset": {"nome", "descricao"}, "fontes": {"titulo", "intro"}, "formulas": {"titulo", "intro", "blocos"},
    "arquivos": {"titulo", "intro"}, "dados": {"titulo", "intro", "conferir", "arquivos"},
    "estados": {
        "titulo", "intro", "titulo_mapa", "titulo_ranking", "escala_pior", "escala_melhor", "nota_do_mapa", "tabela",
        "fonte", "sem_dados",
    },
    "explorar": {
        **dict.fromkeys(("titulo", "intro", "nota", "tabela", "fonte", "sem_dados", "sem_periodo", "erro")),
        "zoom": {"grupo", "de", "ate", "inicio", "fim", "ampliar", "todo", "ajuda"},
    },
    "cards": {"titulo", "intro", "sera", "baixar", "voltar"},
}
FRASE_DA_DATA = "na data desta publicação"
MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro")


class Pagina(NamedTuple):
    chave: str  # tambem a chave em textos.yaml (paginas) e o nome da imagem OpenGraph
    modelo: str
    arquivo: str
    rota: str
    rotulo: str  # no menu


PAGINAS = (
    Pagina("index", "inicio.html", "index.html", "/", "Início"),
    Pagina("estados", "estados.html", "estados/index.html", "/estados/", "Estados"),
    Pagina("explorar", "explorar.html", "explorar/index.html", "/explorar/", "Explorar"),
    Pagina("cards", "cards.html", "cards/index.html", "/cards/", "Cards"),
    Pagina("sobre", "sobre.html", "sobre/index.html", "/sobre/", "Sobre os dados"),
    Pagina("dados", "dados.html", "dados/index.html", "/dados/", "Dados"),
)
PAGINAS_COM_DATASET = ("index", "dados")


@dataclass
class RelatorioSite:
    paginas: list[str]
    # ids das perguntas que ficaram sem fecho ou sairam inteiras e da faixa de numeros da abertura, se saiu (abertura_numeros)
    fechos_suprimidos: list[str]
    cards_suprimidos: list[str]


# --- datas e textos ---

def data_por_extenso(aaaa_mm_dd: str) -> str:
    """`2026-11-01` -> `1º de novembro de 2026`."""
    ano, mes, dia = aaaa_mm_dd.split("-")
    return f"{int(dia)}{'º' if int(dia) == 1 else ''} de {MESES[int(mes) - 1]} de {ano}"


def mes_por_extenso(aaaa_mm: str) -> str:
    """`2027-02` -> `fevereiro de 2027`."""
    ano, mes = aaaa_mm.split("-")
    return f"{MESES[int(mes) - 1]} de {ano}"


def _textos(obj: object) -> Iterator[str]:
    """Todos os textos do conteudo, menos as condicoes (que nao sao texto de leitura)."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for chave, valor in obj.items():
            if chave != "condicao":
                yield from _textos(valor)
    elif isinstance(obj, list):
        for valor in obj:
            yield from _textos(valor)


def _cita_so_o_que_existe(obj: object, destaques: dict[str, Destaque]) -> bool:
    return all(destaques_citados(t) <= destaques.keys() for t in _textos(obj))


def _resolver(obj: object, destaques: dict[str, Destaque], data: str) -> object:
    """Preenche os marcadores dos textos fixos e a data da publicacao. Item de lista que cita destaque ausente sai."""
    if isinstance(obj, str):
        return preencher(obj, destaques).replace(FRASE_DA_DATA, f"em {data}")
    if isinstance(obj, list):
        return [_resolver(item, destaques, data) for item in obj if _cita_so_o_que_existe(item, destaques)]
    if isinstance(obj, dict):
        return {chave: _resolver(valor, destaques, data) for chave, valor in obj.items()}
    return obj


# --- graficos ---

def _linhas(dados: DadosSite, grafico: dict) -> list[Linha]:
    return [
        Linha(l["rotulo"], l["rotulo_curto"], pontos_da_selecao(dados, l), l["destaque"]) for l in grafico["linhas"]
    ]


def _config(grafico: dict, destaques: dict[str, Destaque]) -> ConfigGrafico:
    descricao = grafico.get("descricao") or grafico.get("titulo") or grafico["id"]
    return ConfigGrafico(
        titulo=preencher(descricao, destaques),
        casas=grafico["casas"],
        sufixo=grafico.get("sufixo", ""),
        min0=grafico.get("min0", False),
        ref100=grafico.get("ref100", False),
        quebras=tuple((q["ano"], q["rotulo"]) for q in grafico.get("quebras", [])),
    )


def _tabela(linhas: list[Linha], cfg: ConfigGrafico, nome: str) -> list[dict]:
    """Os valores do grafico em ordem de ano. Linha com mais de uma serie leva a serie no nome: nunca se emendam."""
    linhas_da_tabela = []
    for ordem, linha in enumerate(linhas):
        varias = len({p.serie for p in linha.pontos}) > 1
        for p in linha.pontos:
            rotulo = f"{linha.rotulo} ({p.serie})" if varias else linha.rotulo
            linhas_da_tabela.append((p.ano, ordem, p.serie, nome, rotulo, f"{numero(p.valor, cfg.casas)}{cfg.sufixo}"))
    return [
        {"grafico": nome, "ano": ano, "serie": rotulo, "valor": valor}
        for ano, _, _, nome, rotulo, valor in sorted(linhas_da_tabela, key=lambda t: t[:3])
    ]


def _desenhar(linhas: list[Linha], cfg: ConfigGrafico, governos: pd.DataFrame) -> tuple[str, str]:
    """O grafico nas duas larguras (Ruling S-O); vazio quando nenhuma linha tem ponto no eixo."""
    largo = grafico_linhas(linhas, cfg, governos, **LARGO)
    return (largo, grafico_linhas(linhas, cfg, governos, **ESTREITO)) if largo else ("", "")


def _montar_grafico(dados: DadosSite, destaques: dict[str, Destaque], grafico: dict) -> dict | None:
    """O grafico nas tres larguras (a do modal tambem), a tabela dos numeros e o que o modal mostra do grafico
    (notas de quebra e atualizacoes dos seus indicadores); None quando nenhuma linha tem ponto no eixo."""
    linhas, cfg = _linhas(dados, grafico), _config(grafico, destaques)
    largo, estreito = _desenhar(linhas, cfg, dados.governos)
    if not largo:
        return None
    nome = preencher(grafico.get("titulo") or grafico.get("descricao") or grafico["id"], destaques)
    indicadores = list(dict.fromkeys(l["indicador"] for l in grafico["linhas"]))
    return {
        "id": grafico["id"].replace("_", "-"),
        "titulo": preencher(grafico["titulo"], destaques) if "titulo" in grafico else None,
        "subtitulo": preencher(grafico["subtitulo"], destaques) if "subtitulo" in grafico else None,
        "largo": largo,
        "estreito": estreito,
        "ampliado": grafico_linhas(linhas, cfg, dados.governos, **AMPLIADO),
        "quebras": [{"ano": q["ano"], "rotulo": q["rotulo"]} for q in grafico.get("quebras", [])],
        "atualizacoes": _atualizacoes(dados, indicadores),
        "tabela": _tabela(linhas, cfg, nome),
    }


# --- perguntas e cards ---

def _atualizacoes(dados: DadosSite, indicadores: list[str]) -> list[dict]:
    """Por indicador: nome, data da ultima coleta e proxima publicacao esperada (None quando nao ha previsao)."""
    atualizacoes = []
    for indicador in indicadores:
        ficha = dados.fichas.get(indicador)
        if ficha is None:
            continue
        try:
            atualizado = data_por_extenso(dados.atualizado_em(indicador))
        except KeyError:
            continue
        proximo = dados.proxima_publicacao(indicador)
        atualizacoes.append(
            {"nome": ficha.nome, "atualizado": atualizado, "proximo": mes_por_extenso(proximo) if proximo else None}
        )
    return atualizacoes


def _pergunta(dados: DadosSite, destaques: dict[str, Destaque], p: dict, com_fecho: bool) -> dict:
    graficos = [g for g in (_montar_grafico(dados, destaques, g) for g in p["graficos"]) if g is not None]
    indicadores = list(dict.fromkeys(l["indicador"] for g in p["graficos"] for l in g["linhas"]))
    return {
        "id": p["id"],
        "rotulo": preencher(p["rotulo"], destaques),
        "frase_feita": preencher(p["frase_feita"], destaques),
        "explicacao": preencher(p["explicacao"], destaques) if "explicacao" in p else None,
        "lide": preencher(p["lide"], destaques),
        "graficos": graficos,
        "tabela": [linha for g in graficos for linha in g["tabela"]],
        "fecho": preencher(p["fecho"]["texto"], destaques) if com_fecho else None,
        "alerta": preencher(p["alerta"], destaques) if "alerta" in p else None,
        "fonte": [preencher(f, destaques) for f in p["fonte"]],
        "atualizacoes": _atualizacoes(dados, indicadores),
    }


def _perguntas(dados: DadosSite, destaques: dict[str, Destaque], conteudo: Conteudo) -> tuple[list[dict], list[str]]:
    """Perguntas publicaveis e os ids das que perderam o fecho ou sairam inteiras.

    O corpo (lide, explicacao, alerta, fonte, graficos) que cita destaque ausente tira a pergunta toda; o fecho cuja
    condicao e falsa, ou cujo texto cita destaque ausente, tira so o fecho.
    """
    publicadas, suprimidas = [], []
    for p in conteudo.perguntas:
        corpo = {k: v for k, v in p.items() if k != "fecho"}
        if not _cita_so_o_que_existe(corpo, destaques):
            suprimidas.append(p["id"])
            continue
        fecho = p["fecho"]
        com_fecho = avaliar_condicao(fecho["condicao"], destaques) and _cita_so_o_que_existe(fecho["texto"], destaques)
        if not com_fecho:
            suprimidas.append(p["id"])
        publicadas.append(_pergunta(dados, destaques, p, com_fecho))
    return publicadas, suprimidas


def _cards_suprimidos(conteudo: Conteudo, destaques: dict[str, Destaque]) -> list[str]:
    """Ids dos cards cuja condicao e falsa ou cujo texto cita destaque ausente da base."""
    return [
        c["id"] for c in conteudo.cards
        if not (avaliar_condicao(c["condicao"], destaques) and _cita_so_o_que_existe(c, destaques))
    ]


# --- Estados, Explorar e Cards ---

def _contexto_dos_estados(dados: DadosSite) -> dict:
    vistas = vistas_estados(dados)
    for vista in vistas:
        vista["atualizacoes"] = _atualizacoes(dados, [vista["indicador_id"]])
    return {"estados": vistas, "faixas": [f"nn-f{i}" for i in range(FAIXAS)]}


def _vista_explorar(dados: DadosSite, ind: IndicadorExplorar, por_territorio: dict, territorio: str) -> dict:
    """O titulo, o grafico (as duas larguras) e a tabela do territorio escolhido.

    Territorio sem nenhum ponto no indicador: `grafico` fica None e a pagina mostra o aviso. As linhas de referencia
    (Brasil, Nordeste) nao aparecem sozinhas, para nao parecerem a serie do territorio.
    """
    vista = {
        "titulo": f"{ind.nome}: {NOME_DO_TERRITORIO[territorio]} ({ind.unidade})", "grafico": None, "tabela": [],
    }
    if not por_territorio[territorio]:
        return vista
    linhas = [
        Linha(NOME_DO_TERRITORIO[t], ETIQUETA_DO_TERRITORIO[t], pontos(por_territorio[t]), t == territorio)
        for t in (*referencias(territorio), territorio)
    ]
    cfg = ConfigGrafico(titulo=f"{ind.nome}, {NOME_DO_TERRITORIO[territorio]}", casas=ind.casas, sufixo=ind.sufixo)
    largo, estreito = _desenhar(linhas, cfg, dados.governos)
    if largo:
        vista["grafico"] = {"id": "g-explorar", "largo": largo, "estreito": estreito}
        vista["tabela"] = tabela_do_territorio(ind, por_territorio[territorio], territorio)
    return vista


def vista_explorar_em_html(dados: DadosSite, textos: dict, indicador: str, territorio: str) -> str:
    """O HTML da vista do Explorar de um indicador e territorio: grafico e tabela, ou o aviso de que nao ha dados."""
    ind = POR_CHAVE[indicador]
    vista = _vista_explorar(dados, ind, pontos_do_indicador(dados, ind), territorio)
    return str(_ambiente().get_template("_vista_explorar.html").module.vista(vista, textos["explorar"]))


def _contexto_do_explorar(dados: DadosSite, por_indicador: dict[str, dict[str, list[list]]]) -> dict:
    chave, territorio = EXPLORAR_INICIAL
    vista = _vista_explorar(dados, POR_CHAVE[chave], por_indicador[chave], territorio)
    return {
        "explorar": {
            "indicadores": INDICADORES_EXPLORAR,
            "territorios": [{"id": id_, "nome": nome, "etiqueta": etiqueta} for id_, nome, etiqueta in TERRITORIOS],
            "inicial": {"indicador": chave, "territorio": territorio},
            "vista": vista,
            "governos": faixas_em_json(dados.governos),
        }
    }


def _cartao(dados: DadosSite, destaques: dict[str, Destaque], card: dict) -> dict:
    """O card pronto para o modelo: textos preenchidos, minigrafico e o resumo das previas de compartilhamento."""
    de, para = preencher(card["de"], destaques), preencher(card["para"], destaques)
    frase, fecho = preencher(card["frase"], destaques), preencher(card["fecho"], destaques)
    frase_feita = preencher(card["frase_feita"], destaques)
    return {
        "id": card["id"], "rotulo": preencher(card["rotulo"], destaques), "frase_feita": frase_feita,
        "titulo_sem_aspas": frase_feita.strip("“”"), "de": de, "para": para, "frase": frase, "fecho": fecho,
        "fonte": preencher(card["fonte"], destaques), "longo": card.get("longo", False),
        "mini": minigrafico(_linhas(dados, card["grafico"])),
        "resumo": f"{de} → {para} {frase} {fecho}",
    }


# --- paginas ---

def _anos_da_base(dados: DadosSite) -> tuple[int, int]:
    com_valor = dados.base.loc[dados.base["valor"].notna() & (dados.base["tipo_dado"] != "indisponivel"), "ano"]
    return int(com_valor.min()), int(com_valor.max())


def _tamanho(n_bytes: int) -> str:
    return f"{numero(n_bytes / 1e6, 1)} MB" if n_bytes >= 1e6 else f"{numero(n_bytes / 1e3, 0)} kB"


def _arquivos_de_dados(caminhos: Caminhos, textos: dict) -> list[dict]:
    arquivos = []
    for nome in ARQUIVOS_DE_DADOS:
        conteudo = (caminhos.base / nome).read_bytes()
        arquivos.append({
            "nome": nome, "rota": f"/dados/{nome}", "url": f"{URL_DO_SITE}/dados/{nome}",
            "descricao": textos["dados"]["arquivos"][nome],
            "sha256": hashlib.sha256(conteudo).hexdigest(), "tamanho": _tamanho(len(conteudo)),
        })
    return arquivos


def _json_ld(dados: DadosSite, textos: dict, anos: tuple[int, int], arquivos: list[dict]) -> str:
    ld = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": textos["dataset"]["nome"],
        "description": textos["dataset"]["descricao"],
        "url": f"{URL_DO_SITE}/dados/",
        "inLanguage": "pt-BR",
        "creator": {"@type": "Person", "name": "Júlio Diógenes", "url": URL_DO_AUTOR},
        "license": LICENCA,
        "temporalCoverage": f"{anos[0]}/{anos[1]}",
        "spatialCoverage": "Nordeste, Brasil",
        "dateModified": dados.data_base,
        "distribution": [
            {"@type": "DataDownload", "encodingFormat": "text/csv", "name": a["nome"], "contentUrl": a["url"]}
            for a in arquivos
        ],
    }
    return json.dumps(ld, ensure_ascii=False, indent=2).replace("<", "\\u003c")  # nunca fecha o <script>


def _fontes(dados: DadosSite) -> list[dict]:
    """Uma entrada por indicador, com uma linha por serie, na ordem das fichas (por id)."""
    return [
        {
            "nome": f.nome, "orgao": f.orgao,
            "series": [{"fonte": s.fonte, "url": s.url, "base_origem": s.base_origem} for s in f.series],
        }
        for f in dados.fichas.values()
    ]


def _ambiente() -> Environment:
    return Environment(
        loader=FileSystemLoader(PASTA_MODELOS), autoescape=True, undefined=StrictUndefined,
        trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True,
    )


def _contorno(caminhos: Caminhos) -> dict:
    """O viewBox e o caminho do contorno do Nordeste (metadados/site/nordeste-contorno.svg), para a imagem OpenGraph."""
    svg = ET.fromstring((caminhos.metadados.joinpath(*CONTORNO)).read_text(encoding="utf-8"))
    caminho = next(e for e in svg.iter() if e.tag.endswith("}path"))
    return {"viewbox": svg.attrib["viewBox"], "d": caminho.attrib["d"]}


def _texto_og(chave: str, textos: dict) -> dict:
    """O titulo da imagem de uma pagina: a pergunta da abertura (com o destaque) no Inicio, o nome da pagina nas demais."""
    if chave == "index":
        return {"linhas": textos["abertura"]["titulo"], "destaque": textos["abertura"]["destaque"]}
    return {"linhas": [textos["paginas"][chave]["titulo"].split(" · ")[0]], "destaque": None}


def _gerar_imagens(saida: Path, ambiente: Environment, comum: dict, cards: list[dict], contorno: dict) -> None:
    """og/<pagina>.png (1200x630) para cada pagina que nao e de card e cards/<id>.png (1080x1350) para cada card.

    As paginas de card ja apontam o og:image para o PNG do proprio card. O Chromium fotografa paginas de apoio
    (modelos/og.html) escritas em `_imagens/`, que somem ao fim, com o estilo e as fontes locais do site.
    """
    apoio = saida / "_imagens"
    apoio.mkdir()
    alvos = []
    try:
        for p in PAGINAS:
            nome = f"og-{p.chave}.html"
            _escrever(
                ambiente, apoio, "og.html", nome, titulo=NOME_DO_SITE, card=None, contorno=contorno,
                og=_texto_og(p.chave, comum["textos"]), **comum,
            )
            alvos.append(AlvoImagem(apoio / nome, saida / "og" / f"{p.chave}.png", *OG))
        for card in cards:
            nome = f"card-{card['id']}.html"
            _escrever(ambiente, apoio, "og.html", nome, titulo=card["frase_feita"], card=card, contorno=None, og=None, **comum)
            alvos.append(AlvoImagem(apoio / nome, saida / "cards" / f"{card['id']}.png", *CARD))
        renderizar(alvos, raiz=saida)
    finally:
        shutil.rmtree(apoio)


def _validar_saida(caminhos: Caminhos, saida: Path) -> None:
    """A saida e apagada: nunca a base publicada, os relatorios ou os metadados, nem uma pasta que os contenha ou
    que esteja dentro deles."""
    destino = saida.resolve()
    for protegida in (caminhos.base, caminhos.relatorios, caminhos.metadados):
        protegida = protegida.resolve()
        if destino == protegida or destino in protegida.parents or protegida in destino.parents:
            raise ValueError(f"A pasta de saída {saida} mexeria em {protegida}: escolha outra, fora da base e dos metadados.")


def _exigir(parte: object, spec: set | dict, caminho: str) -> None:
    """`spec` e um conjunto de chaves ou um mapa chave -> spec (None: so a chave); falta vira ErroConteudo."""
    if not isinstance(parte, dict):
        raise ErroConteudo(f"textos.yaml: falta a seção {caminho}.")
    for chave in sorted(spec):
        if chave not in parte:
            raise ErroConteudo(f"textos.yaml: falta {caminho}.{chave}.")
        if isinstance(spec, dict) and spec[chave] is not None:
            _exigir(parte[chave], spec[chave], f"{caminho}.{chave}")


def _validar_textos(textos: object) -> None:
    """As chaves de textos.yaml que o gerador e os modelos leem; faltando uma, ErroConteudo em vez de KeyError."""
    exigidos = {
        **TEXTOS_EXIGIDOS,
        "paginas": {p.chave: {"titulo", "descricao"} for p in PAGINAS},
        "dados": {**dict.fromkeys(TEXTOS_EXIGIDOS["dados"] - {"arquivos"}), "arquivos": set(ARQUIVOS_DE_DADOS)},
    }
    _exigir(textos, exigidos, "textos")
    if "foto" in textos:
        _validar_foto(textos["foto"])


def _validar_foto(foto: object) -> None:
    """`foto: {arquivo, credito, url}` (Ruling S-Q): o arquivo esta em estaticos/ e o credito aponta para a pagina da licenca."""
    _exigir(foto, set(FOTO_EXIGIDA), "textos.foto")
    if not all(isinstance(foto[chave], str) and foto[chave].strip() for chave in FOTO_EXIGIDA):
        raise ErroConteudo("textos.yaml: foto.arquivo, foto.credito e foto.url são textos, não vazios.")
    if foto["arquivo"] != FOTO_ARQUIVO:
        raise ErroConteudo(f"textos.yaml: foto.arquivo é {FOTO_ARQUIVO!r}, o nome que o estilo.css usa; veio {foto['arquivo']!r}.")
    if not (PASTA_ESTATICOS / foto["arquivo"]).is_file():
        raise ErroConteudo(f"textos.yaml: foto.arquivo {foto['arquivo']!r} não está em estaticos/ do pacote.")
    if (PASTA_ESTATICOS / foto["arquivo"]).stat().st_size > FOTO_TAMANHO_MAXIMO:
        raise ErroConteudo(f"textos.yaml: foto.arquivo {foto['arquivo']!r} passa de {FOTO_TAMANHO_MAXIMO // 1000} KB.")


def _paragrafos_da_abertura(itens: list, destaques: dict[str, Destaque]) -> tuple[list[str], list[str]]:
    """Textos dos paragrafos da abertura que valem e os ids dos que sairam.

    Como no fecho, sai o paragrafo cuja condicao e falsa ou cujo texto cita destaque ausente da base.
    """
    textos, suprimidos = [], []
    for item in itens:
        if not isinstance(item, dict) or not {"id", "texto"} <= item.keys() or item.keys() - {"id", "texto", "condicao"}:
            raise ErroConteudo(f"textos.yaml, abertura.intro: cada parágrafo tem id e texto, e pode ter condicao: {item!r}.")
        vale = _cita_so_o_que_existe(item["texto"], destaques)
        if vale and "condicao" in item:
            vale = avaliar_condicao(item["condicao"], destaques)
        if vale:
            textos.append(item["texto"])
        else:
            suprimidos.append(item["id"])
    return textos, suprimidos


def _faixa(faixa: dict, destaques: dict[str, Destaque]) -> tuple[dict, list[str]]:
    """A faixa de numeros da abertura pronta para preencher e os ids que sairam (`[]` ou o id da faixa).

    Os numeros grandes e o paragrafo valem juntos: saem se a condicao e falsa ou se algum texto cita destaque ausente
    da base. A nota (de onde vem o dado, o que as faixas de governo nao dizem) nao tem numero e fica sempre.
    """
    numeros = faixa["numeros"]
    formato_ok = isinstance(numeros, list) and numeros and all(
        isinstance(n, dict) and n.keys() == {"valor", "rotulo", "ano"} for n in numeros
    )
    if not formato_ok or faixa.keys() - {*TEXTOS_EXIGIDOS["faixa"], "condicao"}:
        raise ErroConteudo("textos.yaml, faixa: numeros é uma lista de valor, rotulo e ano; as demais chaves são "
                           "rotulo, id, texto, nota e, se houver, condicao.")
    vale = _cita_so_o_que_existe([faixa["texto"], numeros], destaques)
    if vale and "condicao" in faixa:
        vale = avaliar_condicao(faixa["condicao"], destaques)
    pronta = {"rotulo": faixa["rotulo"], "nota": faixa["nota"], "texto": None, "numeros": []}
    if not vale:
        return pronta, [faixa["id"]]
    return {**pronta, "texto": faixa["texto"], "numeros": numeros}, []


def _copiar_estaticos(saida: Path) -> None:
    """Estilo, script, fontes (com a licenca OFL) e .htaccess, na raiz do site; cache do Python fica de fora."""
    shutil.copytree(PASTA_ESTATICOS, saida, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def _escrever(ambiente: Environment, saida: Path, modelo: str, arquivo: str, **contexto: object) -> None:
    destino = saida / arquivo
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(ambiente.get_template(modelo).render(**contexto).encode("utf-8"))


def _pagina(chave: str, rota: str, titulo: str, descricao: str, imagem: str, json_ld: str | None = None) -> dict:
    return {
        "chave": chave, "rota": rota, "url": URL_DO_SITE + rota, "titulo": titulo, "descricao": descricao,
        "imagem": imagem, "json_ld": json_ld,
    }


def gerar_site(caminhos: Caminhos, saida: Path, *, imagens: bool = True) -> RelatorioSite:
    """Apaga e recria `saida` com as paginas do site e as copias dos CSVs; devolve o que foi suprimido."""
    _validar_saida(caminhos, saida)
    dados = DadosSite.carregar(caminhos)
    conteudo = carregar_conteudo(caminhos.metadados / "site")
    _validar_textos(conteudo.textos)
    destaques = calcular_destaques(dados, conteudo)
    data = data_por_extenso(dados.data_base)
    abertura, paragrafos_suprimidos = _paragrafos_da_abertura(conteudo.textos["abertura"]["intro"], destaques)
    faixa, faixa_suprimida = _faixa(conteudo.textos["faixa"], destaques)
    com_abertura = {
        **conteudo.textos, "abertura": {**conteudo.textos["abertura"], "intro": abertura}, "faixa": faixa,
    }
    textos = _resolver(com_abertura, destaques, data)
    perguntas, fechos_suprimidos = _perguntas(dados, destaques, conteudo)
    cards_fora = _cards_suprimidos(conteudo, destaques)
    cards = [_cartao(dados, destaques, c) for c in conteudo.cards if c["id"] not in cards_fora]
    explorar = dados_explorar(dados)
    anos = _anos_da_base(dados)
    arquivos = _arquivos_de_dados(caminhos, textos)
    comum = {
        "menu": [{"chave": p.chave, "rota": p.rota, "rotulo": p.rotulo} for p in PAGINAS],
        "data_base": data, "sha256_base": dados.sha256_base, "licenca": LICENCA, "autor_url": URL_DO_AUTOR,
        "foto": textos.get("foto"),
        "textos": textos, "selo": f"{textos['abertura']['eyebrow']} · {anos[0]} a {anos[1]}",
        "perguntas": perguntas, "fontes": _fontes(dados), "arquivos": arquivos, "cards": cards,
        "data_curta": "/".join(reversed(dados.data_base.split("-"))),
    }
    por_pagina = {"estados": _contexto_dos_estados(dados), "explorar": _contexto_do_explorar(dados, explorar)}

    if saida.exists():
        shutil.rmtree(saida)
    (saida / "dados").mkdir(parents=True)
    (saida / "explorar" / "dados").mkdir(parents=True)
    _copiar_estaticos(saida)
    ambiente = _ambiente()
    for p in PAGINAS:
        pagina = _pagina(
            p.chave, p.rota, textos["paginas"][p.chave]["titulo"], textos["paginas"][p.chave]["descricao"],
            f"{URL_DO_SITE}/og/{p.chave}.png",
            _json_ld(dados, textos, anos, arquivos) if p.chave in PAGINAS_COM_DATASET else None,
        )
        _escrever(ambiente, saida, p.modelo, p.arquivo, pagina=pagina, **comum, **por_pagina.get(p.chave, {}))
    for card in cards:
        rota = f"/cards/{card['id']}/"
        pagina = _pagina(
            "cards", rota, f"{card['frase_feita']} · {NOME_DO_SITE}", card["resumo"],
            f"{URL_DO_SITE}/cards/{card['id']}.png",
        )
        _escrever(ambiente, saida, "card.html", f"cards/{card['id']}/index.html", pagina=pagina, card=card, **comum)
    for nome in ARQUIVOS_DE_DADOS:
        shutil.copyfile(caminhos.base / nome, saida / "dados" / nome)
    for chave, por_territorio in explorar.items():
        texto = json.dumps(por_territorio, ensure_ascii=False, separators=(",", ":")) + "\n"
        (saida / "explorar" / "dados" / f"{chave}.json").write_bytes(texto.encode("utf-8"))

    paginas = [p.arquivo for p in PAGINAS] + [f"cards/{c['id']}/index.html" for c in cards]
    if imagens:
        _gerar_imagens(saida, ambiente, comum, cards, _contorno(caminhos))
    return RelatorioSite(paginas, [*paragrafos_suprimidos, *faixa_suprimida, *fechos_suprimidos], cards_fora)


def relatorio_em_json(relatorio: RelatorioSite) -> str:
    return json.dumps(asdict(relatorio), ensure_ascii=False, indent=2) + "\n"
