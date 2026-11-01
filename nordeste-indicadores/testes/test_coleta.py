import hashlib
import shutil
import ssl
from functools import partial
from dataclasses import replace
from datetime import date
from pathlib import Path

import certifi
import pytest
import requests

from nordeste.coletores import ErroColeta, coletar_serie
from nordeste.coletores.http import baixar
from nordeste.coletores.registro import Coleta, ler_registro, registrar, ultima_coleta
from nordeste.coletores.sidra import url_sidra

HOJE = date(2026, 11, 1)


class RespostaFalsa:
    def __init__(self, conteudo: bytes):
        self.content = conteudo

    def raise_for_status(self):
        pass


class SessaoFalsa:
    """Dublê de requests.Session: levanta ConnectionError nas primeiras `falhas` chamadas."""

    def __init__(self, falhas=0, conteudo=b""):
        self.falhas, self.conteudo, self.chamadas, self.urls = falhas, conteudo, 0, []

    def get(self, url, **kwargs):
        self.chamadas += 1
        self.urls.append(url)
        self.kwargs = getattr(self, "kwargs", []) + [kwargs]
        if self.chamadas <= self.falhas:
            raise requests.ConnectionError("sem rede")
        return RespostaFalsa(self.conteudo)


def _coleta(sha="ab12cd34" + "0" * 56, **campos) -> Coleta:
    base = dict(
        coleta_id=f"i.s.2026-11-01.{sha[:8]}", indicador_id="i", serie_id="s", url="http://x",
        data_coleta="2026-11-01", sha256=sha, origem="rede", arquivo=f"dados/brutos/i/s/{sha[:8]}.json",
    )
    base.update(campos)
    return Coleta(**base)


def test_url_sidra():
    assert url_sidra({"tabela": "1234", "variavel": "56", "classificacoes": {"c11255": "90707"}}) == (
        "https://apisidra.ibge.gov.br/values/t/1234/n1/all/n2/all/n3/"
        "21,22,23,24,25,26,27,28,29/v/56/p/all/c11255/90707")


def test_url_sidra_com_periodos_e_sem_classificacoes():
    assert url_sidra({"tabela": "1", "variavel": "2", "periodos": "2010-2020"}).endswith("/v/2/p/2010-2020")


def test_baixar_tenta_de_novo_e_desiste():
    esperas = []
    sessao = SessaoFalsa(falhas=10)
    with pytest.raises(ErroColeta, match="http://x"):
        baixar("http://x", esperar=esperas.append, sessao=sessao)
    assert esperas == [1.0, 2.0, 4.0] and sessao.chamadas == 4


def test_baixar_recupera_na_terceira():
    assert baixar("http://x", esperar=lambda s: None, sessao=SessaoFalsa(falhas=2, conteudo=b"ok")) == b"ok"


def test_baixar_trata_status_http_de_erro_como_falha():
    class Resposta404(RespostaFalsa):
        def raise_for_status(self):
            raise requests.HTTPError("404")

    class Sessao404(SessaoFalsa):
        def get(self, url, **kwargs):
            self.chamadas += 1
            return Resposta404(b"")

    sessao = Sessao404()
    with pytest.raises(ErroColeta, match="http://x"):
        baixar("http://x", tentativas_extras=1, esperar=lambda s: None, sessao=sessao)
    assert sessao.chamadas == 2


def test_registro_inexistente_devolve_vazio_com_colunas(tmp_path):
    df = ler_registro(tmp_path / "coletas.csv")
    assert df.empty
    assert list(df.columns) == list(Coleta.__dataclass_fields__)


def test_registrar_grava_cabecalho_e_deduplica(tmp_path):
    path = tmp_path / "relatorios" / "coletas.csv"
    primeira = registrar(path, _coleta())
    repetida = registrar(path, _coleta(coleta_id="i.s.2026-11-02.ab12cd34", data_coleta="2026-11-02"))
    assert repetida == primeira
    assert path.read_text(encoding="utf-8").splitlines()[0] == ",".join(Coleta.__dataclass_fields__)
    assert len(ler_registro(path)) == 1


def test_registrar_conteudo_novo_acrescenta_linha(tmp_path):
    path = tmp_path / "coletas.csv"
    registrar(path, _coleta())
    registrar(path, _coleta(sha="ff" * 32))
    assert len(ler_registro(path)) == 2


