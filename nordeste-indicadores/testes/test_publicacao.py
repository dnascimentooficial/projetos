from datetime import date

import pandas as pd
import pytest

from nordeste.coletores import coletar_serie
from nordeste.coletores.registro import ler_registro
from nordeste.consolidacao import Pendencia, consolidar
from nordeste.derivados import brasil_fora_ne, metricas_convergencia
from nordeste.esquema import CHAVE_BASE, COLUNAS_BASE, normalizar_base
from nordeste.fichas import carregar_fichas
from nordeste.governos import carregar_governos
from nordeste.publicacao import ErroPublicacao, mudancas, publicar, versao_completa
from nordeste.territorios import carregar_territorios

HOJE = date(2026, 11, 1)
COLUNAS_MUDANCAS = [*CHAVE_BASE, "valor_anterior", "valor_novo", "tipo"]
COLUNAS_EXTRAS = [
    "territorio_nome", "indicador_nome", "unidade", "fonte", "orgao", "url", "periodicidade",
    "presidente", "mandato", "compatibilidade",
]


def gravar_pendencias(caminhos, pendencias):
    caminhos.trabalho.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [(p.indicador_id, p.serie_id, p.motivo) for p in pendencias],
        columns=["indicador_id", "serie_id", "motivo"],
    ).to_csv(caminhos.trabalho / "pendencias.csv", index=False)


def montar_trabalho(projeto, origem):
    """Coleta offline, consolida e deriva sobre as fixtures do PIB; grava dados/trabalho e os registros."""
    fichas = carregar_fichas(projeto.fichas)
    territorios = carregar_territorios(projeto.territorios_csv)
    for ficha in fichas.values():
        coletar_serie(ficha, ficha.series[0], projeto, offline=True, hoje=HOJE)
    observada, pendencias = consolidar(projeto, fichas, territorios)
    assert pendencias == []
    fora_ne, derivacoes = brasil_fora_ne(observada, fichas)
    base = pd.concat([observada, fora_ne], ignore_index=True)
    base = base.sort_values(CHAVE_BASE, kind="stable").reset_index(drop=True)
    projeto.trabalho.mkdir(parents=True, exist_ok=True)
    base.to_csv(projeto.trabalho / "base.csv", index=False)
    metricas_convergencia(base, fichas, territorios).to_csv(projeto.trabalho / "derivados.csv", index=False)
    gravar_pendencias(projeto, [])
    derivacoes.to_csv(projeto.registro_derivacoes, index=False)
    if origem == "rede":
        coletas = ler_registro(projeto.registro_coletas)
        coletas["origem"] = "rede"
        coletas.to_csv(projeto.registro_coletas, index=False)
    return projeto


@pytest.fixture
def trabalho_aprovado(projeto):
    return montar_trabalho(projeto, "rede")


@pytest.fixture
def trabalho_com_fixture(projeto):
    return montar_trabalho(projeto, "fixture")


def base_com_valor(valor, **campos):
    linha = {
        "indicador_id": "x", "territorio_id": "NE", "ano": 2002, "valor": valor,
        "tipo_dado": "observado", "serie_id": "s", "coleta_id": "c", **campos,
    }
    return normalizar_base(pd.DataFrame([linha]))


def ler_base_de_trabalho(caminhos):
    return pd.read_csv(
        caminhos.trabalho / "base.csv", keep_default_na=False, na_values={"valor": [""]}, float_precision="round_trip",
    )


def ler_publicada(caminhos):
    return pd.read_csv(
        caminhos.base / "base_nordeste.csv", keep_default_na=False, na_values={"valor": [""]},
        float_precision="round_trip",
    )


# ---------------------------------------------------------------------------
# Publicacao
# ---------------------------------------------------------------------------

def test_reprovado_nao_toca_na_base(trabalho_com_fixture):
    with pytest.raises(ErroPublicacao, match="R01"):
        publicar(trabalho_com_fixture, hoje=HOJE)
    assert not (trabalho_com_fixture.base / "base_nordeste.csv").exists()
    assert not trabalho_com_fixture.base.exists()


def test_reprovado_grava_relatorios_e_preserva_publicacao_anterior(trabalho_aprovado):
    publicar(trabalho_aprovado, hoje=HOJE)
    arquivos = ("base_nordeste.csv", "base_nordeste.parquet", "derivados.csv", "base_nordeste_completa.csv")
    antes = {nome: (trabalho_aprovado.base / nome).read_bytes() for nome in arquivos}
    coletas = ler_registro(trabalho_aprovado.registro_coletas)
    coletas["origem"] = "fixture"
    coletas.to_csv(trabalho_aprovado.registro_coletas, index=False)

    with pytest.raises(ErroPublicacao, match="R01"):
        publicar(trabalho_aprovado, hoje=HOJE)

    assert {nome: (trabalho_aprovado.base / nome).read_bytes() for nome in arquivos} == antes
    validacao = pd.read_csv(trabalho_aprovado.relatorios / "validacao.csv")
    assert ("erro", "R01") in set(zip(validacao.nivel, validacao.regra))
    assert (trabalho_aprovado.relatorios / "mudancas.csv").exists()


