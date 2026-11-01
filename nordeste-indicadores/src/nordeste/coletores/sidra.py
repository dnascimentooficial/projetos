"""URL da API de valores do SIDRA (IBGE)."""

_BASE = "https://apisidra.ibge.gov.br/values"
_TERRITORIOS = "n1/all/n2/all/n3/21,22,23,24,25,26,27,28,29"


def url_sidra(parametros: dict) -> str:
    """Monta a URL a partir de tabela, variavel, periodos (padrao all) e classificacoes."""
    url = (
        f"{_BASE}/t/{parametros['tabela']}/{_TERRITORIOS}"
        f"/v/{parametros['variavel']}/p/{parametros.get('periodos', 'all')}"
    )
    for classificacao, categoria in (parametros.get("classificacoes") or {}).items():
        url += f"/{classificacao}/{categoria}"
    return url
