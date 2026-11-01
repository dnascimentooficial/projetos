"""Coleta dos arquivos brutos: rede (SIDRA, arquivos por URL) ou fixtures no modo offline."""

import hashlib
import json
import os
import shutil
import tempfile
import zlib
from datetime import date
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

import requests

from nordeste.caminhos import Caminhos
from nordeste.coletores.arquivo import (
    ParteBaixada, Receita, escrever_pacote, preparar_parte, receita_em_json, receitas_das_partes, url_arquivo,
)
from nordeste.coletores.erros import ErroColeta
from nordeste.coletores.http import baixar, baixar_para_arquivo
from nordeste.coletores.ipeadata import url_ipeadata, urls_ipeadata
from nordeste.coletores.registro import Coleta, ler_registro, registrar
from nordeste.coletores.sidra import url_sidra
from nordeste.fichas import Ficha, Serie

__all__ = ["ErroColeta", "coletar_serie"]

VALIDADE_PARTE_DIAS = 7  # parte guardada por uma coleta interrompida so e reaproveitada ate esta idade


def _guardar(
    ficha: Ficha, serie: Serie, caminhos: Caminhos, conteudo: bytes,
    url: str, extensao: str, origem: str, hoje: date,
) -> Coleta:
    sha256 = hashlib.sha256(conteudo).hexdigest()
    destino = caminhos.brutos / ficha.id / serie.id / f"{sha256[:8]}.{extensao}"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(conteudo)
    return _registrar(ficha, serie, caminhos, destino, sha256, url, origem, hoje)


def _sha256_arquivo(caminho: Path) -> str:
    resumo = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        while bloco := arquivo.read(1 << 20):
            resumo.update(bloco)
    return resumo.hexdigest()


def _guardar_arquivo(
    ficha: Ficha, serie: Serie, caminhos: Caminhos, arquivo: Path,
    url: str, extensao: str, origem: str, hoje: date,
) -> Coleta:
    """Como `_guardar`, mas move um arquivo ja gravado em disco (sem le-lo inteiro na memoria)."""
    sha256 = _sha256_arquivo(arquivo)
    destino = caminhos.brutos / ficha.id / serie.id / f"{sha256[:8]}.{extensao}"
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(arquivo, destino)
    return _registrar(ficha, serie, caminhos, destino, sha256, url, origem, hoje)


def _registrar(
    ficha: Ficha, serie: Serie, caminhos: Caminhos, destino: Path, sha256: str, url: str, origem: str, hoje: date,
) -> Coleta:
    data = hoje.isoformat()
    return registrar(caminhos.registro_coletas, Coleta(
        coleta_id=f"{ficha.id}.{serie.id}.{data}.{sha256[:8]}",
        indicador_id=ficha.id, serie_id=serie.id, url=url, data_coleta=data,
        sha256=sha256, origem=origem,
        arquivo=destino.relative_to(caminhos.raiz).as_posix(),
    ))


def _coleta_de_rede_existente(ficha: Ficha, serie: Serie, caminhos: Caminhos) -> Coleta | None:
    registro = ler_registro(caminhos.registro_coletas)
    registro = registro[
        (registro["indicador_id"] == ficha.id) & (registro["serie_id"] == serie.id)
        & (registro["origem"] == "rede")
    ]
    for _, linha in registro.iloc[::-1].iterrows():
        coleta = Coleta(**linha.to_dict())
        if (caminhos.raiz / coleta.arquivo).exists():
            return coleta
    return None


def _coletar_offline(ficha: Ficha, serie: Serie, caminhos: Caminhos, hoje: date) -> Coleta:
    existente = _coleta_de_rede_existente(ficha, serie, caminhos)
    if existente is not None:
        return existente
    candidatas = sorted((caminhos.fixtures / ficha.id).glob(f"{serie.id}.*"))
    if not candidatas:
        raise ErroColeta(f"sem fixture para {ficha.id}/{serie.id}")
    if len(candidatas) > 1:
        nomes = ", ".join(c.name for c in candidatas)
        raise ErroColeta(f"mais de uma fixture para {ficha.id}/{serie.id}: {nomes}")
    fixture = candidatas[0]
    return _guardar(
        ficha, serie, caminhos, fixture.read_bytes(),
        url=fixture.relative_to(caminhos.raiz).as_posix(),
        extensao=fixture.suffix.lstrip("."), origem="fixture", hoje=hoje,
    )


