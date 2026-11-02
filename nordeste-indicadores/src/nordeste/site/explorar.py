"""Dados das paginas Estados e Explorar: os indicadores, os territorios e os filtros do prototipo aprovado.

O Explorar entrega, por indicador, os pontos de cada territorio como `[ano, valor, serie]` (series de pesquisas
diferentes ficam separadas, nunca emendadas) para os JSON que o site.js le. O Estados entrega vistas prontas para o
HTML: mapa de calor em faixas de cor (`nn-f0` a `nn-f9`, a mais escura e a melhor), ranking do ultimo ano e tabela.
"""

from dataclasses import dataclass

from nordeste.site.dados import DadosSite, Ponto
from nordeste.site.formatacao import numero

# (id na base, nome, etiqueta curta na ponta do grafico), na ordem dos seletores do prototipo
TERRITORIOS = (
    ("NE", "Nordeste", "NE"),
    ("BR", "Brasil", "BR"),
    ("BR_FORA_NE", "Brasil fora do Nordeste", "BR fora NE"),
    ("MA", "Maranhão", "MA"),
    ("PI", "Piauí", "PI"),
    ("CE", "Ceará", "CE"),
    ("RN", "Rio Grande do Norte", "RN"),
    ("PB", "Paraíba", "PB"),
    ("PE", "Pernambuco", "PE"),
    ("AL", "Alagoas", "AL"),
    ("SE_UF", "Sergipe", "SE"),
    ("BA", "Bahia", "BA"),
    ("N", "Região Norte", "Norte"),
    ("SE", "Região Sudeste", "Sudeste"),
    ("S", "Região Sul", "Sul"),
    ("CO", "Região Centro-Oeste", "C.-Oeste"),
)
NOME_DO_TERRITORIO = {id_: nome for id_, nome, _ in TERRITORIOS}
ETIQUETA_DO_TERRITORIO = {id_: etiqueta for id_, _, etiqueta in TERRITORIOS}
UFS = ("MA", "PI", "CE", "RN", "PB", "PE", "AL", "SE_UF", "BA")  # ordem do mapa de calor
FAIXAS = 10  # classes nn-f0 a nn-f9


@dataclass(frozen=True)
class IndicadorExplorar:
    chave: str
    indicador_id: str
    rotulo: str  # no seletor
    nome: str
    unidade: str
    casas: int
    sufixo: str = ""
    sub: str | None = None
    etapa: str | None = None
    rede: str | None = None


INDICADORES_EXPLORAR = (
    IndicadorExplorar("pib_pc", "pib_per_capita", "PIB per capita (R$ correntes)", "PIB per capita", "R$ correntes", 0),
    IndicadorExplorar(
        "pib_vol", "pib_volume", "Volume do PIB (índice, primeiro ano = 100)", "Volume do PIB",
        "índice, primeiro ano = 100", 1,
    ),
    IndicadorExplorar(
        "pib_part", "pib_participacao", "Participação no PIB do Brasil (%)", "Participação no PIB do Brasil", "%", 2, "%",
    ),
    IndicadorExplorar(
        "renda", "renda_dom_pc", "Renda domiciliar por pessoa (R$ por mês)", "Renda domiciliar por pessoa",
        "R$ por mês, a preços do último ano da série", 0,
    ),
    IndicadorExplorar(
        "rend_trab", "rendimento_trabalho", "Rendimento do trabalho (R$ por mês)", "Rendimento do trabalho",
        "R$ por mês, a preços do último ano da série", 0,
    ),
    IndicadorExplorar("desoc", "desocupacao", "Desocupação (%)", "Taxa de desocupação", "% da força de trabalho", 1, "%"),
    IndicadorExplorar("informal", "informalidade", "Informalidade (%)", "Informalidade", "% dos ocupados", 1, "%"),
    IndicadorExplorar(
        "pobreza", "pobreza", "Pobreza (%)", "Pobreza", "% da população abaixo de US$ 8,30 por dia", 1, "%",
    ),
    IndicadorExplorar(
        "extrema", "extrema_pobreza", "Extrema pobreza (%)", "Extrema pobreza",
        "% da população abaixo de US$ 3,00 por dia", 1, "%",
    ),
    IndicadorExplorar("gini", "gini", "Índice de Gini (0 a 1)", "Índice de Gini", "0 a 1, maior é mais desigual", 3),
    IndicadorExplorar("idhm", "idhm", "IDHM (0 a 1)", "IDHM", "0 a 1", 3, sub="idhm"),
    IndicadorExplorar(
        "ideb_ai", "ideb", "IDEB, anos iniciais", "IDEB, anos iniciais", "0 a 10", 1, sub="anos_iniciais", rede="total",
    ),
    IndicadorExplorar(
        "ideb_af", "ideb", "IDEB, anos finais", "IDEB, anos finais", "0 a 10", 1, sub="anos_finais", rede="total",
    ),
    IndicadorExplorar(
        "ideb_em", "ideb", "IDEB, ensino médio", "IDEB, ensino médio", "0 a 10", 1, sub="ensino_medio", rede="total",
    ),
    IndicadorExplorar(
        "aband", "abandono_em", "Abandono no ensino médio (%)", "Abandono no ensino médio", "% dos matriculados", 1, "%",
        rede="total",
    ),
    IndicadorExplorar(
        "matric", "matriculas_basica", "Matrículas na educação básica", "Matrículas na educação básica", "matrículas", 0,
        etapa="educacao_basica", rede="total",
    ),
    IndicadorExplorar(
        "superior", "superior", "Matrículas no ensino superior", "Matrículas no ensino superior", "matrículas", 0,
        sub="matriculas", rede="total",
    ),
    IndicadorExplorar("pop", "populacao", "População", "População", "pessoas", 0),
)
POR_CHAVE = {i.chave: i for i in INDICADORES_EXPLORAR}


