"""Derivados da base: o agregado Brasil fora do Nordeste e, adiante, as metricas de convergencia."""

import hashlib

import pandas as pd

from nordeste.esquema import CHAVE_BASE, COLUNAS_BASE, normalizar_base
from nordeste.fichas import Ficha

TERRITORIO_DERIVADO = "BR_FORA_NE"
COLUNAS_REGISTRO: list[str] = ["coleta_id", "indicador_id", "serie_id", "insumos"]

_GRUPO = ["subindicador", "etapa", "rede"]


class ErroSerie(ValueError):
    """Uma conta tentou misturar observacoes de series (serie_id) diferentes."""


# ---------------------------------------------------------------------------
# Brasil fora do Nordeste
# ---------------------------------------------------------------------------

def _diferencas_br_ne(base: pd.DataFrame, indicador_id: str) -> pd.DataFrame:
    """BR - NE de um indicador, por grupo, ano e serie, so onde os dois valores existem.

    Devolve as colunas _GRUPO, ano, serie_id, valor e insumos (tupla com os coleta_id de BR e NE).
    """
    chaves = [*_GRUPO, "ano", "serie_id"]
    presentes = base[(base.indicador_id == indicador_id) & base.valor.notna()]
    br = presentes[presentes.territorio_id == "BR"][[*chaves, "valor", "coleta_id"]]
    ne = presentes[presentes.territorio_id == "NE"][[*chaves, "valor", "coleta_id"]]
    junto = br.merge(ne, on=chaves, suffixes=("_br", "_ne"))
    junto["valor"] = junto.valor_br - junto.valor_ne
    junto["insumos"] = list(zip(junto.coleta_id_br, junto.coleta_id_ne))
    return junto[[*chaves, "valor", "insumos"]]


def _termo(base: pd.DataFrame, indicador_id: str) -> pd.DataFrame:
    """Diferenca BR - NE de um termo de razao, sem a coluna de serie (uma linha por grupo e ano)."""
    termo = _diferencas_br_ne(base, indicador_id)
    repetidos = termo.duplicated([*_GRUPO, "ano"], keep=False)
    if repetidos.any():
        anos = sorted(termo[repetidos].ano.unique().tolist())
        raise ErroSerie(
            f"O indicador {indicador_id!r} tem mais de uma serie nos anos {anos}; "
            "uma razao nao pode misturar series."
        )
    return termo.drop(columns="serie_id")


def _linhas_soma(base: pd.DataFrame, ficha: Ficha) -> list[dict]:
    return _diferencas_br_ne(base, ficha.id).to_dict("records")


def _linhas_razao(base: pd.DataFrame, ficha: Ficha) -> list[dict]:
    comp = ficha.comparacao
    junto = _termo(base, comp.numerador).merge(
        _termo(base, comp.denominador), on=[*_GRUPO, "ano"], suffixes=("_num", "_den"),
    )
    junto = junto[junto.valor_den != 0]
    linhas: list[dict] = []
    for r in junto.to_dict("records"):
        serie = ficha.serie_do_ano(r["ano"])
        if serie is None:
            continue
        linhas.append({
            **{c: r[c] for c in _GRUPO}, "ano": r["ano"], "serie_id": serie.id,
            "valor": r["valor_num"] / r["valor_den"] * comp.fator,
            "insumos": (*r["insumos_num"], *r["insumos_den"]),
        })
    return linhas


