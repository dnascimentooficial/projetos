"""Pacote de partes reduzido: so os membros declarados nas partes e, nos xlsx, so as abas lidas."""

import hashlib
import io
import json
import re
import zipfile
from dataclasses import replace

import pandas as pd
import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.drawing.image import Image as ImagemXlsx

from nordeste.coletores.arquivo import (
    empacotar_partes, ler_manifesto, ler_pacote, receita_em_json, receitas_das_partes,
)
from nordeste.coletores.erros import ErroColeta
from nordeste.padronizacao.planilha import padronizar_planilha

URL = "https://download.inep.gov.br/sinopse/sinopse_2019.zip"
URL_XLS = "https://download.inep.gov.br/sinopse/sinopse_2005.zip"
MEMBRO = "sinopse_estatística_educaç╞o_básica_2019/Sinopse_2019.xlsx"  # nome cp437, como nos zips do INEP
ABAS_LIDAS = ("Educação Básica 1.1", "Ensino Fundamental 1.14")


def _png() -> bytes:
    """PNG 1x1 valido (o openpyxl confere a imagem ao gravar)."""
    import struct
    import zlib

    def bloco(tipo: bytes, dados: bytes) -> bytes:
        return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados))

    return (b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0))
            + bloco(b"IDAT", zlib.compress(b"\x00\x00")) + bloco(b"IEND", b""))


def _linhas(valor: int) -> list[list]:
    return [["Sinopse (sintético)"], ["Território", "Total"], ["Nordeste", valor], ["Bahia", valor + 1]]


def _xlsx_grande() -> bytes:
    """xlsx com abas que a ficha nao le, imagem numa delas, area de impressao (nome local) e aba ativa no fim."""
    livro = Workbook()
    nomes = ["Sinopse", "Educação Básica 1.1", "Municípios 1.2", "Ensino Fundamental 1.14", "Municípios 1.15"]
    for posicao, nome in enumerate(nomes):
        aba = livro.active if posicao == 0 else livro.create_sheet()
        aba.title = nome
        for linha in _linhas(100 * posicao):
            aba.append(linha)
        if nome.startswith("Municípios"):
            for numero in range(300):  # o peso que a poda tira
                aba.append([f"Município sintético {numero}", numero])
    livro["Municípios 1.15"].print_area = "A1:B10"  # nome definido local (localSheetId = 4)
    livro["Municípios 1.2"].add_image(ImagemXlsx(io.BytesIO(_png())), "D2")
    livro.active = 4
    saida = io.BytesIO()
    livro.save(saida)
    return saida.getvalue()


def _zip(arquivos: dict[str, bytes]) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as pacote:
        for nome, conteudo in arquivos.items():
            pacote.writestr(zipfile.ZipInfo(nome, date_time=(2019, 10, 25, 20, 49, 36)), conteudo,
                            compress_type=zipfile.ZIP_DEFLATED)
    return saida.getvalue()


def _zip_da_fonte() -> bytes:
    """Como os zips do INEP: a planilha que a ficha le, a mesma em .ods (peso morto) e um md5."""
    peso_morto = b"".join(hashlib.sha256(numero.to_bytes(4, "big")).digest() for numero in range(3000))  # nao comprime
    return _zip({MEMBRO: _xlsx_grande(), MEMBRO.replace(".xlsx", ".ods"): peso_morto,
                 "md5.txt": b"d41d8cd98f00b204e9800998ecf8427e\n"})


def _parte(aba: str, subindicador: str = "") -> dict:
    return {"url": URL, "formato": "xlsx", "arquivo_no_zip": MEMBRO, "aba": aba, "linha_cabecalho": 2,
            "coluna_territorio": "Território",
            "colunas": [{"coluna": "Total", "ano": 2019, "subindicador": subindicador}]}


PARAMETROS = {"padronizador": "planilha",
              "partes": [_parte(ABAS_LIDAS[0], "basica"), _parte(ABAS_LIDAS[1], "fundamental")]}


