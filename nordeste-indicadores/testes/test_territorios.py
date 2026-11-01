from nordeste.territorios import (
    REGIOES, UFS_NE, carregar_territorios, territorio_por_codigo, territorio_por_nome,
)


def test_dezesseis_territorios_e_sergipe_separado_do_sudeste(projeto):
    t = carregar_territorios(projeto.territorios_csv)
    assert len(t) == 16
    assert t.set_index("territorio_id").loc["SE", "tipo"] == "regiao"
    assert t.set_index("territorio_id").loc["SE_UF", "nome"] == "Sergipe"


def test_codigo_1_depende_do_nivel(projeto):
    t = carregar_territorios(projeto.territorios_csv)
    assert territorio_por_codigo(t, "n1", "1") == "BR"
    assert territorio_por_codigo(t, "n2", "1") == "N"
    assert territorio_por_codigo(t, "n3", "28") == "SE_UF"
    assert territorio_por_codigo(t, "n3", "35") is None


def test_nome_sem_acento(projeto):
    assert territorio_por_nome(carregar_territorios(projeto.territorios_csv), "PIAUI") == "PI"


def test_nome_inexistente_devolve_none(projeto):
    assert territorio_por_nome(carregar_territorios(projeto.territorios_csv), "Atlantida") is None


def test_territorios_sao_texto_e_agregado_derivado_nao_tem_codigo(territorios):
    t = territorios
    assert list(t.columns) == ["territorio_id", "nome", "tipo", "codigo_ibge", "regiao_id"]
    assert all(t[c].map(type).eq(str).all() for c in t.columns)
    fora = t.set_index("territorio_id").loc["BR_FORA_NE"]
    assert (fora.tipo, fora.codigo_ibge) == ("agregado_derivado", "")


def test_constantes_coincidem_com_a_tabela(territorios):
    t = territorios.set_index("territorio_id")
    assert UFS_NE == ("MA", "PI", "CE", "RN", "PB", "PE", "AL", "SE_UF", "BA")
    assert REGIOES == ("N", "NE", "SE", "S", "CO")
    assert all(t.loc[u, "tipo"] == "uf" and t.loc[u, "regiao_id"] == "NE" for u in UFS_NE)
    assert all(t.loc[r, "tipo"] == "regiao" and t.loc[r, "regiao_id"] == r for r in REGIOES)
