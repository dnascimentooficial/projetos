"""Conteudo editorial do site: destaques, perguntas, cards e textos, com marcadores de numero e condicoes de fecho.

Nenhum numero de dado e digitado nos textos: cada um e um marcador `{id.campo:formato}` preenchido pela base.
Cada fecho e cada card trazem uma condicao (comparacoes `id.campo [* numero] <op> ...` ligadas por `e`) que,
falsa, suprime o texto que ela sustenta.
"""

import copy
import operator
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from nordeste.site.dados import DadosSite, Ponto
from nordeste.site.formatacao import escala_auto, numero


class ErroConteudo(ValueError):
    """Conteudo editorial invalido: estrutura errada, marcador ou condicao fora da gramatica."""


@dataclass(frozen=True)
class Destaque:
    """Primeiro e ultimo ano com valor de um numero citado nos textos."""
    id: str
    primeiro: Ponto
    ultimo: Ponto

    @property
    def dif(self) -> float:
        return self.ultimo.valor - self.primeiro.valor


@dataclass
class Conteudo:
    destaques: dict[str, dict]
    perguntas: list[dict]
    cards: list[dict]
    textos: dict


_CAMPOS = ("primeiro", "ultimo", "ano_primeiro", "ano_ultimo", "dif")
_CAMPOS_DE_ANO = ("ano_primeiro", "ano_ultimo")
_ID = r"[a-z][a-z0-9_]*"
_MARCADOR = re.compile(r"\{([^{}]*)\}")
_CORPO_DO_MARCADOR = re.compile(rf"({_ID})\.({'|'.join(_CAMPOS)})(?::(\S+))?")
_FORMATO_EM_CASAS = re.compile(r"(\+?)(\d+)(%?)")
_TERMO_DE_DESTAQUE = re.compile(rf"({_ID})\.({'|'.join(_CAMPOS)})")
_NUMERO_LITERAL = re.compile(r"-?\d+(?:\.\d+)?")
_COMPARADORES = {"<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge}


# --- marcadores ---

def _analisar_marcador(corpo: str) -> tuple[str, str, str | None]:
    achado = _CORPO_DO_MARCADOR.fullmatch(corpo)
    if achado is None:
        raise ErroConteudo(f"Marcador invalido: {{{corpo}}}. Use {{id.campo[:formato]}}, campo em {_CAMPOS}.")
    id_, campo, formato = achado.groups()
    if campo in _CAMPOS_DE_ANO:
        if formato is not None:
            raise ErroConteudo(f"Ano nao leva formato: {{{corpo}}}.")
    elif formato is None or not (formato == "auto" or _FORMATO_EM_CASAS.fullmatch(formato)):
        raise ErroConteudo(f"Formato invalido em {{{corpo}}}: use casas (1), casas e sufixo (1%), +1 ou auto.")
    return id_, campo, formato


def _formatar(valor: float, formato: str) -> str:
    if formato == "auto":
        if abs(valor) < 1000:
            raise ErroConteudo(f"Formato auto so vale de 1.000 em diante, nao para {valor}.")
        return escala_auto(valor)
    sinal, casas, sufixo = _FORMATO_EM_CASAS.fullmatch(formato).groups()
    texto = numero(valor, int(casas))
    if sinal and round(valor, int(casas)) > 0:
        texto = "+" + texto
    return texto + ("%" if sufixo else "")


def _valor_do_campo(destaque: Destaque, campo: str) -> float:
    if campo == "ano_primeiro":
        return destaque.primeiro.ano
    if campo == "ano_ultimo":
        return destaque.ultimo.ano
    return destaque.dif if campo == "dif" else getattr(destaque, campo).valor


def destaques_citados(texto: str) -> set[str]:
    """Ids dos destaques citados pelos marcadores do texto (marcador invalido levanta ErroConteudo)."""
    return {_analisar_marcador(corpo)[0] for corpo in _MARCADOR.findall(texto)}


def preencher(texto: str, destaques: dict[str, Destaque]) -> str:
    """Troca cada marcador `{id.campo[:formato]}` pelo numero do destaque; marcador sem dado levanta ErroConteudo."""
    def trocar(achado: re.Match) -> str:
        id_, campo, formato = _analisar_marcador(achado.group(1))
        if id_ not in destaques:
            raise ErroConteudo(f"Marcador {achado.group(0)} cita destaque sem dado: {id_!r}.")
        valor = _valor_do_campo(destaques[id_], campo)
        return str(int(valor)) if campo in _CAMPOS_DE_ANO else _formatar(valor, formato)

    preenchido = _MARCADOR.sub(trocar, texto)
    if "{" in preenchido or "}" in preenchido:
        raise ErroConteudo(f"Chave solta no texto: {texto!r}.")
    return preenchido


# --- condicoes ---
# Gramatica: `<termo> <op> <termo>`, varias ligadas por ` e ` (todas verdadeiras). Termo: `id.campo`, `id.campo * numero`
# ou numero literal. Sem `eval`: a expressao e quebrada em palavras e cada palavra e conferida.

_Termo = tuple[str, str, float] | float  # (id, campo, fator) ou literal


def _analisar_termo(palavras: list[str], expr: str) -> _Termo:
    """Consome um termo do inicio de `palavras` (e o remove da lista)."""
    if not palavras:
        raise ErroConteudo(f"Condicao invalida: {expr!r}. Falta um termo.")
    palavra = palavras.pop(0)
    achado = _TERMO_DE_DESTAQUE.fullmatch(palavra)
    if achado:
        fator = 1.0
        if palavras[:1] == ["*"]:
            if len(palavras) < 2 or not _NUMERO_LITERAL.fullmatch(palavras[1]):
                raise ErroConteudo(f"Condicao invalida: {expr!r}. '*' so multiplica id.campo por um numero literal.")
            fator = float(palavras[1])
            del palavras[:2]
        return achado.group(1), achado.group(2), fator
    if _NUMERO_LITERAL.fullmatch(palavra):
        return float(palavra)
    raise ErroConteudo(f"Condicao invalida: {expr!r}. Termo invalido {palavra!r}: use id.campo (campo em {_CAMPOS}) ou um numero.")


def _analisar_condicao(expr: str) -> list[tuple[_Termo, str, _Termo]]:
    palavras = expr.split()
    comparacoes = []
    while True:
        esquerda = _analisar_termo(palavras, expr)
        if not palavras or palavras[0] not in _COMPARADORES:
            raise ErroConteudo(f"Condicao invalida: {expr!r}. Use '<termo> <op> <termo>', op em {tuple(_COMPARADORES)}.")
        op = palavras.pop(0)
        comparacoes.append((esquerda, op, _analisar_termo(palavras, expr)))
        if not palavras:
            return comparacoes
        if palavras.pop(0) != "e":
            raise ErroConteudo(f"Condicao invalida: {expr!r}. Comparacoes se ligam so por 'e'.")


def destaques_da_condicao(expr: str) -> set[str]:
    """Ids dos destaques citados pela condicao (condicao fora da gramatica levanta ErroConteudo)."""
    return {t[0] for esq, _, dir_ in _analisar_condicao(expr) for t in (esq, dir_) if not isinstance(t, float)}


def avaliar_condicao(expr: str, destaques: dict[str, Destaque]) -> bool:
    """Todas as comparacoes de `expr` verdadeiras; destaque ausente da base torna a condicao falsa."""
    comparacoes = _analisar_condicao(expr)
    if not destaques_da_condicao(expr) <= destaques.keys():
        return False

    def valor(termo: _Termo) -> float:
        if isinstance(termo, float):
            return termo
        id_, campo, fator = termo
        return _valor_do_campo(destaques[id_], campo) * fator

    return all(_COMPARADORES[op](valor(esq), valor(dir_)) for esq, op, dir_ in comparacoes)


# --- carga e validacao dos YAML ---

_SELECAO = ("tipo", "indicador", "territorio", "referencia", "sub", "etapa", "rede", "serie")
_FILTROS_DA_SERIE = ("sub", "etapa", "rede", "serie")
_CHAVES_DO_CARD = {
    "obrigatorias": {"id", "rotulo", "frase_feita", "de", "para", "frase", "grafico", "fecho", "condicao", "fonte"},
    "opcionais": {"longo"},
}
_CHAVES_DA_PERGUNTA = {
    "obrigatorias": {"id", "rotulo", "frase_feita", "lide", "graficos", "fecho", "fonte"},
    "opcionais": {"explicacao", "alerta"},
}
_CHAVES_DO_GRAFICO = {
    "obrigatorias": {"id", "casas", "linhas"},
    "opcionais": {"titulo", "subtitulo", "descricao", "sufixo", "min0", "ref100", "quebras"},
}
_CHAVES_DA_LINHA = {
    "obrigatorias": {"rotulo", "rotulo_curto", "destaque", "tipo", "indicador", "territorio"},
    "opcionais": set(_SELECAO) - {"tipo", "indicador", "territorio"},
}


def _exigir_chaves(obj: object, chaves: dict[str, set[str]], onde: str) -> None:
    if not isinstance(obj, dict):
        raise ErroConteudo(f"{onde}: esperava um mapa, veio {type(obj).__name__}.")
    faltam = chaves["obrigatorias"] - obj.keys()
    sobram = obj.keys() - chaves["obrigatorias"] - chaves["opcionais"]
    if faltam or sobram:
        raise ErroConteudo(f"{onde}: faltam {sorted(faltam)}, sobram {sorted(sobram)}.")


def _validar_selecao(spec: object, onde: str) -> None:
    """Destaque ou linha de grafico: `serie` filtra a base; `razao` le a razao publicada contra a referencia."""
    if not isinstance(spec, dict) or not {"tipo", "indicador", "territorio"} <= spec.keys():
        raise ErroConteudo(f"{onde}: precisa de tipo, indicador e territorio.")
    if spec["tipo"] not in ("serie", "razao"):
        raise ErroConteudo(f"{onde}: tipo {spec['tipo']!r} fora de serie|razao.")
    if spec["tipo"] == "serie" and "referencia" in spec:
        raise ErroConteudo(f"{onde}: serie nao leva referencia.")
    if spec["tipo"] == "razao":
        if "referencia" not in spec:
            raise ErroConteudo(f"{onde}: razao exige referencia.")
        if any(f in spec for f in _FILTROS_DA_SERIE):
            raise ErroConteudo(f"{onde}: razao nao filtra por {_FILTROS_DA_SERIE}.")


def _validar_destaques(destaques: object) -> None:
    if not isinstance(destaques, dict) or not destaques:
        raise ErroConteudo("destaques.yaml: esperava um mapa id -> selecao.")
    for id_, spec in destaques.items():
        if not re.fullmatch(_ID, str(id_)):
            raise ErroConteudo(f"destaques.yaml: id invalido {id_!r}.")
        _validar_selecao(spec, f"destaques.yaml, {id_}")
        sobram = spec.keys() - set(_SELECAO)
        if sobram:
            raise ErroConteudo(f"destaques.yaml, {id_}: chaves desconhecidas {sorted(sobram)}.")


def _validar_grafico(grafico: object, onde: str) -> None:
    _exigir_chaves(grafico, _CHAVES_DO_GRAFICO, onde)
    if not isinstance(grafico["linhas"], list) or not grafico["linhas"]:
        raise ErroConteudo(f"{onde}: linhas deve ser uma lista com ao menos uma linha.")
    for i, linha in enumerate(grafico["linhas"]):
        _exigir_chaves(linha, _CHAVES_DA_LINHA, f"{onde}, linha {i}")
        _validar_selecao(linha, f"{onde}, linha {i}")
        if not isinstance(linha["destaque"], bool):
            raise ErroConteudo(f"{onde}, linha {i}: destaque deve ser verdadeiro ou falso.")
    for i, quebra in enumerate(grafico.get("quebras", [])):
        _exigir_chaves(quebra, {"obrigatorias": {"ano", "rotulo"}, "opcionais": set()}, f"{onde}, quebra {i}")


def _validar_perguntas(perguntas: object) -> dict[str, dict]:
    """Valida as perguntas e devolve os graficos delas por id."""
    if not isinstance(perguntas, list):
        raise ErroConteudo("perguntas.yaml: esperava uma lista.")
    graficos: dict[str, dict] = {}
    ids = set()
    for pergunta in perguntas:
        _exigir_chaves(pergunta, _CHAVES_DA_PERGUNTA, "perguntas.yaml")
        onde = f"pergunta {pergunta['id']}"
        _exigir_chaves(pergunta["fecho"], {"obrigatorias": {"texto", "condicao"}, "opcionais": set()}, f"{onde}, fecho")
        if pergunta["id"] in ids:
            raise ErroConteudo(f"{onde}: id repetido.")
        ids.add(pergunta["id"])
        if not isinstance(pergunta["graficos"], list) or not pergunta["graficos"]:
            raise ErroConteudo(f"{onde}: graficos deve ser uma lista com ao menos um grafico.")
        for grafico in pergunta["graficos"]:
            _validar_grafico(grafico, f"{onde}, grafico")
            if grafico["id"] in graficos:
                raise ErroConteudo(f"{onde}: grafico {grafico['id']!r} repetido.")
            graficos[grafico["id"]] = grafico
    return graficos


def _validar_cards(cards: object, graficos: dict[str, dict]) -> None:
    """Valida os cards e troca `grafico` por id pelo dicionario do grafico da pergunta (o inline fica como esta)."""
    if not isinstance(cards, list):
        raise ErroConteudo("cards.yaml: esperava uma lista.")
    ids = set()
    for card in cards:
        _exigir_chaves(card, _CHAVES_DO_CARD, "cards.yaml")
        onde = f"card {card['id']}"
        if card["id"] in ids:
            raise ErroConteudo(f"{onde}: id repetido.")
        ids.add(card["id"])
        if isinstance(card["grafico"], str):
            if card["grafico"] not in graficos:
                raise ErroConteudo(f"{onde}: grafico {card['grafico']!r} nao esta em perguntas.yaml.")
            card["grafico"] = copy.deepcopy(graficos[card["grafico"]])
        else:
            _validar_grafico(card["grafico"], f"{onde}, grafico")


def _validar_textos_e_condicoes(obj: object, declarados: set[str], onde: str, chave: str | None = None) -> None:
    """Todo marcador e toda condicao do conteudo citam so destaques declarados e seguem a gramatica."""
    if chave == "condicao" and not isinstance(obj, str):
        raise ErroConteudo(f"{onde}: condicao deve ser um texto, veio {obj!r}.")
    if isinstance(obj, str):
        if chave == "condicao":
            citados = destaques_da_condicao(obj)
        else:
            citados = destaques_citados(obj)
            resto = _MARCADOR.sub("", obj)
            if "{" in resto or "}" in resto:
                raise ErroConteudo(f"{onde}: chave solta em {obj!r}.")
        desconhecidos = citados - declarados
        if desconhecidos:
            raise ErroConteudo(f"{onde}: destaque nao declarado em destaques.yaml: {sorted(desconhecidos)}.")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _validar_textos_e_condicoes(v, declarados, onde, k)
    elif isinstance(obj, list):
        for v in obj:
            _validar_textos_e_condicoes(v, declarados, onde, chave)


def _ler(pasta: Path, nome: str) -> object:
    caminho = pasta / f"{nome}.yaml"
    try:
        return yaml.safe_load(caminho.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as erro:
        raise ErroConteudo(f"{caminho}: nao foi possivel ler ({erro}).") from erro


def carregar_conteudo(pasta: Path) -> Conteudo:
    """Le e valida destaques, perguntas, cards e textos de `pasta` (metadados/site)."""
    destaques, perguntas, cards, textos = (_ler(pasta, n) for n in ("destaques", "perguntas", "cards", "textos"))
    _validar_destaques(destaques)
    _validar_cards(cards, _validar_perguntas(perguntas))
    if not isinstance(textos, dict):
        raise ErroConteudo("textos.yaml: esperava um mapa.")
    for nome, parte in (("perguntas.yaml", perguntas), ("cards.yaml", cards), ("textos.yaml", textos)):
        _validar_textos_e_condicoes(parte, set(destaques), nome)
    return Conteudo(destaques=destaques, perguntas=perguntas, cards=cards, textos=textos)


# --- calculo ---

def pontos_da_selecao(dados: DadosSite, spec: dict) -> list[Ponto]:
    """Pontos de um destaque ou linha de grafico: serie filtrada da base, ou razao publicada contra a referencia."""
    if spec["tipo"] == "razao":
        return dados.razao(spec["indicador"], spec["territorio"], spec["referencia"])
    return dados.serie(spec["indicador"], spec["territorio"], **{f: spec.get(f) for f in _FILTROS_DA_SERIE})


def calcular_destaques(dados: DadosSite, conteudo: Conteudo) -> dict[str, Destaque]:
    """Primeiro e ultimo ponto de cada destaque, sempre da mesma serie (a do ultimo ponto): pesquisas diferentes
    nunca se emendam. O que nao tem dado na base fica fora do dicionario."""
    resultado = {}
    for id_, spec in conteudo.destaques.items():
        pontos = pontos_da_selecao(dados, spec)
        if pontos:
            ultimo = pontos[-1]
            primeiro = next(p for p in pontos if p.serie == ultimo.serie)
            resultado[id_] = Destaque(id_, primeiro, ultimo)
    return resultado
