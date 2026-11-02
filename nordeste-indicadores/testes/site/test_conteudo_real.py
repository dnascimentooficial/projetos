"""O conteudo editorial de metadados/site contra a base publicada do repositorio."""

import re
from pathlib import Path

import pytest

from nordeste.caminhos import Caminhos
from nordeste.site.conteudo import avaliar_condicao, calcular_destaques, carregar_conteudo, preencher
from nordeste.site.dados import DadosSite
from nordeste.site.formatacao import escala_auto, numero

RAIZ = Path(__file__).resolve().parents[2]
PASTA_SITE = RAIZ / "metadados" / "site"

IDS_DOS_DESTAQUES = {
    "pib_pc_razao", "pob_ne", "pob_br", "ext_ne", "ext_br", "ideb_ai_ne", "ideb_ai_br", "ideb_af_ne", "ideb_af_br",
    "ideb_em_ne", "ideb_em_br", "vol_ne", "vol_br", "part_ne", "desoc_ne", "desoc_br", "renda_razao", "renda_ne",
    "renda_ref", "rend_ne", "rend_br", "informal_ne", "informal_ref", "gini_ne", "gini_br", "idhm_ne", "idhm_br",
    "superior_ne", "creche_ne",
}


@pytest.fixture(scope="module")
def conteudo():
    return carregar_conteudo(PASTA_SITE)


@pytest.fixture(scope="module")
def destaques(conteudo):
    return calcular_destaques(DadosSite.carregar(Caminhos(raiz=RAIZ)), conteudo)


def _textos(obj, chave=None):
    """Todas as strings do conteudo, menos as condicoes (que nao sao texto de leitura)."""
    if isinstance(obj, str):
        if chave != "condicao":
            yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _textos(v, k)
    elif isinstance(obj, list):
        for v in obj:
            yield from _textos(v, chave)


def _condicoes(conteudo):
    for p in conteudo.perguntas:
        yield f"pergunta {p['id']}", p["fecho"]["condicao"]
    for c in conteudo.cards:
        yield f"card {c['id']}", c["condicao"]


def test_conteudo_real_tem_17_cards_e_6_perguntas(conteudo):
    assert len(conteudo.perguntas) == 6
    assert len(conteudo.cards) == 17
    assert set(conteudo.destaques) == IDS_DOS_DESTAQUES
    assert len({c["id"] for c in conteudo.cards}) == 17


def test_conteudo_real_carrega_e_preenche_tudo(conteudo, destaques):
    assert set(destaques) == IDS_DOS_DESTAQUES  # todos os destaques tem dado na base publicada
    textos = list(_textos([conteudo.perguntas, conteudo.cards, conteudo.textos]))
    assert len(textos) > 100
    for texto in textos:
        preenchido = preencher(texto, destaques)
        assert "{" not in preenchido and "}" not in preenchido
        assert not re.search(r"\bnan\b|\bNaN\b|\bNone\b|\bundefined\b", preenchido), preenchido


def test_numeros_do_conteudo_real_vem_da_base_publicada(conteudo, destaques):
    # A base muda toda semana: nada aqui fixa valor, so a relacao entre o texto e o destaque que o alimenta.
    pob, pib, sup, creche = destaques["pob_ne"], destaques["pib_pc_razao"], destaques["superior_ne"], destaques["creche_ne"]
    esperado = {
        "{pob_ne.primeiro:1%}": numero(pob.primeiro.valor, 1) + "%",
        "{pob_ne.ultimo:1%}": numero(pob.ultimo.valor, 1) + "%",
        "{pob_ne.ano_primeiro}": str(pob.primeiro.ano),
        "{pib_pc_razao.dif:+1}": ("+" if pib.dif > 0 else "") + numero(pib.dif, 1),
        "{superior_ne.ultimo:auto}": escala_auto(sup.ultimo.valor),
        "{creche_ne.primeiro:auto}": escala_auto(creche.primeiro.valor),
        "R$ {renda_ref.ultimo:0}": "R$ " + numero(destaques["renda_ref"].ultimo.valor, 0),
        "{gini_ne.ultimo:3}": numero(destaques["gini_ne"].ultimo.valor, 3),
        "{vol_ne.ultimo:0}": numero(destaques["vol_ne"].ultimo.valor, 0),
    }
    for marcador, texto in esperado.items():
        assert preencher(marcador, destaques) == texto
    pobreza = next(c for c in conteudo.cards if c["id"] == "pobreza")
    assert preencher(pobreza["de"], destaques) == numero(pob.primeiro.valor, 1) + "%"
    assert preencher(pobreza["para"], destaques) == numero(pob.ultimo.valor, 1) + "%"
    assert preencher(pobreza["frase"], destaques) == (
        f"da população do Nordeste vivia abaixo da linha de pobreza, de {pob.primeiro.ano} a {pob.ultimo.ano}. "
        f"No Brasil, hoje, {numero(destaques['pob_br'].ultimo.valor, 1)}%."
    )


def test_condicoes_reais_valem_na_base_publicada(conteudo, destaques):
    condicoes = list(_condicoes(conteudo))
    assert len(condicoes) == 6 + 17
    falsas = [(onde, expr) for onde, expr in condicoes if not avaliar_condicao(expr, destaques)]
    assert falsas == []


def test_fecho_cujo_destaque_sumiu_da_base_fica_suprimido_sem_quebrar(conteudo, destaques):
    # Foco 2: sem o destaque da pobreza, a condicao do fecho da pergunta e dos cards que o citam falha;
    # as demais seguem valendo e nenhuma avaliacao levanta erro.
    sem_pobreza = {k: v for k, v in destaques.items() if k != "pob_ne"}
    suprimidas = {onde for onde, expr in _condicoes(conteudo) if not avaliar_condicao(expr, sem_pobreza)}
    assert suprimidas == {"pergunta pobreza", "card pobreza"}


def test_sem_travessao_nos_textos():
    arquivos = sorted(PASTA_SITE.glob("*.yaml"))
    assert {a.name for a in arquivos} == {"destaques.yaml", "perguntas.yaml", "cards.yaml", "textos.yaml"}
    for arquivo in arquivos:
        assert "—" not in arquivo.read_text(encoding="utf-8"), arquivo.name


def test_sem_decimal_digitado_nos_textos(conteudo):
    # Todo valor decimal vem de marcador. Sobram so as definicoes dos indicadores (linhas de pobreza em US$).
    # Anos de fatos historicos (pandemia, lacunas, metodologia) ficam digitados: sao fatos fixos.
    decimais = []
    for texto in _textos([conteudo.perguntas, conteudo.cards, conteudo.textos]):
        decimais += re.findall(r"\d+[.,]\d+", re.sub(r"\{[^{}]*\}", "", texto))
    assert sorted(set(decimais)) == ["3,00", "8,30"]
