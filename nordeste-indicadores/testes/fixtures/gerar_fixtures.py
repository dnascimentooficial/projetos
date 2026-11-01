"""Gera as fixtures sinteticas em testes/fixtures/<indicador_id>/<serie_id>.<ext>.

Tambem gera as fixtures das fichas de teste da amostra (testes/amostra/fixtures/), que a fixture
`projeto` dos testes copia para testes/fixtures/ do projeto temporario.

Uso, a partir da raiz do projeto: python testes/fixtures/gerar_fixtures.py
Os valores sao derivados de 99999 e nao representam dado oficial.
"""

import io
import json
import re
import struct
import zipfile
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook

PASTA = Path(__file__).resolve().parent
PASTA_AMOSTRA = PASTA.parent / "amostra" / "fixtures"
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

    `classificacoes` e uma tupla de (rotulo, codigo) ou (rotulo, codigo, nome da categoria) das classificacoes
    da tabela (colunas D4, D5, ...), como a API devolve quando a consulta fixa a categoria; sem nome, "Total".
    """
    cabecalho = dict(_CABECALHO)
    for posicao, (rotulo, *_) in enumerate(classificacoes, start=4):
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
            for posicao, (_, categoria, *nome) in enumerate(classificacoes, start=4):
                linha[f"D{posicao}C"], linha[f"D{posicao}N"] = categoria, (nome or ["Total"])[0]
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


_FIM_DE_CADEIA, _LIVRE = 0xFFFFFFFE, 0xFFFFFFFF
_TAMANHO_SETOR = 512


def _registro_biff(codigo: int, dados: bytes) -> bytes:
    return struct.pack("<HH", codigo, len(dados)) + dados


def _texto_biff(texto: str, tamanho_bytes: int) -> bytes:
    """String Unicode do BIFF8 (UTF-16, sem compressao); o tamanho vem em 1 ou 2 bytes."""
    prefixo = struct.pack("<B" if tamanho_bytes == 1 else "<H", len(texto))
    return prefixo + b"\x01" + texto.encode("utf-16-le")


def _fluxo_biff8(aba: str, linhas: list[list]) -> bytes:
    """Fluxo `Workbook` minimo: globais com uma aba e as celulas de texto e numero da planilha."""
    def bof(tipo: int) -> bytes:
        return _registro_biff(0x0809, struct.pack("<HHHHII", 0x0600, tipo, 0x0DBB, 0x07CC, 0, 6))

    nome = _texto_biff(aba, 1)
    tamanho_globais = len(bof(0x0005)) + 6 + (4 + 4 + 2 + len(nome)) + 4  # BOF, CODEPAGE, ABA, EOF
    celulas = b""
    for i, linha in enumerate(linhas):
        for j, valor in enumerate(linha):
            if valor is None:
                continue
            if isinstance(valor, str):
                celulas += _registro_biff(0x0204, struct.pack("<HHH", i, j, 0) + _texto_biff(valor, 2))
            else:
                celulas += _registro_biff(0x0203, struct.pack("<HHHd", i, j, 0, float(valor)))
    return (
        bof(0x0005) + _registro_biff(0x0042, struct.pack("<H", 1200))
        + _registro_biff(0x0085, struct.pack("<IH", tamanho_globais, 0) + nome)
        + _registro_biff(0x000A, b"")
        + bof(0x0010) + celulas + _registro_biff(0x000A, b"")
    )


def _entrada_diretorio(nome: str, tipo: int, filho: int, inicio: int, tamanho: int) -> bytes:
    codificado = nome.encode("utf-16-le")
    return (
        codificado.ljust(64, b"\0") + struct.pack("<HBB", len(codificado) + 2 if nome else 0, tipo, 1)
        + struct.pack("<III", _LIVRE, _LIVRE, filho) + bytes(16 + 4 + 8 + 8)
        + struct.pack("<IQ", inicio, tamanho)
    )


def xls_sintetico(aba: str, linhas: list[list]) -> bytes:
    """Monta um .xls (BIFF8 em contêiner OLE2) com uma aba; `linhas` como em `xlsx_sintetico`.

    Escritor minimo, so com texto e numero, para nao depender de uma biblioteca de escrita de .xls.
    O fluxo e completado a ao menos 4096 bytes para dispensar o mini-fluxo do OLE2; sem datas: bytes estaveis.
    """
    fluxo = _fluxo_biff8(aba, linhas)
    setores = max(-(-len(fluxo) // _TAMANHO_SETOR), 4096 // _TAMANHO_SETOR)  # o diretorio vem depois, depois a FAT
    fluxo = fluxo.ljust(setores * _TAMANHO_SETOR, b"\0")
    fat = 1
    while fat * 128 < setores + 1 + fat:
        fat += 1
    diretorio = setores
    tabela = [*range(1, setores), _FIM_DE_CADEIA, _FIM_DE_CADEIA]  # fluxo, depois o diretorio
    tabela += [0xFFFFFFFD] * fat  # setores da propria FAT
    tabela += [_LIVRE] * (fat * 128 - len(tabela))
    cabecalho = (
        bytes.fromhex("D0CF11E0A1B11AE1") + bytes(16) + struct.pack("<HHHHH", 0x3E, 3, 0xFFFE, 9, 6)
        + bytes(6) + struct.pack("<IIIIIIIII", 0, fat, diretorio, 0, 4096, _FIM_DE_CADEIA, 0, _FIM_DE_CADEIA, 0)
        + b"".join(struct.pack("<I", diretorio + 1 + k) for k in range(fat))
    ).ljust(_TAMANHO_SETOR, b"\xff")
    entradas = (
        _entrada_diretorio("Root Entry", 5, 1, _FIM_DE_CADEIA, 0)
        + _entrada_diretorio("Workbook", 2, _LIVRE, 0, len(fluxo))
        + _entrada_diretorio("", 0, _LIVRE, 0, 0) * 2
    )
    return cabecalho + fluxo + entradas + struct.pack(f"<{len(tabela)}I", *tabela)


# Linhas da Tabela 3 das Contas Regionais (tab03.xls): Brasil e regioes com nome recuado por espacos,
# cada regiao seguida das suas UFs, como no arquivo do IBGE.
_LINHAS_TABELA3 = [
    "          Brasil",
    "          Norte", "Rondônia", "Acre", "Amazonas", "Roraima", "Pará", "Amapá", "Tocantins",
    "          Nordeste", "Maranhão", "Piauí", "Ceará", "Rio Grande do Norte", "Paraíba",
    "Pernambuco", "Alagoas", "Sergipe", "Bahia",
    "          Sudeste", "Minas Gerais", "Espírito Santo", "Rio de Janeiro", "São Paulo",
    "          Sul", "Paraná", "Santa Catarina", "Rio Grande do Sul",
    "          Centro-Oeste", "Mato Grosso do Sul", "Mato Grosso ", "Goiás", "Distrito Federal",
]


def zip_com_um_arquivo(nome: str, conteudo: bytes) -> bytes:
    """Zip com um unico arquivo, com data fixa: a mesma entrada gera sempre os mesmos bytes."""
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as pacote:
        item = zipfile.ZipInfo(nome, date_time=(2026, 1, 1, 0, 0, 0))
        item.compress_type = zipfile.ZIP_DEFLATED
        pacote.writestr(item, conteudo)
    return saida.getvalue()


def zip_tabela3_volume() -> bytes:
    """Especiais_2002_2023_xls.zip sintetico: so tab03.xls, no layout real (anos na 4a linha, 2002-2023).

    Todo valor e 99999: o indice de cada territorio nao soma nem se compoe com os demais.
    """
    anos = list(ANOS)
    linhas = [
        ["Tabela 3 - Série encadeada do volume do Produto Interno Bruto (sintético)"],
        [],
        ["Brasil, Grandes Regiões\ne\nUnidades da Federação",
         "Série encadeada do volume do Produto Interno Bruto (base:2002 = 100)"],
        [None, *anos],
        *([nome, *[BASE] * len(anos)] for nome in _LINHAS_TABELA3),
        ["Fonte: IBGE, em parceria com os Órgãos Estaduais de Estatística (sintético)."],
    ]
    return zip_com_um_arquivo("tab03.xls", xls_sintetico("Tabela3", linhas))


def json_ipeadata(registros: list[tuple]) -> dict:
    """Monta a resposta OData do Ipeadata; cada registro e (NIVNOME, TERCODIGO, VALDATA, VALVALOR)."""
    return {"value": [
        {"SERCODIGO": "SINTETICO", "VALDATA": data, "VALVALOR": valor,
         "NIVNOME": nivel, "TERCODIGO": codigo}
        for nivel, codigo, data, valor in registros
    ]}


_NIVEL_IPEADATA = {"1": "Brasil", "2": "Regiões", "3": "Estados"}


def json_ipeadata_anual(anos, valor: float, metropoles: bool = False) -> dict:
    """Resposta OData do Ipeadata com o mesmo valor em todo territorio e ano.

    Como na resposta real, o Brasil vem com TERCODIGO vazio, e regioes e UFs com o codigo do IBGE.
    `metropoles` acrescenta uma linha de area metropolitana por ano, que o padronizador descarta.
    """
    registros = [
        (_NIVEL_IPEADATA[nc], "" if nc == "1" else codigo, f"{ano}-01-01T00:00:00-02:00", valor)
        for ano in anos for nc, codigo, _, _ in _TERRITORIOS
    ]
    if metropoles:
        registros += [("Área metropolitana", "1", f"{ano}-01-01T00:00:00-02:00", valor) for ano in anos]
    return json_ipeadata(registros)


# IDHM (Ipeadata, series encadeadas): um codigo por subindicador, reunidos pelo coletor num JSON combinado
# {"subindicadores": {<subindicador>: <resposta OData>}}. Valores constantes e distintos por subindicador (um indice
# nao soma nem se compoe a partir das UFs). Como na resposta real: 1991, 2000 e 2010 so com Brasil e UFs, e as
# regioes (e o Brasil) so de 2012 em diante; a ficha recorta a janela de cada serie (`periodos`).
VALORES_IDHM = {"idhm": 0.5, "renda": 0.6, "educacao": 0.4, "longevidade": 0.7}
ANOS_IDHM_CENSO = [1991, 2000, 2010]
ANOS_IDHM_PNADC = range(2012, 2025)


def json_idhm_combinado() -> dict:
    def resposta(valor: float) -> dict:
        registros = [
            (_NIVEL_IPEADATA[nc], "" if nc == "1" else codigo, f"{ano}-01-01T00:00:00-02:00", valor)
            for ano in [*ANOS_IDHM_CENSO, *ANOS_IDHM_PNADC] for nc, codigo, _, _ in _TERRITORIOS
            if nc != "2" or ano >= 2012
        ]
        return json_ipeadata(registros)

    return {"subindicadores": {nome: resposta(valor) for nome, valor in VALORES_IDHM.items()}}


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

# Bloco IBGE, parte B. PNAD Continua anual: rendimento de todas as fontes e taxas desde 2012, informalidade desde 2016,
# pobreza ate 2024 (a tabela do ODS fecha um ano antes). A PNAD antiga (Ipeadata) nao tem 2010.
ANOS_PNADC = range(2012, 2026)
ANOS_INFORMALIDADE = range(2016, 2026)
ANOS_POBREZA = range(2012, 2025)
# O Ipeadata devolve a serie inteira da PNAD antiga; a ficha guarda so 2001 a 2014 (parametro `periodos`). A PNAD nao foi a
# campo nos anos de Censo (1980, 1991, 2000 e 2010) nem em 1994; o PGINI comeca em 1976 e o Dese_Pnad, em 1992.
ANOS_PNAD_ANTIGA = [*range(2001, 2010), *range(2011, 2015)]
ANOS_PGINI = [*range(1976, 1980), *range(1981, 1991), 1992, 1993, *range(1995, 2000), *ANOS_PNAD_ANTIGA]
ANOS_DESE_PNAD = [1992, 1993, *range(1995, 2000), *ANOS_PNAD_ANTIGA]
ANOS_SEM_CONTAGEM_REGIONAL = (2020, 2021, 2022)  # desocupados e forca de trabalho: so o Brasil tem valor
_CLASSE_RENDA = (("Classes de percentual das pessoas em ordem crescente de rendimento domiciliar per capita", "49243"),)
_SEXO_TOTAL = (("Sexo", "6794"),)


def _constante(valor: str):
    return lambda nc, codigo, ano, multiplicador: valor


def _soma_vezes(fator: int):
    return lambda nc, codigo, ano, multiplicador: str(BASE * multiplicador * fator)


def _contagem_sem_regioes(fator: int):
    """Contagem anual com as regioes e UFs sem valor ("...") nos anos em que o IBGE so publica o Brasil."""
    soma = _soma_vezes(fator)
    return lambda nc, codigo, ano, multiplicador: (
        "..." if nc != "1" and ano in ANOS_SEM_CONTAGEM_REGIONAL else soma(nc, codigo, ano, multiplicador))


GERADORES = {
    "pib_nominal/scr_ref2010.json": lambda: json_sidra(
        "PIB a preços correntes (sintético)", "99999", "Mil Reais", _soma),
    "pib_volume/scr_ref2010.zip": zip_tabela3_volume,
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
    # Rendimento: a razao massa / populacao x 1000 (1000 em todo territorio e no Brasil fora do NE) bate com a media.
    "populacao_pnadc/pnadc.json": lambda: json_sidra(
        "População (sintético)", "49", "Mil pessoas", _soma, anos=ANOS_PNADC),
    "massa_renda_dom_pc/pnadc.json": lambda: json_sidra(
        "Massa de rendimento mensal real domiciliar per capita (sintético)", "36", "Milhões de Reais", _soma,
        anos=ANOS_PNADC, classificacoes=_CLASSE_RENDA),
    "renda_dom_pc/pnadc.json": lambda: json_sidra(
        "Rendimento médio mensal real domiciliar per capita (sintético)", "38", "Reais", _constante("1000"),
        anos=ANOS_PNADC, classificacoes=_CLASSE_RENDA),
    "pobreza/pnadc.json": lambda: json_sidra(
        "Proporção da população abaixo da linha de pobreza nacional (sintético)", "2", "Proporção (%)",
        _constante("50.0"), anos=ANOS_POBREZA),
    "extrema_pobreza/pnadc.json": lambda: json_sidra(
        "Proporção da população abaixo da linha de pobreza internacional (sintético)", "2", "Proporção (%)",
        _constante("10.0"), anos=ANOS_POBREZA),
    "gini/pnad.json": lambda: json_ipeadata_anual(ANOS_PGINI, 0.5),
    "gini/pnadc.json": lambda: json_sidra(
        "Índice de Gini do rendimento domiciliar per capita (sintético)", "75", "Índice", _constante("0.5"),
        anos=ANOS_PNADC),
    # Desocupacao: desocupados / forca de trabalho x 100 = 10 em todo territorio, e o mesmo valor no Brasil fora do NE.
    "desocupacao/pnad.json": lambda: json_ipeadata_anual(ANOS_DESE_PNAD, 10.0, metropoles=True),
    "desocupacao/pnadc.json": lambda: json_sidra(
        "Taxa de desocupação (sintético)", "2", "%", _constante("10.0"), anos=ANOS_PNADC),
    "desocupados/pnadc.json": lambda: json_sidra(
        "Pessoas desocupadas (sintético)", "49", "Mil pessoas", _contagem_sem_regioes(1),
        anos=ANOS_PNADC, classificacoes=_SEXO_TOTAL),
    "forca_trabalho/pnadc.json": lambda: json_sidra(
        "Pessoas na força de trabalho (sintético)", "49", "Mil pessoas", _contagem_sem_regioes(10),
        anos=ANOS_PNADC, classificacoes=_SEXO_TOTAL),
    # Informalidade: informais / ocupados x 100 = 50 em todo territorio.
    "informalidade/pnadc.json": lambda: json_sidra(
        "Taxa de informalidade (sintético)", "2", "%", _constante("50.0"), anos=ANOS_INFORMALIDADE),
    "informais/pnadc.json": lambda: json_sidra(
        "Pessoas ocupadas informais (sintético)", "49", "Mil pessoas", _soma, anos=ANOS_INFORMALIDADE,
        classificacoes=(("Situação de informalidade", "57303", "Informais"),)),
    "ocupados/pnadc.json": lambda: json_sidra(
        "Pessoas ocupadas (sintético)", "49", "Mil pessoas", _soma_vezes(2), anos=ANOS_INFORMALIDADE,
        classificacoes=(("Situação de informalidade", "57302"),)),
    # As duas series do IDHM saem dos mesmos quatro downloads do Ipeadata: o arquivo bruto e o mesmo.
    "idhm/censo.json": json_idhm_combinado,
    "idhm/pnadc.json": json_idhm_combinado,
    "rendimento_trabalho/pnadc.json": lambda: json_sidra(
        "Rendimento médio mensal real do trabalho (sintético)", "38", "Reais", _constante("99999"),
        anos=ANOS_PNADC),
}


# Fichas de teste da amostra (testes/amostra/indicadores/): uma razao com valor oficial e seu denominador.
GERADORES_AMOSTRA = {
    "amostra_populacao/scr_ref2010.json": lambda: json_sidra(
        "População (sintético)", "99998", "Pessoas", _soma),
    "amostra_per_capita/scr_ref2010.json": lambda: json_sidra(
        "PIB per capita (sintético)", "99997", "Reais", _per_capita),
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
    for pasta, geradores in ((PASTA, GERADORES), (PASTA_AMOSTRA, GERADORES_AMOSTRA)):
        for relativo, gerar in geradores.items():
            destino = pasta / relativo
            destino.parent.mkdir(parents=True, exist_ok=True)
            _escrever(destino, gerar())
            print(f"gerado: {destino.relative_to(PASTA.parent.parent)}")


if __name__ == "__main__":
    main()
