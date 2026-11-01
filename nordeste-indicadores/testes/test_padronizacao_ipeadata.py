import json
from dataclasses import replace
from datetime import date

import pytest
from gerar_fixtures import json_ipeadata as montar_json

from nordeste.coletores import ErroColeta, coletar_serie
from nordeste.coletores.ipeadata import url_ipeadata
from nordeste.coletores.registro import Coleta
from nordeste.esquema import COLUNAS_BASE
from nordeste.padronizacao import ErroLayout, padronizar
from nordeste.padronizacao.ipeadata import padronizar_ipeadata

DATA_2001 = "2001-01-01T00:00:00-02:00"


def json_ipea(registros) -> bytes:
    return json.dumps(montar_json(registros)).encode("utf-8")


@pytest.fixture
def ficha_ipeadata(fichas):
    ficha = fichas["pib_nominal"]
    serie = replace(ficha.series[0], coletor="ipeadata", parametros={"codigo": "SERIE_SINTETICA"})
    return replace(ficha, series=(serie,))


def test_url_ipeadata():
    assert url_ipeadata({"codigo": "ABC12_X"}) == (
        "https://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='ABC12_X')")


def test_url_ipeadata_sem_codigo():
    with pytest.raises(ErroColeta, match="codigo"):
        url_ipeadata({})


def test_ipeadata(ficha_ipeadata, territorios):
    df = padronizar_ipeadata(
        json_ipea([("Regiões", "2", DATA_2001, 99999.0), ("Brasil", "", DATA_2001, None)]),
        ficha_ipeadata, ficha_ipeadata.series[0], "c1", territorios)
    assert df.set_index("territorio_id").tipo_dado.to_dict() == {"NE": "observado", "BR": "indisponivel"}
    assert list(df.columns) == COLUNAS_BASE
    ne = df[df.territorio_id == "NE"].iloc[0]
    assert (ne.valor, ne.ano, ne.coleta_id, ne.serie_id, ne.nota) == (99999.0, 2001, "c1", "scr_ref2010", "")
    br = df[df.territorio_id == "BR"].iloc[0]
    assert br.valor != br.valor and br.nota == "Ipeadata: sem valor"


def test_niveis_codigos_e_anos(ficha_ipeadata, territorios):
    df = padronizar_ipeadata(json_ipea([
        ("Brasil", None, DATA_2001, 1.0),
        ("Regiões", "1", "2002-01-01T00:00:00-02:00", 2.0),
        ("Estados", "22", "2003-01-01T00:00:00-02:00", 3),
        ("Estados", "29", "2004-01-01T00:00:00-03:00", 4.0),
    ]), ficha_ipeadata, ficha_ipeadata.series[0], "c1", territorios)
    assert df.set_index("territorio_id").ano.to_dict() == {"BR": 2001, "N": 2002, "PI": 2003, "BA": 2004}
    assert df.set_index("territorio_id").valor.to_dict() == {"BR": 1.0, "N": 2.0, "PI": 3.0, "BA": 4.0}


def test_descarta_niveis_e_territorios_desconhecidos(ficha_ipeadata, territorios):
    df = padronizar_ipeadata(json_ipea([
        ("Municípios", "2211001", DATA_2001, 1.0),
        ("Estados", "35", DATA_2001, 2.0),   # SP: fora da tabela
        ("Regiões", "9", DATA_2001, 3.0),
        ("Estados", "21", DATA_2001, 4.0),
    ]), ficha_ipeadata, ficha_ipeadata.series[0], "c1", territorios)
    assert df.territorio_id.tolist() == ["MA"]


def test_sem_registros_devolve_base_vazia(ficha_ipeadata, territorios):
    df = padronizar_ipeadata(json_ipea([]), ficha_ipeadata, ficha_ipeadata.series[0], "c1", territorios)
    assert df.empty and list(df.columns) == COLUNAS_BASE


@pytest.mark.parametrize("conteudo", [b"nao e json", b"[]", b'{"value": 3}', b'{"outro": []}', b'{"value": [1]}'])
def test_layout_irreconhecivel(ficha_ipeadata, territorios, conteudo):
    with pytest.raises(ErroLayout, match="Ipeadata"):
        padronizar_ipeadata(conteudo, ficha_ipeadata, ficha_ipeadata.series[0], "c1", territorios)


@pytest.mark.parametrize("data,valor", [(None, 1.0), ("sem-data", 1.0), (DATA_2001, "12"), (DATA_2001, True)])
def test_data_ou_valor_irreconhecivel(ficha_ipeadata, territorios, data, valor):
    with pytest.raises(ErroLayout, match="Ipeadata"):
        padronizar_ipeadata(json_ipea([("Brasil", "", data, valor)]), ficha_ipeadata,
                            ficha_ipeadata.series[0], "c1", territorios)


