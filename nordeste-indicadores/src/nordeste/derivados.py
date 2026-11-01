"""Derivados da base: indicadores calculados, o agregado Brasil fora do Nordeste e as metricas de convergencia."""

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


def _com_registro(linhas: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Linhas derivadas (com `insumos`) -> (linhas no formato da base, registro de derivacoes).

    Uma derivacao por indicador e serie: o registro lista os coleta_id usados e todas as linhas
    daquele indicador e serie apontam para ele.
    """
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
            **{c: linha[c] for c in ("indicador_id", *_GRUPO, "territorio_id", "ano", "valor", "serie_id")},
            "tipo_dado": "derivado",
            "coleta_id": coleta_de[(linha["indicador_id"], linha["serie_id"])], "nota": "",
        }
        for linha in linhas
    ])
    saida = normalizar_base(saida).sort_values(CHAVE_BASE, kind="stable").reset_index(drop=True)
    return saida, registro_df


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
            linhas.append({"indicador_id": ficha.id, "territorio_id": TERRITORIO_DERIVADO, **linha})
    return _com_registro(linhas)


# ---------------------------------------------------------------------------
# Indicadores calculados pelo projeto (ficha com `calculo`)
# ---------------------------------------------------------------------------

def _por_chave(linhas: pd.DataFrame, chave: list[str]) -> dict[tuple, tuple[float, str]]:
    return {
        tuple(r[c] for c in chave): (r["valor"], r["coleta_id"])
        for r in linhas[[*chave, "valor", "coleta_id"]].to_dict("records")
    }


def _linhas_razao_por_ano(base: pd.DataFrame, ficha: Ficha) -> list[dict]:
    """num / den x fator por territorio e ano, com o denominador da serie (e ano) que o mapeamento indica.

    Sem denominador mapeado, sem valor ou com denominador zero, o ano fica sem linha. Com referencia
    brasil_fora_ne, o agregado e (num_BR - num_NE) / (den_BR - den_NE) x fator, com o mesmo mapeamento.
    """
    calculo, serie_id = ficha.calculo, ficha.series[0].id
    presentes = base[base.valor.notna() & (base.territorio_id != TERRITORIO_DERIVADO)]
    chave = [*_GRUPO, "territorio_id", "serie_id", "ano"]
    numeradores = _por_chave(presentes[
        (presentes.indicador_id == calculo.numerador) & (presentes.serie_id == calculo.serie_numerador)
    ], chave)
    denominadores = _por_chave(presentes[presentes.indicador_id == calculo.denominador], chave)

    def termos(grupo: tuple, territorio: str, ano: int) -> tuple | None:
        alvo = calculo.denominador_do_ano(ano)
        num = numeradores.get((*grupo, territorio, calculo.serie_numerador, ano))
        den = denominadores.get((*grupo, territorio, *alvo)) if alvo else None
        return (num, den) if num is not None and den is not None else None

    linhas: list[dict] = []
    for (*grupo, territorio, _, ano) in sorted(numeradores):
        if not _cobre(ficha, serie_id, ano):
            continue
        achados = termos(tuple(grupo), territorio, ano)
        if achados is not None and achados[1][0] != 0:
            (num, coleta_num), (den, coleta_den) = achados
            linhas.append({
                **dict(zip(_GRUPO, grupo)), "territorio_id": territorio, "ano": ano, "serie_id": serie_id,
                "valor": num / den * calculo.fator, "insumos": (coleta_num, coleta_den),
            })
        if territorio != "BR" or ficha.comparacao.referencia != "brasil_fora_ne":
            continue
        br, ne = achados, termos(tuple(grupo), "NE", ano)
        if br is None or ne is None or br[1][0] == ne[1][0]:
            continue
        linhas.append({
            **dict(zip(_GRUPO, grupo)), "territorio_id": TERRITORIO_DERIVADO, "ano": ano, "serie_id": serie_id,
            "valor": (br[0][0] - ne[0][0]) / (br[1][0] - ne[1][0]) * calculo.fator,
            "insumos": (br[0][1], ne[0][1], br[1][1], ne[1][1]),
        })
    return linhas


_CALCULOS_DE_FICHA = {"razao_por_ano": _linhas_razao_por_ano}


def aplicar_calculos(
    base: pd.DataFrame, fichas: dict[str, Ficha],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Linhas dos indicadores cuja ficha declara `calculo`, a partir das linhas observadas da base.

    Devolve (linhas de todos os territorios com numerador e denominador no ano, mais BR_FORA_NE quando a
    referencia e brasil_fora_ne, com tipo_dado "derivado" e a serie da ficha; registro de derivacoes,
    uma linha por indicador e serie, com os coleta_id de numerador e denominador usados).
    """
    linhas: list[dict] = []
    for ficha in fichas.values():
        if ficha.calculo is None:
            continue
        for linha in _CALCULOS_DE_FICHA[ficha.calculo.metodo](base, ficha):
            linhas.append({"indicador_id": ficha.id, **linha})
    return _com_registro(linhas)


# ---------------------------------------------------------------------------
# Metricas de convergencia
# ---------------------------------------------------------------------------

_REFERENCIAS = {"brasil": "BR", "brasil_fora_ne": TERRITORIO_DERIVADO}
_ALVOS = ("NE", *UFS_NE)  # territorios que recebem razao, diferenca e crescimento relativo
_CHAVE_METRICA = [*_GRUPO, "serie_id"]


def _exigir_uma_serie(*partes: pd.DataFrame) -> None:
    series = pd.concat([p["serie_id"] for p in partes]).unique()
    if len(series) > 1:
        raise ErroSerie(
            f"a conta mistura observacoes de series diferentes: {', '.join(sorted(map(str, series)))}"
        )


def variacao_acumulada(df: pd.DataFrame, ano_base: int | None = None) -> pd.Series:
    """(v / v_ano_base - 1) * 100, indexada por ano, de uma unica serie de um unico territorio.

    `ano_base` padrao: o primeiro ano com valor. Sem valor (ou com zero) no ano-base, a serie sai vazia; anos
    anteriores ao ano-base nao entram.
    """
    _exigir_uma_serie(df)
    valores = df[df.valor.notna()].sort_values("ano").set_index("ano").valor
    if ano_base is None and not valores.empty:
        ano_base = valores.index[0]
    if ano_base not in valores.index or valores[ano_base] == 0:
        return pd.Series(dtype=float, name="valor")
    valores = valores[valores.index >= ano_base]
    return ((valores / valores[ano_base] - 1) * 100).rename("valor")


def crescimento_relativo(
    df_territorio: pd.DataFrame, df_referencia: pd.DataFrame, calendario=None,
) -> pd.Series:
    """Variacao (%) do territorio menos a da referencia entre anos publicados consecutivos, em pontos percentuais.

    `calendario`: os anos publicados da serie (anos em que algum territorio tem valor); padrao, os anos com valor
    no territorio ou na referencia. O par (anterior -> ano) so sai quando `anterior` e o ano publicado
    imediatamente anterior a `ano` e os dois tem valor no territorio e na referencia (valor anterior zero tambem
    nao gera ponto): uma lacuna nunca vira variacao de varios anos. Em serie bienal, o par e entre edicoes.
    O indice e o ano mais recente do par.
    """
    _exigir_uma_serie(df_territorio, df_referencia)
    territorio, referencia = (
        d[d.valor.notna()].drop_duplicates("ano").set_index("ano").valor for d in (df_territorio, df_referencia))
    anos = sorted(set(calendario) if calendario is not None else set(territorio.index) | set(referencia.index))
    pontos: dict[int, float] = {}
    for anterior, ano in zip(anos, anos[1:]):
        if not all(a in v.index for a in (anterior, ano) for v in (territorio, referencia)):
            continue
        if territorio[anterior] == 0 or referencia[anterior] == 0:
            continue
        pontos[ano] = (territorio[ano] / territorio[anterior] - 1) * 100 - (referencia[ano] / referencia[anterior] - 1) * 100
    return pd.Series(pontos, dtype=float, name="valor").rename_axis("ano")


def _serie_por_ano(df: pd.DataFrame) -> pd.Series:
    return df.drop_duplicates("ano").set_index("ano").valor


def _referencia_do_ano(preferida: str | None, valores: dict[str, pd.Series]):
    """Funcao ano -> territorio de referencia daquele ano (ou None).

    A referencia declarada, quando tem valor no ano; se a declarada e o Brasil fora do Nordeste e ele nao existe
    no ano, o Brasil (decisao da spec: "Brasil total nos demais").
    """
    candidatas = [] if preferida is None else [preferida]
    if preferida == TERRITORIO_DERIVADO:
        candidatas.append("BR")

    def referencia(ano: int) -> str | None:
        return next((c for c in candidatas if c in valores and ano in valores[c].index), None)
    return referencia


def _metricas_da_serie(ficha: Ficha, serie: pd.DataFrame, ident: dict) -> list[dict]:
    """Metricas de um grupo (subindicador, etapa, rede) numa unica serie_id.

    Ficha em R$ correntes (`tratamento_monetario.modo: razao`) so recebe as metricas do mesmo ano (razao,
    posicao_regioes e dispersao_ufs): variacao entre anos de valor nominal mediria inflacao.
    """
    nominal = (ficha.tratamento_monetario or {}).get("modo") == "razao"
    por_territorio = {t: g for t, g in serie.groupby("territorio_id")}
    valores = {t: _serie_por_ano(g) for t, g in por_territorio.items()}
    calendario = sorted(set(serie["ano"]))
    referencia_do_ano = _referencia_do_ano(_REFERENCIAS.get(ficha.comparacao.referencia), valores)
    linhas: list[dict] = []

    def emite(metrica: str, territorio_id: str, pontos: pd.Series, ref: str = "") -> None:
        linhas.extend(
            {**ident, "metrica": metrica, "referencia": ref, "territorio_id": territorio_id,
             "ano": int(ano), "valor": float(valor)}
            for ano, valor in pontos.dropna().items()
        )

    if not nominal:
        # ano-base comum: o primeiro ano do Brasil na serie (sem Brasil, o primeiro ano da serie)
        ano_base = valores["BR"].index.min() if "BR" in valores else calendario[0]
        for territorio_id, dados in por_territorio.items():
            emite("variacao_acumulada", territorio_id, variacao_acumulada(dados, ano_base))

    for alvo in _ALVOS:
        if alvo not in por_territorio:
            continue
        for ref in sorted({referencia_do_ano(a) for a in calendario} - {None}):
            anos_da_ref = [a for a in calendario if referencia_do_ano(a) == ref]
            valor_t = valores[alvo][valores[alvo].index.isin(anos_da_ref)]
            valor_r = valores[ref]
            emite("razao", alvo, valor_t / valor_r.where(valor_r != 0) * 100, ref)
            if nominal:
                continue
            emite("diferenca", alvo, valor_t - valor_r, ref)
            cresc = crescimento_relativo(por_territorio[alvo], por_territorio[ref], calendario)
            emite("crescimento_relativo", alvo, cresc[cresc.index.isin(anos_da_ref)], ref)

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
        validas = base[(base.indicador_id == ficha.id) & (base.tipo_dado != "indisponivel") & base.valor.notna()]
        for chaves, serie in validas.groupby(_CHAVE_METRICA, sort=True):
            ident = {"indicador_id": ficha.id, **dict(zip(_CHAVE_METRICA, chaves))}
            linhas.extend(_metricas_da_serie(ficha, serie, ident))

    saida = pd.DataFrame(linhas, columns=COLUNAS_DERIVADOS)
    saida["ano"] = saida["ano"].astype(int)
    saida["valor"] = saida["valor"].astype(float)
    ordem = [c for c in COLUNAS_DERIVADOS if c != "valor"]
    return saida.sort_values(ordem, kind="stable").reset_index(drop=True)
