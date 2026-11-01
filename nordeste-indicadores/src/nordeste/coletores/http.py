"""Download HTTP com novas tentativas e espera exponencial."""

import hashlib
import os
import tempfile
import time
from pathlib import Path

import certifi
import requests

from nordeste.coletores.erros import ErroColeta

TEMPO_LIMITE_S = 120  # por leitura no socket, nao para o download inteiro
BLOCO_DOWNLOAD = 1 << 20


def _bundle_com_extra(ca_extra: Path, destino: Path) -> Path:
    """Grava em `destino` o bundle de CAs em uso (REQUESTS_CA_BUNDLE, senao certifi) mais `ca_extra`.

    A verificacao TLS segue ligada: o bundle so acrescenta uma intermediaria que o servidor deixou de enviar.
    """
    padrao = Path(os.environ.get("REQUESTS_CA_BUNDLE") or certifi.where())
    try:
        texto = padrao.read_text(encoding="utf-8").rstrip("\n")
        extra = Path(ca_extra).read_text(encoding="utf-8").strip()
    except OSError as erro:
        raise ErroColeta(f"nao foi possivel montar o bundle de certificados com {ca_extra} ({erro})") from erro
    bundle = destino / "bundle.pem"
    bundle.write_text(f"{texto}\n{extra}\n", encoding="utf-8")
    return bundle


def _com_tentativas(url: str, acao, tentativas_extras: int, espera_inicial: float, esperar, ca_extra: Path | None):
    """Chama acao(opcoes) ate dar certo; apos cada falha espera espera_inicial * 2**k antes de tentar de novo.

    `opcoes` tem o `verify` do bundle com `ca_extra`, quando ha (nunca `verify=False`). Esgotadas as tentativas,
    levanta ErroColeta com a URL.
    """
    with tempfile.TemporaryDirectory(prefix="nordeste-ca-") as pasta:
        opcoes = {} if ca_extra is None else {"verify": str(_bundle_com_extra(ca_extra, Path(pasta)))}
        ultimo_erro: Exception | None = None
        for tentativa in range(tentativas_extras + 1):
            if tentativa:
                esperar(espera_inicial * 2 ** (tentativa - 1))
            try:
                return acao(opcoes)
            except requests.RequestException as erro:
                ultimo_erro = erro
    raise ErroColeta(
        f"falha ao baixar {url} apos {tentativas_extras + 1} tentativas ({ultimo_erro})"
    ) from ultimo_erro


def baixar(
    url: str,
    tentativas_extras: int = 3,
    espera_inicial: float = 1.0,
    esperar=time.sleep,
    sessao: requests.Session | None = None,
    ca_extra: Path | None = None,
) -> bytes:
    """Baixa a URL para a memoria; apos cada falha espera espera_inicial * 2**k antes de tentar de novo.

    `ca_extra`: certificado PEM de uma intermediaria que o servidor nao envia; a verificacao usa o bundle
    padrao mais ele (nunca `verify=False`). Esgotadas as tentativas, levanta ErroColeta com a URL.
    """
    sessao = sessao or requests.Session()

    def acao(opcoes: dict) -> bytes:
        resposta = sessao.get(url, timeout=TEMPO_LIMITE_S, **opcoes)
        resposta.raise_for_status()
        return resposta.content

    return _com_tentativas(url, acao, tentativas_extras, espera_inicial, esperar, ca_extra)


def baixar_para_arquivo(
    url: str,
    destino: Path,
    tentativas_extras: int = 3,
    espera_inicial: float = 1.0,
    esperar=time.sleep,
    sessao: requests.Session | None = None,
    ca_extra: Path | None = None,
) -> tuple[str, int]:
    """Baixa a URL em blocos direto para `destino`, sem carregar o arquivo na memoria; devolve (sha256, bytes).

    Mesmas tentativas e mesma verificacao TLS de `baixar`. Cada tentativa recomeca o arquivo do zero; se todas
    falharem, `destino` e apagado e sobe ErroColeta.
    """
    sessao = sessao or requests.Session()

    def acao(opcoes: dict) -> tuple[str, int]:
        resumo, tamanho = hashlib.sha256(), 0
        with sessao.get(url, timeout=TEMPO_LIMITE_S, stream=True, **opcoes) as resposta:
            resposta.raise_for_status()
            with destino.open("wb") as saida:
                for bloco in resposta.iter_content(chunk_size=BLOCO_DOWNLOAD):
                    saida.write(bloco)
                    resumo.update(bloco)
                    tamanho += len(bloco)
        return resumo.hexdigest(), tamanho

    try:
        return _com_tentativas(url, acao, tentativas_extras, espera_inicial, esperar, ca_extra)
    except BaseException:
        destino.unlink(missing_ok=True)
        raise