def _conteudo(pacote: bytes, url: str = URL) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(ler_pacote(pacote)[url]))


# ---------------------------------------------------------------------------
# Receitas: o que guardar de cada URL
# ---------------------------------------------------------------------------

def test_receitas_juntam_as_abas_de_cada_membro_na_ordem_das_partes():
    partes = [
        {"url": URL, "arquivo_no_zip": "a.xlsx", "aba": "1.1"},  # formato padrao do padronizador: xlsx
        {"url": URL, "arquivo_no_zip": "a.xlsx", "aba": "1.5", "formato": "xlsx"},
        {"url": URL, "arquivo_no_zip": "a.xlsx", "aba": "1.1", "formato": "xlsx"},
        {"url": URL, "arquivo_no_zip": "b.xls", "aba": "1.1", "formato": "xls"},  # xls: membro inteiro
        {"url": URL_XLS, "arquivo_no_zip": "c.xlsx", "aba": 0, "formato": "xlsx"},  # aba por posicao: nao poda
    ]
    assert receitas_das_partes({"partes": partes}) == {
        URL: {"a.xlsx": ("1.1", "1.5"), "b.xls": None}, URL_XLS: {"c.xlsx": None}}


def test_receita_de_url_com_parte_sem_membro_e_o_arquivo_inteiro():
    for partes in ([{"url": URL, "arquivo_no_zip": "a.xlsx", "aba": "1"}, {"url": URL, "aba": "2"}],
                   [{"url": URL, "aba": "2"}, {"url": URL, "arquivo_no_zip": "a.xlsx", "aba": "1"}]):
        assert receitas_das_partes({"partes": partes}) == {URL: None}


def test_membro_lido_por_parte_sem_aba_ou_csv_segue_inteiro():
    partes = [{"url": URL, "arquivo_no_zip": "a.xlsx", "aba": "1"}, {"url": URL, "arquivo_no_zip": "a.xlsx"}]
    assert receitas_das_partes({"partes": partes}) == {URL: {"a.xlsx": None}}
    partes = [{"url": URL, "arquivo_no_zip": "a.csv", "formato": "csv"}]
    assert receitas_das_partes({"partes": partes}) == {URL: {"a.csv": None}}
    assert receita_em_json({"a.xlsx": ("1",), "b.xls": None}) == {"a.xlsx": ["1"], "b.xls": None}


# ---------------------------------------------------------------------------
# Reducao do zip e poda do xlsx
# ---------------------------------------------------------------------------

def test_pacote_guarda_so_o_membro_com_as_abas_lidas_e_o_rastro_do_original():
    fonte = _zip_da_fonte()
    pacote = empacotar_partes({URL: fonte}, PARAMETROS)
    (item,) = ler_manifesto(pacote)
    assert item["sha256_original"] == hashlib.sha256(fonte).hexdigest()
    assert item["bytes_original"] == len(fonte)
    assert item["membros"] == [{"membro": MEMBRO, "abas": list(ABAS_LIDAS)}]
    with _conteudo(pacote) as reduzido:
        assert reduzido.namelist() == [MEMBRO]  # o mesmo nome: o padronizador acha o arquivo_no_zip
        assert reduzido.testzip() is None
        xlsx = reduzido.read(MEMBRO)
    assert len(pacote) < len(fonte) / 3
    livro = load_workbook(io.BytesIO(xlsx), read_only=True)
    assert livro.sheetnames == list(ABAS_LIDAS)
    livro.close()
    with zipfile.ZipFile(io.BytesIO(xlsx)) as podado:
        nomes = podado.namelist()
        livro_xml = podado.read("xl/workbook.xml")
    assert not any(n.startswith(("xl/media/", "xl/drawings/")) for n in nomes)  # a imagem so estava na aba cortada
    assert "xl/sharedStrings.xml" in nomes or "xl/styles.xml" in nomes
    assert b"definedName" not in livro_xml and b"activeTab" not in livro_xml


