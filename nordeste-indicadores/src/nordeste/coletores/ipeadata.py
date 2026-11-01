"""URL da API OData de valores de serie do Ipeadata."""

from nordeste.coletores.erros import ErroColeta

_BASE = "https://www.ipeadata.gov.br/api/odata4"


def url_ipeadata(parametros: dict) -> str:
    """Monta a URL dos valores da serie a partir de parametros['codigo'] (SERCODIGO)."""
    try:
        codigo = parametros["codigo"]
    except KeyError:
        raise ErroColeta("parametros do coletor ipeadata sem a chave codigo") from None
    return f"{_BASE}/ValoresSerie(SERCODIGO='{codigo}')"
