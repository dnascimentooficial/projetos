"""Automacao da publicacao semanal: agenda da coleta, brutos na release do GitHub, avisos e conferencia do site.

Cada funcao e uma peca que os workflows chamam por `python -m nordeste.automacao <comando>`. Nada aqui coleta ou
publica dados: so decide, guarda os brutos fora do repositorio e verifica o que ja foi feito.
"""

import argparse
import filecmp
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path, PurePosixPath

import pandas as pd
import requests

from nordeste.caminhos import Caminhos
from nordeste.coletores.erros import ErroColeta
from nordeste.coletores.http import _bundle_com_extra
from nordeste.coletores.registro import ler_registro
from nordeste.fichas import ErroFicha, Ficha, carregar_fichas
from nordeste.site.formatacao import numero

RAIZ_PADRAO = Path(__file__).resolve().parents[2]
INDICADORES_INEP_PESADOS = ("matriculas_basica", "superior")  # sinopses do INEP: centenas de MB, saem uma vez por mes
RELEASE_DOS_BRUTOS = "brutos"
SEPARADOR_DO_ANEXO = "__"
USER_AGENT = "nordeste-em-numeros/1.0 (+https://nordeste.dnascimento.com.br)"  # quem consulta fontes e site se identifica
CABECALHOS = {"User-Agent": USER_AGENT}
TERRITORIOS_DO_RESUMO = {"NE": "Nordeste", "BR": "Brasil"}


class ErroAutomacao(RuntimeError):
    """Falha de uma etapa da automacao (gh que falhou, anexo que falta na release)."""


# --- agenda ---

def coleta_do_inep(hoje: date) -> bool:
    """O INEP so e coletado na primeira semana do mes: o resto do mes pula os indicadores pesados dele."""
    return hoje.day <= 7


# --- brutos na release ---

def nome_do_anexo(relativo: PurePosixPath) -> str:
    """`matriculas_basica/educacenso/b08dea69.zip` -> `matriculas_basica__educacenso__b08dea69.zip` (anexo sem pastas)."""
    partes = relativo.parts
    if len(partes) != 3 or any(SEPARADOR_DO_ANEXO in p or not p for p in partes):
        raise ValueError(f"Bruto fora do padrao indicador/serie/arquivo (sem '{SEPARADOR_DO_ANEXO}' nos nomes): {relativo}")
    return SEPARADOR_DO_ANEXO.join(partes)


def caminho_do_anexo(nome: str) -> PurePosixPath:
    """Inverso de `nome_do_anexo`."""
    partes = nome.split(SEPARADOR_DO_ANEXO)
    if len(partes) != 3 or not all(partes):
        raise ValueError(f"Nome de anexo fora do padrao indicador__serie__arquivo: {nome}")
    return PurePosixPath(*partes)


def brutos_necessarios(caminhos: Caminhos) -> list[PurePosixPath]:
    """O arquivo da ultima coleta de rede de cada serie no registro, relativo a dados/brutos, em ordem alfabetica.

    Coleta de fixture nao entra: nao ha o que baixar nem guardar. A ultima e a ultima linha gravada.
    """
    registro = ler_registro(caminhos.registro_coletas)
    registro = registro[registro["origem"] == "rede"].drop_duplicates(["indicador_id", "serie_id"], keep="last")
    base = caminhos.brutos.relative_to(caminhos.raiz).as_posix()
    return sorted(PurePosixPath(a).relative_to(base) for a in registro["arquivo"])


