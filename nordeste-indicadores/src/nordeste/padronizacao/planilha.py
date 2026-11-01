"""Padronizador de planilhas (xlsx, xls ou csv, opcionalmente dentro de um zip) com um ano por coluna."""

import io
import math
import numbers
import re
import zipfile

import pandas as pd

from nordeste.coletores.arquivo import ler_pacote
from nordeste.esquema import CHAVE_BASE, COLUNAS_BASE, normalizar_base
from nordeste.fichas import Ficha, Serie
from nordeste.padronizacao.erros import ErroLayout
from nordeste.territorios import normalizar_nome, territorio_por_nome

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


def _sem_nota(celula) -> str | None:
    """Tira espacos e sufixos de nota de rodape, como '(1)', '(3)(4)' ou '*', de um texto (territorio, rede)."""
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
    com marcador de ausencia viram indisponivel. Com `parametros.partes`, o conteudo e o pacote do
    coletor `arquivo` (uma entrada por URL) e cada parte e lida como uma planilha independente, com os
    seus proprios parametros de leitura; o resultado e a concatenacao, na ordem das partes. Parte sem nenhuma
    linha aceita e erro de layout. Com `territorios_esperados` (na serie ou na parte), a ausencia de qualquer
    um deles no resultado tambem e.
    """
    parametros = serie.parametros
    if "partes" not in parametros:
        membro = parametros.get("arquivo_no_zip")
        return _padronizar_tabela(
            conteudo, parametros, membro or f"{ficha.id}/{serie.id}", ficha, serie, coleta_id, territorios)
    partes = parametros["partes"]
    if not isinstance(partes, list) or not partes or not all(isinstance(p, dict) for p in partes):
        raise ErroLayout(f"Planilha {ficha.id}/{serie.id}: partes deve ser uma lista de mapas de parâmetros")
    try:
        arquivos = ler_pacote(conteudo)
    except ValueError as erro:
        raise ErroLayout(f"Planilha {ficha.id}/{serie.id}: {erro}") from erro
    quadros = []
    for posicao, parte in enumerate(partes, start=1):
        url = parte.get("url")
        onde = f"{ficha.id}/{serie.id}, parte {posicao} ({parte.get('arquivo_no_zip') or url})"
        if url not in arquivos:
            raise ErroLayout(f"Planilha {ficha.id}/{serie.id}, parte {posicao}: {url} ausente do pacote coletado")
        quadro = _padronizar_tabela(arquivos[url], parte, onde, ficha, serie, coleta_id, territorios)
        if quadro.empty:  # "Total" renomeado ou celula mesclada: o subindicador sumiria sem nenhuma regra notar
            raise ErroLayout(
                f"Planilha {onde}, aba {parte.get('aba', '-')}: nenhuma linha aceita "
                "(o filtro_linhas ou os nomes de territorio nao casaram com a planilha)")
        quadros.append(quadro)
    df = normalizar_base(pd.concat(quadros, ignore_index=True))
    _sem_linhas_repetidas(df, f"{ficha.id}/{serie.id}")
    return df


def _sem_linhas_repetidas(df: pd.DataFrame, onde: str) -> None:
    repetidas = df[df.duplicated(CHAVE_BASE, keep=False)]
    if not repetidas.empty:
        exemplo = repetidas.iloc[0]
        raise ErroLayout(
            f"Planilha {onde}: {len(repetidas)} linhas repetidas para a mesma chave (ex.: "
            f"{exemplo.territorio_id} {exemplo.ano} {exemplo.subindicador or '-'}/{exemplo.etapa or '-'}/"
            f"{exemplo.rede or '-'}); falta filtro_linhas ou as partes se sobrepoem")


def _filtro(parametros: dict, onde: str) -> dict[str, str]:
    filtro = parametros.get("filtro_linhas") or {}
    if not isinstance(filtro, dict):
        raise ErroLayout(f"Planilha {onde}: filtro_linhas deve mapear coluna para valor aceito")
    return {str(coluna): normalizar_nome(_texto(valor)) for coluna, valor in filtro.items()}


def _apelidos(parametros: dict, territorios: pd.DataFrame, onde: str) -> dict[str, str]:
    """`nomes_territorio`: nome como a planilha escreve -> territorio_id, para abreviacoes ("R. G. do Norte")."""
    nomes = parametros.get("nomes_territorio") or {}
    conhecidos = set(territorios["territorio_id"])
    if not isinstance(nomes, dict) or not all(isinstance(v, str) and v in conhecidos for v in nomes.values()):
        raise ErroLayout(f"Planilha {onde}: nomes_territorio deve mapear nome para territorio_id conhecido ({nomes})")
    return {normalizar_nome(_sem_nota(str(nome))): territorio for nome, territorio in nomes.items()}


def _texto(celula) -> str:
    """Celula como texto para o filtro: inteiros sem ".0"; vazio para nulos."""
    if isinstance(celula, str):
        return _sem_nota(celula)
    if isinstance(celula, numbers.Real) and not isinstance(celula, bool):
        if math.isnan(celula):
            return ""
        return str(int(celula)) if float(celula).is_integer() else str(celula)
    return ""


def _padronizar_tabela(
    conteudo: bytes, parametros: dict, onde: str, ficha: Ficha, serie: Serie, coleta_id: str,
    territorios: pd.DataFrame,
) -> pd.DataFrame:
    membro = parametros.get("arquivo_no_zip")
    if membro:
        conteudo = _abrir_zip(conteudo, membro, onde)
    tabela = _ler_tabela(conteudo, parametros, onde)

    aba = parametros.get("aba", "-")
    coluna_territorio = str(parametros.get("coluna_territorio", ""))
    colunas = parametros.get("colunas") or []
    filtro = _filtro(parametros, onde)
    apelidos = _apelidos(parametros, territorios, onde)
    for nome in [coluna_territorio, *filtro, *(str(c["coluna"]) for c in colunas)]:
        if nome not in tabela.columns:
            raise ErroLayout(f"Planilha {onde}, aba {aba}: coluna {nome!r} não encontrada")

    registros = []
    for _, linha in tabela.iterrows():
        if any(normalizar_nome(_texto(linha[coluna])) != aceito for coluna, aceito in filtro.items()):
            continue
        nome = _sem_nota(linha[coluna_territorio])
        territorio = (apelidos.get(normalizar_nome(nome)) or territorio_por_nome(territorios, nome)) if nome else None
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
    df = normalizar_base(pd.DataFrame(registros, columns=COLUNAS_BASE))
    _sem_linhas_repetidas(df, f"{onde}, aba {aba}")
    ausentes = [t for t in parametros.get("territorios_esperados") or [] if t not in set(df.territorio_id)]
    if ausentes:
        raise ErroLayout(
            f"Planilha {onde}, aba {aba}: territórios esperados ausentes: {', '.join(ausentes)} "
            "(nome, filtro_linhas ou nomes_territorio não casaram)")
    return df
