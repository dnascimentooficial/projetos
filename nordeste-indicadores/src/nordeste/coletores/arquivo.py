"""Coletor generico de arquivos por URL (planilhas e similares), com uma URL ou varias partes por serie.

Com `parametros.partes`, cada URL distinta das partes e baixada uma vez e o arquivo bruto da serie e um
pacote zip deterministico, sem compressao: `manifesto.json` e um arquivo por URL, na ordem da primeira aparicao
da URL nas partes. Data, ordem e atributos fixos: o mesmo conteudo da fonte gera os mesmos bytes, e portanto o
mesmo sha256 (uma coleta por serie, como no Ipeadata com `codigos`).

Reducao: quando todas as partes de uma URL declaram `arquivo_no_zip`, o pacote nao guarda o zip baixado, e sim um
zip reduzido com so os membros declarados, com os bytes comprimidos copiados do original (nada e recomprimido).
Um membro .xlsx lido so por partes com `aba` (texto) e `formato: xlsx` e ainda podado: ficam as abas declaradas e
as partes do pacote OOXML que elas alcancam (estilos, textos compartilhados, tema), tambem copiadas sem
recompressao; o podado so entra se for menor que o membro comprimido original (senao vai o membro cru). Assim os
dados comprimidos do zip reduzido nunca passam dos do original; o arquivo em si pode ficar alguns bytes maior, pois
os cabecalhos sao regravados (por exemplo, nome de membro nao ASCII em CP437 passa a UTF-8). O nome do membro nao muda, entao o padronizador `planilha` le o pacote
como antes. Se a poda nao for segura (aba ausente, estrutura inesperada), o membro segue inteiro e o erro de layout
aparece no padronizador, como antes. Se o arquivo baixado nao for um zip legivel ou nao tiver um membro declarado
(download cortado, pagina de erro servida com status 200), sobe ErroColeta: a parte nao e guardada.

Cada item do manifesto tem `url`, `nome` (entrada no pacote), `sha256_original` e `bytes_original` (do arquivo
baixado, para rastrear a fonte) e, se reduzido, `membros`: [{membro, abas?}] (`abas` so quando podado).
"""

import hashlib
import html
import io
import json
import posixpath
import re
import shutil
import struct
import tempfile
import warnings
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Callable
from urllib.parse import urlparse

from nordeste.coletores.erros import ErroColeta

MANIFESTO = "manifesto.json"
_DATA_FIXA = (2026, 1, 1, 0, 0, 0)
_BLOCO = 1 << 20

# url -> None (arquivo inteiro) ou {membro: abas a manter (xlsx podavel) ou None (membro inteiro)}
Receita = dict[str, tuple[str, ...] | None] | None


def urls_arquivo(parametros: dict) -> list[str]:
    """URLs a baixar: a `url` da serie ou as URLs distintas de `partes`, na ordem da primeira aparicao."""
    if "partes" in parametros:
        if "url" in parametros:
            raise ErroColeta("parametros do coletor arquivo com url e partes ao mesmo tempo")
        partes = parametros["partes"]
        valido = isinstance(partes, list) and partes and all(
            isinstance(p, dict) and isinstance(p.get("url"), str) and p["url"] for p in partes)
        if not valido:
            raise ErroColeta("parametros['partes'] do coletor arquivo deve ser uma lista de partes, cada uma com url")
        return list(dict.fromkeys(p["url"] for p in partes))
    try:
        return [parametros["url"]]
    except KeyError:
        raise ErroColeta("parametros do coletor arquivo sem a chave url (ou partes)") from None


def url_arquivo(parametros: dict) -> str:
    """URL registrada da coleta: a da serie; com `partes`, as URLs distintas separadas por um espaco."""
    return " ".join(urls_arquivo(parametros))


