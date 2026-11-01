"""Validacao bloqueante da base (regras R01 a R10): aponta problemas, nao corrige dados."""

import calendar
import math
from dataclasses import dataclass
from datetime import date

import pandas as pd

from nordeste.cobertura import proxima_publicacao
from nordeste.derivados import TERRITORIO_DERIVADO, _cobre
from nordeste.esquema import CHAVE_BASE, COLUNAS_BASE, COLUNAS_DERIVADOS, METRICAS, TIPOS_DADO
from nordeste.fichas import Ficha
from nordeste.territorios import REGIOES, UFS_NE

TOLERANCIA = 0.005  # relativa, regras R07 e R08
MAX_EXEMPLOS = 5

_GRUPO = ["subindicador", "etapa", "rede"]
_TEXTO = ["indicador_id", *_GRUPO, "territorio_id", "tipo_dado", "serie_id", "coleta_id", "nota"]


@dataclass(frozen=True)
class Falha:
    regra: str
    mensagem: str


@dataclass
class ResultadoValidacao:
    erros: list[Falha]
    avisos: list[Falha]

    @property
    def aprovado(self) -> bool:
        return not self.erros

    def para_dataframe(self) -> pd.DataFrame:
        linhas = [("erro", f.regra, f.mensagem) for f in self.erros]
        linhas += [("aviso", f.regra, f.mensagem) for f in self.avisos]
        return pd.DataFrame(linhas, columns=["nivel", "regra", "mensagem"])


# ---------------------------------------------------------------------------
# Auxiliares de mensagem
# ---------------------------------------------------------------------------

def _rotulo(indicador_id: str, serie_id: str, subindicador: str = "", etapa: str = "", rede: str = "") -> str:
    partes = [f"serie {serie_id}"] + [
        f"{nome} {valor}" for nome, valor in (("subindicador", subindicador), ("etapa", etapa), ("rede", rede)) if valor
    ]
    return f"{indicador_id} ({', '.join(partes)})"


def _agregar(regra: str, linhas: pd.DataFrame, problema: str) -> list[Falha]:
    """Uma falha por (indicador, serie), com ate MAX_EXEMPLOS exemplos de territorio e ano."""
    falhas = []
    for (indicador_id, serie_id), grupo in linhas.groupby(["indicador_id", "serie_id"], sort=True, dropna=False):
        primeiros = grupo.head(MAX_EXEMPLOS)
        exemplos = ", ".join(f"{t} {a}" for t, a in zip(primeiros.territorio_id, primeiros.ano))
        if len(grupo) > MAX_EXEMPLOS:
            exemplos += ", ..."
        falhas.append(Falha(
            regra, f"{_rotulo(indicador_id, serie_id)}: {problema} em {len(grupo)} linha(s); exemplos: {exemplos}",
        ))
    return falhas


def _diverge(oficial: float, calculado: float) -> bool:
    """Diferenca relativa acima da tolerancia; qualquer termo nao finito (inf, nan) diverge."""
    if not (math.isfinite(oficial) and math.isfinite(calculado)):
        return True
    if oficial == 0:
        return calculado != 0
    return abs(oficial - calculado) / abs(oficial) > TOLERANCIA


def _pct(oficial: float, calculado: float) -> str:
    if oficial == 0 or not (math.isfinite(oficial) and math.isfinite(calculado)):
        return "inf"
    return f"{abs(oficial - calculado) / abs(oficial) * 100:.2f}%"


# ---------------------------------------------------------------------------
# Regras
# ---------------------------------------------------------------------------

