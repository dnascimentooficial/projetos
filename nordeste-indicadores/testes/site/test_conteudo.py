from pathlib import Path

import pytest
import yaml

from nordeste.caminhos import Caminhos
from nordeste.site.conteudo import (
    Conteudo,
    Destaque,
    ErroConteudo,
    avaliar_condicao,
    calcular_destaques,
    carregar_conteudo,
    preencher,
)
from nordeste.site.dados import DadosSite, Ponto

BASE_MINI = Path(__file__).parent / "base_mini"


def _d(id_: str, ano0: int, valor0: float, ano1: int, valor1: float) -> Destaque:
    return Destaque(id_, Ponto(ano0, valor0, "s"), Ponto(ano1, valor1, "s"))


@pytest.fixture
def destaques() -> dict[str, Destaque]:
    return {
        "x": _d("x", 2012, 58.8, 2024, 44.7),
        "y": _d("y", 2009, 1136732.0, 2024, 2186521.0),
        "z": _d("z", 2002, 38.7792, 2023, 43.5683),
    }


def test_destaque_calcula_a_diferenca(destaques):
    assert destaques["x"].dif == pytest.approx(-14.1)


def test_preencher_formatos(destaques):
    assert preencher("{x.ultimo:1%}", destaques) == "44,7%"
    assert preencher("{x.ano_ultimo}", destaques) == "2024"
    assert preencher("{z.dif:+1}", destaques) == "+4,8"
    assert preencher("{y.ultimo:auto}", destaques) == "2,19 mi"
    # casas sem sufixo, valor grande com separador de milhar, texto em volta preservado
    assert preencher("de {x.ano_primeiro} a {x.ano_ultimo}: {x.primeiro:0} para {x.ultimo:2}", destaques) \
        == "de 2012 a 2024: 59 para 44,70"
    assert preencher("R$ {y.ultimo:0}", destaques) == "R$ 2.186.521"
    assert preencher("sem marcador", destaques) == "sem marcador"


def test_preencher_sinal_explicito_so_para_positivo(destaques):
    assert preencher("{x.dif:+1}", destaques) == "-14,1"  # negativo ja leva o proprio sinal
    destaques["zero"] = _d("zero", 2000, 5.0, 2001, 5.0)
    assert preencher("{zero.dif:+1}", destaques) == "0,0"  # nunca "+0,0"


def test_preencher_marcador_desconhecido_levanta(destaques):
    for texto in (
        "{nao_existe.ultimo:1}",   # destaque sem dado ou nao declarado
        "{x.nao_existe:1}",        # campo fora da lista
        "{x.ultimo}",              # valor sem formato
        "{x.ano_ultimo:1}",        # ano nao leva formato
        "{x.ultimo:uma}",          # formato fora da lista
        "{x.ultimo:1",             # chave solta
        "sobrou } aqui",
    ):
        with pytest.raises(ErroConteudo):
            preencher(texto, destaques)


def test_preencher_auto_recusa_valor_pequeno(destaques):
    # escala_auto so vale de 1.000 em diante; abaixo disso "0 mil" enganaria
    with pytest.raises(ErroConteudo):
        preencher("{x.ultimo:auto}", destaques)


def test_condicao_verdadeira_e_falsa(destaques):
    assert avaliar_condicao("x.ultimo < x.primeiro", destaques) is True
    assert avaliar_condicao("x.ultimo > x.primeiro", destaques) is False
    assert avaliar_condicao("x.ultimo <= x.ultimo", destaques) is True
    assert avaliar_condicao("x.ultimo >= x.primeiro", destaques) is False
    assert avaliar_condicao("z.dif > z.primeiro", destaques) is False
    assert avaliar_condicao("y.dif > y.primeiro", destaques) is False
    assert avaliar_condicao("y.ultimo > y.primeiro", destaques) is True
    assert avaliar_condicao("x.ultimo < 50", destaques) is True  # numero literal
    assert avaliar_condicao("z.ano_ultimo > x.ano_primeiro", destaques) is True   # 2023 > 2012
    assert avaliar_condicao("x.ano_ultimo > z.ano_ultimo", destaques) is True     # 2024 > 2023
    assert avaliar_condicao("x.ano_ultimo < z.ano_ultimo", destaques) is False