def receitas_das_partes(parametros: dict) -> dict[str, Receita]:
    """O que guardar de cada URL das partes, na ordem de `urls_arquivo`.

    None: a URL tem parte sem `arquivo_no_zip`, e o arquivo segue inteiro. Senao, os membros declarados, cada um
    com as abas a manter (todas as partes do membro sao `formato: xlsx` com `aba` texto) ou None (membro inteiro).
    """
    receitas: dict[str, Receita] = {url: {} for url in urls_arquivo(parametros)}
    for parte in parametros["partes"]:
        url, membro = parte["url"], parte.get("arquivo_no_zip")
        if receitas[url] is None:
            continue
        if not membro:
            receitas[url] = None
            continue
        aba = parte.get("aba")
        podavel = parte.get("formato", "xlsx") == "xlsx" and isinstance(aba, str) and aba != ""
        membros = receitas[url]
        if membro not in membros:
            membros[membro] = (aba,) if podavel else None
        elif membros[membro] is not None:
            membros[membro] = tuple(dict.fromkeys([*membros[membro], aba])) if podavel else None
    return receitas


def receita_em_json(receita: Receita):
    """Forma serializavel da receita (para comparar com a de uma parte guardada)."""
    return None if receita is None else {m: None if a is None else list(a) for m, a in receita.items()}


# ---------------------------------------------------------------------------
# Zip com bytes comprimidos copiados: sem recompressao, o resultado nao depende do zlib nem da plataforma
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Entrada:
    nome: str
    metodo: int
    crc: int
    comprimido: int
    tamanho: int
    copiar: Callable[[BinaryIO], None]


def _copiar_trecho(origem: BinaryIO, inicio: int, tamanho: int, saida: BinaryIO) -> None:
    origem.seek(inicio)
    while tamanho:
        bloco = origem.read(min(_BLOCO, tamanho))
        if not bloco:
            raise zipfile.BadZipFile("zip de origem truncado")
        saida.write(bloco)
        tamanho -= len(bloco)


def _entrada_crua(origem: BinaryIO, info: zipfile.ZipInfo) -> _Entrada:
    """Entrada com os bytes comprimidos de `info`, lidos do arquivo zip `origem` aberto em modo binario."""
    if info.flag_bits & 0x1:
        raise ValueError(f"membro cifrado: {info.filename}")
    origem.seek(info.header_offset)
    cabecalho = origem.read(zipfile.sizeFileHeader)
    if len(cabecalho) != zipfile.sizeFileHeader or cabecalho[:4] != zipfile.stringFileHeader:
        raise zipfile.BadZipFile(f"cabecalho local invalido: {info.filename}")
    campos = struct.unpack(zipfile.structFileHeader, cabecalho)
    inicio = info.header_offset + zipfile.sizeFileHeader + campos[10] + campos[11]
    return _Entrada(info.filename, info.compress_type, info.CRC, info.compress_size, info.file_size,
                    lambda saida: _copiar_trecho(origem, inicio, info.compress_size, saida))


def _entrada_arquivo(nome: str, caminho: Path) -> _Entrada:
    """Entrada sem compressao com o conteudo de `caminho`."""
    crc, tamanho = 0, 0
    with caminho.open("rb") as arquivo:
        while bloco := arquivo.read(_BLOCO):
            crc, tamanho = zlib.crc32(bloco, crc), tamanho + len(bloco)

    def copiar(saida: BinaryIO) -> None:
        with caminho.open("rb") as arquivo:
            shutil.copyfileobj(arquivo, saida, _BLOCO)

    return _Entrada(nome, zipfile.ZIP_STORED, crc, tamanho, tamanho, copiar)


def _entrada_bytes(nome: str, dados: bytes) -> _Entrada:
    return _Entrada(nome, zipfile.ZIP_STORED, zlib.crc32(dados), len(dados), len(dados),
                    lambda saida: saida.write(dados))