def test_padronizar_usa_o_padronizador_do_coletor(projeto, ficha_ipeadata, territorios):
    relativo = "dados/brutos/x/y/abc.json"
    (projeto.raiz / relativo).parent.mkdir(parents=True)
    (projeto.raiz / relativo).write_bytes(json_ipea([("Regiões", "2", DATA_2001, 99999.0)]))
    serie = replace(ficha_ipeadata.series[0], parametros={**ficha_ipeadata.series[0].parametros, "anos_estimativa": [2001]})
    coleta = Coleta(
        coleta_id="c9", indicador_id="pib_nominal", serie_id=serie.id, url="x", data_coleta="2026-11-01",
        sha256="0" * 64, origem="fixture", arquivo=relativo,
    )
    df = padronizar(ficha_ipeadata, serie, coleta, projeto, territorios)
    assert df.territorio_id.tolist() == ["NE"] and df.tipo_dado.tolist() == ["estimativa_oficial"]


class _Resposta:
    content = b'{"value": []}'

    def raise_for_status(self):
        pass


class _Sessao:
    def __init__(self):
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        return _Resposta()


def test_coletar_serie_ipeadata_baixa_json_verificado(projeto, ficha_ipeadata):
    serie = replace(ficha_ipeadata.series[0], verificado=True)
    sessao = _Sessao()
    coleta = coletar_serie(ficha_ipeadata, serie, projeto, offline=False, hoje=date(2026, 11, 1), sessao=sessao)
    assert sessao.urls == ["https://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='SERIE_SINTETICA')"]
    assert coleta.arquivo.endswith(".json") and coleta.origem == "rede"
    assert (projeto.raiz / coleta.arquivo).read_bytes() == _Resposta.content


def _serie_com_periodos(ficha_ipeadata, periodos):
    serie = replace(ficha_ipeadata.series[0], parametros={"codigo": "SERIE_SINTETICA", "periodos": periodos})
    return replace(ficha_ipeadata, series=(serie,)), serie


def test_periodos_limitam_os_anos_da_serie(ficha_ipeadata, territorios):
    """O Ipeadata devolve a serie inteira (a PNAD antiga vem desde 1976); `periodos` guarda so a janela da ficha."""
    ficha, serie = _serie_com_periodos(ficha_ipeadata, "2001-2002")
    conteudo = json_ipea([("Brasil", "", f"{ano}-01-01T00:00:00-02:00", float(ano)) for ano in (1999, 2001, 2002, 2003)])
    df = padronizar_ipeadata(conteudo, ficha, serie, "c1", territorios)
    assert sorted(df.ano) == [2001, 2002]


def test_periodos_com_um_ano_so(ficha_ipeadata, territorios):
    ficha, serie = _serie_com_periodos(ficha_ipeadata, "2002")
    conteudo = json_ipea([("Brasil", "", f"{ano}-01-01T00:00:00-02:00", 1.0) for ano in (2001, 2002, 2003)])
    assert list(padronizar_ipeadata(conteudo, ficha, serie, "c1", territorios).ano) == [2002]


@pytest.mark.parametrize("periodos", ["2001-", "2002-2001", "abc", "2001/2003", 2001])
def test_periodos_invalidos_interrompem_com_mensagem_clara(ficha_ipeadata, territorios, periodos):
    ficha, serie = _serie_com_periodos(ficha_ipeadata, periodos)
    with pytest.raises(ErroLayout, match="periodos"):
        padronizar_ipeadata(json_ipea([("Brasil", "", DATA_2001, 1.0)]), ficha, serie, "c1", territorios)


def test_sem_periodos_a_serie_vem_inteira(ficha_ipeadata, territorios):
    conteudo = json_ipea([("Brasil", "", f"{ano}-01-01T00:00:00-02:00", 1.0) for ano in (1976, 2001)])
    df = padronizar_ipeadata(conteudo, ficha_ipeadata, ficha_ipeadata.series[0], "c1", territorios)
    assert sorted(df.ano) == [1976, 2001]


# ---------------------------------------------------------------------------
# `codigos`: varias series do Ipeadata (uma por subindicador) reunidas em um unico arquivo bruto
# ---------------------------------------------------------------------------

CODIGOS = {"idhm": "IDHM", "renda": "IDHMRE"}
URL_IDHM = "https://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='IDHM')"
URL_RENDA = "https://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='IDHMRE')"


@pytest.fixture
def ficha_codigos(ficha_ipeadata):
    serie = replace(ficha_ipeadata.series[0], parametros={"codigos": CODIGOS, "periodos": "2000-2010"})
    return replace(ficha_ipeadata, series=(serie,))


def combinado(**respostas) -> bytes:
    return json.dumps({"subindicadores": {k: montar_json(v) for k, v in respostas.items()}}).encode("utf-8")


def test_url_ipeadata_com_codigos_lista_as_urls_na_ordem_do_mapa():
    assert url_ipeadata({"codigos": CODIGOS}) == f"{URL_IDHM} {URL_RENDA}"