def _linhas_razao_encadeada(base: pd.DataFrame, ficha: Ficha) -> list[dict]:
    comp = ficha.comparacao
    numeradores = {
        (r["subindicador"], r["etapa"], r["rede"], r["ano"]): r
        for r in _termo(base, comp.numerador).to_dict("records")
    }
    denominadores = {
        (r["subindicador"], r["etapa"], r["rede"], r["ano"]): r
        for r in _termo(base, comp.denominador).to_dict("records")
    }
    anos_com_dado = [chave[3] for chave in (*numeradores, *denominadores)]
    if not anos_com_dado:
        return []
    ultimo_ano = max(anos_com_dado)
    grupos = {chave[:3] for chave in denominadores}

    linhas: list[dict] = []
    for grupo in sorted(grupos):
        for serie in ficha.series:
            anos_da_serie = {
                a for a in range(serie.inicio, ultimo_ano + 1)
                if (dona := ficha.serie_do_ano(a)) is not None and dona.id == serie.id
            }
            ancoras = sorted(a for a in anos_da_serie if (*grupo, a) in denominadores)
            if not ancoras:
                continue
            ano, indice = ancoras[0], 100.0
            insumos = denominadores[(*grupo, ano)]["insumos"]
            while True:
                linhas.append({
                    **dict(zip(_GRUPO, grupo)), "ano": ano, "serie_id": serie.id,
                    "valor": indice, "insumos": insumos,
                })
                ano += 1
                num = numeradores.get((*grupo, ano))
                den = denominadores.get((*grupo, ano - 1))
                if ano not in anos_da_serie or num is None or den is None or den["valor"] == 0:
                    break
                indice = indice * num["valor"] / den["valor"]  # multiplica antes de dividir: 100 * 88 / 80 sai exato
                insumos = (*num["insumos"], *den["insumos"])
    return linhas


_CALCULOS = {
    "soma": _linhas_soma,
    "razao": _linhas_razao,
    "razao_encadeada": _linhas_razao_encadeada,
}


def _id_da_derivacao(indicador_id: str, serie_id: str, insumos: str) -> str:
    resumo = hashlib.sha256(insumos.encode("utf-8")).hexdigest()[:8]
    return f"deriv.{indicador_id}.{serie_id}.{resumo}"


def brasil_fora_ne(
    base: pd.DataFrame, fichas: dict[str, Ficha],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calcula o agregado BR_FORA_NE dos indicadores cuja ficha define um metodo exato.

    Devolve (linhas BR_FORA_NE no formato da base, com tipo_dado "derivado";
    registro de derivacoes, uma linha por indicador e serie, listando os coleta_id usados).
    Fichas com outra referencia, ou sem metodo, nao geram linhas.
    """
    linhas: list[dict] = []
    for ficha in fichas.values():
        comp = ficha.comparacao
        if comp.referencia != "brasil_fora_ne" or comp.metodo not in _CALCULOS:
            continue
        for linha in _CALCULOS[comp.metodo](base, ficha):
            linhas.append({"indicador_id": ficha.id, **linha})

    if not linhas:
        return (
            normalizar_base(pd.DataFrame(columns=COLUNAS_BASE)),
            pd.DataFrame(columns=COLUNAS_REGISTRO),
        )

    insumos_por_serie: dict[tuple[str, str], set[str]] = {}
    for linha in linhas:
        insumos_por_serie.setdefault((linha["indicador_id"], linha["serie_id"]), set()).update(linha["insumos"])
    registro = []
    for (indicador_id, serie_id), coletas in sorted(insumos_por_serie.items()):
        insumos = ";".join(sorted(coletas))
        registro.append({
            "coleta_id": _id_da_derivacao(indicador_id, serie_id, insumos),
            "indicador_id": indicador_id, "serie_id": serie_id, "insumos": insumos,
        })
    registro_df = pd.DataFrame(registro, columns=COLUNAS_REGISTRO)
    coleta_de = {(r["indicador_id"], r["serie_id"]): r["coleta_id"] for r in registro}

    saida = pd.DataFrame([
        {
            **{c: linha[c] for c in ("indicador_id", *_GRUPO, "ano", "valor", "serie_id")},
            "territorio_id": TERRITORIO_DERIVADO, "tipo_dado": "derivado",
            "coleta_id": coleta_de[(linha["indicador_id"], linha["serie_id"])], "nota": "",
        }
        for linha in linhas
    ])
    saida = normalizar_base(saida).sort_values(CHAVE_BASE, kind="stable").reset_index(drop=True)
    return saida, registro_df