def _gravar_zip(saida: BinaryIO, entradas: list[_Entrada]) -> None:
    """Zip simples (sem zip64) com data, sistema de origem (3, Unix) e atributos fixos; dados por `copiar`.

    Nome nao ASCII vai em UTF-8, com a bandeira 0x800: e o nome como o zipfile o leu no original (da bandeira, do
    campo extra Unicode 0x7075 ou do CP437), e qualquer leitor o decodifica igual, entao o `arquivo_no_zip` casa.
    """
    ano, mes, dia, hora, minuto, segundo = _DATA_FIXA
    data_dos = (ano - 1980) << 9 | mes << 5 | dia
    hora_dos = hora << 11 | minuto << 5 | segundo // 2
    if len(entradas) >= 0xFFFF:
        raise ValueError("zip reduzido com entradas demais")
    central = []
    for entrada in entradas:
        nome = entrada.nome.encode("utf-8")
        bandeiras = 0 if entrada.nome.isascii() else 0x800
        posicao = saida.tell()
        if max(entrada.comprimido, entrada.tamanho, posicao) >= 0xFFFFFFFF:
            raise ValueError("zip reduzido exigiria zip64")
        comum = (bandeiras, entrada.metodo, hora_dos, data_dos, entrada.crc, entrada.comprimido, entrada.tamanho)
        # versao necessaria 2.0; no diretorio central, criado por 2.0 em Unix (3)
        saida.write(struct.pack(zipfile.structFileHeader, zipfile.stringFileHeader, 20, 0, *comum, len(nome), 0))
        saida.write(nome)
        entrada.copiar(saida)
        if saida.tell() != posicao + zipfile.sizeFileHeader + len(nome) + entrada.comprimido:
            raise ValueError(f"tamanho copiado diferente do declarado: {entrada.nome}")
        central.append(struct.pack(
            zipfile.structCentralDir, zipfile.stringCentralDir, 20, 3, 20, 0, *comum, len(nome), 0, 0, 0, 0,
            0o644 << 16, posicao) + nome)
    inicio_central = saida.tell()
    for registro in central:
        saida.write(registro)
    tamanho_central = saida.tell() - inicio_central
    if inicio_central >= 0xFFFFFFFF:
        raise ValueError("zip reduzido exigiria zip64")
    saida.write(struct.pack(zipfile.structEndArchive, zipfile.stringEndArchive, 0, 0, len(entradas),
                            len(entradas), tamanho_central, inicio_central, 0))


# ---------------------------------------------------------------------------
# Poda de xlsx: so as abas declaradas e as partes OOXML que elas alcancam pelos relacionamentos
# ---------------------------------------------------------------------------

_PREFIXO = rb"(?:[\w.-]+:)?"
_ATRIBUTO = re.compile(rb"([\w:.-]+)\s*=\s*(\"[^\"]*\"|'[^']*')")
_ABERTURA_ABA = re.compile(rb"<" + _PREFIXO + rb"sheet\b")
_ABA = re.compile(rb"<" + _PREFIXO + rb"sheet\b[^>]*?/>")
_NOMES_DEFINIDOS = re.compile(
    rb"<" + _PREFIXO + rb"definedNames\b[^>]*?(?:/>|>.*?</" + _PREFIXO + rb"definedNames\s*>)", re.DOTALL)
_ATRIBUTO_VISTA = re.compile(rb"\s(?:activeTab|firstSheet)\s*=\s*(?:\"[^\"]*\"|'[^']*')")
_RELACAO = re.compile(rb"<" + _PREFIXO + rb"Relationship\b[^>]*?/>")
_SOBRESCRITA = re.compile(rb"<" + _PREFIXO + rb"Override\b[^>]*?/>")
_TIPO_DOCUMENTO = "/officeDocument"
_TIPO_CADEIA_CALCULO = "/calcChain"


def _atributos(elemento: bytes) -> dict[str, str]:
    return {chave.decode("ascii"): html.unescape(valor[1:-1].decode("utf-8"))
            for chave, valor in _ATRIBUTO.findall(elemento)}


def _rels_de(parte: str) -> str:
    pasta, nome = posixpath.split(parte)
    return posixpath.join(pasta, "_rels", f"{nome}.rels")


def _alvo(parte: str, alvo: str) -> str:
    if alvo.startswith("/"):
        return alvo.lstrip("/")
    return posixpath.normpath(posixpath.join(posixpath.dirname(parte), alvo))