def test_reversao_de_conteudo_grava_de_novo(tmp_path):
    path = tmp_path / "coletas.csv"
    a, b = "aa" * 32, "bb" * 32
    registrar(path, _coleta(sha=a, data_coleta="2026-11-01"))
    registrar(path, _coleta(sha=b, data_coleta="2026-11-02"))
    de_novo = registrar(path, _coleta(sha=a, data_coleta="2026-11-03",
                                      coleta_id="i.s.2026-11-03.aaaaaaaa"))
    registro = ler_registro(path)
    assert len(registro) == 3
    assert de_novo.data_coleta == "2026-11-03"
    assert ultima_coleta(registro, "i", "s").sha256 == a
    assert ultima_coleta(registro, "i", "s") == de_novo


def test_ultima_coleta_e_a_ultima_gravada_nao_a_mais_recente_em_data(tmp_path):
    path = tmp_path / "coletas.csv"
    registrar(path, _coleta(sha="aa" * 32, data_coleta="2026-12-01"))
    gravada_por_ultimo = registrar(path, _coleta(sha="bb" * 32, data_coleta="2026-01-01"))
    registrar(path, _coleta(sha="cc" * 32, indicador_id="outro"))
    assert ultima_coleta(ler_registro(path), "i", "s") == gravada_por_ultimo
    assert ultima_coleta(ler_registro(path), "i", "inexistente") is None


def test_offline_usa_fixture_e_marca_origem(projeto, fichas):
    f = fichas["amostra_per_capita"]
    c = coletar_serie(f, f.serie("scr_ref2010"), projeto, offline=True, hoje=HOJE)
    assert c.origem == "fixture" and (projeto.raiz / c.arquivo).exists()
    assert c.coleta_id.startswith("amostra_per_capita.scr_ref2010.2026-11-01.")
    assert c.arquivo == f"dados/brutos/amostra_per_capita/scr_ref2010/{c.sha256[:8]}.json"


def test_mesmo_arquivo_nao_duplica_registro(projeto, fichas):
    f = fichas["amostra_per_capita"]; s = f.serie("scr_ref2010")
    a = coletar_serie(f, s, projeto, offline=True, hoje=HOJE)
    b = coletar_serie(f, s, projeto, offline=True, hoje=date(2026, 11, 2))
    assert a == b and len(ler_registro(projeto.registro_coletas)) == 1


def test_sem_fixture_erro_claro(projeto, fichas):
    f = fichas["pib_nominal"]; shutil.rmtree(projeto.fixtures / "pib_nominal")
    with pytest.raises(ErroColeta, match="sem fixture para pib_nominal/scr_ref2010"):
        coletar_serie(f, f.serie("scr_ref2010"), projeto, offline=True, hoje=HOJE)


def test_rede_recusa_serie_nao_verificada(projeto, fichas):
    f = fichas["amostra_per_capita"]
    with pytest.raises(ErroColeta, match="não verificada"):
        coletar_serie(f, f.serie("scr_ref2010"), projeto, offline=False, hoje=HOJE)


def test_rede_sidra_baixa_grava_e_offline_reaproveita(projeto, fichas):
    f = fichas["amostra_per_capita"]
    s = replace(f.serie("scr_ref2010"), verificado=True,
                parametros={"tabela": "1", "variavel": "2", "classificacoes": {}})
    sessao = SessaoFalsa(conteudo=b'[{"V": "1"}]')
    c = coletar_serie(f, s, projeto, offline=False, hoje=HOJE, sessao=sessao)
    assert c.origem == "rede" and c.url == url_sidra(s.parametros) == sessao.urls[0]
    assert (projeto.raiz / c.arquivo).read_bytes() == b'[{"V": "1"}]'
    # offline reaproveita a coleta de rede em vez da fixture
    assert coletar_serie(f, s, projeto, offline=True, hoje=date(2026, 11, 2)) == c


def test_offline_ignora_coleta_de_rede_sem_arquivo(projeto, fichas):
    f = fichas["amostra_per_capita"]
    s = replace(f.serie("scr_ref2010"), verificado=True,
                parametros={"tabela": "1", "variavel": "2"})
    c = coletar_serie(f, s, projeto, offline=False, hoje=HOJE, sessao=SessaoFalsa(conteudo=b"[1]"))
    (projeto.raiz / c.arquivo).unlink()
    d = coletar_serie(f, s, projeto, offline=True, hoje=HOJE)
    assert d.origem == "fixture"