def _r01_fixture(base: pd.DataFrame, coletas: pd.DataFrame, derivacoes: pd.DataFrame) -> list[Falha]:
    """Linhas cuja coleta, direta ou pelos insumos da derivacao, tem origem fixture. Uma falha por coleta_id."""
    fixtures = set(coletas.loc[coletas.origem == "fixture", "coleta_id"])
    insumos_fixture = {
        d.coleta_id: sorted(set(d.insumos.split(";")) & fixtures) for d in derivacoes.itertuples()
    }
    falhas = []
    for coleta_id, linhas in base.groupby("coleta_id", sort=True):
        indicadores = ", ".join(sorted(map(str, linhas.indicador_id.unique())))
        if coleta_id in fixtures:
            falhas.append(Falha(
                "R01", f"coleta {coleta_id} tem origem fixture e alimenta {len(linhas)} linha(s) da base ({indicadores})",
            ))
        elif insumos_fixture.get(coleta_id):
            falhas.append(Falha(
                "R01", f"derivacao {coleta_id} usa insumo(s) de origem fixture ({', '.join(insumos_fixture[coleta_id])}) "
                       f"e alimenta {len(linhas)} linha(s) da base ({indicadores})",
            ))
    return falhas


def _r02_estrutura(base: pd.DataFrame) -> list[Falha]:
    """Sem as colunas do esquema, ou sem linhas, nenhuma regra de linha pode ser avaliada."""
    if list(base.columns) != COLUNAS_BASE:
        return [Falha("R02", f"colunas da base diferem do esquema: esperado {', '.join(COLUNAS_BASE)}; "
                             f"encontrado {', '.join(map(str, base.columns))}")]
    if base.empty:
        return [Falha("R02", "base sem linhas")]
    return []


def _r02_tipos(base: pd.DataFrame) -> list[Falha]:
    """Sem ano inteiro, valor numerico e texto sem nulos as demais regras de linha nao podem ser avaliadas."""
    falhas = []
    for coluna in _TEXTO:
        falhas += _agregar("R02", base[base[coluna].isna()], f"{coluna} nulo (texto vazio deve ser \"\")")
    if not pd.api.types.is_integer_dtype(base.ano):
        falhas.append(Falha("R02", f"coluna ano deve ser inteira (tipo encontrado: {base.ano.dtype})"))
    if not pd.api.types.is_numeric_dtype(base.valor):
        falhas.append(Falha("R02", f"coluna valor deve ser numerica (tipo encontrado: {base.valor.dtype})"))
    return falhas


def _r02_linhas(base: pd.DataFrame, fichas: dict[str, Ficha], conhecidos: set[str]) -> list[Falha]:
    falhas = _agregar("R02", base[~base.tipo_dado.isin(TIPOS_DADO)], "tipo_dado fora do dominio")
    falhas += _agregar("R02", base[base.valor.abs() == math.inf], "valor nao finito (infinito)")
    falhas += _agregar("R02", base[~base.territorio_id.isin(conhecidos)], "territorio_id desconhecido")
    falhas += _agregar("R02", base[~base.indicador_id.isin(fichas)], "indicador_id sem ficha")
    return falhas


def _r02_derivados(derivados: pd.DataFrame, fichas: dict[str, Ficha], conhecidos: set[str]) -> list[Falha]:
    if list(derivados.columns) != COLUNAS_DERIVADOS:
        return [Falha("R02", f"colunas dos derivados diferem do esquema: esperado {', '.join(COLUNAS_DERIVADOS)}; "
                             f"encontrado {', '.join(map(str, derivados.columns))}")]
    falhas = _agregar("R02", derivados[~derivados.metrica.isin(METRICAS)], "metrica desconhecida nos derivados")
    falhas += _agregar("R02", derivados[~derivados.territorio_id.isin(conhecidos)], "territorio_id desconhecido nos derivados")
    falhas += _agregar("R02", derivados[~derivados.indicador_id.isin(fichas)], "indicador_id sem ficha nos derivados")
    return falhas


def _r03_chave(base: pd.DataFrame) -> list[Falha]:
    return _agregar("R03", base[base.duplicated(CHAVE_BASE, keep=False)], "chave duplicada")


def _r04_nulo(base: pd.DataFrame) -> list[Falha]:
    nulo, indisponivel = base.valor.isna(), base.tipo_dado == "indisponivel"
    return (
        _agregar("R04", base[nulo & ~indisponivel], "valor nulo com tipo_dado diferente de indisponivel")
        + _agregar("R04", base[~nulo & indisponivel], "valor preenchido com tipo_dado indisponivel")
    )