def test_abas_podadas_leem_igual_as_do_original():
    original = _xlsx_grande()
    pacote = empacotar_partes({URL: _zip({MEMBRO: original})}, PARAMETROS)
    with _conteudo(pacote) as reduzido:
        podado = reduzido.read(MEMBRO)
    for aba in ABAS_LIDAS:
        esperado = pd.read_excel(io.BytesIO(original), sheet_name=aba, header=1, dtype=object)
        obtido = pd.read_excel(io.BytesIO(podado), sheet_name=aba, header=1, dtype=object)
        pd.testing.assert_frame_equal(obtido, esperado)


def test_partes_da_aba_mantida_sao_copiadas_sem_recompressao():
    original = _xlsx_grande()
    pacote = empacotar_partes({URL: _zip({MEMBRO: original})}, PARAMETROS)
    with _conteudo(pacote) as reduzido, zipfile.ZipFile(io.BytesIO(reduzido.read(MEMBRO))) as podado, \
            zipfile.ZipFile(io.BytesIO(original)) as inteiro:
        for info in podado.infolist():
            if info.filename.startswith("xl/worksheets/sheet"):
                fonte = inteiro.getinfo(info.filename)
                assert (info.compress_type, info.compress_size, info.CRC) == (
                    fonte.compress_type, fonte.compress_size, fonte.CRC)


def test_membro_xls_e_copiado_com_a_compressao_original():
    xls = b"\xd0\xcf\x11\xe0" + b"planilha xls sintetica " * 2000
    fonte = _zip({"Censo2005/Censo Escolar 2005.xls": xls, "leiame.pdf": bytes(range(256)) * 200})
    parametros = {"partes": [{"url": URL_XLS, "formato": "xls", "arquivo_no_zip": "Censo2005/Censo Escolar 2005.xls",
                              "aba": "1.1"}]}
    pacote = empacotar_partes({URL_XLS: fonte}, parametros)
    assert ler_manifesto(pacote)[0]["membros"] == [{"membro": "Censo2005/Censo Escolar 2005.xls"}]
    with _conteudo(pacote, URL_XLS) as reduzido, zipfile.ZipFile(io.BytesIO(fonte)) as inteiro:
        (info,) = reduzido.infolist()
        assert reduzido.read(info) == xls
        original = inteiro.getinfo(info.filename)
        assert (info.compress_type, info.compress_size, info.CRC) == (
            zipfile.ZIP_DEFLATED, original.compress_size, original.CRC)
    assert len(ler_pacote(pacote)[URL_XLS]) < len(xls) / 10  # nao vira membro descomprimido


@pytest.mark.parametrize("caso", ["aba ausente", "xlsx ilegivel"])
def test_sem_poda_segura_o_membro_segue_inteiro_e_o_padronizador_acusa(caso):
    if caso == "aba ausente":
        fonte = _zip_da_fonte()
        parametros = {"partes": [_parte(ABAS_LIDAS[0]), _parte("Aba que não existe")]}
    else:
        fonte = _zip({MEMBRO: b"isto nao e xlsx", "md5.txt": b"x"})
        parametros = PARAMETROS
    pacote = empacotar_partes({URL: fonte}, parametros)
    (item,) = ler_manifesto(pacote)
    assert item["membros"] == [{"membro": MEMBRO}]
    with zipfile.ZipFile(io.BytesIO(ler_pacote(pacote)[URL])) as reduzido, \
            zipfile.ZipFile(io.BytesIO(fonte)) as inteiro:
        assert reduzido.namelist() == [MEMBRO] and reduzido.read(MEMBRO) == inteiro.read(MEMBRO)
    assert item["sha256_original"] == hashlib.sha256(fonte).hexdigest()