def _podar_xlsx(origem: Path, abas: tuple[str, ...], destino: Path) -> bool:
    """Grava em `destino` o xlsx so com `abas`; False (sem gravar nada util) se a poda nao for segura."""
    try:
        with zipfile.ZipFile(origem) as xlsx, origem.open("rb") as bruto:
            infos = {info.filename: info for info in xlsx.infolist()}
            por_minuscula = {nome.lower(): nome for nome in infos}

            def ler(nome: str) -> bytes:
                return xlsx.read(infos[nome])

            def relacoes(xml: bytes) -> list[tuple[bytes, dict[str, str]]]:
                return [(elemento, _atributos(elemento)) for elemento in _RELACAO.findall(xml)]

            pacote = relacoes(ler("_rels/.rels"))
            (documento,) = [_alvo("", a["Target"]) for _, a in pacote if a.get("Type", "").endswith(_TIPO_DOCUMENTO)]
            documento = por_minuscula[documento.lower()]
            livro = ler(documento)
            elementos = _ABA.findall(livro)
            if len(elementos) != len(_ABERTURA_ABA.findall(livro)):
                return False  # aba que nao e elemento vazio: estrutura que a poda nao conhece
            folhas = []
            for elemento in elementos:
                atributos = _atributos(elemento)
                (rid,) = [v for k, v in atributos.items() if k.endswith(":id")]
                folhas.append((elemento, atributos["name"], rid))
            nomes_folhas = [nome for _, nome, _ in folhas]
            if any(aba not in nomes_folhas for aba in abas):
                return False
            fora = [(elemento, rid) for elemento, nome, rid in folhas if nome not in abas]
            for elemento, _ in fora:
                livro = livro.replace(elemento, b"", 1)
            livro = _ATRIBUTO_VISTA.sub(b"", _NOMES_DEFINIDOS.sub(b"", livro))
            ids_fora = {rid for _, rid in fora}

            manter = {por_minuscula["[content_types].xml"], "_rels/.rels"}
            substituir = {documento: livro}
            fila = [_alvo("", a["Target"]) for _, a in pacote if a.get("TargetMode") != "External"]
            while fila:
                parte = por_minuscula.get(fila.pop(0).lower())
                if parte is None or parte in manter:
                    continue
                manter.add(parte)
                rels = por_minuscula.get(_rels_de(parte).lower())
                if rels is None:
                    continue
                xml = ler(rels)
                lista = relacoes(xml)
                if parte == documento:
                    for elemento, atributos in lista:
                        if atributos.get("Id") in ids_fora or atributos.get("Type", "").endswith(_TIPO_CADEIA_CALCULO):
                            xml = xml.replace(elemento, b"", 1)
                    lista = relacoes(xml)
                    substituir[rels] = xml
                manter.add(rels)
                fila += [_alvo(parte, a["Target"]) for _, a in lista if a.get("TargetMode") != "External"]

            tipos_nome = por_minuscula["[content_types].xml"]
            tipos = ler(tipos_nome)
            mantidas = {nome.lower() for nome in manter}
            for elemento in _SOBRESCRITA.findall(tipos):
                if _atributos(elemento).get("PartName", "").lstrip("/").lower() not in mantidas:
                    tipos = tipos.replace(elemento, b"", 1)
            substituir[tipos_nome] = tipos

            entradas = [
                _entrada_bytes(nome, substituir[nome]) if nome in substituir else _entrada_crua(bruto, info)
                for nome, info in infos.items() if nome in manter]
            with destino.open("wb") as saida:
                _gravar_zip(saida, entradas)
    except (KeyError, ValueError, zipfile.BadZipFile, NotImplementedError, UnicodeDecodeError, zlib.error):
        return False
    return _abas_do_xlsx(destino) == [nome for nome in nomes_folhas if nome in abas]


