"""Linha de comando: coletar, consolidar, validar e publicar a base historica."""

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from nordeste.caminhos import Caminhos
from nordeste.cobertura import relatorio_cobertura
from nordeste.coletores import ErroColeta, coletar_serie
from nordeste.consolidacao import Pendencia, consolidar
from nordeste.derivados import brasil_fora_ne, metricas_convergencia
from nordeste.esquema import CHAVE_BASE
from nordeste.fichas import ErroFicha, carregar_fichas
from nordeste.publicacao import ErroPublicacao, gravar_csv, ler_derivacoes, mensagem_de_reprovacao, publicar
from nordeste.territorios import carregar_territorios

RAIZ_PADRAO = Path(__file__).resolve().parents[2]


def _data(texto: str) -> date:
    try:
        return date.fromisoformat(texto)
    except ValueError:
        raise argparse.ArgumentTypeError(f"data invalida: {texto!r} (use AAAA-MM-DD)") from None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nordeste", description="Base historica de indicadores do Nordeste.")
    parser.add_argument("--raiz", type=Path, default=RAIZ_PADRAO, help="pasta nordeste-indicadores")
    parser.add_argument("--hoje", type=_data, default=None, help="data de referencia, AAAA-MM-DD (padrao: hoje)")
    comandos = parser.add_subparsers(dest="comando", required=True)
    coletar = comandos.add_parser("coletar", help="coleta os arquivos brutos de todas as series")
    coletar.add_argument("--indicador", help="coleta so as series deste indicador")
    coletar.add_argument("--offline", action="store_true", help="usa as fixtures em vez da rede")
    comandos.add_parser("consolidar", help="monta a base de trabalho e seus relatorios")
    comandos.add_parser("validar", help="valida a base de trabalho sem publicar")
    publicar_ = comandos.add_parser("publicar", help="valida e publica a base")
    publicar_.add_argument("--ensaio", action="store_true", help="valida sem gravar dados/base/")
    return parser


def _fichas(caminhos: Caminhos) -> dict:
    fichas = carregar_fichas(caminhos.fichas)
    if not fichas:  # raiz errada nao pode virar sucesso silencioso
        raise ErroFicha(f"nenhuma ficha de indicador em {caminhos.fichas}")
    return fichas


def _coletar(caminhos: Caminhos, hoje: date, indicador: str | None, offline: bool) -> int:
    fichas = _fichas(caminhos)
    if indicador is not None and indicador not in fichas:
        print(f"indicador desconhecido: {indicador}", file=sys.stderr)
        return 1
    falhas: list[str] = []
    for ficha in fichas.values():
        if indicador is not None and ficha.id != indicador:
            continue
        for serie in ficha.series:
            try:
                coletar_serie(ficha, serie, caminhos, offline=offline, hoje=hoje)
            except ErroColeta as erro:
                falhas.append(f"{ficha.id}/{serie.id}: {erro}")
    for falha in falhas:
        print(falha, file=sys.stderr)
    return 1 if falhas else 0


def _acrescentar_derivacoes(caminhos: Caminhos, novas: pd.DataFrame) -> None:
    """O registro de derivacoes e historico: so acrescenta coleta_id novos, nunca reescreve os antigos."""
    existentes = ler_derivacoes(caminhos.registro_derivacoes)
    inedito = ~novas["coleta_id"].isin(existentes["coleta_id"])
    gravar_csv(pd.concat([existentes, novas[inedito]], ignore_index=True), caminhos.registro_derivacoes)


def _consolidar(caminhos: Caminhos) -> int:
    fichas = _fichas(caminhos)
    territorios = carregar_territorios(caminhos.territorios_csv)
    observada, pendencias = consolidar(caminhos, fichas, territorios)
    fora_ne, derivacoes = brasil_fora_ne(observada, fichas)
    base = pd.concat([observada, fora_ne], ignore_index=True)
    base = base.sort_values(CHAVE_BASE, kind="stable").reset_index(drop=True)

    caminhos.trabalho.mkdir(parents=True, exist_ok=True)
    caminhos.relatorios.mkdir(parents=True, exist_ok=True)
    gravar_csv(base, caminhos.trabalho / "base.csv")
    gravar_csv(metricas_convergencia(base, fichas, territorios), caminhos.trabalho / "derivados.csv")
    gravar_csv(
        pd.DataFrame([vars(p) for p in pendencias], columns=list(Pendencia.__dataclass_fields__)),
        caminhos.trabalho / "pendencias.csv",
    )
    _acrescentar_derivacoes(caminhos, derivacoes)
    gravar_csv(relatorio_cobertura(base, fichas), caminhos.relatorios / "cobertura.csv")
    for p in pendencias:
        print(f"serie pendente: {p.indicador_id}/{p.serie_id}: {p.motivo}")
    return 0


def _publicar(caminhos: Caminhos, hoje: date, ensaio: bool) -> int:
    resultado = publicar(caminhos, hoje, ensaio=ensaio)
    if not resultado.aprovado:  # so chega aqui com ensaio: sem ensaio, publicar levanta ErroPublicacao
        raise ErroPublicacao(mensagem_de_reprovacao(resultado))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    caminhos = Caminhos(args.raiz)
    hoje = args.hoje or date.today()
    try:
        if args.comando == "coletar":
            return _coletar(caminhos, hoje, args.indicador, args.offline)
        if args.comando == "consolidar":
            return _consolidar(caminhos)
        # validar e o ensaio de publicacao: mesmos insumos, grava validacao.csv e nunca toca dados/base/.
        return _publicar(caminhos, hoje, ensaio=args.comando == "validar" or args.ensaio)
    except (ErroColeta, ErroFicha, ErroPublicacao) as erro:
        print(erro, file=sys.stderr)
        return 1
