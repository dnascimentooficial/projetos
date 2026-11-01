import shutil
from dataclasses import replace
from datetime import date

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


def test_ultima_coleta_e_a_ultima_gravada_nao_a_mais_recente_em_data(tmp_path):
    path = tmp_path / "coletas.csv"
    registrar(path, _coleta(sha="aa" * 32, data_coleta="2026-12-01"))
    gravada_por_ultimo = registrar(path, _coleta(sha="bb" * 32, data_coleta="2026-01-01"))
    registrar(path, _coleta(sha="cc" * 32, indicador_id="outro"))
    assert ultima_coleta(ler_registro(path), "i", "s") == gravada_por_ultimo
    assert ultima_coleta(ler_registro(path), "i", "inexistente") is None


def test_offline_usa_fixture_e_marca_origem(projeto, fichas):
    f = fichas["pib_per_capita"]
    c = coletar_serie(f, f.serie("scr_ref2010"), projeto, offline=True, hoje=HOJE)
    assert c.origem == "fixture" and (projeto.raiz / c.arquivo).exists()
    assert c.coleta_id.startswith("pib_per_capita.scr_ref2010.2026-11-01.")
    assert c.arquivo == f"dados/brutos/pib_per_capita/scr_ref2010/{c.sha256[:8]}.json"


def test_mesmo_arquivo_nao_duplica_registro(projeto, fichas):
    f = fichas["pib_per_capita"]; s = f.serie("scr_ref2010")
    a = coletar_serie(f, s, projeto, offline=True, hoje=HOJE)
    b = coletar_serie(f, s, projeto, offline=True, hoje=date(2026, 11, 2))
    assert a == b and len(ler_registro(projeto.registro_coletas)) == 1


def test_sem_fixture_erro_claro(projeto, fichas):
    f = fichas["pib_nominal"]; shutil.rmtree(projeto.fixtures / "pib_nominal")
    with pytest.raises(ErroColeta, match="sem fixture para pib_nominal/scr_ref2010"):
        coletar_serie(f, f.serie("scr_ref2010"), projeto, offline=True, hoje=HOJE)


def test_rede_recusa_serie_nao_verificada(projeto, fichas):
    f = fichas["pib_per_capita"]
    with pytest.raises(ErroColeta, match="não verificada"):
        coletar_serie(f, f.serie("scr_ref2010"), projeto, offline=False, hoje=HOJE)


def test_rede_sidra_baixa_grava_e_offline_reaproveita(projeto, fichas):
    f = fichas["pib_per_capita"]
    s = replace(f.serie("scr_ref2010"), verificado=True,
                parametros={"tabela": "1", "variavel": "2", "classificacoes": {}})
    sessao = SessaoFalsa(conteudo=b'[{"V": "1"}]')
    c = coletar_serie(f, s, projeto, offline=False, hoje=HOJE, sessao=sessao)
    assert c.origem == "rede" and c.url == url_sidra(s.parametros) == sessao.urls[0]
    assert (projeto.raiz / c.arquivo).read_bytes() == b'[{"V": "1"}]'
    # offline reaproveita a coleta de rede em vez da fixture
    assert coletar_serie(f, s, projeto, offline=True, hoje=date(2026, 11, 2)) == c


def test_offline_ignora_coleta_de_rede_sem_arquivo(projeto, fichas):
    f = fichas["pib_per_capita"]
    s = replace(f.serie("scr_ref2010"), verificado=True,
                parametros={"tabela": "1", "variavel": "2"})
    c = coletar_serie(f, s, projeto, offline=False, hoje=HOJE, sessao=SessaoFalsa(conteudo=b"[1]"))
    (projeto.raiz / c.arquivo).unlink()
    d = coletar_serie(f, s, projeto, offline=True, hoje=HOJE)
    assert d.origem == "fixture"


def test_rede_arquivo_usa_url_e_sufixo(projeto, fichas):
    f = fichas["pib_per_capita"]
    s = replace(f.serie("scr_ref2010"), verificado=True, coletor="arquivo",
                parametros={"url": "http://x.gov.br/dados/planilha.XLSX?v=1"})
    c = coletar_serie(f, s, projeto, offline=False, hoje=HOJE, sessao=SessaoFalsa(conteudo=b"xlsx"))
    assert c.arquivo.endswith(f"/{c.sha256[:8]}.xlsx") and c.url == s.parametros["url"]


def test_rede_coletor_desconhecido(projeto, fichas):
    f = fichas["pib_per_capita"]
    s = replace(f.serie("scr_ref2010"), verificado=True, coletor="inventado")
    with pytest.raises(ErroColeta, match="inventado"):
        coletar_serie(f, s, projeto, offline=False, hoje=HOJE, sessao=SessaoFalsa())
