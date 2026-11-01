"""Derivados da base: o agregado Brasil fora do Nordeste e as metricas de convergencia."""

import hashlib

import pandas as pd

from nordeste.esquema import CHAVE_BASE, COLUNAS_BASE, COLUNAS_DERIVADOS, normalizar_base
from nordeste.fichas import Ficha
from nordeste.territorios import REGIOES, UFS_NE

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


def _linhas_soma(base: pd.DataFrame, ficha: Ficha) -> list[dict]:
    return _diferencas_br_ne(base, ficha.id).to_dict("records")


def _cobre(ficha: Ficha, serie_id: str, ano: int) -> bool:
    """A serie esta declarada na ficha do indicador e cobre o ano (fim nulo = em curso)?"""
    return any(
        s.id == serie_id and s.inicio <= ano and (s.fim is None or ano <= s.fim)
        for s in ficha.series
    )


def _linhas_razao(base: pd.DataFrame, ficha: Ficha) -> list[dict]:
    comp = ficha.comparacao
    junto = _diferencas_br_ne(base, comp.numerador).merge(
        _diferencas_br_ne(base, comp.denominador),
        on=[*_GRUPO, "ano", "serie_id"], suffixes=("_num", "_den"),
    )
    junto = junto[junto.valor_den != 0]
    return [
        {
            **{c: r[c] for c in _GRUPO}, "ano": r["ano"], "serie_id": r["serie_id"],
            "valor": r["valor_num"] / r["valor_den"] * comp.fator,
            "insumos": (*r["insumos_num"], *r["insumos_den"]),
        }
        for r in junto.to_dict("records")
        if _cobre(ficha, r["serie_id"], r["ano"])
    ]


def _por_grupo_serie_ano(diferencas: pd.DataFrame) -> dict[tuple, dict]:
    return {
        (r["subindicador"], r["etapa"], r["rede"], r["serie_id"], r["ano"]): r
        for r in diferencas.to_dict("records")
    }


def _linhas_razao_encadeada(base: pd.DataFrame, ficha: Ficha) -> list[dict]:
    """Indice encadeado, uma cadeia por (grupo, serie): so encadeia dentro da mesma serie_id."""
    comp = ficha.comparacao
    numeradores = _por_grupo_serie_ano(_diferencas_br_ne(base, comp.numerador))
    denominadores = _por_grupo_serie_ano(_diferencas_br_ne(base, comp.denominador))

    linhas: list[dict] = []
    for subindicador, etapa, rede, serie_id in sorted({k[:4] for k in denominadores}):
        grupo = (subindicador, etapa, rede, serie_id)
        ancoras = sorted(
            k[4] for k in denominadores if k[:4] == grupo and _cobre(ficha, serie_id, k[4])
        )
        if not ancoras:
            continue
        ano, indice = ancoras[0], 100.0
        insumos = denominadores[(*grupo, ano)]["insumos"]
        while True:
            linhas.append({
                "subindicador": subindicador, "etapa": etapa, "rede": rede,
                "ano": ano, "serie_id": serie_id, "valor": indice, "insumos": insumos,
            })
            ano += 1
            num = numeradores.get((*grupo, ano))
            den = denominadores.get((*grupo, ano - 1))
            if num is None or den is None or den["valor"] == 0 or not _cobre(ficha, serie_id, ano):
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


# ---------------------------------------------------------------------------
# Metricas de convergencia
# ---------------------------------------------------------------------------

_REFERENCIAS = {"brasil": "BR", "brasil_fora_ne": TERRITORIO_DERIVADO}
_ALVOS = ("NE", *UFS_NE)  # territorios que recebem razao, diferenca, variacao e crescimento
_CHAVE_METRICA = [*_GRUPO, "serie_id"]


def _exigir_uma_serie(*partes: pd.DataFrame) -> None:
    series = pd.concat([p["serie_id"] for p in partes]).unique()
    if len(series) > 1:
        raise ErroSerie(
            f"a conta mistura observacoes de series diferentes: {', '.join(sorted(map(str, series)))}"
        )


def _variacoes_pct(valores: pd.Series) -> pd.Series:
    """Variacao percentual entre observacoes consecutivas; valor anterior nulo ou zero nao gera ponto."""
    anterior = valores.shift(1)
    return ((valores / anterior - 1) * 100).where(anterior != 0).dropna()


def variacao_acumulada(df: pd.DataFrame) -> pd.Series:
    """(v / v_primeiro - 1) * 100, indexada por ano, de uma unica serie de um unico territorio."""
    _exigir_uma_serie(df)
    valores = df[df.valor.notna()].sort_values("ano").set_index("ano").valor
    if valores.empty or valores.iloc[0] == 0:
        return pd.Series(dtype=float, name="valor")
    return ((valores / valores.iloc[0] - 1) * 100).rename("valor")


