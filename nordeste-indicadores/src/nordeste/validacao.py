"""Validacao bloqueante da base (regras R01 a R10): aponta problemas, nao corrige dados."""

from dataclasses import dataclass
from datetime import date

import pandas as pd

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
    if oficial == 0:
        return calculado != 0
    return abs(oficial - calculado) / abs(oficial) > TOLERANCIA


def _pct(oficial: float, calculado: float) -> str:
    return "inf" if oficial == 0 else f"{abs(oficial - calculado) / abs(oficial) * 100:.2f}%"


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


def _r02_colunas(base: pd.DataFrame) -> list[Falha]:
    """Sem as colunas do esquema nenhuma regra de linha pode ser avaliada."""
    if list(base.columns) == COLUNAS_BASE:
        return []
    return [Falha("R02", f"colunas da base diferem do esquema: esperado {', '.join(COLUNAS_BASE)}; "
                         f"encontrado {', '.join(map(str, base.columns))}")]


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
    """Valores presentes por (grupo, ano, serie) nas linhas e por territorio nas colunas."""
    return linhas[linhas.valor.notna()].pivot_table(
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
        for r in junto[junto.den != 0].to_dict("records"):
            calculado = r["num"] / r["den"] * comp.fator
            if _diverge(r["oficial"], calculado):
                falhas.append(Falha("R08", (
                    f"{_rotulo(ficha.id, r['serie_id'], r['subindicador'], r['etapa'], r['rede'])} NE {r['ano']}: "
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

    `base_publicada` e `hoje` alimentam os avisos (ainda nao calculados: `avisos` sai vazia).
    A regra R01 (dado de fixture) nao tem como ser desligada.
    """
    erros = _r02_colunas(base)
    if not erros:
        erros = _r01_fixture(base, coletas, derivacoes)
        tipos = _r02_tipos(base)
        erros += tipos
        if not tipos:
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
    return ResultadoValidacao(erros=erros, avisos=[])