# --- Explorar ---

def pontos_do_indicador(dados: DadosSite, ind: IndicadorExplorar) -> dict[str, list[list]]:
    """`{territorio: [[ano, valor, serie], ...]}` dos 16 territorios, em ordem de ano e serie; sem dado, lista vazia.

    Mesmos filtros do prototipo: o indicador sem `sub` nao aceita linha de subindicador (exceto a populacao).
    """
    base = dados.base
    selecao = (
        (base["indicador_id"] == ind.indicador_id) & (base["tipo_dado"] != "indisponivel") & base["valor"].notna()
        & base["territorio_id"].isin(NOME_DO_TERRITORIO)
    )
    if ind.sub is not None:
        selecao &= base["subindicador"] == ind.sub
    elif ind.indicador_id != "populacao":
        selecao &= base["subindicador"] == ""
    if ind.etapa is not None:
        selecao &= base["etapa"] == ind.etapa
    if ind.rede is not None:
        selecao &= base["rede"] == ind.rede
    ordenadas = base[selecao].sort_values(["ano", "serie_id"], kind="stable")
    por_territorio = {t: [] for t in NOME_DO_TERRITORIO}
    for territorio, ano, valor, serie in zip(
        ordenadas["territorio_id"], ordenadas["ano"], ordenadas["valor"], ordenadas["serie_id"]
    ):
        por_territorio[territorio].append([int(ano), float(valor), serie])
    return por_territorio


def dados_explorar(dados: DadosSite) -> dict[str, dict[str, list[list]]]:
    """`{indicador: {territorio: [[ano, valor, serie], ...]}}` dos 18 indicadores do Explorar."""
    return {ind.chave: pontos_do_indicador(dados, ind) for ind in INDICADORES_EXPLORAR}


def pontos(lista: list[list]) -> list[Ponto]:
    return [Ponto(ano, valor, serie) for ano, valor, serie in lista]


def referencias(territorio: str) -> list[str]:
    """Linhas de referencia (claras) do territorio escolhido: o Brasil e, para estados e regioes, o Nordeste."""
    if territorio == "NE":
        return ["BR"]
    if territorio in ("BR", "BR_FORA_NE"):
        return ["NE"]
    return ["NE", "BR"]


# --- Estados ---

@dataclass(frozen=True)
class IndicadorEstados:
    chave: str
    indicador_id: str
    rotulo: str  # no seletor
    nome: str  # no titulo da vista
    casas: int
    sufixo: str
    maior_melhor: bool
    razao: bool = False  # razao publicada contra o Brasil fora do Nordeste, em vez do valor da base
    sub: str | None = None
    rede: str | None = None
    serie: str | None = None


INDICADORES_ESTADOS = (
    IndicadorEstados(
        "pib_pc", "pib_per_capita", "PIB per capita (% do Brasil fora do NE)",
        "PIB per capita como % do Brasil fora do Nordeste", 1, "%", True, razao=True,
    ),
    IndicadorEstados(
        "renda", "renda_dom_pc", "Renda domiciliar por pessoa (% do Brasil fora do NE)",
        "renda domiciliar por pessoa como % do Brasil fora do Nordeste", 1, "%", True, razao=True,
    ),
    IndicadorEstados("pobreza", "pobreza", "Pobreza (% da população)", "pobreza, % da população", 1, "%", False),
    IndicadorEstados(
        "desoc", "desocupacao", "Desocupação (% da força de trabalho)", "desocupação, % da força de trabalho", 1, "%",
        False, serie="pnadc",
    ),
    IndicadorEstados(
        "ideb_ai", "ideb", "IDEB, anos iniciais (0 a 10)", "IDEB dos anos iniciais", 1, "", True,
        sub="anos_iniciais", rede="total",
    ),
    IndicadorEstados("idhm", "idhm", "IDHM (0 a 1)", "IDHM", 3, "", True, sub="idhm", serie="pnadc"),
    IndicadorEstados(
        "aband", "abandono_em", "Abandono no ensino médio (%)", "abandono no ensino médio, %", 1, "%", False, rede="total",
    ),
)