def test_rede_arquivo_usa_url_e_sufixo(projeto, fichas):
    f = fichas["amostra_per_capita"]
    s = replace(f.serie("scr_ref2010"), verificado=True, coletor="arquivo",
                parametros={"url": "http://x.gov.br/dados/planilha.XLSX?v=1"})
    c = coletar_serie(f, s, projeto, offline=False, hoje=HOJE, sessao=SessaoFalsa(conteudo=b"xlsx"))
    assert c.arquivo.endswith(f"/{c.sha256[:8]}.xlsx") and c.url == s.parametros["url"]


def test_rede_coletor_desconhecido(projeto, fichas):
    f = fichas["amostra_per_capita"]
    s = replace(f.serie("scr_ref2010"), verificado=True, coletor="inventado")
    with pytest.raises(ErroColeta, match="inventado"):
        coletar_serie(f, s, projeto, offline=False, hoje=HOJE, sessao=SessaoFalsa())


# ---------------------------------------------------------------------------
# ca_extra: intermediaria publica que o servidor do INEP nao envia na cadeia TLS
# ---------------------------------------------------------------------------

RAIZ_REPOSITORIO = Path(__file__).resolve().parent.parent
CERTIFICADO_RNP = RAIZ_REPOSITORIO / "metadados" / "certificados" / "rnp-icpedu-gr46-ov-tls-ca-2025.pem"
SHA256_RNP = "E1:07:47:D4:DA:7B:AB:09:CB:A9:95:2F:01:9D:35:34:CB:9F:BA:07:0B:F1:3D:87:91:B1:69:9C:D2:FF:59:DD"


class SessaoQueLeOBundle(SessaoFalsa):
    """Le o arquivo passado em `verify` durante a chamada: o bundle e temporario e some depois."""

    def __init__(self, **campos):
        super().__init__(**campos)
        self.verificacoes, self.bundles = [], []

    def get(self, url, **kwargs):
        verify = kwargs.get("verify")
        self.verificacoes.append(verify)
        if isinstance(verify, str):
            self.bundles.append(Path(verify).read_text(encoding="utf-8"))
        return super().get(url, **kwargs)


def _pem(tmp_path, nome, rotulo) -> Path:
    arquivo = tmp_path / nome
    arquivo.write_text(f"-----BEGIN CERTIFICATE-----\n{rotulo}\n-----END CERTIFICATE-----", encoding="utf-8")  # sem \n final
    return arquivo


def test_certificado_da_intermediaria_do_inep_e_o_da_rnp_com_o_fingerprint_declarado():
    texto = CERTIFICADO_RNP.read_text(encoding="ascii")
    assert texto.count("BEGIN CERTIFICATE") == 1
    der = ssl.PEM_cert_to_DER_cert(texto)
    obtido = hashlib.sha256(der).hexdigest().upper()
    assert ":".join(obtido[i:i + 2] for i in range(0, len(obtido), 2)) == SHA256_RNP


def test_baixar_com_ca_extra_verifica_com_o_bundle_padrao_mais_a_intermediaria(tmp_path, monkeypatch):
    padrao, extra = _pem(tmp_path, "padrao.pem", "PADRAO"), _pem(tmp_path, "extra.pem", "EXTRA")
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(padrao))
    sessao = SessaoQueLeOBundle(conteudo=b"ok")
    assert baixar("https://x", sessao=sessao, ca_extra=extra) == b"ok"
    (bundle,) = sessao.bundles
    assert bundle.index("PADRAO") < bundle.index("EXTRA")
    assert bundle.count("BEGIN CERTIFICATE") == 2 and "END CERTIFICATE-----BEGIN" not in bundle
    assert sessao.verificacoes[0] != str(padrao) and sessao.kwargs[0]["timeout"] == 120


def test_baixar_com_ca_extra_sem_variavel_usa_o_bundle_do_certifi(tmp_path, monkeypatch):
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    sessao = SessaoQueLeOBundle(conteudo=b"ok")
    baixar("https://x", sessao=sessao, ca_extra=CERTIFICADO_RNP)
    (bundle,) = sessao.bundles
    assert bundle.startswith(Path(certifi.where()).read_text(encoding="utf-8").rstrip("\n"))
    assert bundle.rstrip().endswith(CERTIFICADO_RNP.read_text(encoding="ascii").strip())
    assert bundle.count("BEGIN CERTIFICATE") == Path(certifi.where()).read_text().count("BEGIN CERTIFICATE") + 1