def _abas_do_xlsx(caminho: Path) -> list[str] | None:
    """Abas que o openpyxl (o leitor do padronizador) enxerga; None se nao abrir."""
    from openpyxl import load_workbook

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            livro = load_workbook(caminho, read_only=True, data_only=True, keep_links=False)
            try:
                return list(livro.sheetnames)
            finally:
                livro.close()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Reducao de uma parte e montagem do pacote
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ParteBaixada:
    """Uma URL pronta para o pacote: o arquivo a guardar (reduzido ou inteiro) e o rastro do original baixado."""

    url: str
    arquivo: Path
    sha256_original: str
    bytes_original: int
    membros: list[dict] | None = None  # None: arquivo inteiro


def _reduzir_zip(original: Path, membros: dict[str, tuple[str, ...] | None], destino: Path,
                 pasta: Path) -> list[dict] | None:
    """Grava em `destino` o zip so com `membros` (xlsx podados quando menores); None se for preciso o inteiro.

    zipfile.BadZipFile se `original` nao for um zip legivel ou nao tiver algum dos `membros`.
    """
    with zipfile.ZipFile(original) as zip_, original.open("rb") as bruto:
        infos = {info.filename: info for info in zip_.infolist()}
        ausentes = [membro for membro in membros if membro not in infos]
        if ausentes:
            raise zipfile.BadZipFile(f"sem o membro {', '.join(ausentes)}")
        if any(infos[membro].flag_bits & 0x1 for membro in membros):
            return None
        try:
            entradas, manifesto = [], []
            for posicao, (membro, abas) in enumerate(membros.items(), start=1):
                info = infos[membro]
                podado = pasta / f"podado_{posicao:03d}.xlsx"
                if (abas and _extrair_e_podar(zip_, info, abas, pasta / f"membro_{posicao:03d}.xlsx", podado)
                        and podado.stat().st_size < info.compress_size):
                    entradas.append(_entrada_arquivo(membro, podado))
                    manifesto.append({"membro": membro, "abas": list(abas)})
                else:
                    entradas.append(_entrada_crua(bruto, info))
                    manifesto.append({"membro": membro})
            with destino.open("wb") as saida:
                _gravar_zip(saida, entradas)
        except ValueError:  # zip reduzido que exigiria zip64: vai o arquivo inteiro
            return None
    with zipfile.ZipFile(destino) as conferido:
        if conferido.testzip() is not None:
            raise ValueError(f"zip reduzido com CRC invalido a partir de {original.name}")
    return manifesto


def _extrair_e_podar(zip_: zipfile.ZipFile, info: zipfile.ZipInfo, abas: tuple[str, ...], extraido: Path,
                     podado: Path) -> bool:
    try:
        with zip_.open(info) as membro, extraido.open("wb") as saida:
            shutil.copyfileobj(membro, saida, _BLOCO)
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError, OSError, EOFError, zlib.error):
        return False
    try:
        return _podar_xlsx(extraido, abas, podado)
    finally:
        extraido.unlink(missing_ok=True)


def preparar_parte(url: str, original: Path, sha256_original: str, bytes_original: int, receita: Receita,
                   pasta: Path) -> ParteBaixada:
    """Reduz o arquivo baixado conforme a receita; o reduzido fica em `pasta`, o original nao e alterado.

    ErroColeta se a receita declara membros e o arquivo nao e um zip legivel com todos eles.
    """
    if receita:
        reduzido = pasta / "reduzido.zip"
        try:
            membros = _reduzir_zip(original, receita, reduzido, pasta)
        except (zipfile.BadZipFile, zlib.error) as erro:  # zlib.error: deflate corrompido no membro
            raise ErroColeta(
                f"{url} não é um zip legível com {', '.join(receita)} ({erro}): download incompleto ou página de "
                "erro no lugar do arquivo; a parte não foi guardada") from erro
        if membros is not None:
            return ParteBaixada(url, reduzido, sha256_original, bytes_original, membros)
    return ParteBaixada(url, original, sha256_original, bytes_original)


