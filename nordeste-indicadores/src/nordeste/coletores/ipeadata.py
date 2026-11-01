"""URLs da API OData de valores de serie do Ipeadata."""

from nordeste.coletores.erros import ErroColeta

_BASE = "https://www.ipeadata.gov.br/api/odata4"


def _url(codigo: str) -> str:
    return f"{_BASE}/ValoresSerie(SERCODIGO='{codigo}')"


def urls_ipeadata(parametros: dict) -> dict[str, str]:
    """URLs a baixar, por subindicador ("" para o modo de codigo unico), na ordem declarada.

    `codigo` (SERCODIGO unico, subindicador vazio) ou `codigos` (mapa subindicador -> SERCODIGO, para quando
    o indicador tem um codigo do Ipeadata por subindicador); os dois juntos nao valem.
    """
    if "codigos" in parametros:
        if "codigo" in parametros:
            raise ErroColeta("parametros do coletor ipeadata com codigo e codigos ao mesmo tempo")
        codigos = parametros["codigos"]
        valido = isinstance(codigos, dict) and codigos and all(
            isinstance(k, str) and k and isinstance(v, str) and v for k, v in codigos.items())
        if not valido:
            raise ErroColeta("parametros['codigos'] do coletor ipeadata deve mapear subindicador para codigo (textos nao vazios)")
        return {subindicador: _url(codigo) for subindicador, codigo in codigos.items()}
    try:
        return {"": _url(parametros["codigo"])}
    except KeyError:
        raise ErroColeta("parametros do coletor ipeadata sem a chave codigo (ou codigos)") from None


def url_ipeadata(parametros: dict) -> str:
    """URL registrada da coleta: a da serie; com `codigos`, as URLs de cada codigo separadas por um espaco."""
    return " ".join(urls_ipeadata(parametros).values())