@pytest.mark.parametrize("caso", ["zip truncado", "HTML com status 200", "membro ausente"])
def test_arquivo_baixado_sem_o_membro_declarado_e_erro_de_coleta(caso):
    """Download cortado ou pagina de erro servida com 200: nao vira parte valida (nem inteira, nem reduzida)."""
    if caso == "zip truncado":
        fonte = _zip_da_fonte()
        fonte = fonte[:len(fonte) // 2]
    elif caso == "HTML com status 200":
        fonte = "<html><body>Servidor em manutenção</body></html>".encode()
    else:
        fonte = _zip({"outro.xlsx": b"x"})
    with pytest.raises(ErroColeta, match=re.escape(URL)):
        empacotar_partes({URL: fonte}, PARAMETROS)


def test_url_sem_arquivo_no_zip_segue_inteira_mesmo_sem_ser_zip():
    """Sem `arquivo_no_zip` nao ha o que conferir: o arquivo vai como veio e o padronizador o le."""
    fonte = b"<html>tabela</html>"
    pacote = empacotar_partes({URL: fonte}, {"partes": [{"url": URL, "formato": "html"}]})
    (item,) = ler_manifesto(pacote)
    assert "membros" not in item and ler_pacote(pacote)[URL] == fonte


def _xlsx_sem_compressao(xlsx: bytes) -> bytes:
    """O mesmo xlsx com as partes OOXML guardadas sem compressao (ha geradores que fazem assim)."""
    saida = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(xlsx)) as origem, zipfile.ZipFile(saida, "w", zipfile.ZIP_STORED) as destino:
        for info in origem.infolist():
            destino.writestr(zipfile.ZipInfo(info.filename, date_time=info.date_time), origem.read(info))
    return saida.getvalue()


def test_xlsx_podado_maior_que_o_membro_comprimido_nao_e_usado():
    """Poda copia as partes como estao (aqui, sem compressao) e o pacote as guarda sem compressao: se o podado sair
    maior que o membro comprimido do zip baixado, fica o membro original, copiado cru."""
    todas = ("Sinopse", "Educação Básica 1.1", "Municípios 1.2", "Ensino Fundamental 1.14", "Municípios 1.15")
    fonte = _zip({MEMBRO: _xlsx_sem_compressao(_xlsx_grande())})
    parametros = {"partes": [_parte(aba) for aba in todas]}
    pacote = empacotar_partes({URL: fonte}, parametros)
    assert ler_manifesto(pacote)[0]["membros"] == [{"membro": MEMBRO}]
    guardado = ler_pacote(pacote)[URL]
    with zipfile.ZipFile(io.BytesIO(guardado)) as reduzido, zipfile.ZipFile(io.BytesIO(fonte)) as inteiro:
        (info,) = reduzido.infolist()
        original = inteiro.getinfo(MEMBRO)
        assert (info.compress_type, info.compress_size, info.CRC) == (
            zipfile.ZIP_DEFLATED, original.compress_size, original.CRC)
    assert len(guardado) <= len(fonte)


def test_pacote_reduzido_e_deterministico():
    fonte = _zip_da_fonte()
    assert empacotar_partes({URL: fonte}, PARAMETROS) == empacotar_partes({URL: fonte}, PARAMETROS)
    with _conteudo(empacotar_partes({URL: fonte}, PARAMETROS)) as reduzido:
        (info,) = reduzido.infolist()
        assert (info.date_time, info.create_system, info.compress_type) == (
            (2026, 1, 1, 0, 0, 0), 3, zipfile.ZIP_STORED)  # o xlsx podado ja e comprimido por dentro


def test_pacote_antigo_com_zips_inteiros_continua_legivel():
    """Brutos coletados antes da reducao: manifesto so com url e nome."""
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as pacote:
        pacote.writestr("manifesto.json", json.dumps({"arquivos": [{"url": URL, "nome": "01_sinopse_2019.zip"}]}))
        pacote.writestr("01_sinopse_2019.zip", b"zip inteiro")
    assert ler_pacote(saida.getvalue()) == {URL: b"zip inteiro"}