def _entrada(nome: str, tamanho: int = 0) -> zipfile.ZipInfo:
    """Entrada sem compressao, com data, sistema de origem (3, Unix) e atributos fixos.

    Sem compressao, os bytes nao dependem da versao do zlib; com `create_system` fixo, nao dependem da plataforma
    (o padrao do zipfile e 0 no Windows). Assim o sha256 do pacote so muda quando muda o conteudo da fonte.
    """
    entrada = zipfile.ZipInfo(nome, date_time=_DATA_FIXA)
    entrada.compress_type = zipfile.ZIP_STORED
    entrada.create_system = 3
    entrada.external_attr = 0o644 << 16
    entrada.file_size = tamanho
    return entrada


def escrever_pacote(partes: list[ParteBaixada], destino: Path) -> None:
    """Grava o pacote em `destino`, copiando cada arquivo em blocos (sem carregar nenhum inteiro na memoria)."""
    manifesto = []
    for posicao, parte in enumerate(partes, start=1):
        base = PurePosixPath(urlparse(parte.url).path).name or "arquivo"
        item = {"url": parte.url, "nome": f"{posicao:02d}_{base}", "sha256_original": parte.sha256_original,
                "bytes_original": parte.bytes_original}
        if parte.membros is not None:
            item["membros"] = parte.membros
        manifesto.append(item)
    with zipfile.ZipFile(destino, "w") as pacote:
        texto = json.dumps({"arquivos": manifesto}, ensure_ascii=False, indent=1) + "\n"
        pacote.writestr(_entrada(MANIFESTO), texto.encode("utf-8"))
        for item, parte in zip(manifesto, partes):
            with parte.arquivo.open("rb") as origem, pacote.open(
                    _entrada(item["nome"], parte.arquivo.stat().st_size), "w") as saida:
                shutil.copyfileobj(origem, saida, _BLOCO)


def empacotar_partes(baixados: dict[str, bytes], parametros: dict | None = None) -> bytes:
    """Pacote, em memoria, com o conteudo de cada URL na ordem de `baixados` (para fixtures e testes).

    Com `parametros` (os da serie, com `partes`), cada URL e reduzida como na coleta; sem, segue inteira.
    """
    receitas = receitas_das_partes(parametros) if parametros else {}
    with tempfile.TemporaryDirectory(prefix="nordeste-pacote-") as nome_pasta:
        pasta = Path(nome_pasta)
        partes = []
        for posicao, (url, conteudo) in enumerate(baixados.items(), start=1):
            trabalho = pasta / f"{posicao:03d}"
            trabalho.mkdir()
            original = trabalho / "original"
            original.write_bytes(conteudo)
            partes.append(preparar_parte(url, original, hashlib.sha256(conteudo).hexdigest(), len(conteudo),
                                         receitas.get(url), trabalho))
        escrever_pacote(partes, pasta / "pacote.zip")
        return (pasta / "pacote.zip").read_bytes()


def ler_manifesto(conteudo: bytes) -> list[dict]:
    """Itens do manifesto do pacote; ValueError se o pacote estiver ilegivel."""
    try:
        with zipfile.ZipFile(io.BytesIO(conteudo)) as pacote:
            return json.loads(pacote.read(MANIFESTO).decode("utf-8"))["arquivos"]
    except (zipfile.BadZipFile, KeyError, TypeError, ValueError) as erro:
        raise ValueError(f"pacote de partes ilegível ({erro!r})") from erro


def ler_pacote(conteudo: bytes) -> dict[str, bytes]:
    """Conteudo guardado de cada URL do pacote (reduzido ou inteiro); ValueError se ilegivel ou incompleto."""
    try:
        with zipfile.ZipFile(io.BytesIO(conteudo)) as pacote:
            manifesto = json.loads(pacote.read(MANIFESTO).decode("utf-8"))
            return {item["url"]: pacote.read(item["nome"]) for item in manifesto["arquivos"]}
    except (zipfile.BadZipFile, KeyError, TypeError, ValueError) as erro:
        raise ValueError(f"pacote de partes ilegível ({erro!r})") from erro