def test_ensaio_nunca_grava_base(trabalho_aprovado):
    assert publicar(trabalho_aprovado, hoje=HOJE, ensaio=True).aprovado
    assert not (trabalho_aprovado.base / "base_nordeste.csv").exists()
    assert not trabalho_aprovado.base.exists()
    assert (trabalho_aprovado.relatorios / "validacao.csv").exists()
    assert (trabalho_aprovado.relatorios / "mudancas.csv").exists()


def test_ensaio_reprovado_devolve_resultado_sem_levantar(trabalho_com_fixture):
    resultado = publicar(trabalho_com_fixture, hoje=HOJE, ensaio=True)
    assert not resultado.aprovado and "R01" in {f.regra for f in resultado.erros}
    assert not trabalho_com_fixture.base.exists()


def test_publica_e_versao_completa_para_excel(trabalho_aprovado):
    publicar(trabalho_aprovado, hoje=HOJE)
    bruto = (trabalho_aprovado.base / "base_nordeste_completa.csv").read_bytes()
    assert bruto.startswith(b"\xef\xbb\xbf") and b";" in bruto.splitlines()[0]
    completa = pd.read_csv(
        trabalho_aprovado.base / "base_nordeste_completa.csv", sep=";", decimal=",", encoding="utf-8-sig",
    )
    assert completa.query("ano == 2016").presidente.unique().tolist() == ["transicao_dilma_temer"]
    assert "Pernambuco" in set(completa.territorio_nome)
    assert list(completa.columns) == [*COLUNAS_BASE, *COLUNAS_EXTRAS]


def test_base_principal_em_formato_de_maquina_e_ordenada(trabalho_aprovado):
    publicar(trabalho_aprovado, hoje=HOJE)
    bruto = (trabalho_aprovado.base / "base_nordeste.csv").read_bytes()
    assert not bruto.startswith(b"\xef\xbb\xbf") and b"," in bruto.splitlines()[0]
    publicada = ler_publicada(trabalho_aprovado)
    assert list(publicada.columns) == COLUNAS_BASE
    assert publicada[CHAVE_BASE].equals(publicada[CHAVE_BASE].sort_values(CHAVE_BASE, kind="stable"))
    assert not publicada.duplicated(CHAVE_BASE).any()
    assert 2016 in set(publicada.ano)
    assert {"NE", "BR_FORA_NE"} <= set(publicada.territorio_id)


def test_grava_parquet_e_derivados_iguais_ao_trabalho(trabalho_aprovado):
    publicar(trabalho_aprovado, hoje=HOJE)
    parquet = pd.read_parquet(trabalho_aprovado.base / "base_nordeste.parquet")
    csv = ler_publicada(trabalho_aprovado)
    assert list(parquet.columns) == COLUNAS_BASE and len(parquet) == len(csv)
    assert parquet.valor.equals(csv.valor) and parquet.valor.isna().any()
    derivados = pd.read_csv(trabalho_aprovado.base / "derivados.csv", keep_default_na=False)
    de_trabalho = pd.read_csv(trabalho_aprovado.trabalho / "derivados.csv", keep_default_na=False)
    assert len(derivados) == len(de_trabalho) > 0
    assert set(derivados.metrica) == set(de_trabalho.metrica)


def test_republicar_sem_mudanca_e_idempotente(trabalho_aprovado):
    publicar(trabalho_aprovado, hoje=HOJE)
    arquivos = ("base_nordeste.csv", "base_nordeste.parquet", "derivados.csv", "base_nordeste_completa.csv")
    antes = {nome: (trabalho_aprovado.base / nome).read_bytes() for nome in arquivos}
    segunda = publicar(trabalho_aprovado, hoje=HOJE)
    assert (trabalho_aprovado.base / "base_nordeste.csv").read_bytes() == antes["base_nordeste.csv"]
    assert (trabalho_aprovado.base / "derivados.csv").read_bytes() == antes["derivados.csv"]
    assert (trabalho_aprovado.base / "base_nordeste_completa.csv").read_bytes() == antes["base_nordeste_completa.csv"]
    assert pd.read_csv(trabalho_aprovado.relatorios / "mudancas.csv").empty
    assert "A02" not in {f.regra for f in segunda.avisos}
    assert "A02" not in set(pd.read_csv(trabalho_aprovado.relatorios / "validacao.csv").regra)


