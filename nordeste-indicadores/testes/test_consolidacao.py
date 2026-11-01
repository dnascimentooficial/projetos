import hashlib
from datetime import date

import pytest

from nordeste.coletores import coletar_serie
from nordeste.coletores.registro import Coleta, ler_registro, registrar, ultima_coleta
from nordeste.consolidacao import Pendencia, consolidar
from nordeste.esquema import CHAVE_BASE, COLUNAS_BASE

HOJE = date(2026, 11, 1)


@pytest.fixture
def projeto_coletado(projeto, fichas):
    for ficha in fichas.values():
        serie = next(s for s in ficha.series if s.id == "scr_ref2010")
        coletar_serie(ficha, serie, projeto, offline=True, hoje=HOJE)
    return projeto


def test_consolida_tres_fichas(projeto_coletado, fichas, territorios):
    base, pend = consolidar(projeto_coletado, fichas, territorios)
    assert set(base.indicador_id) == {"pib_per_capita", "pib_nominal", "populacao_contas_regionais"}
    assert pend == []
    assert list(base.columns) == COLUNAS_BASE
    assert not base.duplicated(CHAVE_BASE).any()
    ordenada = base.sort_values(CHAVE_BASE, kind="stable").reset_index(drop=True)
    assert base.equals(ordenada)


def test_usa_apenas_a_ultima_coleta(projeto_coletado, fichas, territorios):
    registro = ler_registro(projeto_coletado.registro_coletas)
    primeira = ultima_coleta(registro, "pib_nominal", "scr_ref2010")
    original = (projeto_coletado.raiz / primeira.arquivo).read_text(encoding="utf-8")
    linha_ne = (
        '"V": "899991", "D1C": "2", "D1N": "Nordeste", "D2C": "99999", '
        '"D2N": "PIB a preços correntes (sintético)", "D3C": "2002"'
    )
    assert original.count(linha_ne) == 1
    alterado = original.replace(linha_ne, linha_ne.replace("899991", "1")).encode("utf-8")
    sha256 = hashlib.sha256(alterado).hexdigest()
    destino = projeto_coletado.brutos / "pib_nominal" / "scr_ref2010" / f"{sha256[:8]}.json"
    destino.write_bytes(alterado)
    registrar(projeto_coletado.registro_coletas, Coleta(
        coleta_id=f"pib_nominal.scr_ref2010.2026-11-02.{sha256[:8]}",
        indicador_id="pib_nominal", serie_id="scr_ref2010", url="fixture-alterada",
        data_coleta="2026-11-02", sha256=sha256, origem="fixture",
        arquivo=destino.relative_to(projeto_coletado.raiz).as_posix(),
    ))

    base, _ = consolidar(projeto_coletado, fichas, territorios)
    sel = base[(base.indicador_id == "pib_nominal") & (base.territorio_id == "NE") & (base.ano == 2002)]
    assert sel.valor.tolist() == [1.0]
    assert set(sel.coleta_id) == {f"pib_nominal.scr_ref2010.2026-11-02.{sha256[:8]}"}


def test_serie_sem_coleta_vira_pendencia(projeto, fichas, territorios):
    base, pend = consolidar(projeto, fichas, territorios)
    assert Pendencia("pib_nominal", "scr_ref2010", "sem coleta") in pend
    assert len(pend) == 3
    assert base.empty
    assert list(base.columns) == COLUNAS_BASE


def test_erro_de_layout_vira_pendencia(projeto_coletado, fichas, territorios):
    registro = ler_registro(projeto_coletado.registro_coletas)
    coleta = ultima_coleta(registro, "pib_nominal", "scr_ref2010")
    (projeto_coletado.raiz / coleta.arquivo).write_text("[]", encoding="utf-8")

    base, pend = consolidar(projeto_coletado, fichas, territorios)
    assert len(pend) == 1
    assert (pend[0].indicador_id, pend[0].serie_id) == ("pib_nominal", "scr_ref2010")
    assert pend[0].motivo
    assert "pib_nominal" not in set(base.indicador_id)
    assert {"pib_per_capita", "populacao_contas_regionais"} <= set(base.indicador_id)


def test_outras_excecoes_propagam(projeto_coletado, fichas, territorios):
    registro = ler_registro(projeto_coletado.registro_coletas)
    coleta = ultima_coleta(registro, "pib_nominal", "scr_ref2010")
    (projeto_coletado.raiz / coleta.arquivo).unlink()
    with pytest.raises(FileNotFoundError):
        consolidar(projeto_coletado, fichas, territorios)