def _r05_serie(base: pd.DataFrame, fichas: dict[str, Ficha]) -> list[Falha]:
    falhas = []
    for indicador_id, linhas in base[base.indicador_id.isin(fichas)].groupby("indicador_id", sort=True):
        ficha = fichas[indicador_id]
        declaradas = {s.id for s in ficha.series}
        falhas += _agregar("R05", linhas[~linhas.serie_id.isin(declaradas)], "serie nao declarada na ficha")
        fora = [s in declaradas and not _cobre(ficha, s, a) for s, a in zip(linhas.serie_id, linhas.ano)]
        for serie_id, grupo in linhas[fora].groupby("serie_id", sort=True):
            serie = ficha.serie(serie_id)
            cobertura = f"[{serie.inicio}, {serie.fim if serie.fim is not None else 'em curso'}]"
            falhas += _agregar("R05", grupo, f"ano fora da cobertura da serie {cobertura}")
    return falhas


def _r06_limites(base: pd.DataFrame, fichas: dict[str, Ficha]) -> list[Falha]:
    falhas = []
    presentes = base[base.indicador_id.isin(fichas) & base.valor.notna()]
    for indicador_id, linhas in presentes.groupby("indicador_id", sort=True):
        limites = fichas[indicador_id].limites
        fora = pd.Series(False, index=linhas.index)
        if "min" in limites:
            fora |= linhas.valor < limites["min"]
        if "max" in limites:
            fora |= linhas.valor > limites["max"]
        descricao = ", ".join(f"{k} {v}" for k, v in sorted(limites.items()))
        falhas += _agregar("R06", linhas[fora], f"valor fora dos limites da ficha ({descricao})")
    return falhas


def _valores_por_ano(linhas: pd.DataFrame) -> pd.DataFrame:
    """Valores finitos por (grupo, ano, serie) nas linhas e por territorio nas colunas.

    Nulos e infinitos ficam de fora (infinito ja bloqueia em R02); o ano fica incompleto.
    """
    return linhas[linhas.valor.abs() < math.inf].pivot_table(
        index=[*_GRUPO, "ano", "serie_id"], columns="territorio_id", values="valor", aggfunc="first",
    )


def _r07_soma(base: pd.DataFrame, fichas: dict[str, Ficha]) -> list[Falha]:
    """UFs -> NE e regioes -> BR, so nos anos em que todas as partes e o total tem valor."""
    conferencias = (("NE", UFS_NE, "das 9 UFs"), ("BR", REGIOES, "das 5 regioes"))
    falhas = []
    for ficha in fichas.values():
        if ficha.comparacao.metodo != "soma":
            continue
        linhas = base[(base.indicador_id == ficha.id) & (base.territorio_id != TERRITORIO_DERIVADO)]
        tabela = _valores_por_ano(linhas)
        for total, partes, nome in conferencias:
            if not {total, *partes} <= set(tabela.columns):
                continue
            completos = tabela[[total, *partes]].dropna()
            for (subindicador, etapa, rede, ano, serie_id), valores in completos.iterrows():
                oficial, soma = valores[total], valores[list(partes)].sum()
                if _diverge(oficial, soma):
                    falhas.append(Falha("R07", (
                        f"{_rotulo(ficha.id, serie_id, subindicador, etapa, rede)} {total} {ano}: "
                        f"soma {nome} = {soma:g} difere de {total} = {oficial:g} ({_pct(oficial, soma)})"
                    )))
    return falhas


