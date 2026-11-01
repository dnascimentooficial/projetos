"""Download HTTP com novas tentativas e espera exponencial."""

import time

import requests

from nordeste.coletores.erros import ErroColeta

TEMPO_LIMITE_S = 120


def baixar(
    url: str,
    tentativas_extras: int = 3,
    espera_inicial: float = 1.0,
    esperar=time.sleep,
    sessao: requests.Session | None = None,
) -> bytes:
    """Baixa a URL; apos cada falha espera espera_inicial * 2**k antes de tentar de novo.

    Esgotadas as tentativas, levanta ErroColeta com a URL.
    """
    sessao = sessao or requests.Session()
    ultimo_erro: Exception | None = None
    for tentativa in range(tentativas_extras + 1):
        if tentativa:
            esperar(espera_inicial * 2 ** (tentativa - 1))
        try:
            resposta = sessao.get(url, timeout=TEMPO_LIMITE_S)
            resposta.raise_for_status()
            return resposta.content
        except requests.RequestException as erro:
            ultimo_erro = erro
    raise ErroColeta(
        f"falha ao baixar {url} apos {tentativas_extras + 1} tentativas ({ultimo_erro})"
    ) from ultimo_erro
