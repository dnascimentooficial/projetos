"""Coletor generico de arquivos por URL (planilhas e similares)."""

from nordeste.coletores.erros import ErroColeta


def url_arquivo(parametros: dict) -> str:
    try:
        return parametros["url"]
    except KeyError:
        raise ErroColeta("parametros do coletor arquivo sem a chave url") from None
