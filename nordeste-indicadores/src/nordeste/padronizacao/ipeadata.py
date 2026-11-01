"""Padronizador de respostas JSON da API OData do Ipeadata (ValoresSerie)."""

import json
import math
import re

import pandas as pd

from nordeste.esquema import COLUNAS_BASE, normalizar_base
from nordeste.fichas import Ficha, Serie
from nordeste.padronizacao.erros import ErroLayout
from nordeste.territorios import territorio_por_codigo

# NIVNOME -> nivel territorial; no Brasil o Ipeadata deixa TERCODIGO vazio e o codigo IBGE e "1".
_NIVEL_POR_NOME = {"Brasil": "n1", "Regiões": "n2", "Estados": "n3"}
_PERIODOS = re.compile(r"(\d{4})(?:-(\d{4}))?")


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


def _janela(serie: Serie) -> tuple[int, int] | None:
    """Janela de anos de parametros["periodos"] ("AAAA" ou "AAAA-AAAA", fechada); None se nao declarada."""
    if "periodos" not in serie.parametros:
        return None
    periodos = serie.parametros["periodos"]
    achado = _PERIODOS.fullmatch(periodos) if isinstance(periodos, str) else None
    inicio, fim = (int(achado.group(1)), int(achado.group(2) or achado.group(1))) if achado else (1, 0)
    if inicio > fim:
        raise ErroLayout(
            f"Ipeadata: periodos invalido em {serie.id} ({periodos!r}); use AAAA ou AAAA-AAAA, com inicio <= fim")
    return inicio, fim


def _registros(dados, ficha: Ficha, serie: Serie, coleta_id: str, territorios: pd.DataFrame,
               subindicador: str, onde: str) -> list[dict]:
    """Linhas da base de uma resposta OData ({"value": [...]}); `onde` identifica a resposta nas mensagens."""
    if not (isinstance(dados, dict) and isinstance(dados.get("value"), list)):
        raise ErroLayout(f'Ipeadata: esperado um objeto JSON com a lista "value"{onde}')
    janela = _janela(serie)
    registros = []
    for linha in dados["value"]:
        if not isinstance(linha, dict):
            raise ErroLayout(f"Ipeadata: linha não reconhecida {linha!r}{onde}")
        nivel = _NIVEL_POR_NOME.get(linha.get("NIVNOME"))
        if nivel is None:
            continue
        codigo = "1" if nivel == "n1" else linha.get("TERCODIGO")
        territorio = territorio_por_codigo(territorios, nivel, codigo)
        if territorio is None:
            continue
        ano = _ano(linha.get("VALDATA"))
        if janela is not None and not janela[0] <= ano <= janela[1]:
            continue
        valor, tipo_dado, nota = _valor(linha.get("VALVALOR"))
        registros.append({
            "indicador_id": ficha.id, "subindicador": subindicador, "etapa": "", "rede": "",
            "territorio_id": territorio, "ano": ano, "valor": valor,
            "tipo_dado": tipo_dado, "serie_id": serie.id, "coleta_id": coleta_id, "nota": nota,
        })
    return registros


def padronizar_ipeadata(
    conteudo: bytes, ficha: Ficha, serie: Serie, coleta_id: str, territorios: pd.DataFrame,
) -> pd.DataFrame:
    """Converte o JSON Ipeadata para o formato da base.

    Codigo unico (`codigo`): a resposta OData ({"value": [...]}), sem subindicador. Varios codigos (`codigos`,
    subindicador -> SERCODIGO): o arquivo combinado que o coletor grava, {"subindicadores": {<subindicador>:
    <resposta OData>}}, com as mesmas chaves do mapa; cada resposta vira o seu subindicador.
    Niveis diferentes de Brasil, Regioes e Estados e territorios fora da tabela sao descartados. O Ipeadata
    devolve a serie inteira; com parametros["periodos"] ("AAAA" ou "AAAA-AAAA") ficam so os anos da janela.
    """
    try:
        dados = json.loads(conteudo)
    except ValueError as erro:
        raise ErroLayout(f"Ipeadata: JSON ilegível ({erro})") from erro

    if "codigos" not in serie.parametros:
        registros = _registros(dados, ficha, serie, coleta_id, territorios, "", "")
    else:
        esperados = list(serie.parametros["codigos"])
        recebidos = dados.get("subindicadores") if isinstance(dados, dict) else None
        if not isinstance(recebidos, dict):
            raise ErroLayout('Ipeadata: esperado um objeto JSON com "subindicadores" (a serie declara `codigos`)')
        faltam, sobram = [s for s in esperados if s not in recebidos], [s for s in recebidos if s not in esperados]
        if faltam or sobram:
            raise ErroLayout(
                f"Ipeadata: subindicadores do arquivo diferem de `codigos` (faltam: {', '.join(faltam) or '-'}; "
                f"sobram: {', '.join(sobram) or '-'})")
        registros = [
            r for subindicador in esperados
            for r in _registros(recebidos[subindicador], ficha, serie, coleta_id, territorios, subindicador,
                                f" (subindicador {subindicador})")
        ]
    return normalizar_base(pd.DataFrame(registros, columns=COLUNAS_BASE))