def test_condicao_com_destaque_ausente_e_falsa(destaques):
    # Foco 2: o destaque sumiu da base, a condicao e falsa e nada quebra (nem mesmo o "contrario")
    assert avaliar_condicao("sumiu.ultimo < x.primeiro", destaques) is False
    assert avaliar_condicao("x.ultimo > sumiu.ultimo", destaques) is False
    assert avaliar_condicao("sumiu.ultimo >= sumiu.primeiro", destaques) is False
    assert avaliar_condicao("sumiu.ultimo > 0", destaques) is False


@pytest.mark.parametrize("expressao", [
    "__import__('os')",
    "x.ultimo",
    "x.ultimo < x.primeiro < 3",
    "x.ultimo == x.primeiro",
    "x.ultimo < x.primeiro and x.dif > 0",
    "x.ultimo < (x.primeiro)",
    "x.nao_existe < 1",
    "x.ultimo < um",
    "x.ultimo<x.primeiro",
    "",
])
def test_condicao_rejeita_expressao_fora_da_gramatica(destaques, expressao):
    with pytest.raises(ErroConteudo):
        avaliar_condicao(expressao, destaques)


def test_calcular_destaques_usa_os_filtros_e_ignora_destaque_sem_dado():
    dados = DadosSite.carregar(Caminhos(raiz=BASE_MINI))
    conteudo = Conteudo(
        destaques={
            "a_ne": {"tipo": "serie", "indicador": "alfa", "territorio": "NE"},
            "a_nova": {"tipo": "serie", "indicador": "alfa", "territorio": "NE", "serie": "s_nova"},
            "a_razao": {"tipo": "razao", "indicador": "alfa", "territorio": "NE", "referencia": "BR"},
            "b_ne": {"tipo": "serie", "indicador": "beta", "territorio": "NE", "sub": "a"},
            "sem_dado": {"tipo": "serie", "indicador": "alfa", "territorio": "XX"},
            "sem_razao": {"tipo": "razao", "indicador": "alfa", "territorio": "NE", "referencia": "BR_FORA_NE"},
        },
        perguntas=[], cards=[], textos={},
    )
    d = calcular_destaques(dados, conteudo)
    assert set(d) == {"a_ne", "a_nova", "a_razao", "b_ne"}  # destaque sem dado fica fora
    assert d["a_ne"] == Destaque("a_ne", Ponto(2011, 10.0, "s_antiga"), Ponto(2013, 12.5, "s_nova"))
    assert d["a_nova"].primeiro == Ponto(2012, 11.5, "s_nova")
    assert d["a_razao"].ultimo == Ponto(2013, 0.75, "s_nova")
    assert d["b_ne"].primeiro.ano == 2011 and d["b_ne"].ultimo.ano == 2013  # 2012 e indisponivel: nao conta
    assert avaliar_condicao("sem_dado.ultimo > a_ne.ultimo", d) is False


# --- carregar_conteudo ---

_LINHA = {"rotulo": "Nordeste", "rotulo_curto": "NE", "destaque": True,
          "tipo": "serie", "indicador": "alfa", "territorio": "NE"}
_GRAFICO = {"id": "g_a", "casas": 1, "linhas": [_LINHA]}


def _conteudo_minimo() -> dict[str, object]:
    return {
        "destaques": {"x": {"tipo": "serie", "indicador": "alfa", "territorio": "NE"}},
        "perguntas": [{
            "id": "p1", "rotulo": "R", "frase_feita": "F", "lide": "De {x.ano_primeiro} a {x.ano_ultimo}.",
            "graficos": [_GRAFICO],
            "fecho": {"texto": "Subiu.", "condicao": "x.ultimo > x.primeiro"},
            "fonte": ["Fonte: A."],
        }],
        "cards": [{
            "id": "c1", "rotulo": "R", "frase_feita": "F", "de": "{x.primeiro:1}", "para": "{x.ultimo:1}",
            "frase": "de {x.ano_primeiro} a {x.ano_ultimo}.", "grafico": "g_a",
            "fecho": "Subiu.", "condicao": "x.ultimo > x.primeiro", "fonte": "A",
        }],
        "textos": {"abertura": {"intro": ["Em {x.ano_ultimo}."]}},
    }