def test_verify_nunca_e_false_e_o_bundle_temporario_some_ao_fim(tmp_path, monkeypatch):
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    sessao = SessaoQueLeOBundle(falhas=2, conteudo=b"ok")  # as 3 tentativas usam o mesmo bundle
    baixar("https://x", sessao=sessao, ca_extra=CERTIFICADO_RNP, esperar=lambda s: None)
    assert sessao.chamadas == 3 and len(set(sessao.verificacoes)) == 1
    (verify,) = set(sessao.verificacoes)
    assert isinstance(verify, str) and verify is not False and not Path(verify).exists()
    sem_extra = SessaoQueLeOBundle(conteudo=b"ok")  # sem ca_extra: nada de verify=False; o padrao do requests vale
    baixar("https://x", sessao=sem_extra)
    assert sem_extra.verificacoes == [None] and False not in sem_extra.verificacoes


def test_baixar_com_ca_extra_inexistente_falha_alto(tmp_path):
    sessao = SessaoFalsa(conteudo=b"ok")
    with pytest.raises(ErroColeta, match="ausente.pem"):
        baixar("https://x", sessao=sessao, ca_extra=tmp_path / "ausente.pem")
    assert sessao.chamadas == 0


def test_coletor_arquivo_resolve_ca_extra_a_partir_da_raiz(projeto, fichas):
    f = fichas["amostra_per_capita"]
    assert (projeto.raiz / "metadados" / "certificados" / CERTIFICADO_RNP.name).exists()  # a fixture copia metadados/
    s = replace(f.serie("scr_ref2010"), verificado=True, coletor="arquivo", parametros={
        "url": "https://download.inep.gov.br/x/planilha.zip",
        "ca_extra": f"metadados/certificados/{CERTIFICADO_RNP.name}"})
    sessao = SessaoQueLeOBundle(conteudo=b"zip")
    c = coletar_serie(f, s, projeto, offline=False, hoje=HOJE, sessao=sessao)
    assert c.url == s.parametros["url"] and c.arquivo.endswith(".zip")
    assert CERTIFICADO_RNP.read_text(encoding="ascii").strip() in sessao.bundles[0]


def test_coletor_arquivo_com_ca_extra_ausente_na_raiz_falha_alto(projeto, fichas):
    f = fichas["amostra_per_capita"]
    s = replace(f.serie("scr_ref2010"), verificado=True, coletor="arquivo", parametros={
        "url": "https://download.inep.gov.br/x/planilha.zip", "ca_extra": "metadados/certificados/nao_existe.pem"})
    with pytest.raises(ErroColeta, match="nao_existe.pem"):
        coletar_serie(f, s, projeto, offline=False, hoje=HOJE, sessao=SessaoFalsa(conteudo=b"zip"))


# ---------------------------------------------------------------------------
# Series com partes: varias URLs (ou abas do mesmo arquivo) num unico arquivo bruto por serie
# ---------------------------------------------------------------------------

URL_UFS = "https://download.inep.gov.br/ideb/resultados/ufs.zip"
URL_BRASIL = "https://download.inep.gov.br/ideb/resultados/brasil.zip"


class SessaoPorUrl(SessaoFalsa):
    """Responde o conteudo de cada URL; as URLs de `falham` levantam ConnectionError sempre."""

    def __init__(self, conteudos: dict, falham=()):
        super().__init__()
        self.conteudos, self.falham = conteudos, set(falham)

    def get(self, url, **kwargs):
        self.chamadas += 1
        self.urls.append(url)
        if url in self.falham:
            raise requests.ConnectionError("sem rede")
        return RespostaFalsa(self.conteudos[url])


def _serie_com_partes(fichas, **extra):
    f = fichas["amostra_per_capita"]
    partes = [
        {"url": URL_UFS, "aba": "AI"},
        {"url": URL_UFS, "aba": "AF"},  # mesma URL, outra aba: baixa uma vez so
        {"url": URL_BRASIL, "aba": "Brasil"},
    ]
    return f, replace(f.serie("scr_ref2010"), verificado=True, coletor="arquivo",
                      parametros={"padronizador": "planilha", "partes": partes, **extra})


def test_url_arquivo_com_partes_lista_as_urls_distintas_na_ordem():
    from nordeste.coletores.arquivo import url_arquivo, urls_arquivo
    partes = [{"url": "https://a/1.zip"}, {"url": "https://a/2.zip"}, {"url": "https://a/1.zip"}]
    assert urls_arquivo({"partes": partes}) == ["https://a/1.zip", "https://a/2.zip"]
    assert url_arquivo({"partes": partes}) == "https://a/1.zip https://a/2.zip"
    assert urls_arquivo({"url": "https://a/x.xlsx"}) == ["https://a/x.xlsx"]


