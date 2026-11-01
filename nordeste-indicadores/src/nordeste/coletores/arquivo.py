"""Coletor generico de arquivos por URL (planilhas e similares), com uma URL ou varias partes por serie.

Com `parametros.partes`, cada URL distinta das partes e baixada uma vez e o arquivo bruto da serie e um
pacote zip deterministico: `manifesto.json` (lista de {url, nome}, na ordem da primeira aparicao da URL nas
partes) e um arquivo por URL, com o nome do manifesto. Data fixa e ordem fixa: o mesmo conteudo da fonte
gera os mesmos bytes, e portanto o mesmo sha256 (uma coleta por serie, como no Ipeadata com `codigos`).
"""

import io
import json
import zipfile
from pathlib import PurePosixPath
from urllib.parse import urlparse

from nordeste.coletores.erros import ErroColeta

MANIFESTO = "manifesto.json"
_DATA_FIXA = (2026, 1, 1, 0, 0, 0)


def urls_arquivo(parametros: dict) -> list[str]:
    """URLs a baixar: a `url` da serie ou as URLs distintas de `partes`, na ordem da primeira aparicao."""
    if "partes" in parametros:
        if "url" in parametros:
            raise ErroColeta("parametros do coletor arquivo com url e partes ao mesmo tempo")
        partes = parametros["partes"]
        valido = isinstance(partes, list) and partes and all(
            isinstance(p, dict) and isinstance(p.get("url"), str) and p["url"] for p in partes)
        if not valido:
            raise ErroColeta("parametros['partes'] do coletor arquivo deve ser uma lista de partes, cada uma com url")
        return list(dict.fromkeys(p["url"] for p in partes))
    try:
        return [parametros["url"]]
    except KeyError:
        raise ErroColeta("parametros do coletor arquivo sem a chave url (ou partes)") from None


def url_arquivo(parametros: dict) -> str:
    """URL registrada da coleta: a da serie; com `partes`, as URLs distintas separadas por um espaco."""
    return " ".join(urls_arquivo(parametros))


def _entrada(nome: str) -> zipfile.ZipInfo:
    entrada = zipfile.ZipInfo(nome, date_time=_DATA_FIXA)
    entrada.compress_type = zipfile.ZIP_DEFLATED
    return entrada


def empacotar_partes(baixados: dict[str, bytes]) -> bytes:
    """Pacote zip com o manifesto e um arquivo por URL, na ordem de `baixados`."""
    manifesto = []
    for posicao, url in enumerate(baixados, start=1):
        base = PurePosixPath(urlparse(url).path).name or "arquivo"
        manifesto.append({"url": url, "nome": f"{posicao:02d}_{base}"})
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as pacote:
        texto = json.dumps({"arquivos": manifesto}, ensure_ascii=False, indent=1) + "\n"
        pacote.writestr(_entrada(MANIFESTO), texto.encode("utf-8"))
        for item in manifesto:
            pacote.writestr(_entrada(item["nome"]), baixados[item["url"]])
    return saida.getvalue()


def ler_pacote(conteudo: bytes) -> dict[str, bytes]:
    """Conteudo de cada URL do pacote; ValueError se o pacote estiver ilegivel ou incompleto."""
    try:
        with zipfile.ZipFile(io.BytesIO(conteudo)) as pacote:
            manifesto = json.loads(pacote.read(MANIFESTO).decode("utf-8"))
            return {item["url"]: pacote.read(item["nome"]) for item in manifesto["arquivos"]}
    except (zipfile.BadZipFile, KeyError, TypeError, ValueError) as erro:
        raise ValueError(f"pacote de partes ilegível ({erro!r})") from erro
