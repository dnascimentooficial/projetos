"""Publicacao: valida a base de trabalho e, se aprovada, grava a base publicada e seus relatorios."""

import os
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pandas as pd

from nordeste.caminhos import Caminhos
from nordeste.coletores.registro import ler_registro
from nordeste.consolidacao import Pendencia
from nordeste.derivados import COLUNAS_REGISTRO, metricas_convergencia
from nordeste.esquema import CHAVE_BASE, COLUNAS_BASE, COLUNAS_DERIVADOS, normalizar_base
from nordeste.fichas import Ficha, carregar_fichas, verificar_fichas
from nordeste.governos import atribuir_governo, carregar_governos
from nordeste.territorios import carregar_territorios
from nordeste.validacao import ResultadoValidacao, validar

COLUNAS_MUDANCAS: list[str] = [*CHAVE_BASE, "valor_anterior", "valor_novo", "tipo"]
_CHAVE_DERIVADOS = [c for c in COLUNAS_DERIVADOS if c != "valor"]


class ErroPublicacao(RuntimeError):
    """A base de trabalho nao esta pronta para publicar, ou foi reprovada na validacao."""


# ---------------------------------------------------------------------------
# Relatorio de mudancas
# ---------------------------------------------------------------------------

def mudancas(nova: pd.DataFrame, publicada: pd.DataFrame | None) -> pd.DataFrame:
    """Diferencas de valor entre a base nova e a publicada, linha a linha pela CHAVE_BASE.

    `tipo`: alterado (nas duas, valor diferente; nulo so e igual a nulo), novo (so na nova) ou
    removido (so na publicada). Sem base publicada, toda linha e nova.
    """
    if publicada is None:
        publicada = nova.iloc[0:0]
    atual = nova.drop_duplicates(CHAVE_BASE)[[*CHAVE_BASE, "valor"]].rename(columns={"valor": "valor_novo"})
    anterior = publicada.drop_duplicates(CHAVE_BASE)[[*CHAVE_BASE, "valor"]].rename(columns={"valor": "valor_anterior"})
    junto = anterior.merge(atual, on=CHAVE_BASE, how="outer", indicator=True)
    iguais = (junto.valor_anterior == junto.valor_novo) | (junto.valor_anterior.isna() & junto.valor_novo.isna())
    junto["tipo"] = junto["_merge"].map({"left_only": "removido", "right_only": "novo", "both": "alterado"})
    mudou = junto[(junto["_merge"] != "both") | ~iguais]
    return mudou[COLUNAS_MUDANCAS].sort_values(CHAVE_BASE, kind="stable").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Versao completa (para leitura humana)
# ---------------------------------------------------------------------------

def versao_completa(
    base: pd.DataFrame, fichas: dict[str, Ficha], territorios: pd.DataFrame, governos: pd.DataFrame,
) -> pd.DataFrame:
    """A base com nome do territorio, dados da ficha e da serie, e o governo do ano.

    Exige base validada: territorio, indicador ou serie desconhecidos levantam KeyError.
    """
    nomes = dict(zip(territorios["territorio_id"], territorios["nome"]))
    series = {
        (i, s): fichas[i].serie(s) for i, s in base[["indicador_id", "serie_id"]].drop_duplicates().itertuples(index=False)
    }
    governo_do_ano = {ano: atribuir_governo(int(ano), governos) for ano in base["ano"].unique()}
    por_serie = [series[i, s] for i, s in zip(base["indicador_id"], base["serie_id"])]
    por_ficha = [fichas[i] for i in base["indicador_id"]]

    completa = base.copy()
    completa["territorio_nome"] = [nomes[t] for t in base["territorio_id"]]
    completa["indicador_nome"] = [f.nome for f in por_ficha]
    completa["unidade"] = [f.unidade for f in por_ficha]
    completa["fonte"] = [s.fonte for s in por_serie]
    completa["orgao"] = [f.orgao for f in por_ficha]
    completa["url"] = [s.url for s in por_serie]
    completa["periodicidade"] = [f.periodicidade for f in por_ficha]
    completa["presidente"] = [governo_do_ano[a][0] for a in base["ano"]]
    completa["mandato"] = [governo_do_ano[a][1] for a in base["ano"]]
    completa["compatibilidade"] = [s.compatibilidade for s in por_serie]
    return completa


# ---------------------------------------------------------------------------
# Leitura e gravacao
# ---------------------------------------------------------------------------

def _ler_csv(path: Path, texto: list[str], **opcoes) -> pd.DataFrame:
    """CSV com colunas de texto como str ("" continua ""), `valor` vazio como NaN e floats exatos na ida e volta."""
    if not path.exists():
        raise ErroPublicacao(f"{path.name} nao encontrado em {path.parent}; rode a consolidacao antes de publicar")
    return pd.read_csv(
        path, dtype={c: str for c in texto}, keep_default_na=False, na_values={"valor": [""]},
        float_precision="round_trip", encoding="utf-8", **opcoes,
    )


def _ler_base(path: Path) -> pd.DataFrame:
    texto = [c for c in COLUNAS_BASE if c not in ("ano", "valor")]
    return normalizar_base(_ler_csv(path, texto))


def _ler_pendencias(path: Path) -> list[Pendencia]:
    tabela = _ler_csv(path, ["indicador_id", "serie_id", "motivo"])
    return [Pendencia(r.indicador_id, r.serie_id, r.motivo) for r in tabela.itertuples(index=False)]