@pytest.mark.parametrize("parametros", [
    {"partes": []}, {"partes": "x"}, {"partes": [{"aba": "AI"}]}, {"partes": [{"url": ""}]},
    {"url": "https://a/x.zip", "partes": [{"url": "https://a/x.zip"}]}, {},
])
def test_url_arquivo_rejeita_partes_invalidas(parametros):
    from nordeste.coletores.arquivo import url_arquivo
    with pytest.raises(ErroColeta):
        url_arquivo(parametros)


def test_coletor_com_partes_baixa_cada_url_uma_vez_e_grava_um_pacote_por_serie(projeto, fichas):
    from nordeste.coletores.arquivo import ler_pacote
    f, s = _serie_com_partes(fichas)
    sessao = SessaoPorUrl({URL_UFS: b"zip das ufs", URL_BRASIL: b"zip do brasil"})
    c = coletar_serie(f, s, projeto, offline=False, hoje=HOJE, sessao=sessao)
    assert sessao.urls == [URL_UFS, URL_BRASIL]
    assert c.url == f"{URL_UFS} {URL_BRASIL}" and c.origem == "rede"
    assert c.arquivo == f"dados/brutos/amostra_per_capita/scr_ref2010/{c.sha256[:8]}.zip"
    bruto = (projeto.raiz / c.arquivo).read_bytes()
    assert hashlib.sha256(bruto).hexdigest() == c.sha256
    assert ler_pacote(bruto) == {URL_UFS: b"zip das ufs", URL_BRASIL: b"zip do brasil"}
    assert len(ler_registro(projeto.registro_coletas)) == 1
    # o pacote e deterministico: o mesmo conteudo da fonte gera o mesmo arquivo e nao duplica o registro
    de_novo = coletar_serie(f, s, projeto, offline=False, hoje=date(2026, 11, 2),
                            sessao=SessaoPorUrl({URL_UFS: b"zip das ufs", URL_BRASIL: b"zip do brasil"}))
    assert de_novo == c and len(ler_registro(projeto.registro_coletas)) == 1


def test_coletor_com_partes_falha_na_segunda_url_sem_arquivo_nem_registro(projeto, fichas, monkeypatch):
    monkeypatch.setattr("nordeste.coletores.baixar", partial(baixar, esperar=lambda s: None))
    f, s = _serie_com_partes(fichas)
    sessao = SessaoPorUrl({URL_UFS: b"zip das ufs"}, falham=[URL_BRASIL])
    with pytest.raises(ErroColeta, match="brasil.zip"):
        coletar_serie(f, s, projeto, offline=False, hoje=HOJE, sessao=sessao)
    assert sessao.urls[0] == URL_UFS and set(sessao.urls[1:]) == {URL_BRASIL}
    pasta = projeto.brutos / "amostra_per_capita" / "scr_ref2010"
    assert not pasta.exists() or not any(pasta.iterdir())
    assert ler_registro(projeto.registro_coletas).empty


def test_coletor_com_partes_herda_o_ca_extra_da_serie(projeto, fichas):
    f, s = _serie_com_partes(fichas, ca_extra=f"metadados/certificados/{CERTIFICADO_RNP.name}")

    class Sessao(SessaoQueLeOBundle, SessaoPorUrl):
        pass

    sessao = Sessao(conteudos={URL_UFS: b"a", URL_BRASIL: b"b"})
    coletar_serie(f, s, projeto, offline=False, hoje=HOJE, sessao=sessao)
    assert len(sessao.bundles) == 2
    assert all(CERTIFICADO_RNP.read_text(encoding="ascii").strip() in b for b in sessao.bundles)


def test_pacote_de_partes_e_deterministico_e_rejeita_conteudo_estranho():
    from nordeste.coletores.arquivo import empacotar_partes, ler_pacote
    a = empacotar_partes({"https://a/1.zip": b"um", "https://a/2.zip?x=1": b"dois"})
    assert a == empacotar_partes({"https://a/1.zip": b"um", "https://a/2.zip?x=1": b"dois"})
    assert ler_pacote(a) == {"https://a/1.zip": b"um", "https://a/2.zip?x=1": b"dois"}
    with pytest.raises(ValueError):
        ler_pacote(b"nao e zip")