def _escrever(pasta: Path, conteudo: dict[str, object]) -> Path:
    for nome, valor in conteudo.items():
        (pasta / f"{nome}.yaml").write_text(yaml.safe_dump(valor, allow_unicode=True), encoding="utf-8")
    return pasta


def test_carregar_conteudo_le_os_quatro_arquivos(tmp_path):
    conteudo = carregar_conteudo(_escrever(tmp_path, _conteudo_minimo()))
    assert set(conteudo.destaques) == {"x"}
    assert [p["id"] for p in conteudo.perguntas] == ["p1"]
    assert [c["id"] for c in conteudo.cards] == ["c1"]
    assert conteudo.textos["abertura"]["intro"] == ["Em {x.ano_ultimo}."]
    # o grafico do card, citado por id, ja vem resolvido para o dicionario da pergunta
    assert conteudo.cards[0]["grafico"] == _GRAFICO


def test_carregar_conteudo_recusa_id_inexistente(tmp_path):
    bruto = _conteudo_minimo()
    bruto["perguntas"][0]["lide"] = "Em {nao_declarado.ano_ultimo}."
    with pytest.raises(ErroConteudo, match="nao_declarado"):
        carregar_conteudo(_escrever(tmp_path, bruto))


@pytest.mark.parametrize("onde", ["fecho", "card", "texto"])
def test_carregar_conteudo_recusa_condicao_ou_marcador_invalido_em_qualquer_arquivo(tmp_path, onde):
    bruto = _conteudo_minimo()
    if onde == "fecho":
        bruto["perguntas"][0]["fecho"]["condicao"] = "x.ultimo > fantasma.primeiro"
    elif onde == "card":
        bruto["cards"][0]["condicao"] = "__import__('os')"
    else:
        bruto["textos"]["abertura"]["intro"] = ["Em {x.ultimo}."]  # valor sem formato
    with pytest.raises(ErroConteudo):
        carregar_conteudo(_escrever(tmp_path, bruto))


def test_carregar_conteudo_recusa_grafico_de_card_inexistente(tmp_path):
    bruto = _conteudo_minimo()
    bruto["cards"][0]["grafico"] = "g_outro"
    with pytest.raises(ErroConteudo, match="g_outro"):
        carregar_conteudo(_escrever(tmp_path, bruto))


def test_carregar_conteudo_aceita_grafico_de_card_inline(tmp_path):
    bruto = _conteudo_minimo()
    inline = {"id": "g_solto", "casas": 0, "linhas": [_LINHA]}
    bruto["cards"][0]["grafico"] = inline
    assert carregar_conteudo(_escrever(tmp_path, bruto)).cards[0]["grafico"] == inline


@pytest.mark.parametrize("alterar", [
    lambda c: c["destaques"]["x"].update(tipo="outro"),
    lambda c: c["destaques"]["x"].update(referencia="BR"),            # serie nao leva referencia
    lambda c: c["destaques"]["x"].update(tipo="razao"),               # razao exige referencia
    lambda c: c["destaques"]["x"].update(filtro_inventado="a"),
    lambda c: c["destaques"]["x"].pop("indicador"),
    lambda c: c["perguntas"][0].pop("fecho"),
    lambda c: c["perguntas"][0].update(campo_inventado="a"),
    lambda c: c["perguntas"][0]["graficos"][0]["linhas"][0].update(tipo="outro"),
    lambda c: c["perguntas"][0]["graficos"][0]["linhas"][0].pop("rotulo_curto"),
    lambda c: c["cards"].append(dict(c["cards"][0])),                 # id repetido
    lambda c: c["cards"][0].pop("condicao"),
])
def test_carregar_conteudo_recusa_estrutura_errada(tmp_path, alterar):
    bruto = _conteudo_minimo()
    alterar(bruto)
    with pytest.raises(ErroConteudo):
        carregar_conteudo(_escrever(tmp_path, bruto))
