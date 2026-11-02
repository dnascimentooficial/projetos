"""Gerador do site estatico: Inicio, Sobre e Dados a partir da base publicada, dos relatorios e dos metadados.

Nada aqui le o relogio nem a base de trabalho: a mesma base publicada gera o mesmo site, byte a byte. Todo numero de
texto vem de um marcador preenchido pela base (`conteudo.preencher`); fecho e card cuja condicao falha, ou cujo texto
cita um destaque que sumiu da base, nao saem e vao para o `RelatorioSite`.
"""

import hashlib
import json
import shutil
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import NamedTuple

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from nordeste.caminhos import Caminhos
from nordeste.site.conteudo import (
    Conteudo, Destaque, avaliar_condicao, calcular_destaques, carregar_conteudo, destaques_citados,
    pontos_da_selecao, preencher,
)
from nordeste.site.dados import DadosSite
from nordeste.site.formatacao import numero
from nordeste.site.graficos import ConfigGrafico, Linha, grafico_linhas

URL_DO_SITE = "https://nordeste.dnascimento.com.br"
URL_DO_AUTOR = "https://dnascimento.com.br"
LICENCA = "https://creativecommons.org/licenses/by/4.0/"
PASTA_MODELOS = Path(__file__).parent / "modelos"
LARGO = {"largura": 720}  # os dois tamanhos de cada grafico (Ruling S-O): o CSS mostra um conforme a largura da tela
ESTREITO = {"largura": 360, "altura": 240}
ARQUIVOS_DE_DADOS = ("base_nordeste.csv", "derivados.csv")
FRASE_DA_DATA = "na data desta publicação"
MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro")


class Pagina(NamedTuple):
    chave: str  # tambem a chave em textos.yaml (paginas) e o nome da imagem OpenGraph
    modelo: str
    arquivo: str
    rota: str
    rotulo: str  # no menu


# As paginas das proximas tarefas entram aqui.
PAGINAS = (
    Pagina("index", "inicio.html", "index.html", "/", "Início"),
    Pagina("sobre", "sobre.html", "sobre/index.html", "/sobre/", "Sobre os dados"),
    Pagina("dados", "dados.html", "dados/index.html", "/dados/", "Dados"),
)
PAGINAS_COM_DATASET = ("index", "dados")


@dataclass
class RelatorioSite:
    paginas: list[str]
    fechos_suprimidos: list[str]  # ids das perguntas que ficaram sem fecho ou sairam inteiras
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


def _montar_grafico(dados: DadosSite, destaques: dict[str, Destaque], grafico: dict) -> dict | None:
    """O grafico nas duas larguras e a tabela dos numeros; None quando nenhuma linha tem ponto no eixo."""
    linhas, cfg = _linhas(dados, grafico), _config(grafico, destaques)
    largo = grafico_linhas(linhas, cfg, dados.governos, **LARGO)
    if not largo:
        return None
    nome = preencher(grafico.get("titulo") or grafico.get("descricao") or grafico["id"], destaques)
    return {
        "id": grafico["id"].replace("_", "-"),
        "titulo": preencher(grafico["titulo"], destaques) if "titulo" in grafico else None,
        "subtitulo": preencher(grafico["subtitulo"], destaques) if "subtitulo" in grafico else None,
        "largo": largo,
        "estreito": grafico_linhas(linhas, cfg, dados.governos, **ESTREITO),
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


def _gerar_imagens(saida: Path, paginas: list[str]) -> None:
    """Gancho da Tarefa 8 (imagens OpenGraph e cards). Ate la, so as paginas sao geradas."""


def _validar_saida(caminhos: Caminhos, saida: Path) -> None:
    """A saida e apagada: nunca a pasta do projeto nem uma pasta que a contenha."""
    raiz, destino = caminhos.raiz.resolve(), saida.resolve()
    if destino == raiz or destino in raiz.parents:
        raise ValueError(f"A pasta de saída {saida} contém o projeto: escolha uma pasta fora dele.")


def gerar_site(caminhos: Caminhos, saida: Path, *, imagens: bool = True) -> RelatorioSite:
    """Apaga e recria `saida` com as paginas do site e as copias dos CSVs; devolve o que foi suprimido."""
    _validar_saida(caminhos, saida)
    dados = DadosSite.carregar(caminhos)
    conteudo = carregar_conteudo(caminhos.metadados / "site")
    destaques = calcular_destaques(dados, conteudo)
    data = data_por_extenso(dados.data_base)
    textos = _resolver(conteudo.textos, destaques, data)
    perguntas, fechos_suprimidos = _perguntas(dados, destaques, conteudo)
    anos = _anos_da_base(dados)
    arquivos = _arquivos_de_dados(caminhos, textos)
    comum = {
        "menu": [{"chave": p.chave, "rota": p.rota, "rotulo": p.rotulo} for p in PAGINAS],
        "data_base": data, "sha256_base": dados.sha256_base, "licenca": LICENCA, "autor_url": URL_DO_AUTOR,
        "foto": textos.get("foto"),
        "textos": textos, "selo": f"{textos['abertura']['eyebrow']} · {anos[0]} a {anos[1]}",
        "perguntas": perguntas, "fontes": _fontes(dados), "arquivos": arquivos,
    }

    if saida.exists():
        shutil.rmtree(saida)
    (saida / "dados").mkdir(parents=True)
    ambiente = _ambiente()
    for p in PAGINAS:
        pagina = {
            "chave": p.chave, "rota": p.rota, "url": URL_DO_SITE + p.rota,
            "titulo": textos["paginas"][p.chave]["titulo"], "descricao": textos["paginas"][p.chave]["descricao"],
            "imagem": f"{URL_DO_SITE}/og/{p.chave}.png",
            "json_ld": _json_ld(dados, textos, anos, arquivos) if p.chave in PAGINAS_COM_DATASET else None,
        }
        destino = saida / p.arquivo
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(ambiente.get_template(p.modelo).render(pagina=pagina, **comum).encode("utf-8"))
    for nome in ARQUIVOS_DE_DADOS:
        shutil.copyfile(caminhos.base / nome, saida / "dados" / nome)

    paginas = [p.arquivo for p in PAGINAS]
    if imagens:
        _gerar_imagens(saida, paginas)
    return RelatorioSite(paginas, fechos_suprimidos, _cards_suprimidos(conteudo, destaques))


def relatorio_em_json(relatorio: RelatorioSite) -> str:
    return json.dumps(asdict(relatorio), ensure_ascii=False, indent=2) + "\n"
