"""Download HTTP com novas tentativas e espera exponencial."""

import os
import tempfile
import time
from pathlib import Path

import certifi
import requests

from nordeste.coletores.erros import ErroColeta

TEMPO_LIMITE_S = 120


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


def baixar(
    url: str,
    tentativas_extras: int = 3,
    espera_inicial: float = 1.0,
    esperar=time.sleep,
    sessao: requests.Session | None = None,
    ca_extra: Path | None = None,
) -> bytes:
    """Baixa a URL; apos cada falha espera espera_inicial * 2**k antes de tentar de novo.

    `ca_extra`: certificado PEM de uma intermediaria que o servidor nao envia; a verificacao usa o bundle
    padrao mais ele (nunca `verify=False`). Esgotadas as tentativas, levanta ErroColeta com a URL.
    """
    sessao = sessao or requests.Session()
    with tempfile.TemporaryDirectory(prefix="nordeste-ca-") as pasta:
        opcoes = {} if ca_extra is None else {"verify": str(_bundle_com_extra(ca_extra, Path(pasta)))}
        ultimo_erro: Exception | None = None
        for tentativa in range(tentativas_extras + 1):
            if tentativa:
                esperar(espera_inicial * 2 ** (tentativa - 1))
            try:
                resposta = sessao.get(url, timeout=TEMPO_LIMITE_S, **opcoes)
                resposta.raise_for_status()
                return resposta.content
            except requests.RequestException as erro:
                ultimo_erro = erro
    raise ErroColeta(
        f"falha ao baixar {url} apos {tentativas_extras + 1} tentativas ({ultimo_erro})"
    ) from ultimo_erro
