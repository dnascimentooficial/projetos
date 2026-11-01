"""Tabela dos indicadores gerada das fichas: papel, series, cobertura efetiva e situacao de verificacao.

Uso: `python -m nordeste.tabela` imprime a tabela em Markdown; com `--atualizar-readme`, grava-a no README.md
da raiz, entre os marcadores INICIO_TABELA e FIM_TABELA.
"""

import argparse
import sys
from pathlib import Path

from nordeste.caminhos import Caminhos
from nordeste.fichas import Ficha, carregar_fichas

RAIZ_PADRAO = Path(__file__).resolve().parents[2]
_EM_CURSO = 9999  # ano sentinela das series sem `fim`
_SEM_COBERTURA = "—"
INICIO_TABELA = "<!-- tabela-indicadores:inicio (gerada por python -m nordeste.tabela --atualizar-readme) -->"
FIM_TABELA = "<!-- tabela-indicadores:fim -->"
CABECALHO = ("Indicador", "Nome", "Eixo", "Papel", "Séries", "Cobertura efetiva", "Situação")


def cobertura_efetiva(ficha: Ficha) -> str:
    """Anos que a coleta cobre: as series verificadas, sem os anos em que nenhuma delas tem pesquisa.

    Faixas separadas por "; " e "AAAA–" para serie em curso. Sem serie verificada, "—".
    """
    anos: set[int] = set()
    for serie in (s for s in ficha.series if s.verificado):
        fim = _EM_CURSO if serie.fim is None else serie.fim
        anos |= set(range(serie.inicio, fim + 1)) - set(serie.anos_sem_publicacao)
    faixas: list[list[int]] = []
    for ano in sorted(anos):
        if faixas and ano == faixas[-1][1] + 1:
            faixas[-1][1] = ano
        else:
            faixas.append([ano, ano])
    textos = [
        f"{inicio}–" if fim == _EM_CURSO else f"{inicio}–{fim}" if fim != inicio else str(inicio)
        for inicio, fim in faixas
    ]
    return "; ".join(textos) or _SEM_COBERTURA


def situacao(ficha: Ficha) -> str:
    verificadas = sum(s.verificado for s in ficha.series)
    if verificadas == 0:
        return "não verificada (fora da coleta)"
    if verificadas < len(ficha.series):
        return f"parcial ({verificadas} de {len(ficha.series)} séries verificadas)"
    return "verificada, calculada pelo projeto" if ficha.calculo else "verificada"


def _celula(texto: str) -> str:
    return texto.replace("|", "\\|")


def tabela_markdown(fichas: dict[str, Ficha]) -> str:
    """Uma linha por ficha, em ordem alfabetica do id."""
    linhas = [f"| {' | '.join(CABECALHO)} |", f"|{'---|' * len(CABECALHO)}"]
    for ficha in sorted(fichas.values(), key=lambda f: f.id):
        celulas = (
            f"`{ficha.id}`", ficha.nome, ficha.eixo, "auxiliar" if ficha.auxiliar else "exibido",
            ", ".join(f"`{s.id}`" for s in ficha.series), cobertura_efetiva(ficha), situacao(ficha),
        )
        linhas.append(f"| {' | '.join(_celula(c) for c in celulas)} |")
    return "\n".join(linhas)


def atualizar_readme(readme: Path, tabela: str) -> None:
    """Troca o trecho entre os marcadores do README pela tabela; sem os marcadores, ValueError."""
    texto = readme.read_text(encoding="utf-8")
    antes, achou_inicio, resto = texto.partition(INICIO_TABELA)
    _, achou_fim, depois = resto.partition(FIM_TABELA)
    if not (achou_inicio and achou_fim):
        raise ValueError(f"{readme} sem os marcadores {INICIO_TABELA!r} e {FIM_TABELA!r}")
    readme.write_text(f"{antes}{INICIO_TABELA}\n{tabela}\n{FIM_TABELA}{depois}", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m nordeste.tabela", description=__doc__.splitlines()[0])
    parser.add_argument("--raiz", type=Path, default=RAIZ_PADRAO, help="pasta nordeste-indicadores")
    parser.add_argument("--atualizar-readme", action="store_true", help="grava a tabela no README.md da raiz")
    args = parser.parse_args(argv)
    tabela = tabela_markdown(carregar_fichas(Caminhos(args.raiz).fichas))
    if not args.atualizar_readme:
        print(tabela)
        return 0
    try:
        atualizar_readme(args.raiz / "README.md", tabela)
    except (OSError, ValueError) as erro:
        print(erro, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