@pytest.mark.parametrize("parametros, trecho", [
    ({"codigos": {}}, "codigos"),
    ({"codigos": ["IDHM"]}, "codigos"),
    ({"codigos": {"idhm": ""}}, "codigos"),
    ({"codigos": {"": "IDHM"}}, "codigos"),
    ({"codigos": {"idhm": "IDHM"}, "codigo": "IDHM"}, "codigo"),
])
def test_url_ipeadata_com_codigos_invalidos(parametros, trecho):
    with pytest.raises(ErroColeta, match=trecho):
        url_ipeadata(parametros)


def test_coletar_serie_com_codigos_baixa_cada_codigo_e_guarda_um_arquivo(projeto, ficha_codigos):
    class Sessao:
        def __init__(self):
            self.urls = []

        def get(self, url, **kwargs):
            self.urls.append(url)
            resposta = _Resposta()
            resposta.content = json.dumps(montar_json([("Brasil", "", DATA_2001, float(len(self.urls)))])).encode()
            return resposta

    serie = replace(ficha_codigos.series[0], verificado=True)
    sessao = Sessao()
    coleta = coletar_serie(ficha_codigos, serie, projeto, offline=False, hoje=date(2026, 11, 1), sessao=sessao)
    assert sessao.urls == [URL_IDHM, URL_RENDA]
    assert coleta.url == f"{URL_IDHM} {URL_RENDA}" and coleta.origem == "rede" and coleta.arquivo.endswith(".json")
    guardado = json.loads((projeto.raiz / coleta.arquivo).read_bytes())
    assert list(guardado["subindicadores"]) == ["idhm", "renda"]
    assert [v["value"][0]["VALVALOR"] for v in guardado["subindicadores"].values()] == [1.0, 2.0]


def test_coletar_serie_com_codigos_recusa_resposta_que_nao_e_json(projeto, ficha_codigos):
    class Sessao:
        def get(self, url, **kwargs):
            return _Resposta()  # `{"value": []}` valido

    class SessaoRuim:
        def get(self, url, **kwargs):
            resposta = _Resposta()
            resposta.content = b"<html>"
            return resposta

    serie = replace(ficha_codigos.series[0], verificado=True)
    coletar_serie(ficha_codigos, serie, projeto, offline=False, hoje=date(2026, 11, 1), sessao=Sessao())
    with pytest.raises(ErroColeta, match="IDHM"):
        coletar_serie(ficha_codigos, serie, projeto, offline=False, hoje=date(2026, 11, 1), sessao=SessaoRuim())


def test_padronizar_com_codigos_preenche_o_subindicador(ficha_codigos, territorios):
    conteudo = combinado(
        idhm=[("Brasil", "", DATA_2001, 0.5), ("Estados", "23", "2010-01-01T00:00:00-02:00", 0.682)],
        renda=[("Brasil", "", DATA_2001, 0.6), ("Regiões", "2", "2012-01-01T00:00:00-02:00", 0.7)],  # 2012: fora da janela
    )
    df = padronizar_ipeadata(conteudo, ficha_codigos, ficha_codigos.series[0], "c1", territorios)
    lido = {(r.subindicador, r.territorio_id, r.ano): r.valor for r in df.itertuples()}
    assert lido == {("idhm", "BR", 2001): 0.5, ("idhm", "CE", 2010): 0.682, ("renda", "BR", 2001): 0.6}
    assert list(df.columns) == COLUNAS_BASE and set(df.coleta_id) == {"c1"}


def test_padronizar_com_codigos_exige_o_formato_combinado(ficha_codigos, territorios):
    with pytest.raises(ErroLayout, match="subindicadores"):
        padronizar_ipeadata(json_ipea([("Brasil", "", DATA_2001, 1.0)]), ficha_codigos,
                            ficha_codigos.series[0], "c1", territorios)


def test_padronizar_com_codigos_confere_os_subindicadores_do_arquivo(ficha_codigos, territorios):
    so_um = combinado(idhm=[("Brasil", "", DATA_2001, 0.5)])
    with pytest.raises(ErroLayout, match="renda"):
        padronizar_ipeadata(so_um, ficha_codigos, ficha_codigos.series[0], "c1", territorios)
    sobra = combinado(idhm=[], renda=[], extra=[])
    with pytest.raises(ErroLayout, match="extra"):
        padronizar_ipeadata(sobra, ficha_codigos, ficha_codigos.series[0], "c1", territorios)


def test_padronizar_com_codigos_aponta_a_resposta_ilegivel(ficha_codigos, territorios):
    ruim = json.dumps({"subindicadores": {"idhm": {"value": []}, "renda": {"x": 1}}}).encode()
    with pytest.raises(ErroLayout, match="renda"):
        padronizar_ipeadata(ruim, ficha_codigos, ficha_codigos.series[0], "c1", territorios)


def test_serie_com_codigo_unico_segue_sem_subindicador(ficha_ipeadata, territorios):
    df = padronizar_ipeadata(json_ipea([("Brasil", "", DATA_2001, 1.0)]), ficha_ipeadata,
                             ficha_ipeadata.series[0], "c1", territorios)
    assert set(df.subindicador) == {""}
