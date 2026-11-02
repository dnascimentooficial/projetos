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
from nordeste.derivados import aplicar_calculos, brasil_fora_ne, metricas_convergencia
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
    coletar.add_argument("--pular-indicador", action="append", default=[], metavar="ID",
                         help="nao coleta este indicador (repetivel)")
    comandos.add_parser("consolidar", help="monta a base de trabalho e seus relatorios")
    comandos.add_parser("validar", help="valida a base de trabalho sem publicar")
    publicar_ = comandos.add_parser("publicar", help="valida e publica a base")
    publicar_.add_argument("--ensaio", action="store_true", help="valida sem gravar dados/base/")
    site = comandos.add_parser("site", help="gera o site estatico a partir da base publicada")
    site.add_argument("--saida", type=Path, required=True, help="pasta do site (apagada e recriada)")
    site.add_argument("--sem-imagens", action="store_true", help="nao gera as imagens OpenGraph e dos cards")
    site.add_argument("--anterior", type=Path,
                      help="saida da geracao anterior: dela se copiam os PNG cuja entrada nao mudou (fora de --saida)")
    site.add_argument("--relatorio", type=Path, help="grava em JSON o que foi suprimido (fechos e cards)")
    return parser


def _fichas(caminhos: Caminhos) -> dict:
    fichas = carregar_fichas(caminhos.fichas)
    if not fichas:  # raiz errada nao pode virar sucesso silencioso
        raise ErroFicha(f"nenhuma ficha de indicador em {caminhos.fichas}")
    return fichas


COLUNAS_FALHAS_COLETA: list[str] = ["indicador_id", "serie_id", "motivo"]


def _coletar(caminhos: Caminhos, hoje: date, indicador: str | None, offline: bool, pular: list[str]) -> int:
    """Coleta as series e grava relatorios/falhas_coleta.csv (cabecalho sempre; uma linha por serie que falhou).

    Com rede, series `verificado: false` sao puladas com aviso, sem contar como falha. A serie que falha mantem a
    coleta anterior no registro (e, na publicacao, os dados ja publicados).
    """
    fichas = _fichas(caminhos)
    if indicador is not None and indicador not in fichas:
        print(f"indicador desconhecido: {indicador}", file=sys.stderr)
        return 1
    desconhecidos = [id_ for id_ in pular if id_ not in fichas]  # erro de digitacao nao pode coletar o que era para pular
    if desconhecidos:
        print(f"indicador desconhecido em --pular-indicador: {', '.join(desconhecidos)}", file=sys.stderr)
        return 1
    falhas: list[tuple[str, str, str]] = []
    for ficha in fichas.values():
        if (indicador is not None and ficha.id != indicador) or ficha.id in pular or ficha.calculo is not None:
            continue  # indicador calculado nao tem arquivo bruto: sai do consolidar
        for serie in ficha.series:
            if not offline and not serie.verificado:
                print(f"série não verificada, pulada: {ficha.id}/{serie.id}", file=sys.stderr)
                continue
            try:
                coletar_serie(ficha, serie, caminhos, offline=offline, hoje=hoje)
            except ErroColeta as erro:
                falhas.append((ficha.id, serie.id, str(erro)))
    for indicador_id, serie_id, motivo in falhas:
        print(f"{indicador_id}/{serie_id}: {motivo}", file=sys.stderr)
    caminhos.relatorios.mkdir(parents=True, exist_ok=True)
    gravar_csv(pd.DataFrame(falhas, columns=COLUNAS_FALHAS_COLETA), caminhos.relatorios / "falhas_coleta.csv")
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
    calculada, derivacoes_calculo = aplicar_calculos(observada, fichas)
    fora_ne, derivacoes = brasil_fora_ne(observada, fichas)
    derivacoes = pd.concat([derivacoes, derivacoes_calculo], ignore_index=True)
    base = pd.concat([observada, calculada, fora_ne], ignore_index=True)
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


def _site(caminhos: Caminhos, saida: Path, imagens: bool, relatorio: Path | None, anterior: Path | None) -> int:
    from nordeste.site.gerar import gerar_site, relatorio_em_json  # o pipeline nao precisa do gerador

    try:
        resultado = gerar_site(caminhos, saida, imagens=imagens, anterior=anterior)
    except (ValueError, OSError) as erro:  # inclui ErroConteudo; base ou metadados ilegiveis nao viram traceback
        print(f"site: {erro}", file=sys.stderr)
        return 1
    if relatorio is not None:
        relatorio.write_text(relatorio_em_json(resultado), encoding="utf-8")
    for id_ in resultado.fechos_suprimidos:
        print(f"fecho suprimido: {id_}")
    for id_ in resultado.cards_suprimidos:
        print(f"card suprimido: {id_}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    caminhos = Caminhos(args.raiz)
    hoje = args.hoje or date.today()
    try:
        if args.comando == "coletar":
            return _coletar(caminhos, hoje, args.indicador, args.offline, args.pular_indicador)
        if args.comando == "consolidar":
            return _consolidar(caminhos)
        if args.comando == "site":
            return _site(caminhos, args.saida, not args.sem_imagens, args.relatorio, args.anterior)
        # validar e o ensaio de publicacao: mesmos insumos, grava validacao.csv e nunca toca dados/base/.
        return _publicar(caminhos, hoje, ensaio=args.comando == "validar" or args.ensaio)
    except (ErroColeta, ErroFicha, ErroPublicacao) as erro:
        print(erro, file=sys.stderr)
        return 1