def test_primeira_publicacao_lista_tudo_como_novo(trabalho_aprovado):
    publicar(trabalho_aprovado, hoje=HOJE)
    # A mudanca da primeira publicacao e relativa a nenhuma base: tudo e novo.
    relatorio = pd.read_csv(trabalho_aprovado.relatorios / "mudancas.csv", keep_default_na=False)
    assert list(relatorio.columns) == COLUNAS_MUDANCAS
    assert set(relatorio.tipo) == {"novo"} and len(relatorio) == len(ler_publicada(trabalho_aprovado))


def test_valor_alterado_aparece_no_relatorio_e_no_aviso_a02(trabalho_aprovado):
    publicar(trabalho_aprovado, hoje=HOJE)
    base = ler_base_de_trabalho(trabalho_aprovado)
    # Escala o PIB nominal de todos os territorios de 2002 por 2: somas continuam coerentes,
    # mas a razao do per capita (R08) deixa de bater; entao escalamos o per capita junto.
    em_2002 = (base.ano == 2002) & base.indicador_id.isin(["pib_nominal", "pib_per_capita"])
    base.loc[em_2002, "valor"] = base.loc[em_2002, "valor"] * 2
    base.to_csv(trabalho_aprovado.trabalho / "base.csv", index=False)

    resultado = publicar(trabalho_aprovado, hoje=HOJE, ensaio=True)

    assert "A02" in {f.regra for f in resultado.avisos}
    relatorio = pd.read_csv(trabalho_aprovado.relatorios / "mudancas.csv", keep_default_na=False)
    assert set(relatorio.tipo) == {"alterado"} and set(relatorio.indicador_id) == {"pib_nominal", "pib_per_capita"}
    assert (relatorio.valor_novo == relatorio.valor_anterior * 2).all()


def test_pendencia_mantem_dado_publicado(trabalho_aprovado):
    publicar(trabalho_aprovado, hoje=HOJE)
    publicada = ler_publicada(trabalho_aprovado)
    antes = (trabalho_aprovado.base / "base_nordeste.csv").read_bytes()

    base = ler_base_de_trabalho(trabalho_aprovado)
    base[base.indicador_id != "pib_nominal"].to_csv(trabalho_aprovado.trabalho / "base.csv", index=False)
    gravar_pendencias(trabalho_aprovado, [Pendencia("pib_nominal", "scr_ref2010", "sem coleta")])

    publicar(trabalho_aprovado, hoje=HOJE)

    nova = ler_publicada(trabalho_aprovado)
    nominal = nova[nova.indicador_id == "pib_nominal"]
    assert len(nominal) > 0
    assert nominal.equals(publicada[publicada.indicador_id == "pib_nominal"])
    assert (trabalho_aprovado.base / "base_nordeste.csv").read_bytes() == antes
    assert pd.read_csv(trabalho_aprovado.relatorios / "mudancas.csv").empty


def test_pendencia_sem_publicacao_anterior_nao_inventa_linhas(trabalho_aprovado):
    base = ler_base_de_trabalho(trabalho_aprovado)
    base[base.indicador_id != "pib_nominal"].to_csv(trabalho_aprovado.trabalho / "base.csv", index=False)
    gravar_pendencias(trabalho_aprovado, [Pendencia("pib_nominal", "scr_ref2010", "sem coleta")])

    # Sem a serie pendente, o per capita do NE nao tem como ser recalculado (R08 nao avalia) e
    # a base segue valida; o que importa aqui e que nada de pib_nominal aparece do nada.
    publicar(trabalho_aprovado, hoje=HOJE, ensaio=True)
    relatorio = pd.read_csv(trabalho_aprovado.relatorios / "mudancas.csv", keep_default_na=False)
    assert "pib_nominal" not in set(relatorio.indicador_id)


def test_pendencia_nao_esconde_fixture_da_serie_reaproveitada(trabalho_aprovado):
    """A R01 examina a base que vai ser gravada, inclusive as linhas reaproveitadas."""
    publicar(trabalho_aprovado, hoje=HOJE)
    base = ler_base_de_trabalho(trabalho_aprovado)
    base[base.indicador_id != "pib_nominal"].to_csv(trabalho_aprovado.trabalho / "base.csv", index=False)
    gravar_pendencias(trabalho_aprovado, [Pendencia("pib_nominal", "scr_ref2010", "sem coleta")])
    coletas = ler_registro(trabalho_aprovado.registro_coletas)
    coletas.loc[coletas.indicador_id == "pib_nominal", "origem"] = "fixture"
    coletas.to_csv(trabalho_aprovado.registro_coletas, index=False)

    with pytest.raises(ErroPublicacao, match="R01"):
        publicar(trabalho_aprovado, hoje=HOJE)