def _pontos_dos_estados(dados: DadosSite, ind: IndicadorEstados) -> list[tuple[str, Ponto]]:
    """(uf, ponto) de cada estado, em ordem de estado e ano; razao publicada ou valor da base, como no prototipo."""
    achados = []
    for uf in UFS:
        if ind.razao:
            lista = dados.razao(ind.indicador_id, uf, "BR_FORA_NE")
        else:
            lista = dados.serie(ind.indicador_id, uf, sub=ind.sub, rede=ind.rede, serie=ind.serie)
        achados += [(uf, p) for p in lista]
    return achados


def _faixa(valor: float, baixo: float, alto: float, maior_melhor: bool) -> int:
    """Faixa de 0 a 9 (9 e a melhor situacao): o valor normalizado no intervalo da vista, invertido quando menor e melhor."""
    t = (valor - baixo) / (alto - baixo) if alto > baixo else 1.0
    if not maior_melhor:
        t = 1 - t
    return min(FAIXAS - 1, int(t * FAIXAS))


def _etiqueta_do_estado(uf: str) -> str:
    return "SE" if uf == "SE_UF" else uf


def vista_estados(dados: DadosSite, ind: IndicadorEstados) -> dict:
    """A vista de um indicador, pronta para o modelo: mapa de calor, ranking do ultimo ano e tabela.

    Dois pontos do mesmo estado e ano (series diferentes) nao entram na mesma celula: vale o de menor id de serie.
    Sem nenhum ponto, `anos` vem vazio e o modelo mostra o aviso.
    """
    achados = _pontos_dos_estados(dados, ind)
    vista: dict = {
        "chave": ind.chave, "rotulo": ind.rotulo, "nome": ind.nome, "indicador_id": ind.indicador_id,
        "anos": [], "linhas": [], "ano_do_ranking": None, "ranking": [], "tabela": [],
    }
    if not achados:
        return vista
    celulas: dict[tuple[str, int], float] = {}
    for uf, p in sorted(achados, key=lambda a: (a[1].ano, a[1].serie)):
        celulas.setdefault((uf, p.ano), p.valor)
    anos = list(range(min(a for _, a in celulas), max(a for _, a in celulas) + 1))
    valores = list(celulas.values())
    baixo, alto = min(valores), max(valores)

    def texto(valor: float) -> str:
        return f"{numero(valor, ind.casas)}{ind.sufixo}"

    vista["anos"] = anos
    for uf in UFS:
        linha = []
        for ano in anos:
            valor = celulas.get((uf, ano))
            if valor is None:
                linha.append({"ano": ano, "classe": "nn-vazia", "titulo": f"{NOME_DO_TERRITORIO[uf]}, {ano}: sem dado"})
            else:
                faixa = _faixa(valor, baixo, alto, ind.maior_melhor)
                linha.append({
                    "ano": ano, "classe": f"nn-f{faixa}", "titulo": f"{NOME_DO_TERRITORIO[uf]}, {ano}: {texto(valor)}",
                })
        vista["linhas"].append({"uf": _etiqueta_do_estado(uf), "estado": NOME_DO_TERRITORIO[uf], "celulas": linha})
        vista["tabela"] += [
            {"estado": NOME_DO_TERRITORIO[uf], "ano": ano, "valor": texto(celulas[uf, ano])}
            for ano in anos if (uf, ano) in celulas
        ]

    ultimo = max(ano for _, ano in celulas)
    do_ano = [(uf, celulas[uf, ultimo]) for uf in UFS if (uf, ultimo) in celulas]
    do_ano.sort(key=lambda par: -par[1] if ind.maior_melhor else par[1])  # estavel: empate mantem a ordem dos estados
    maior = max(valor for _, valor in do_ano) or 1.0
    vista["ano_do_ranking"] = ultimo
    vista["ranking"] = [
        {
            "posicao": f"{i}º {NOME_DO_TERRITORIO[uf]}", "valor": texto(valor),
            "largura": f"{max(2.0, valor / maior * 100):.1f}",
        }
        for i, (uf, valor) in enumerate(do_ano, start=1)
    ]
    return vista


def vistas_estados(dados: DadosSite) -> list[dict]:
    return [vista_estados(dados, ind) for ind in INDICADORES_ESTADOS]


def tabela_do_territorio(ind: IndicadorExplorar, lista: list[list], territorio: str) -> list[dict]:
    """Os numeros do territorio escolhido, na ordem do JSON; a serie da fonte vai em cada linha."""
    return [
        {"ano": ano, "territorio": NOME_DO_TERRITORIO[territorio], "valor": f"{numero(valor, ind.casas)}{ind.sufixo}",
         "serie": serie}
        for ano, valor, serie in lista
    ]

