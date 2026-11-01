"""URL da API de valores do SIDRA (IBGE)."""

from nordeste.coletores.erros import ErroColeta

_BASE = "https://apisidra.ibge.gov.br/values"
_TERRITORIOS = "n1/all/n2/all/n3/21,22,23,24,25,26,27,28,29"


def url_sidra(parametros: dict) -> str:
    """Monta a URL a partir de tabela, variavel, periodos (padrao all) e classificacoes.

    Sem tabela ou variavel (texto nao vazio), ErroColeta: a ficha nao diz o que buscar.
    """
    faltando = [c for c in ("tabela", "variavel") if not str(parametros.get(c) or "").strip()]
    if faltando:
        raise ErroColeta(f"parametros do SIDRA sem {' e '.join(faltando)}")
    url = (
        f"{_BASE}/t/{parametros['tabela']}/{_TERRITORIOS}"
        f"/v/{parametros['variavel']}/p/{parametros.get('periodos', 'all')}"
    )
    for classificacao, categoria in (parametros.get("classificacoes") or {}).items():
        url += f"/{classificacao}/{categoria}"
    return url