def test_ficha_incompleta_reprova_com_r10(trabalho_aprovado):
    (trabalho_aprovado.fichas / "incompleta.yaml").write_text("id: incompleta\n", encoding="utf-8")
    with pytest.raises(ErroPublicacao, match="R10"):
        publicar(trabalho_aprovado, hoje=HOJE)
    assert not trabalho_aprovado.base.exists()


def test_arquivos_de_trabalho_ausentes_dao_erro_claro(projeto):
    with pytest.raises(ErroPublicacao, match="base.csv"):
        publicar(projeto, hoje=HOJE)


# ---------------------------------------------------------------------------
# mudancas
# ---------------------------------------------------------------------------

def test_mudancas():
    m = mudancas(base_com_valor(2.0), base_com_valor(1.0))
    assert list(m.columns) == COLUNAS_MUDANCAS
    assert m[["valor_anterior", "valor_novo", "tipo"]].values.tolist() == [[1.0, 2.0, "alterado"]]


def test_mudancas_novo_removido_e_igual():
    publicada = pd.concat([base_com_valor(1.0, ano=2001), base_com_valor(5.0, ano=2002)], ignore_index=True)
    nova = pd.concat([base_com_valor(5.0, ano=2002), base_com_valor(7.0, ano=2003)], ignore_index=True)
    m = mudancas(nova, publicada)
    resumo = {(r.ano, r.tipo): (r.valor_anterior, r.valor_novo) for r in m.itertuples()}
    assert set(resumo) == {(2001, "removido"), (2003, "novo")}
    assert resumo[(2001, "removido")][0] == 1.0 and pd.isna(resumo[(2001, "removido")][1])
    assert pd.isna(resumo[(2003, "novo")][0]) and resumo[(2003, "novo")][1] == 7.0
    assert m.ano.tolist() == [2001, 2003]


def test_mudancas_sem_publicacao_anterior_tudo_novo():
    m = mudancas(base_com_valor(2.0), None)
    assert m.tipo.tolist() == ["novo"] and m.valor_novo.tolist() == [2.0]


def test_mudancas_iguais_incluindo_nulos_nao_aparecem():
    nulo = base_com_valor(float("nan"), tipo_dado="indisponivel")
    assert mudancas(nulo, nulo).empty
    assert list(mudancas(nulo, nulo).columns) == COLUNAS_MUDANCAS


def test_mudancas_nulo_para_valor_e_alterado():
    m = mudancas(base_com_valor(3.0), base_com_valor(float("nan"), tipo_dado="indisponivel"))
    assert m.tipo.tolist() == ["alterado"] and m.valor_novo.tolist() == [3.0] and pd.isna(m.valor_anterior.iloc[0])


# ---------------------------------------------------------------------------
# versao_completa
# ---------------------------------------------------------------------------

def test_versao_completa_traz_ficha_serie_e_governo(projeto):
    fichas = carregar_fichas(projeto.fichas)
    territorios = carregar_territorios(projeto.territorios_csv)
    governos = carregar_governos(projeto.governos_csv)
    base = pd.concat([
        base_com_valor(1.0, indicador_id="pib_per_capita", territorio_id="PE", ano=2016, serie_id="scr_ref2010"),
        base_com_valor(2.0, indicador_id="pib_per_capita", territorio_id="NE", ano=2023, serie_id="scr_ref2010"),
    ], ignore_index=True)

    completa = versao_completa(base, fichas, territorios, governos)

    assert list(completa.columns) == [*COLUNAS_BASE, *COLUNAS_EXTRAS]
    assert completa[COLUNAS_BASE].equals(base)
    ficha, serie = fichas["pib_per_capita"], fichas["pib_per_capita"].serie("scr_ref2010")
    a, b = completa.iloc[0], completa.iloc[1]
    assert (a.territorio_nome, b.territorio_nome) == ("Pernambuco", "Nordeste")
    assert a.indicador_nome == ficha.nome and a.unidade == ficha.unidade
    assert a.orgao == ficha.orgao and a.periodicidade == ficha.periodicidade
    assert (a.fonte, a.url, a.compatibilidade) == (serie.fonte, serie.url, serie.compatibilidade)
    assert (a.presidente, a.mandato) == ("transicao_dilma_temer", "")
    assert (b.presidente, b.mandato) == ("Luiz Inácio Lula da Silva", "3")