def _r08_razao(base: pd.DataFrame, fichas: dict[str, Ficha]) -> list[Falha]:
    """Valor oficial do NE contra num_NE / den_NE * fator, no mesmo grupo e na mesma serie_id."""
    chaves = [*_GRUPO, "ano", "serie_id"]
    ne = base[(base.territorio_id == "NE") & base.valor.notna()]
    falhas = []
    for ficha in fichas.values():
        comp = ficha.comparacao
        if comp.metodo != "razao":
            continue
        termos = [ne[ne.indicador_id == i][[*chaves, "valor"]].rename(columns={"valor": nome})
                  for i, nome in ((ficha.id, "oficial"), (comp.numerador, "num"), (comp.denominador, "den"))]
        junto = termos[0].merge(termos[1], on=chaves).merge(termos[2], on=chaves)
        for r in junto.to_dict("records"):
            onde = f"{_rotulo(ficha.id, r['serie_id'], r['subindicador'], r['etapa'], r['rede'])} NE {r['ano']}"
            if r["den"] == 0:
                falhas.append(Falha("R08", (
                    f"{onde}: oficial = {r['oficial']:g}, mas {comp.denominador} do NE e zero; "
                    f"nao ha como recalcular {comp.numerador} / {comp.denominador}"
                )))
                continue
            calculado = r["num"] / r["den"] * comp.fator
            if _diverge(r["oficial"], calculado):
                falhas.append(Falha("R08", (
                    f"{onde}: "
                    f"oficial = {r['oficial']:g}, recalculado {comp.numerador} / {comp.denominador} x {comp.fator:g} "
                    f"= {calculado:g} ({_pct(r['oficial'], calculado)})"
                )))
    return falhas


def _r09_registro(base: pd.DataFrame, coletas: pd.DataFrame, derivacoes: pd.DataFrame) -> list[Falha]:
    registrados = set(coletas.coleta_id) | set(derivacoes.coleta_id)
    falhas = []
    for coleta_id, linhas in base[~base.coleta_id.isin(registrados)].groupby("coleta_id", sort=True, dropna=False):
        indicadores = ", ".join(sorted(linhas.indicador_id.unique()))
        falhas.append(Falha(
            "R09", f"coleta_id {coleta_id!r} ausente dos registros de coletas e de derivacoes "
                   f"({len(linhas)} linha(s) de {indicadores})",
        ))
    return falhas


def _r10_fichas(falhas_fichas: list[str]) -> list[Falha]:
    return [Falha("R10", mensagem) for mensagem in falhas_fichas]


# ---------------------------------------------------------------------------
# Avisos (nao bloqueiam a publicacao)
# ---------------------------------------------------------------------------

def _a01_salto(base: pd.DataFrame, fichas: dict[str, Ficha]) -> list[Falha]:
    """Variacao percentual absoluta acima do limiar entre observacoes validas consecutivas.

    "Consecutivas" ignora anos sem valor: a comparacao vai de uma observacao valida a proxima da mesma
    serie, territorio e grupo (subindicador, etapa, rede). Fichas auxiliares nao sao avaliadas.
    """
    elegiveis = [i for i, f in fichas.items() if not f.auxiliar]
    validas = base[base.indicador_id.isin(elegiveis) & base.valor.notna() & (base.valor.abs() < math.inf)]
    ordem = ["indicador_id", "serie_id", *_GRUPO, "territorio_id"]
    validas = validas.sort_values([*ordem, "ano"])
    anterior = validas.groupby(ordem, sort=False)[["valor", "ano"]].shift()
    variacao = (validas.valor - anterior.valor).abs() / anterior.valor.abs() * 100
    limiar = validas.indicador_id.map({i: fichas[i].limiar_salto_pct for i in elegiveis})
    saltos = validas.assign(variacao=variacao, ano_anterior=anterior.ano)[variacao > limiar]
    falhas = []
    for (indicador_id, serie_id), grupo in saltos.groupby(["indicador_id", "serie_id"], sort=True):
        exemplos = ", ".join(
            f"{'/'.join(filter(None, (r.subindicador, r.etapa, r.rede, r.territorio_id)))} "
            f"{int(r.ano_anterior)}->{r.ano} ({r.variacao:.1f}%)"
            for r in grupo.head(MAX_EXEMPLOS).itertuples()
        )
        if len(grupo) > MAX_EXEMPLOS:
            exemplos += ", ..."
        falhas.append(Falha("A01", (
            f"{_rotulo(indicador_id, serie_id)}: variacao acima de {fichas[indicador_id].limiar_salto_pct:g}% "
            f"entre observacoes consecutivas em {len(grupo)} caso(s); exemplos: {exemplos}"
        )))
    return falhas