def _gh(*args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        raise ErroAutomacao("O gh (GitHub CLI) não está instalado ou não está no PATH.") from None


def _gh_ou_erro(*args: str) -> str:
    resultado = _gh(*args)
    if resultado.returncode != 0:
        raise ErroAutomacao(f"gh {' '.join(args[:2])} falhou ({resultado.returncode}): {resultado.stderr.strip()}")
    return resultado.stdout


def _anexos_da_release(repo: str) -> set[str]:
    """Nomes dos anexos da release `brutos`; se ela nao existe, cria (vazia) e devolve o conjunto vazio."""
    visao = _gh("release", "view", RELEASE_DOS_BRUTOS, "--repo", repo, "--json", "assets")
    if visao.returncode == 0:
        return {a["name"] for a in json.loads(visao.stdout)["assets"]}
    _gh_ou_erro(
        "release", "create", RELEASE_DOS_BRUTOS, "--repo", repo, "--title", "Arquivos brutos das fontes",
        "--notes", "Arquivos brutos coletados das fontes oficiais, um anexo por coleta (indicador__serie__hash).",
    )
    return set()


def baixar_brutos(repo: str, caminhos: Caminhos) -> None:
    """Baixa da release `brutos` os arquivos de `brutos_necessarios` que ainda nao estao em dados/brutos/.

    O nome do arquivo leva o hash do conteudo: o que ja esta no disco nao e baixado de novo.
    """
    faltam = [r for r in brutos_necessarios(caminhos) if not (caminhos.brutos / r).exists()]
    if not faltam:
        return
    na_release = _anexos_da_release(repo)
    ausentes = [nome_do_anexo(r) for r in faltam if nome_do_anexo(r) not in na_release]
    if ausentes:
        raise ErroAutomacao(f"A release '{RELEASE_DOS_BRUTOS}' de {repo} não tem: {', '.join(ausentes)}.")
    with tempfile.TemporaryDirectory() as pasta:
        padroes = [arg for r in faltam for arg in ("--pattern", nome_do_anexo(r))]
        _gh_ou_erro("release", "download", RELEASE_DOS_BRUTOS, "--repo", repo, "--dir", pasta, "--clobber", *padroes)
        for relativo in faltam:
            baixado = Path(pasta) / nome_do_anexo(relativo)
            if not baixado.is_file():
                raise ErroAutomacao(f"O gh não baixou {baixado.name}.")
            destino = caminhos.brutos / relativo
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(baixado, destino)


def enviar_brutos(repo: str, caminhos: Caminhos) -> None:
    """Sobe para a release `brutos` os arquivos de `brutos_necessarios` que ela ainda nao tem (cria a release se faltar).

    Cada anexo leva o nome plano de `nome_do_anexo`. O nome tem o hash do conteudo, entao o que ja esta la nao muda
    e nao e enviado de novo (a release tem centenas de MB).
    """
    existentes = [r for r in brutos_necessarios(caminhos) if (caminhos.brutos / r).is_file()]
    if not existentes:
        return
    na_release = _anexos_da_release(repo)
    novos = [r for r in existentes if nome_do_anexo(r) not in na_release]
    if not novos:
        return
    with tempfile.TemporaryDirectory() as pasta:
        arquivos = []
        for relativo in novos:
            plano = Path(pasta) / nome_do_anexo(relativo)  # o gh usa o nome do arquivo como nome do anexo
            try:
                os.link(caminhos.brutos / relativo, plano)
            except OSError:  # outro sistema de arquivos
                shutil.copy2(caminhos.brutos / relativo, plano)
            arquivos.append(str(plano))
        _gh_ou_erro("release", "upload", RELEASE_DOS_BRUTOS, "--repo", repo, "--clobber", *arquivos)


# --- avisos ---

def _numeros(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie, errors="coerce")


def _formatar(valor: float) -> str:
    casas = 2 if abs(valor) < 10 else 1 if abs(valor) < 1000 else 0
    return numero(valor, casas)


def _variacao(antes: float, depois: float) -> str:
    if antes == 0:
        return "n/d"
    pct = (depois - antes) / abs(antes) * 100
    return f"{'+' if pct > 0 else '-' if pct < 0 else ''}{numero(abs(pct), 1)}%"


def _indicador(linha: pd.Series) -> str:
    dimensao = [linha[c] for c in ("subindicador", "etapa", "rede") if str(linha.get(c, "")).strip() not in ("", "nan")]
    return f"{linha['indicador_id']} ({', '.join(dimensao)})" if dimensao else str(linha["indicador_id"])


def resumo_de_mudancas(mudancas: pd.DataFrame, limite: int = 15) -> str:
    """Tabela Markdown das maiores variacoes relativas entre o valor publicado e o novo, so Nordeste e Brasil.

    Entram os valores que ja existiam e mudaram (tipo `alterado`); o ano novo nao tem antes, e vai em `anos_novos`.
    Antes igual a zero nao tem variacao relativa e fica no fim da lista.
    """
    if mudancas.empty:
        alteradas = mudancas
    else:
        alteradas = mudancas[(mudancas["tipo"] == "alterado") & mudancas["territorio_id"].isin(TERRITORIOS_DO_RESUMO)].copy()
        alteradas["_antes"], alteradas["_depois"] = _numeros(alteradas["valor_anterior"]), _numeros(alteradas["valor_novo"])
        alteradas = alteradas.dropna(subset=["_antes", "_depois"])
    if alteradas.empty:
        return "Nenhum valor já publicado mudou no Nordeste ou no Brasil.\n"
    # antes igual a zero nao tem variacao relativa: peso -1, no fim da lista
    pesos = [abs((d - a) / a) if a != 0 else -1.0 for a, d in zip(alteradas["_antes"], alteradas["_depois"])]
    alteradas = alteradas.assign(_peso=pesos).sort_values(
        ["_peso", "indicador_id", "territorio_id", "ano"], ascending=[False, True, True, True], kind="stable",
    )
    linhas = ["| Indicador | Território | Ano | Antes | Depois | Variação |", "| --- | --- | ---: | ---: | ---: | ---: |"]
    for _, linha in alteradas.head(limite).iterrows():
        linhas.append(
            f"| {_indicador(linha)} | {TERRITORIOS_DO_RESUMO[linha['territorio_id']]} | {linha['ano']} "
            f"| {_formatar(linha['_antes'])} | {_formatar(linha['_depois'])} | {_variacao(linha['_antes'], linha['_depois'])} |"
        )
    resto = len(alteradas) - limite
    if resto > 0:
        linhas += ["", f"E mais {resto} mudanças de valor no Nordeste e no Brasil, fora desta lista."]
    return "\n".join(linhas) + "\n"


def anos_novos(mudancas: pd.DataFrame, publicada: pd.DataFrame | None = None) -> list[tuple[str, int]]:
    """(indicador, ano) com valor novo em ano maior que o ultimo publicado antes do indicador, em ordem.

    O ultimo ano publicado vem de `publicada` (a base publicada antes, com `indicador_id`, `ano` e `valor`) ou, sem
    ela, das linhas de `mudancas` que ja existiam (alterado e removido). Indicador sem nenhuma referencia e inteiro
    novo: todos os anos dele entram. Novo sem valor (ano em branco) nao conta.
    """
    if mudancas.empty:
        return []
    if publicada is not None:
        com_valor = publicada[_numeros(publicada["valor"]).notna()]
        referencia = _numeros(com_valor["ano"]).groupby(com_valor["indicador_id"]).max()
    else:
        existentes = mudancas[mudancas["tipo"] != "novo"]
        referencia = _numeros(existentes["ano"]).groupby(existentes["indicador_id"]).max()
    novos = mudancas[(mudancas["tipo"] == "novo") & _numeros(mudancas["valor_novo"]).notna()]
    achados = {
        (linha.indicador_id, int(linha.ano))
        for linha in novos.itertuples()
        if int(linha.ano) > referencia.get(linha.indicador_id, float("-inf"))
    }
    return sorted(achados)


def conferir_publicado(url: str, sha256: str, tentativas: int = 10, espera_s: int = 30) -> bool:
    """True se o HTML de `url` traz o sha256 da base no rodape; tenta de novo, a cada `espera_s`, ate `tentativas`.

    A hospedagem leva alguns minutos para puxar a publicacao: o sha256 antigo no rodape e resposta ruim, nao final.
    Erro de rede ou HTTP conta como tentativa perdida.
    """
    for tentativa in range(tentativas):
        if tentativa:
            time.sleep(espera_s)
        try:
            resposta = requests.get(url, timeout=20, headers={**CABECALHOS, "Cache-Control": "no-cache"})
        except requests.RequestException:
            continue
        if resposta.status_code == 200 and sha256 in resposta.text:
            return True
    return False


def _consultar(url: str, timeout_s: int, verify: str | None = None) -> str | None:
    """None se a URL responde (apos redirecionamentos); senao o motivo. Pergunta com HEAD e, se recusado, com GET.

    `verify`: bundle de CAs (o do coletor, com o `ca_extra` da serie); sem ele vale o padrao. Nunca desliga a verificacao.
    """
    if not url.startswith(("http://", "https://")):
        return "endereço que não é http nem https"
    opcoes = {} if verify is None else {"verify": verify}
    motivo = "sem resposta"
    for metodo in (requests.head, requests.get):
        extra = {"stream": True} if metodo is requests.get else {}
        try:
            resposta = metodo(url, timeout=timeout_s, allow_redirects=True, headers=CABECALHOS, **opcoes, **extra)
            resposta.close()
        except requests.RequestException as erro:
            motivo = f"{type(erro).__name__}: {erro}"
            continue
        if resposta.status_code < 400:
            return None
        motivo = f"HTTP {resposta.status_code}"
    return motivo


def links_quebrados(
    fichas: dict[str, Ficha], timeout_s: int = 20, raiz: Path | None = None,
) -> list[tuple[str, str, str]]:
    """(indicador, URL da serie, motivo) para cada URL de serie que nao responde. Cada URL e consultada uma vez.

    Serie que declara `ca_extra` nos parametros (caminho relativo a `raiz`, padrao a raiz do projeto) e verificada com o
    mesmo bundle do coletor: o de CAs em uso mais esse certificado.
    """
    raiz = raiz or RAIZ_PADRAO
    consultadas: dict[tuple[str, str | None], str | None] = {}
    quebrados: list[tuple[str, str, str]] = []
    listados: set[tuple[str, str]] = set()
    with tempfile.TemporaryDirectory(prefix="nordeste-ca-") as pasta:
        bundles: dict[str, str | ErroColeta] = {}
        for ficha in fichas.values():
            for serie in ficha.series:
                ca_extra = serie.parametros.get("ca_extra")
                if (serie.url, ca_extra) not in consultadas:
                    if ca_extra and ca_extra not in bundles:
                        destino = Path(pasta) / f"{len(bundles)}"
                        destino.mkdir()
                        try:
                            bundles[ca_extra] = str(_bundle_com_extra(raiz / ca_extra, destino))
                        except ErroColeta as erro:
                            bundles[ca_extra] = erro
                    bundle = bundles.get(ca_extra) if ca_extra else None
                    consultadas[serie.url, ca_extra] = (
                        str(bundle) if isinstance(bundle, ErroColeta) else _consultar(serie.url, timeout_s, bundle)
                    )
                motivo = consultadas[serie.url, ca_extra]
                if motivo is not None and (ficha.id, serie.url) not in listados:
                    listados.add((ficha.id, serie.url))
                    quebrados.append((ficha.id, serie.url, motivo))
    return quebrados


# --- site ---

def _arquivos(raiz: Path) -> dict[str, Path]:
    return {p.relative_to(raiz).as_posix(): p for p in sorted(raiz.rglob("*")) if p.is_file()}


def site_mudou(anterior: Path, novo: Path) -> bool:
    """True se o site `novo` difere do publicado em `anterior`.

    Arquivos que nao sao PNG sao comparados byte a byte, o manifesto de imagens (`_imagens.json`) entre eles: os bytes
    de um PNG podem mudar de uma versao do Chromium para outra sem que o desenho mude (Ruling S-X), entao o PNG so
    precisa existir nos dois; o que o produz esta no manifesto.
    """
    if not anterior.is_dir():
        return True
    a, n = _arquivos(anterior), _arquivos(novo)
    if a.keys() != n.keys():
        return True
    return any(not filecmp.cmp(a[nome], n[nome], shallow=False) for nome in a if not nome.endswith(".png"))


# --- linha de comando para os workflows ---

def _ler_mudancas(arquivo: Path) -> pd.DataFrame:
    return pd.read_csv(arquivo, dtype=str, keep_default_na=False)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m nordeste.automacao", description="Pecas da publicacao semanal.")
    comandos = parser.add_subparsers(dest="comando", required=True)

    def com_raiz(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
        p.add_argument("--raiz", type=Path, default=RAIZ_PADRAO, help="pasta nordeste-indicadores")
        return p

    for nome, ajuda in (("baixar-brutos", "baixa da release os brutos que faltam"), ("enviar-brutos", "sobe os brutos novos")):
        com_raiz(comandos.add_parser(nome, help=ajuda)).add_argument("--repo", required=True, help="dono/repositorio")
    resumo = comandos.add_parser("resumo", help="imprime em Markdown as maiores variacoes (NE e BR)")
    resumo.add_argument("--mudancas", type=Path, required=True, help="dados/relatorios/mudancas.csv")
    resumo.add_argument("--limite", type=int, default=15)
    novos = comandos.add_parser("anos-novos", help="imprime indicador:ano dos anos que a base ainda nao tinha")
    novos.add_argument("--mudancas", type=Path, required=True)
    novos.add_argument(
        "--base-anterior", type=Path,
        help="base_nordeste.csv publicada antes (referencia do ultimo ano); sem ela o resultado e aproximado: "
             "o ultimo ano publicado e deduzido so das linhas alteradas ou removidas de mudancas.csv",
    )
    conferir = comandos.add_parser("conferir", help="sai com 1 se o rodape da pagina nao tem o sha256 da base")
    conferir.add_argument("--url", required=True)
    conferir.add_argument("--sha256", required=True)
    conferir.add_argument("--tentativas", type=int, default=10)
    conferir.add_argument("--espera", type=int, default=30, help="segundos entre as tentativas")
    links = com_raiz(comandos.add_parser("links", help="lista as URLs de serie que nao respondem; sai com 1 se houver"))
    links.add_argument("--timeout", type=int, default=20)
    mudou = comandos.add_parser("site-mudou", help="imprime mudou/igual; sai com 0 se o site mudou e 1 se esta igual")
    mudou.add_argument("--anterior", type=Path, required=True, help="site publicado (pasta inexistente conta como mudou)")
    mudou.add_argument("--novo", type=Path, required=True, help="site recem-gerado")
    pular = comandos.add_parser("pular-inep", help="imprime '--pular-indicador ID' dos indicadores pesados do INEP fora da 1a semana")
    pular.add_argument("--hoje", type=date.fromisoformat, default=None, help="AAAA-MM-DD (padrao: hoje)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.comando == "baixar-brutos":
            baixar_brutos(args.repo, Caminhos(args.raiz))
        elif args.comando == "enviar-brutos":
            enviar_brutos(args.repo, Caminhos(args.raiz))
        elif args.comando == "resumo":
            print(resumo_de_mudancas(_ler_mudancas(args.mudancas), args.limite), end="")
        elif args.comando == "anos-novos":
            publicada = None if args.base_anterior is None else pd.read_csv(args.base_anterior, dtype=str, keep_default_na=False)
            for indicador, ano in anos_novos(_ler_mudancas(args.mudancas), publicada):
                print(f"{indicador}:{ano}")
        elif args.comando == "conferir":
            return 0 if conferir_publicado(args.url, args.sha256, args.tentativas, args.espera) else 1
        elif args.comando == "links":
            quebrados = links_quebrados(carregar_fichas(Caminhos(args.raiz).fichas), args.timeout, args.raiz)
            for indicador, url, motivo in quebrados:
                print(f"{indicador}\t{url}\t{motivo}")
            return 1 if quebrados else 0
        elif args.comando == "site-mudou":
            if not args.novo.is_dir():
                raise ErroAutomacao(f"O site novo {args.novo} não existe.")
            mudou = site_mudou(args.anterior, args.novo)
            print("mudou" if mudou else "igual")
            return 0 if mudou else 1
        elif args.comando == "pular-inep":
            if not coleta_do_inep(args.hoje or date.today()):
                for indicador in INDICADORES_INEP_PESADOS:
                    print(f"--pular-indicador {indicador}")
    except (ErroAutomacao, ErroFicha, OSError, ValueError) as erro:
        print(erro, file=sys.stderr)
        return 2  # erro da propria etapa; 1 e a resposta "nao" de conferir, links e site-mudou
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
