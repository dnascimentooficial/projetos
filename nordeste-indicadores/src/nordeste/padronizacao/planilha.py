"""Padronizador de planilhas (xlsx, xls ou csv, opcionalmente dentro de um zip) com um ano por coluna."""

import io
import math
import numbers
import re
import zipfile

import pandas as pd

from nordeste.esquema import COLUNAS_BASE, normalizar_base
from nordeste.fichas import Ficha, Serie
from nordeste.padronizacao.erros import ErroLayout
from nordeste.territorios import territorio_por_nome

_AUSENTES = frozenset({"", "-", "--", "...", "…", "x", "n/d"})
_MILHAR_BR = re.compile(r"-?\d{1,3}(\.\d{3})+(,\d+)?")
_NOTA_NO_NOME = re.compile(r"\s*(\(\d+\)|\*+)$")
_MOTOR_EXCEL = {"xlsx": "openpyxl", "xls": "xlrd"}


def numero_br(texto) -> float | None:
    """Converte numero no padrao brasileiro; marcadores de ausencia e NaN viram None."""
    if isinstance(texto, numbers.Real) and not isinstance(texto, bool):
        numero = float(texto)
        if math.isnan(numero):
            return None
    elif isinstance(texto, str):
        limpo = texto.replace("\xa0", " ").strip()
        if limpo.casefold() in _AUSENTES:
            return None
        if "." in limpo:  # ponto so vale como separador de milhar ("1.234,5"); "3.5" e ambiguo
            if not _MILHAR_BR.fullmatch(limpo):
                raise ValueError(f"número não reconhecido {texto!r}")
            limpo = limpo.replace(".", "")
        try:
            numero = float(limpo.replace(",", "."))
        except ValueError:
            raise ValueError(f"número não reconhecido {texto!r}") from None
    elif texto is None or texto is pd.NA or texto is pd.NaT:
        return None
    else:
        raise ValueError(f"número não reconhecido {texto!r}")
    if not math.isfinite(numero):
        raise ValueError(f"número não reconhecido {texto!r}")
    return numero


def _nome_do_territorio(celula) -> str | None:
    """Tira espacos e sufixos de nota de rodape, como '(1)' ou '*', do nome do territorio."""
    if not isinstance(celula, str):
        return None
    nome = celula.strip()
    while (sem_nota := _NOTA_NO_NOME.sub("", nome)) != nome:
        nome = sem_nota
    return nome


def _abrir_zip(conteudo: bytes, membro: str, onde: str) -> bytes:
    try:
        with zipfile.ZipFile(io.BytesIO(conteudo)) as pacote:
            return pacote.read(membro)
    except zipfile.BadZipFile as erro:
        raise ErroLayout(f"Planilha {onde}: zip ilegível ({erro})") from erro
    except KeyError:
        raise ErroLayout(f"Planilha {onde}: arquivo {membro} não encontrado no zip") from None


def _ler_tabela(conteudo: bytes, parametros: dict, onde: str) -> pd.DataFrame:
    formato = parametros.get("formato", "xlsx")
    puladas = parametros.get("linha_cabecalho", 1) - 1  # linhas de titulo antes do cabecalho
    try:
        if formato in _MOTOR_EXCEL:
            tabela = pd.read_excel(
                io.BytesIO(conteudo), sheet_name=parametros["aba"], header=puladas, dtype=object,
                engine=_MOTOR_EXCEL[formato])
        elif formato == "csv":
            tabela = pd.read_csv(
                io.BytesIO(conteudo), sep=parametros.get("separador", ";"),
                encoding=parametros.get("codificacao", "utf-8"), skiprows=puladas, dtype=object)
        else:
            raise ErroLayout(f"Planilha {onde}: formato desconhecido {formato!r}")
    except KeyError as erro:
        raise ErroLayout(f"Planilha {onde}: parâmetro {erro} ausente") from None
    except ErroLayout:
        raise
    except Exception as erro:
        aba = parametros.get("aba", "-")
        raise ErroLayout(f"Planilha {onde}, aba {aba}: não foi possível ler ({erro})") from erro
    tabela.columns = [str(c).strip() for c in tabela.columns]
    return tabela


def padronizar_planilha(
    conteudo: bytes, ficha: Ficha, serie: Serie, coleta_id: str, territorios: pd.DataFrame,
) -> pd.DataFrame:
    """Converte uma planilha com um territorio por linha e um ano (ou subindicador) por coluna.

    Linhas cujo nome nao case nenhum territorio (totais, notas) sao descartadas; celulas
    com marcador de ausencia viram indisponivel.
    """
    parametros = serie.parametros
    membro = parametros.get("arquivo_no_zip")
    onde = membro or f"{ficha.id}/{serie.id}"
    if membro:
        conteudo = _abrir_zip(conteudo, membro, onde)
    tabela = _ler_tabela(conteudo, parametros, onde)

    aba = parametros.get("aba", "-")
    coluna_territorio = str(parametros.get("coluna_territorio", ""))
    colunas = parametros.get("colunas") or []
    for nome in [coluna_territorio, *(str(c["coluna"]) for c in colunas)]:
        if nome not in tabela.columns:
            raise ErroLayout(f"Planilha {onde}, aba {aba}: coluna {nome!r} não encontrada")

    registros = []
    for _, linha in tabela.iterrows():
        nome = _nome_do_territorio(linha[coluna_territorio])
        territorio = territorio_por_nome(territorios, nome) if nome else None
        if territorio is None:
            continue
        for spec in colunas:
            coluna = str(spec["coluna"])
            celula = linha[coluna]
            try:
                valor = numero_br(celula)
            except ValueError as erro:
                raise ErroLayout(
                    f"Planilha {onde}, aba {aba}, coluna {coluna!r}: {erro}") from erro
            if valor is None:
                bruto = celula.strip() if isinstance(celula, str) else ""
                valor, tipo_dado, nota = float("nan"), "indisponivel", f"Planilha: {bruto or 'vazio'}"
            else:
                tipo_dado, nota = "observado", ""
            registros.append({
                "indicador_id": ficha.id, "subindicador": spec.get("subindicador", ""),
                "etapa": spec.get("etapa", ""), "rede": spec.get("rede", ""),
                "territorio_id": territorio, "ano": spec["ano"], "valor": valor,
                "tipo_dado": tipo_dado, "serie_id": serie.id, "coleta_id": coleta_id, "nota": nota,
            })
    return normalizar_base(pd.DataFrame(registros, columns=COLUNAS_BASE))
