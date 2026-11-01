"""Gera as fixtures sinteticas em testes/fixtures/<indicador_id>/<serie_id>.<ext>.

Uso, a partir da raiz do projeto: python testes/fixtures/gerar_fixtures.py
Os valores sao derivados de 99999 e nao representam dado oficial.
"""

import json
from pathlib import Path

PASTA = Path(__file__).resolve().parent
ANOS = range(2002, 2024)
BASE = 99999

# (nivel NC, codigo IBGE, nome, multiplicador de BASE): UFs do NE, depois as regioes e o Brasil.
_TERRITORIOS = [
    ("1", "1", "Brasil", 13),
    ("2", "1", "Norte", 1), ("2", "2", "Nordeste", 9), ("2", "3", "Sudeste", 1),
    ("2", "4", "Sul", 1), ("2", "5", "Centro-Oeste", 1),
    ("3", "21", "Maranhão", 1), ("3", "22", "Piauí", 1), ("3", "23", "Ceará", 1),
    ("3", "24", "Rio Grande do Norte", 1), ("3", "25", "Paraíba", 1),
    ("3", "26", "Pernambuco", 1), ("3", "27", "Alagoas", 1), ("3", "28", "Sergipe", 1),
    ("3", "29", "Bahia", 1),
]
_NIVEIS = {"1": "Brasil", "2": "Grande Região", "3": "Unidade da Federação"}

_CABECALHO = {
    "NC": "Nível Territorial (Código)", "NN": "Nível Territorial",
    "MC": "Unidade de Medida (Código)", "MN": "Unidade de Medida", "V": "Valor",
    "D1C": "Brasil, Grande Região e Unidade da Federação (Código)",
    "D1N": "Brasil, Grande Região e Unidade da Federação",
    "D2C": "Ano (Código)", "D2N": "Ano", "D3C": "Variável (Código)", "D3N": "Variável",
}


def json_sidra(variavel: str, unidade_codigo: str, unidade: str, valor) -> list[dict]:
    """Monta o JSON SIDRA sintetico; `valor(nc, codigo, ano, multiplicador)` devolve o texto de V."""
    linhas = [_CABECALHO]
    for ano in ANOS:
        for nc, codigo, nome, multiplicador in _TERRITORIOS:
            linhas.append({
                "NC": nc, "NN": _NIVEIS[nc], "MC": unidade_codigo, "MN": unidade,
                "V": valor(nc, codigo, ano, multiplicador),
                "D1C": codigo, "D1N": nome, "D2C": str(ano), "D2N": str(ano),
                "D3C": "99999", "D3N": variavel,
            })
    return linhas


def _soma(nc, codigo, ano, multiplicador) -> str:
    return str(BASE * multiplicador)


def _per_capita(nc, codigo, ano, multiplicador) -> str:
    return "..." if (nc, codigo, ano) == ("3", "27", 2010) else "1000"


GERADORES = {
    "pib_nominal/scr_ref2010.json": lambda: json_sidra(
        "PIB a preços correntes (sintético)", "99999", "Mil Reais", _soma),
    "populacao_contas_regionais/scr_ref2010.json": lambda: json_sidra(
        "População (sintético)", "99998", "Pessoas", _soma),
    "pib_per_capita/scr_ref2010.json": lambda: json_sidra(
        "PIB per capita (sintético)", "99997", "Reais", _per_capita),
}


def _serializar(linhas: list[dict]) -> str:
    """Uma linha do JSON SIDRA por linha de texto, para diffs legiveis."""
    return "[\n" + ",\n".join(json.dumps(l, ensure_ascii=False) for l in linhas) + "\n]\n"


def main() -> None:
    for relativo, gerar in GERADORES.items():
        destino = PASTA / relativo
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(_serializar(gerar()), encoding="utf-8")
        print(f"gerado: {destino.relative_to(PASTA.parent.parent)}")


if __name__ == "__main__":
    main()