def crescimento_relativo(df_territorio: pd.DataFrame, df_referencia: pd.DataFrame) -> pd.Series:
    """Variacao (%) do territorio menos a da referencia entre observacoes consecutivas, em pontos percentuais.

    So conta os anos observados nas duas series; o indice e o ano da observacao mais recente do par.
    """
    _exigir_uma_serie(df_territorio, df_referencia)
    validos = [d[d.valor.notna()].drop_duplicates("ano").set_index("ano").valor for d in (df_territorio, df_referencia)]
    comuns = validos[0].index.intersection(validos[1].index).sort_values()
    territorio, referencia = (_variacoes_pct(v.loc[comuns]) for v in validos)
    return (territorio - referencia).dropna().rename("valor")


def _serie_por_ano(df: pd.DataFrame) -> pd.Series:
    return df.drop_duplicates("ano").set_index("ano").valor


def _metricas_da_serie(ficha: Ficha, serie: pd.DataFrame, ident: dict) -> list[dict]:
    """Metricas de um grupo (subindicador, etapa, rede) numa unica serie_id."""
    referencia = _REFERENCIAS.get(ficha.comparacao.referencia)
    por_territorio = {t: g for t, g in serie.groupby("territorio_id")}
    linhas: list[dict] = []

    def emite(metrica: str, territorio_id: str, valores: pd.Series, ref: str = "") -> None:
        linhas.extend(
            {**ident, "metrica": metrica, "referencia": ref, "territorio_id": territorio_id,
             "ano": int(ano), "valor": float(valor)}
            for ano, valor in valores.dropna().items()
        )

    for alvo in _ALVOS:
        if alvo not in por_territorio:
            continue
        emite("variacao_acumulada", alvo, variacao_acumulada(por_territorio[alvo]))
        if referencia is None or referencia not in por_territorio:
            continue
        t, r = por_territorio[alvo], por_territorio[referencia]
        valor_t = _serie_por_ano(t)
        valor_r = _serie_por_ano(r)
        valor_r_sem_zero = valor_r.where(valor_r != 0)
        emite("razao", alvo, valor_t / valor_r_sem_zero * 100, referencia)
        emite("diferenca", alvo, valor_t - valor_r, referencia)
        emite("crescimento_relativo", alvo, crescimento_relativo(t, r), referencia)

    regioes = _anos_completos(serie, REGIOES)
    if not regioes.empty:
        menor_melhor = ficha.sentido == "menor_melhor"
        emite("posicao_regioes", "NE", regioes.rank(axis=1, method="min", ascending=menor_melhor)["NE"])

    ufs = _anos_completos(serie, UFS_NE)
    if not ufs.empty:
        media = ufs.mean(axis=1)
        emite("dispersao_ufs", "NE", ufs.std(axis=1, ddof=0) / media.where(media != 0) * 100)
    return linhas


def _anos_completos(serie: pd.DataFrame, territorios: tuple[str, ...]) -> pd.DataFrame:
    """Valores por ano (linhas) e territorio (colunas), so dos anos em que todos os territorios existem."""
    ano_x_territorio = serie[serie.territorio_id.isin(territorios)].pivot_table(
        index="ano", columns="territorio_id", values="valor", aggfunc="first",
    )
    if not set(territorios) <= set(ano_x_territorio.columns):
        return ano_x_territorio.iloc[0:0]
    return ano_x_territorio[list(territorios)].dropna()


def metricas_convergencia(
    base: pd.DataFrame, fichas: dict[str, Ficha], territorios: pd.DataFrame,
) -> pd.DataFrame:
    """Metricas de convergencia (esquema COLUNAS_DERIVADOS) de todos os indicadores nao auxiliares.

    Cada conta fica dentro de um unico serie_id; linhas indisponivel nao entram. `territorios` e a
    tabela oficial: todos os territorios usados nas contas precisam existir nela.
    """
    usados = {*REGIOES, *UFS_NE, "BR", TERRITORIO_DERIVADO}
    desconhecidos = sorted(usados - set(territorios["territorio_id"]))
    if desconhecidos:
        raise ValueError(f"territorios ausentes da tabela de territorios: {', '.join(desconhecidos)}")

    linhas: list[dict] = []
    for ficha in fichas.values():
        if ficha.auxiliar:
            continue
        validas = base[(base.indicador_id == ficha.id) & base.valor.notna()]
        for chaves, serie in validas.groupby(_CHAVE_METRICA, sort=True):
            ident = {"indicador_id": ficha.id, **dict(zip(_CHAVE_METRICA, chaves))}
            linhas.extend(_metricas_da_serie(ficha, serie, ident))

    saida = pd.DataFrame(linhas, columns=COLUNAS_DERIVADOS)
    saida["ano"] = saida["ano"].astype(int)
    saida["valor"] = saida["valor"].astype(float)
    ordem = [c for c in COLUNAS_DERIVADOS if c != "valor"]
    return saida.sort_values(ordem, kind="stable").reset_index(drop=True)