def _a02_alteracoes(base: pd.DataFrame, base_publicada: pd.DataFrame | None) -> list[Falha]:
    """Valores das linhas presentes nas duas bases (mesma chave) que mudaram desde a ultima publicacao."""
    if base_publicada is None:
        return []
    atual = base.drop_duplicates(CHAVE_BASE)[[*CHAVE_BASE, "valor"]]
    anterior = base_publicada.drop_duplicates(CHAVE_BASE)[[*CHAVE_BASE, "valor"]]
    junto = atual.merge(anterior, on=CHAVE_BASE, suffixes=("", "_publicado"))
    iguais = (junto.valor == junto.valor_publicado) | (junto.valor.isna() & junto.valor_publicado.isna())
    alterados = junto[~iguais]
    if alterados.empty:
        return []
    indicadores = ", ".join(sorted(alterados.indicador_id.unique()))
    return [Falha("A02", f"{len(alterados)} valores alterados em relacao a base publicada ({indicadores})")]


def _a03_atraso(base: pd.DataFrame, fichas: dict[str, Ficha], hoje: date) -> list[Falha]:
    """Serie em curso cuja proxima publicacao prevista ja passou, a partir do ultimo ano com valor do NE."""
    ne = base[(base.territorio_id == "NE") & base.valor.notna()]
    falhas = []
    for indicador_id in sorted(fichas):
        ficha = fichas[indicador_id]
        for serie in ficha.series:
            if serie.fim is not None:
                continue
            anos = ne.loc[(ne.indicador_id == indicador_id) & (ne.serie_id == serie.id), "ano"]
            if anos.empty:
                continue
            ultimo = int(anos.max())
            previsto = proxima_publicacao(ultimo, ficha.defasagem_meses)
            ano, mes = map(int, previsto.split("-"))
            if hoje > date(ano, mes, calendar.monthrange(ano, mes)[1]):
                falhas.append(Falha("A03", (
                    f"{_rotulo(indicador_id, serie.id)}: ultimo ano com valor do NE e {ultimo}; "
                    f"a proxima publicacao, prevista para {previsto}, ja passou (hoje {hoje.isoformat()})"
                )))
    return falhas


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------

def validar(
    base: pd.DataFrame,
    derivados: pd.DataFrame,
    fichas: dict[str, Ficha],
    falhas_fichas: list[str],
    territorios: pd.DataFrame,
    coletas: pd.DataFrame,
    derivacoes: pd.DataFrame,
    base_publicada: pd.DataFrame | None,
    hoje: date,
) -> ResultadoValidacao:
    """Aplica as regras bloqueantes R01 a R10 aos DataFrames ja carregados.

    `base_publicada` e `hoje` alimentam os avisos A01 a A03, que nao afetam `aprovado` e so sao
    calculados quando a estrutura e os tipos da base permitem. A regra R01 (dado de fixture) nao tem como ser desligada.
    """
    erros = _r02_estrutura(base)
    avisos: list[Falha] = []
    if not erros:
        erros = _r01_fixture(base, coletas, derivacoes)
        tipos = _r02_tipos(base)
        erros += tipos
        if not tipos:
            avisos = _a01_salto(base, fichas) + _a02_alteracoes(base, base_publicada) + _a03_atraso(base, fichas, hoje)
            conhecidos = set(territorios.territorio_id)
            erros += (
                _r02_linhas(base, fichas, conhecidos)
                + _r02_derivados(derivados, fichas, conhecidos)
                + _r03_chave(base)
                + _r04_nulo(base)
                + _r05_serie(base, fichas)
                + _r06_limites(base, fichas)
                + _r07_soma(base, fichas)
                + _r08_razao(base, fichas)
                + _r09_registro(base, coletas, derivacoes)
            )
    erros += _r10_fichas(falhas_fichas)
    return ResultadoValidacao(erros=erros, avisos=avisos)
