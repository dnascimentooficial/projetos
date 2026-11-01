"""Padronizador de respostas JSON da API SIDRA (tabelas 'values')."""

import json
import math
import re

import pandas as pd

from nordeste.esquema import COLUNAS_BASE, normalizar_base
from nordeste.fichas import Ficha, Serie
from nordeste.padronizacao.erros import ErroLayout
from nordeste.territorios import territorio_por_codigo

_NIVEL_POR_NC = {"1": "n1", "2": "n2", "3": "n3"}
_SIMBOLOS_INDISPONIVEIS = ("..", "...", "X")
_COLUNA_CODIGO = re.compile(r"D\d+C")
_ROTULOS_TERRITORIO = ("Brasil", "Grande Região", "Unidade da Federação")


def _achar_coluna(cabecalho: dict, aceita) -> str | None:
    for chave, rotulo in cabecalho.items():
        if _COLUNA_CODIGO.fullmatch(chave) and isinstance(rotulo, str) and aceita(rotulo):
            return chave
    return None


def _coluna(cabecalho: dict, serie: Serie, parametro: str, aceita, descricao: str) -> str:
    chave = serie.parametros.get(parametro)
    if chave is None:
        chave = _achar_coluna(cabecalho, aceita)
    if chave is None or chave not in cabecalho:
        raise ErroLayout(f"SIDRA: coluna de {descricao} não encontrada no cabeçalho ({serie.id})")
    return chave


def _ano(texto: str) -> int:
    if not (isinstance(texto, str) and re.fullmatch(r"\d{4}", texto)):
        raise ErroLayout(f"SIDRA: período anual esperado (quatro dígitos), recebido {texto!r}")
    return int(texto)


def _valor(texto: str) -> tuple[float, str, str]:
    """Devolve (valor, tipo_dado, nota) para o campo V de uma linha."""
    if texto in _SIMBOLOS_INDISPONIVEIS:
        return float("nan"), "indisponivel", f"SIDRA: {texto}"
    if texto == "-":
        return 0.0, "observado", ""
    try:
        numero = float(texto)
    except (TypeError, ValueError):
        raise ErroLayout(f"SIDRA: valor não reconhecido {texto!r}") from None
    if not math.isfinite(numero):
        raise ErroLayout(f"SIDRA: valor não reconhecido {texto!r}")
    return numero, "observado", ""


def padronizar_sidra(
    conteudo: bytes, ficha: Ficha, serie: Serie, coleta_id: str, territorios: pd.DataFrame,
) -> pd.DataFrame:
    """Converte o JSON SIDRA (cabecalho + linhas) para o formato da base.

    Territorios fora da tabela de territorios sao descartados.
    """
    try:
        dados = json.loads(conteudo)
    except ValueError as erro:
        raise ErroLayout(f"SIDRA: JSON ilegível ({erro})") from erro
    if not (isinstance(dados, list) and dados and isinstance(dados[0], dict)):
        raise ErroLayout("SIDRA: esperada uma lista JSON cujo primeiro elemento é o cabeçalho")
    cabecalho, linhas = dados[0], dados[1:]
    col_periodo = _coluna(
        cabecalho, serie, "coluna_periodo", lambda r: r.startswith("Ano"), "período")
    col_territorio = _coluna(
        cabecalho, serie, "coluna_territorio",
        lambda r: any(t in r for t in _ROTULOS_TERRITORIO), "território")

    registros = []
    for linha in linhas:
        nivel = _NIVEL_POR_NC.get(linha.get("NC"))
        territorio = (
            territorio_por_codigo(territorios, nivel, linha[col_territorio]) if nivel else None
        )
        if territorio is None:
            continue
        valor, tipo_dado, nota = _valor(linha.get("V"))
        registros.append({
            "indicador_id": ficha.id, "subindicador": "", "etapa": "", "rede": "",
            "territorio_id": territorio, "ano": _ano(linha[col_periodo]), "valor": valor,
            "tipo_dado": tipo_dado, "serie_id": serie.id, "coleta_id": coleta_id, "nota": nota,
        })
    return normalizar_base(pd.DataFrame(registros, columns=COLUNAS_BASE))