def _baixar_ipeadata(parametros: dict, sessao: requests.Session | None) -> bytes:
    """Resposta do Ipeadata; com `codigos`, as respostas de cada codigo num unico JSON {"subindicadores": {...}}.

    Um arquivo por serie mantem uma coleta e um sha256 por serie. A ordem dos subindicadores e a da ficha.
    """
    urls = urls_ipeadata(parametros)
    if "codigos" not in parametros:
        return baixar(urls[""], sessao=sessao)
    respostas = {}
    for subindicador, url in urls.items():
        conteudo = baixar(url, sessao=sessao)
        try:
            respostas[subindicador] = json.loads(conteudo)
        except ValueError as erro:
            raise ErroColeta(f"resposta do Ipeadata ilegivel em {url} ({erro})") from erro
    return json.dumps({"subindicadores": respostas}, ensure_ascii=False).encode("utf-8")


def _ca_extra(parametros: dict, caminhos: Caminhos) -> Path | None:
    ca_extra = parametros.get("ca_extra")
    return caminhos.raiz / ca_extra if ca_extra else None


def _parte_guardada(pasta: Path, chave: str, url: str, receita: Receita, hoje: date) -> ParteBaixada | None:
    """Parte de uma coleta anterior interrompida, se completa, com a mesma receita e com ate VALIDADE_PARTE_DIAS."""
    try:
        dados = json.loads((pasta / f"{chave}.json").read_text(encoding="utf-8"))
        arquivo = pasta / f"{chave}.parte"
        idade = (hoje - date.fromisoformat(dados["baixada_em"])).days
        valida = (
            dados["url"] == url and dados["receita"] == receita_em_json(receita)
            and 0 <= idade <= VALIDADE_PARTE_DIAS and arquivo.is_file()
            and _sha256_arquivo(arquivo) == dados["sha256_parte"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not valida:
        return None
    return ParteBaixada(url, arquivo, dados["sha256_original"], dados["bytes_original"], dados["membros"])


def _parte(
    url: str, receita: Receita, pasta: Path, ca_extra: Path | None, sessao: requests.Session | None, hoje: date,
) -> ParteBaixada:
    """Baixa a URL para o disco, reduz conforme a receita e guarda a parte em `pasta` (ou reaproveita a guardada).

    O original baixado e apagado depois da reducao; fica so o que vai para o pacote. O `.json` da parte e gravado
    por ultimo: sem ele, a parte nao conta como baixada.
    """
    chave = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    guardada = _parte_guardada(pasta, chave, url, receita, hoje)
    if guardada is not None:
        return guardada
    baixando = pasta / f"{chave}.baixando"
    sha256, tamanho = baixar_para_arquivo(url, baixando, sessao=sessao, ca_extra=ca_extra)
    try:
        with tempfile.TemporaryDirectory(dir=pasta, prefix=f"{chave}-") as trabalho:
            try:
                pronta = preparar_parte(url, baixando, sha256, tamanho, receita, Path(trabalho))
            except (ValueError, zlib.error) as erro:  # zlib.error: deflate corrompido no membro
                raise ErroColeta(f"falha ao reduzir {url} ({erro})") from erro
            arquivo = pasta / f"{chave}.parte"
            os.replace(pronta.arquivo, arquivo)
    finally:
        baixando.unlink(missing_ok=True)
    dados = {"url": url, "receita": receita_em_json(receita), "baixada_em": hoje.isoformat(),
             "sha256_original": sha256, "bytes_original": tamanho, "membros": pronta.membros,
             "sha256_parte": _sha256_arquivo(arquivo)}
    provisorio = pasta / f"{chave}.json.tmp"
    provisorio.write_text(json.dumps(dados, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(provisorio, pasta / f"{chave}.json")
    return ParteBaixada(url, arquivo, sha256, tamanho, pronta.membros)


def _coletar_partes(
    ficha: Ficha, serie: Serie, caminhos: Caminhos, hoje: date, sessao: requests.Session | None,
) -> Coleta:
    """Baixa cada URL distinta das partes (com o `ca_extra` da serie), monta o pacote e registra a coleta.

    Cada parte vai para o disco em blocos e e reduzida ao que as partes leem (ver `coletores.arquivo`). Uma URL que
    falha nao interrompe as outras; se alguma falhou, sobe ErroColeta sem pacote nem linha de registro, e as partes
    completas ficam em `partes_em_coleta` para a proxima coleta retomar dali. Com todas as partes, o pacote e
    gravado, registrado, e as partes guardadas sao apagadas.
    """
    parametros = serie.parametros
    receitas = receitas_das_partes(parametros)
    ca_extra = _ca_extra(parametros, caminhos)
    pasta = caminhos.partes_em_coleta / ficha.id / serie.id
    pasta.mkdir(parents=True, exist_ok=True)
    prontas, falhas = [], []
    for url, receita in receitas.items():
        try:
            prontas.append(_parte(url, receita, pasta, ca_extra, sessao, hoje))
        except ErroColeta as erro:
            falhas.append(str(erro))
    if falhas:
        raise ErroColeta(
            f"{len(falhas)} de {len(receitas)} partes falharam: {'; '.join(falhas)}. As {len(prontas)} partes "
            f"completas ficam em {pasta.relative_to(caminhos.raiz).as_posix()} e a próxima coleta (em até "
            f"{VALIDADE_PARTE_DIAS} dias) baixa só o que falta")
    pacote = pasta / "pacote.zip.tmp"
    escrever_pacote(prontas, pacote)
    coleta = _guardar_arquivo(ficha, serie, caminhos, pacote, url_arquivo(parametros), "zip", "rede", hoje)
    shutil.rmtree(pasta, ignore_errors=True)
    for vazia in (pasta.parent, caminhos.partes_em_coleta):  # so sai se nao houver outra serie pela metade
        try:
            vazia.rmdir()
        except OSError:
            break
    return coleta


def _coletar_da_rede(
    ficha: Ficha, serie: Serie, caminhos: Caminhos, hoje: date, sessao: requests.Session | None,
) -> Coleta:
    if not serie.verificado:
        raise ErroColeta(f"série não verificada: {ficha.id}/{serie.id}")
    if serie.coletor == "sidra":
        url, extensao = url_sidra(serie.parametros), "json"
    elif serie.coletor == "ipeadata":
        url, extensao = url_ipeadata(serie.parametros), "json"
        conteudo = _baixar_ipeadata(serie.parametros, sessao)
        return _guardar(ficha, serie, caminhos, conteudo, url, extensao, "rede", hoje)
    elif serie.coletor == "arquivo":
        url = url_arquivo(serie.parametros)
        if "partes" in serie.parametros:
            return _coletar_partes(ficha, serie, caminhos, hoje, sessao)
        extensao = PurePosixPath(urlparse(url).path).suffix.lstrip(".").lower() or "bin"
    else:
        raise ErroColeta(f"coletor desconhecido em {ficha.id}/{serie.id}: {serie.coletor}")
    conteudo = baixar(url, sessao=sessao, ca_extra=_ca_extra(serie.parametros, caminhos))
    return _guardar(ficha, serie, caminhos, conteudo, url, extensao, "rede", hoje)


def coletar_serie(
    ficha: Ficha, serie: Serie, caminhos: Caminhos, offline: bool, hoje: date,
    sessao: requests.Session | None = None,
) -> Coleta:
    """Coleta o arquivo bruto da serie e o registra.

    Offline: reaproveita a ultima coleta de rede cujo arquivo exista, senao usa a fixture.
    Com rede: so coleta series com verificado: true.
    """
    if offline:
        return _coletar_offline(ficha, serie, caminhos, hoje)
    return _coletar_da_rede(ficha, serie, caminhos, hoje, sessao)
