"""Padronizador de respostas JSON da API OData do Ipeadata (ValoresSerie)."""

import json
import math

import pandas as pd

from nordeste.esquema import COLUNAS_BASE, normalizar_base
from nordeste.fichas import Ficha, Serie
from nordeste.padronizacao.erros import ErroLayout
from nordeste.territorios import territorio_por_codigo

# NIVNOME -> nivel territorial; no Brasil o Ipeadata deixa TERCODIGO vazio e o codigo IBGE e "1".
_NIVEL_POR_NOME = {"Brasil": "n1", "Regiões": "n2", "Estados": "n3"}


def _ano(data) -> int:
    texto = data[:4] if isinstance(data, str) else ""
    if not texto.isdigit():
        raise ErroLayout(f"Ipeadata: VALDATA não reconhecida {data!r}")
    return int(texto)


def _valor(bruto) -> tuple[float, str, str]:
    """Devolve (valor, tipo_dado, nota) para VALVALOR."""
    if bruto is None:
        return float("nan"), "indisponivel", "Ipeadata: sem valor"
    if isinstance(bruto, bool) or not isinstance(bruto, (int, float)) or not math.isfinite(bruto):
        raise ErroLayout(f"Ipeadata: valor não reconhecido {bruto!r}")
    return float(bruto), "observado", ""


def padronizar_ipeadata(
    conteudo: bytes, ficha: Ficha, serie: Serie, coleta_id: str, territorios: pd.DataFrame,
) -> pd.DataFrame:
    """Converte o JSON Ipeadata ({"value": [...]}) para o formato da base.

    Niveis diferentes de Brasil, Regioes e Estados e territorios fora da tabela sao descartados.
    """
    try:
        dados = json.loads(conteudo)
    except ValueError as erro:
        raise ErroLayout(f"Ipeadata: JSON ilegível ({erro})") from erro
    if not (isinstance(dados, dict) and isinstance(dados.get("value"), list)):
        raise ErroLayout('Ipeadata: esperado um objeto JSON com a lista "value"')

    registros = []
    for linha in dados["value"]:
        if not isinstance(linha, dict):
            raise ErroLayout(f"Ipeadata: linha não reconhecida {linha!r}")
        nivel = _NIVEL_POR_NOME.get(linha.get("NIVNOME"))
        if nivel is None:
            continue
        codigo = "1" if nivel == "n1" else linha.get("TERCODIGO")
        territorio = territorio_por_codigo(territorios, nivel, codigo)
        if territorio is None:
            continue
        valor, tipo_dado, nota = _valor(linha.get("VALVALOR"))
        registros.append({
            "indicador_id": ficha.id, "subindicador": "", "etapa": "", "rede": "",
            "territorio_id": territorio, "ano": _ano(linha.get("VALDATA")), "valor": valor,
            "tipo_dado": tipo_dado, "serie_id": serie.id, "coleta_id": coleta_id, "nota": nota,
        })
    return normalizar_base(pd.DataFrame(registros, columns=COLUNAS_BASE))
