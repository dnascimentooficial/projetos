"""Gera as fixtures sinteticas em testes/fixtures/<indicador_id>/<serie_id>.<ext>.

Uso, a partir da raiz do projeto: python testes/fixtures/gerar_fixtures.py
Os valores sao derivados de 99999 e nao representam dado oficial.
"""

import io
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook

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

# Cabecalho de uma resposta SIDRA com uma variavel (D2) e o ano (D3), como na API real.
_CABECALHO = {
    "NC": "Nível Territorial (Código)", "NN": "Nível Territorial",
    "MC": "Unidade de Medida (Código)", "MN": "Unidade de Medida", "V": "Valor",
    "D1C": "Brasil, Grande Região e Unidade da Federação (Código)",
    "D1N": "Brasil, Grande Região e Unidade da Federação",
    "D2C": "Variável (Código)", "D2N": "Variável", "D3C": "Ano (Código)", "D3N": "Ano",
}


def json_sidra(
    variavel: str, unidade_codigo: str, unidade: str, valor,
    anos=ANOS, classificacoes: tuple[tuple[str, str], ...] = (),
) -> list[dict]:
    """Monta o JSON SIDRA sintetico; `valor(nc, codigo, ano, multiplicador)` devolve o texto de V.

    `classificacoes` e uma tupla de (rotulo, codigo) das classificacoes da tabela, todas no total
    (colunas D4, D5, ...), como a API devolve quando a consulta fixa a categoria Total.
    """
    cabecalho = dict(_CABECALHO)
    for posicao, (rotulo, _) in enumerate(classificacoes, start=4):
        cabecalho[f"D{posicao}C"], cabecalho[f"D{posicao}N"] = f"{rotulo} (Código)", rotulo
    linhas = [cabecalho]
    for ano in anos:
        for nc, codigo, nome, multiplicador in _TERRITORIOS:
            linha = {
                "NC": nc, "NN": _NIVEIS[nc], "MC": unidade_codigo, "MN": unidade,
                "V": valor(nc, codigo, ano, multiplicador),
                "D1C": codigo, "D1N": nome, "D2C": "99999", "D2N": variavel,
                "D3C": str(ano), "D3N": str(ano),
            }
            for posicao, (_, categoria) in enumerate(classificacoes, start=4):
                linha[f"D{posicao}C"], linha[f"D{posicao}N"] = categoria, "Total"
            linhas.append(linha)
    return linhas


def xlsx_sintetico(aba: str, linhas: list[list]) -> bytes:
    """Monta um .xlsx com uma aba; `linhas` inclui titulos, cabecalho e dados, na ordem da planilha.

    Datas fixas nas propriedades e no zip: a mesma entrada gera sempre os mesmos bytes.
    """
    pasta = Workbook()
    planilha = pasta.active
    planilha.title = aba
    for linha in linhas:
        planilha.append(linha)
    pasta.properties.created = pasta.properties.modified = datetime(2026, 1, 1)
    gravado = io.BytesIO()
    pasta.save(gravado)
    saida = io.BytesIO()
    with zipfile.ZipFile(gravado) as origem, zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as destino:
        for item in origem.infolist():
            novo = zipfile.ZipInfo(item.filename, date_time=(2026, 1, 1, 0, 0, 0))
            novo.compress_type = zipfile.ZIP_DEFLATED
            conteudo = origem.read(item)
            if item.filename == "docProps/core.xml":  # o openpyxl regrava `modified` ao salvar
                conteudo = re.sub(rb"(<dcterms:modified[^>]*>)[^<]*", rb"\g<1>2026-01-01T00:00:00Z", conteudo)
            destino.writestr(novo, conteudo)
    return saida.getvalue()


def json_ipeadata(registros: list[tuple]) -> dict:
    """Monta a resposta OData do Ipeadata; cada registro e (NIVNOME, TERCODIGO, VALDATA, VALVALOR)."""
    return {"value": [
        {"SERCODIGO": "SINTETICO", "VALDATA": data, "VALVALOR": valor,
         "NIVNOME": nivel, "TERCODIGO": codigo}
        for nivel, codigo, data, valor in registros
    ]}


def _soma(nc, codigo, ano, multiplicador) -> str:
    return str(BASE * multiplicador)


def _per_capita(nc, codigo, ano, multiplicador) -> str:
    return "..." if (nc, codigo, ano) == ("3", "27", 2010) else "1000"


def _participacao(nc, codigo, ano, multiplicador) -> str:
    """Participacao no PIB do Brasil: multiplicador / 13 (o do Brasil) em %, com duas casas, como o SIDRA."""
    return f"{multiplicador / 13 * 100:.2f}"


# Anos em que a tabela 6579 (estimativas de populacao) tem valores; 2007, 2010 e 2022 sao de contagem
# e censo, e 2023 nao foi publicado.
ANOS_ESTIMATIVA_PRE_CENSO2022 = [*range(2001, 2007), 2008, 2009, *range(2011, 2022)]
ANOS_ESTIMATIVA_POS_CENSO2022 = [2024, 2025, 2026]

GERADORES = {
    "pib_nominal/scr_ref2010.json": lambda: json_sidra(
        "PIB a preços correntes (sintético)", "99999", "Mil Reais", _soma),
    "populacao_contas_regionais/scr_ref2010.json": lambda: json_sidra(
        "População (sintético)", "99998", "Pessoas", _soma),
    "pib_per_capita/scr_ref2010.json": lambda: json_sidra(
        "PIB per capita (sintético)", "99997", "Reais", _per_capita),
    "pib_participacao/scr_ref2010.json": lambda: json_sidra(
        "Participação do PIB no PIB do Brasil (sintético)", "2", "%", _participacao),
    "populacao/estimativa_pre_censo2022.json": lambda: json_sidra(
        "População residente estimada (sintético)", "45", "Pessoas", _soma,
        anos=ANOS_ESTIMATIVA_PRE_CENSO2022),
    "populacao/estimativa_pos_censo2022.json": lambda: json_sidra(
        "População residente estimada (sintético)", "45", "Pessoas", _soma,
        anos=ANOS_ESTIMATIVA_POS_CENSO2022),
    "populacao/censo_2000_2010.json": lambda: json_sidra(
        "População residente (sintético)", "45", "Pessoas", _soma, anos=[2000, 2010],
        classificacoes=(("Situação do domicílio", "0"), ("Sexo", "0"))),
    "populacao/censo_2022.json": lambda: json_sidra(
        "População residente (sintético)", "45", "Pessoas", _soma, anos=[2022]),
}


def _serializar(linhas: list[dict]) -> str:
    """Uma linha do JSON SIDRA por linha de texto, para diffs legiveis."""
    return "[\n" + ",\n".join(json.dumps(l, ensure_ascii=False) for l in linhas) + "\n]\n"


def _escrever(destino: Path, conteudo) -> None:
    """Grava bytes (xlsx), lista (JSON SIDRA) ou dict (JSON Ipeadata)."""
    if isinstance(conteudo, bytes):
        destino.write_bytes(conteudo)
    elif isinstance(conteudo, dict):
        destino.write_text(json.dumps(conteudo, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    else:
        destino.write_text(_serializar(conteudo), encoding="utf-8")


def main() -> None:
    for relativo, gerar in GERADORES.items():
        destino = PASTA / relativo
        destino.parent.mkdir(parents=True, exist_ok=True)
        _escrever(destino, gerar())
        print(f"gerado: {destino.relative_to(PASTA.parent.parent)}")


if __name__ == "__main__":
    main()
