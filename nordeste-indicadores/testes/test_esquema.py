import pandas as pd
import pytest

from nordeste.esquema import (
    CHAVE_BASE, COLUNAS_BASE, COLUNAS_DERIVADOS, METRICAS, REDES, TIPOS_DADO, normalizar_base,
)


def test_colunas_base_na_ordem_da_spec():
    assert COLUNAS_BASE == ["indicador_id", "subindicador", "etapa", "rede", "territorio_id",
                            "ano", "valor", "tipo_dado", "serie_id", "coleta_id", "nota"]


def test_chave_e_tipos():
    assert CHAVE_BASE == ["indicador_id", "subindicador", "etapa", "rede", "territorio_id", "ano", "serie_id"]
    assert TIPOS_DADO == ("observado", "estimativa_oficial", "derivado", "indisponivel")


def test_normalizar_preenche_opcionais_com_vazio():
    df = pd.DataFrame([{"indicador_id": "x", "territorio_id": "NE", "ano": "2002", "valor": "1.5",
                        "tipo_dado": "observado", "serie_id": "s", "coleta_id": "c"}])
    out = normalizar_base(df)
    assert list(out.columns) == COLUNAS_BASE
    assert out.loc[0, "subindicador"] == "" and out.loc[0, "nota"] == ""
    assert out.loc[0, "ano"] == 2002 and out.loc[0, "valor"] == 1.5


def test_normalizar_rejeita_coluna_obrigatoria_ausente():
    with pytest.raises(ValueError, match="territorio_id"):
        normalizar_base(pd.DataFrame([{"indicador_id": "x"}]))


def test_vocabularios_e_colunas_de_derivados():
    assert REDES == ("total", "publica", "privada", "federal", "estadual", "municipal")
    assert METRICAS == ("razao", "diferenca", "variacao_acumulada", "crescimento_relativo",
                        "posicao_regioes", "dispersao_ufs")
    assert COLUNAS_DERIVADOS == ["indicador_id", "subindicador", "etapa", "rede", "metrica", "referencia",
                                 "territorio_id", "ano", "valor", "serie_id"]


def test_normalizar_valor_nulo_e_nao_muta_entrada():
    df = pd.DataFrame([{"indicador_id": "x", "territorio_id": "NE", "ano": 2002, "valor": None,
                        "tipo_dado": "indisponivel", "serie_id": "s", "coleta_id": "c", "nota": None}])
    out = normalizar_base(df)
    assert pd.isna(out.loc[0, "valor"]) and out.loc[0, "nota"] == ""
    assert "subindicador" not in df.columns
