"""Coleta dos arquivos brutos: rede (SIDRA, arquivos por URL) ou fixtures no modo offline."""

import hashlib
import json
from datetime import date
from pathlib import PurePosixPath
from urllib.parse import urlparse

import requests

from nordeste.caminhos import Caminhos
from nordeste.coletores.arquivo import url_arquivo
from nordeste.coletores.erros import ErroColeta
from nordeste.coletores.http import baixar
from nordeste.coletores.ipeadata import url_ipeadata, urls_ipeadata
from nordeste.coletores.registro import Coleta, ler_registro, registrar
from nordeste.coletores.sidra import url_sidra
from nordeste.fichas import Ficha, Serie

__all__ = ["ErroColeta", "coletar_serie"]


def _guardar(
    ficha: Ficha, serie: Serie, caminhos: Caminhos, conteudo: bytes,
    url: str, extensao: str, origem: str, hoje: date,
) -> Coleta:
    sha256 = hashlib.sha256(conteudo).hexdigest()
    destino = caminhos.brutos / ficha.id / serie.id / f"{sha256[:8]}.{extensao}"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(conteudo)
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
        extensao = PurePosixPath(urlparse(url).path).suffix.lstrip(".").lower() or "bin"
    else:
        raise ErroColeta(f"coletor desconhecido em {ficha.id}/{serie.id}: {serie.coletor}")
    conteudo = baixar(url, sessao=sessao)
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