def ler_derivacoes(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=COLUNAS_REGISTRO)
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _com_series_pendentes(
    base: pd.DataFrame, publicada: pd.DataFrame | None, pendencias: list[Pendencia],
) -> pd.DataFrame:
    """Base de trabalho sem as linhas das series pendentes, no lugar das quais entram as da base publicada."""
    pares = {(p.indicador_id, p.serie_id) for p in pendencias}
    if not pares:
        return base
    def pendente(tabela):
        return [(i, s) in pares for i, s in zip(tabela["indicador_id"], tabela["serie_id"])]
    partes = [base[[not p for p in pendente(base)]]]
    if publicada is not None:
        partes.append(publicada[pendente(publicada)])
    return pd.concat(partes, ignore_index=True)


def _ordenar(df: pd.DataFrame, chave: list[str]) -> pd.DataFrame:
    return df.sort_values(chave, kind="stable").reset_index(drop=True)


def gravar_csv(df: pd.DataFrame, path: Path, **opcoes) -> None:
    df.to_csv(path, index=False, lineterminator="\n", **opcoes)


def _gravar_parquet(df: pd.DataFrame, path: Path) -> None:
    df.to_parquet(path, index=False)


def _substituir_todos(destino: Path, gravacoes: dict[str, Callable[[Path], None]]) -> None:
    """Grava cada arquivo num temporario ao lado do destino e so troca os definitivos quando todos estao prontos."""
    destino.mkdir(parents=True, exist_ok=True)
    temporarios = {nome: destino / f".{nome}.tmp" for nome in gravacoes}
    try:
        for nome, gravar in gravacoes.items():
            gravar(temporarios[nome])
        for nome, temporario in temporarios.items():
            os.replace(temporario, destino / nome)
    finally:
        for temporario in temporarios.values():
            temporario.unlink(missing_ok=True)


def mensagem_de_reprovacao(resultado: ResultadoValidacao) -> str:
    regras = sorted({f.regra for f in resultado.erros})
    linhas = [f"{f.regra}: {f.mensagem}" for f in resultado.erros]
    return f"publicacao reprovada na validacao ({', '.join(regras)}):\n" + "\n".join(linhas)


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------

def publicar(caminhos: Caminhos, hoje: date, ensaio: bool = False) -> ResultadoValidacao:
    """Valida a base de trabalho e a publica em dados/base/.

    A base validada e a que seria gravada: `trabalho/base.csv`, com as series pendentes trocadas pelas
    linhas daquelas series na base publicada anterior. Os derivados publicados sao as metricas de
    convergencia dessa base final. Os relatorios validacao.csv e mudancas.csv saem sempre.
    Reprovado: ErroPublicacao (sem ensaio) ou o resultado (com ensaio); dados/base/ nunca e tocado.
    Aprovado: tudo e calculado antes de gravar e os arquivos so substituem os anteriores no fim,
    entao uma falha nao deixa dados/base/ incoerente.
    """
    arquivo_publicado = caminhos.base / "base_nordeste.csv"
    publicada = _ler_base(arquivo_publicado) if arquivo_publicado.exists() else None
    trabalho = _ler_base(caminhos.trabalho / "base.csv")
    pendencias = _ler_pendencias(caminhos.trabalho / "pendencias.csv")
    base = _ordenar(_com_series_pendentes(trabalho, publicada, pendencias), CHAVE_BASE)

    falhas_fichas = verificar_fichas(caminhos.fichas)
    fichas = {} if falhas_fichas else carregar_fichas(caminhos.fichas)  # com falha, R10 explica; as demais regras seguem
    territorios = carregar_territorios(caminhos.territorios_csv)
    coletas, derivacoes = ler_registro(caminhos.registro_coletas), ler_derivacoes(caminhos.registro_derivacoes)

    sem_derivados = pd.DataFrame(columns=COLUNAS_DERIVADOS)
    resultado = validar(base, sem_derivados, fichas, falhas_fichas, territorios, coletas, derivacoes, publicada, hoje)
    derivados = sem_derivados
    if resultado.aprovado:
        # Derivados so fazem sentido sobre uma base valida; validados em seguida como os que seriam gravados.
        derivados = _ordenar(metricas_convergencia(base, fichas, territorios), _CHAVE_DERIVADOS)
        resultado = validar(base, derivados, fichas, falhas_fichas, territorios, coletas, derivacoes, publicada, hoje)

    caminhos.relatorios.mkdir(parents=True, exist_ok=True)
    gravar_csv(resultado.para_dataframe(), caminhos.relatorios / "validacao.csv")
    gravar_csv(mudancas(base, publicada), caminhos.relatorios / "mudancas.csv")

    if not resultado.aprovado:
        if ensaio:
            return resultado
        raise ErroPublicacao(mensagem_de_reprovacao(resultado))
    completa = versao_completa(base, fichas, territorios, carregar_governos(caminhos.governos_csv))
    if ensaio:
        return resultado

    _substituir_todos(caminhos.base, {
        "base_nordeste.csv": lambda destino: gravar_csv(base, destino),
        "base_nordeste.parquet": lambda destino: _gravar_parquet(base, destino),
        "derivados.csv": lambda destino: gravar_csv(derivados, destino),
        "base_nordeste_completa.csv": lambda destino: gravar_csv(
            completa, destino, encoding="utf-8-sig", sep=";", decimal=","),
    })
    return resultado