# ---------------------------------------------------------------------------
# O padronizador le o pacote reduzido como lia o inteiro
# ---------------------------------------------------------------------------

def test_padronizador_le_o_pacote_reduzido_como_o_inteiro(fichas, territorios):
    ficha = fichas["pib_nominal"]
    serie = replace(ficha.series[0], coletor="arquivo", parametros=PARAMETROS)
    ficha = replace(ficha, series=(serie,))
    fonte = _zip_da_fonte()
    reduzido = padronizar_planilha(empacotar_partes({URL: fonte}, PARAMETROS), ficha, serie, "c1", territorios)
    inteiro = padronizar_planilha(empacotar_partes({URL: fonte}), ficha, serie, "c1", territorios)
    pd.testing.assert_frame_equal(reduzido, inteiro)
    assert reduzido.set_index(["subindicador", "territorio_id"]).valor.to_dict() == {
        ("basica", "NE"): 100.0, ("basica", "BA"): 101.0, ("fundamental", "NE"): 300.0, ("fundamental", "BA"): 301.0}


def _zip_com_nome_cru(nome_cru: bytes, conteudo: bytes, extra: bytes = b"") -> bytes:
    """Zip com o nome gravado em bytes crus, sem a bandeira UTF-8, como nos zips antigos do INEP."""
    marcador = b"N" * len(nome_cru)
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as pacote:
        info = zipfile.ZipInfo(marcador.decode("ascii"), date_time=(2019, 10, 25, 20, 49, 36))
        info.extra = extra
        pacote.writestr(info, conteudo, compress_type=zipfile.ZIP_DEFLATED)
    return saida.getvalue().replace(marcador, nome_cru)  # mesmo tamanho: os deslocamentos nao mudam


def _campo_unicode(nome_cru: bytes, nome: str) -> bytes:
    """Campo extra Info-ZIP Unicode Path (0x7075): versao 1, CRC do nome cru, nome em UTF-8."""
    import struct
    import zlib
    dados = struct.pack("<BI", 1, zlib.crc32(nome_cru)) + nome.encode("utf-8")
    return struct.pack("<HH", 0x7075, len(dados)) + dados


@pytest.mark.parametrize("caso", ["cp437 sem bandeira", "campo unicode 0x7075"])
def test_membro_com_nome_nao_utf8_e_reduzido_e_achado_pelo_padronizador(caso):
    xlsx = _xlsx_grande()
    if caso == "cp437 sem bandeira":  # Educacenso: "Educaç╞o", como o zipfile decodifica o CP437
        nome_cru = "Sinopse_Educaç╞o_2019/Sinopse.xlsx".encode("cp437")
        fonte = _zip_com_nome_cru(nome_cru, xlsx)
    else:  # Censup: bytes crus quaisquer e o nome verdadeiro no campo extra, com "ã" (fora do CP437)
        nome_cru = b"Sinopse_Educa\x87\xc6o_2009/Sinopse.xlsx"
        fonte = _zip_com_nome_cru(nome_cru, xlsx, _campo_unicode(nome_cru, "Sinopse_Educação_2009/Sinopse.xlsx"))
    with zipfile.ZipFile(io.BytesIO(fonte)) as original:
        (membro,) = original.namelist()
    if caso == "campo unicode 0x7075" and membro != "Sinopse_Educação_2009/Sinopse.xlsx":
        pytest.skip("este Python nao le o campo extra Unicode do zip")
    parametros = {"partes": [{**_parte(ABAS_LIDAS[0]), "arquivo_no_zip": membro}]}
    pacote = empacotar_partes({URL: fonte}, parametros)
    assert ler_manifesto(pacote)[0]["membros"] == [{"membro": membro, "abas": [ABAS_LIDAS[0]]}]
    with _conteudo(pacote) as reduzido:
        assert reduzido.namelist() == [membro]
        assert load_workbook(io.BytesIO(reduzido.read(membro)), read_only=True).sheetnames == [ABAS_LIDAS[0]]
