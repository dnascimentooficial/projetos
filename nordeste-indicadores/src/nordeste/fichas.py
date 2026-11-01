"""Fichas de indicador: leitura, validacao de completude e consulta das series."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from nordeste.territorios import REGIOES, UFS_NE

SENTIDOS: tuple[str, ...] = ("maior_melhor", "menor_melhor")
REFERENCIAS: tuple[str, ...] = ("brasil", "brasil_fora_ne", "nenhuma")
METODOS: tuple[str, ...] = ("soma", "razao", "razao_encadeada")
MODOS_MONETARIOS: tuple[str, ...] = ("razao", "reais_constantes")
METODOS_CALCULO: tuple[str, ...] = ("razao_por_ano",)
# `tratamento_monetario.ano_base` de serie reapresentada a precos do ultimo ano a cada divulgacao (PNAD Continua);
# a unidade traz MARCA_ULTIMO_ANO, que a versao completa troca por "de <ano>" com o ano resolvido na base.
ULTIMO_ANO = "ultimo_ano"
MARCA_ULTIMO_ANO = "do último ano da série"

_METODOS_COM_TERMOS = ("razao", "razao_encadeada")
_TEXTOS_FICHA = (
    "id", "nome", "descricao", "eixo", "categoria", "unidade", "orgao",
    "periodicidade", "metodologia", "observacoes",
)
_TEXTOS_SERIE = ("id", "fonte", "base_origem", "url", "coletor", "compatibilidade")
_FAIXA_DE_ANOS = re.compile(r"^(\d{4})(?:-(\d{4}))?$")
# Territorios que uma fonte publica (o Brasil fora do Nordeste e derivado pelo projeto, nunca lido de planilha).
_TERRITORIOS_DA_FONTE = frozenset({"BR", *REGIOES, *UFS_NE})


class ErroFicha(ValueError):
    """Ficha ilegivel, incompleta ou incoerente."""


@dataclass(frozen=True)
class Serie:
    id: str
    inicio: int
    fim: int | None
    fonte: str
    base_origem: str
    url: str
    coletor: str
    parametros: dict
    compatibilidade: str
    verificado: bool
    anos_sem_publicacao: tuple[int, ...] = ()  # anos dentro da cobertura em que a fonte nao tem pesquisa (ex.: Censo)


@dataclass(frozen=True)
class Comparacao:
    referencia: str
    metodo: str | None = None
    numerador: str | None = None
    denominador: str | None = None
    fator: float = 1.0
    precisao_oficial: float | None = None  # passo de arredondamento do valor oficial (0,1 = uma casa decimal)


@dataclass(frozen=True)
class FaixaDenominador:
    """Anos `inicio` a `fim` (fechado) usam o denominador da `serie`; `ano` fixo ou None (o proprio ano)."""
    inicio: int
    fim: int
    serie: str
    ano: int | None = None


@dataclass(frozen=True)
class Calculo:
    """Indicador calculado pelo projeto, territorio a territorio, a partir de duas fichas da base."""
    metodo: str
    numerador: str
    serie_numerador: str
    denominador: str
    faixas: tuple[FaixaDenominador, ...]
    fator: float = 1.0

    def denominador_do_ano(self, ano: int) -> tuple[str, int] | None:
        """(serie, ano) do denominador usado no ano; None se o ano nao esta mapeado."""
        for faixa in self.faixas:
            if faixa.inicio <= ano <= faixa.fim:
                return faixa.serie, ano if faixa.ano is None else faixa.ano
        return None


@dataclass(frozen=True)
class Ficha:
    id: str
    nome: str
    descricao: str
    eixo: str
    categoria: str
    unidade: str
    orgao: str
    periodicidade: str
    metodologia: str
    observacoes: str
    sentido: str
    limites: dict
    comparacao: Comparacao
    defasagem_meses: int
    series: tuple[Serie, ...]
    tratamento_monetario: dict | None = None
    auxiliar: bool = False
    limiar_salto_pct: float = 50.0
    calculo: Calculo | None = None

    def unidade_resolvida(self, ultimo_ano: int) -> str:
        """A unidade com o ano-base resolvido: em reais do ultimo ano, MARCA_ULTIMO_ANO vira "de <ultimo_ano>"."""
        if (self.tratamento_monetario or {}).get("ano_base") != ULTIMO_ANO:
            return self.unidade
        return self.unidade.replace(MARCA_ULTIMO_ANO, f"de {ultimo_ano}")

    def serie(self, serie_id: str) -> Serie:
        for s in self.series:
            if s.id == serie_id:
                return s
        raise KeyError(f"A ficha {self.id!r} nao tem a serie {serie_id!r}.")

    def serie_do_ano(self, ano: int) -> Serie | None:
        for s in self.series:
            if s.inicio <= ano and (s.fim is None or ano <= s.fim):
                return s
        return None


def _inteiro(valor: Any) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


def _numero(valor: Any) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def _texto_ok(valor: Any) -> bool:
    return isinstance(valor, str) and bool(valor.strip())


def _validar_comparacao(comp: Any, calculada: bool) -> list[str]:
    """`calculada`: a ficha tem `calculo`, que ja produz o Brasil fora do Nordeste; metodo proibido."""
    if not isinstance(comp, dict):
        return ["comparacao deve ser um mapa"]
    problemas: list[str] = []
    referencia, metodo = comp.get("referencia"), comp.get("metodo")
    if referencia not in REFERENCIAS:
        problemas.append(f"comparacao.referencia deve ser um de {', '.join(REFERENCIAS)}")
    if calculada and metodo is not None:
        problemas.append("comparacao.metodo nao se usa em ficha com calculo: o calculo ja gera o Brasil fora do Nordeste")
    if referencia == "brasil_fora_ne" and metodo is None and not calculada:
        problemas.append("comparacao.metodo obrigatorio quando a referencia e brasil_fora_ne")
    if metodo is not None and metodo not in METODOS:
        problemas.append(f"comparacao.metodo deve ser um de {', '.join(METODOS)}")
    if metodo in _METODOS_COM_TERMOS:
        for termo in ("numerador", "denominador"):
            if not _texto_ok(comp.get(termo)):
                problemas.append(f"comparacao.{termo} obrigatorio para o metodo {metodo}")
    fator = comp.get("fator", 1.0)
    if not _numero(fator) or fator <= 0:
        problemas.append("comparacao.fator deve ser um numero positivo")
    if "precisao_oficial" in comp and (not _numero(comp["precisao_oficial"]) or comp["precisao_oficial"] <= 0):
        problemas.append("comparacao.precisao_oficial deve ser um numero positivo")
    return problemas


def _validar_serie(serie: Any, posicao: int) -> list[str]:
    if not isinstance(serie, dict):
        return [f"series[{posicao}] deve ser um mapa"]
    nome = f"series[{serie.get('id', posicao)}]"
    problemas: list[str] = []
    for campo in _TEXTOS_SERIE:
        if not _texto_ok(serie.get(campo)):
            problemas.append(f"{nome}.{campo} obrigatorio (texto nao vazio)")
    inicio, fim = serie.get("inicio"), serie.get("fim", "ausente")
    if not _inteiro(inicio):
        problemas.append(f"{nome}.inicio obrigatorio (ano inteiro)")
    if fim == "ausente":
        problemas.append(f"{nome}.fim obrigatorio (ano inteiro ou null para serie em curso)")
    elif fim is not None and not _inteiro(fim):
        problemas.append(f"{nome}.fim deve ser ano inteiro ou null")
    elif _inteiro(inicio) and fim is not None and fim < inicio:
        problemas.append(f"{nome}.fim nao pode ser anterior ao inicio")
    parametros = serie.get("parametros")
    if not isinstance(parametros, dict):
        problemas.append(f"{nome}.parametros obrigatorio (mapa, pode ser vazio)")
    else:
        problemas += _validar_leitura(parametros, f"{nome}.parametros")
        partes = parametros.get("partes")
        if isinstance(partes, list):
            for posicao, parte in enumerate(partes, start=1):
                if isinstance(parte, dict):
                    problemas += _validar_leitura(parte, f"{nome}.parametros.partes[{posicao}]")
    if not isinstance(serie.get("verificado"), bool):
        problemas.append(f"{nome}.verificado obrigatorio (true ou false)")
    if "anos_sem_publicacao" in serie:
        problemas += _validar_anos_sem_publicacao(serie["anos_sem_publicacao"], inicio, fim, nome)
    return problemas


def _validar_leitura(parametros: dict, nome: str) -> list[str]:
    """`territorios_esperados` (ids publicados pela fonte, sem repeticao) e `filtro_linhas` (coluna -> texto ou numero)."""
    problemas: list[str] = []
    if "territorios_esperados" in parametros:
        esperados = parametros["territorios_esperados"]
        if not isinstance(esperados, list) or not esperados or not all(isinstance(t, str) for t in esperados):
            problemas.append(f"{nome}.territorios_esperados deve ser uma lista nao vazia de territorio_id")
        else:
            desconhecidos = sorted(set(esperados) - _TERRITORIOS_DA_FONTE)
            if desconhecidos:
                problemas.append(f"{nome}.territorios_esperados com territorio desconhecido: {', '.join(desconhecidos)}")
            if len(set(esperados)) != len(esperados):
                problemas.append(f"{nome}.territorios_esperados repete territorio")
    if "filtro_linhas" in parametros:
        filtro = parametros["filtro_linhas"]
        valido = isinstance(filtro, dict) and filtro and all(
            isinstance(v, str) or _numero(v) for v in filtro.values())
        if not valido:
            problemas.append(f"{nome}.filtro_linhas deve mapear coluna para valor aceito (texto ou numero)")
    return problemas


def _validar_anos_sem_publicacao(anos: Any, inicio: Any, fim: Any, nome: str) -> list[str]:
    if not isinstance(anos, list) or not all(_inteiro(a) for a in anos):
        return [f"{nome}.anos_sem_publicacao deve ser uma lista de anos inteiros"]
    problemas = [f"{nome}.anos_sem_publicacao repete o ano {a}" for a in sorted({a for a in anos if anos.count(a) > 1})]
    if _inteiro(inicio) and (fim is None or _inteiro(fim)):
        for ano in sorted(set(anos)):
            if ano < inicio or (fim is not None and ano > fim):
                problemas.append(
                    f"{nome}.anos_sem_publicacao: o ano {ano} esta fora da cobertura da serie "
                    f"({inicio} a {fim if fim is not None else 'em curso'})"
                )
    return problemas


def _faixa(chave: Any) -> tuple[int, int] | None:
    """"AAAA" ou "AAAA-AAAA" (ou o ano inteiro) -> (inicio, fim); None se a chave nao for faixa valida."""
    achado = _FAIXA_DE_ANOS.match(str(chave)) if isinstance(chave, (int, str)) and not isinstance(chave, bool) else None
    if achado is None:
        return None
    inicio = int(achado.group(1))
    fim = int(achado.group(2) or inicio)
    return (inicio, fim) if inicio <= fim else None


def _ler_faixas(series_por_ano: dict) -> tuple[list[FaixaDenominador], list[str]]:
    faixas: list[FaixaDenominador] = []
    problemas: list[str] = []
    for chave, destino in series_por_ano.items():
        nome = f"calculo.denominador.series_por_ano[{chave}]"
        anos = _faixa(chave)
        if anos is None:
            problemas.append(f"{nome}: faixa de anos invalida (use AAAA ou AAAA-AAAA, inicio <= fim)")
            continue
        if isinstance(destino, dict):
            serie, ano = destino.get("serie"), destino.get("ano")
            if not set(destino) <= {"serie", "ano"} or not _inteiro(ano):
                problemas.append(f"{nome}: use {{serie: <id>, ano: <ano inteiro>}} para fixar o ano do denominador")
                continue
        else:
            serie, ano = destino, None
        if not _texto_ok(serie):
            problemas.append(f"{nome}: serie do denominador obrigatoria (texto nao vazio)")
            continue
        if ano is not None and ano > anos[0]:  # populacao de um ano posterior seria projecao silenciosa
            problemas.append(f"{nome}: ano fixo {ano} posterior ao inicio da faixa ({anos[0]})")
            continue
        faixas.append(FaixaDenominador(*anos, serie, ano))
    faixas.sort(key=lambda f: f.inicio)
    for anterior, atual in zip(faixas, faixas[1:]):
        if atual.inicio <= anterior.fim:
            problemas.append(
                f"calculo.denominador.series_por_ano: a faixa {atual.inicio}-{atual.fim} "
                f"se sobrepoe a {anterior.inicio}-{anterior.fim}"
            )
    return faixas, problemas


def _validar_calculo(calculo: Any, series: Any) -> list[str]:
    if not isinstance(calculo, dict):
        return ["calculo deve ser um mapa"]
    problemas: list[str] = []
    if calculo.get("metodo") not in METODOS_CALCULO:
        problemas.append(f"calculo.metodo deve ser um de {', '.join(METODOS_CALCULO)}")
    numerador, denominador = calculo.get("numerador"), calculo.get("denominador")
    if not isinstance(numerador, dict) or not all(_texto_ok(numerador.get(c)) for c in ("indicador", "serie")):
        problemas.append("calculo.numerador deve ser um mapa com indicador e serie")
    if not isinstance(denominador, dict) or not _texto_ok(denominador.get("indicador")):
        problemas.append("calculo.denominador deve ser um mapa com indicador e series_por_ano")
    elif not isinstance(denominador.get("series_por_ano"), dict) or not denominador["series_por_ano"]:
        problemas.append("calculo.denominador.series_por_ano obrigatorio (mapa de faixa de anos para serie)")
    else:
        faixas, achados = _ler_faixas(denominador["series_por_ano"])
        problemas += achados
        if isinstance(series, list) and len(series) == 1 and isinstance(series[0], dict):
            inicio, fim = series[0].get("inicio"), series[0].get("fim")
            for f in faixas:
                if _inteiro(inicio) and (f.inicio < inicio or (_inteiro(fim) and f.fim > fim)):
                    problemas.append(
                        f"calculo.denominador.series_por_ano: a faixa {f.inicio}-{f.fim} esta fora da cobertura "
                        f"da serie da ficha ({inicio} a {fim if fim is not None else 'em curso'})"
                    )
    fator = calculo.get("fator", 1.0)
    if not _numero(fator) or fator <= 0:
        problemas.append("calculo.fator deve ser um numero positivo")
    if not isinstance(series, list) or len(series) != 1:
        problemas.append("ficha com calculo deve ter uma unica serie (a serie do resultado)")
    return problemas


def _validar_tratamento_monetario(tratamento: Any, unidade: Any) -> list[str]:
    """`razao` (exibido como razao, sem deflacionar) ou `reais_constantes` com `deflator` e `ano_base`.

    `ano_base` e um ano inteiro ou ULTIMO_ANO; neste caso a unidade precisa trazer MARCA_ULTIMO_ANO.
    """
    if tratamento is None:
        if isinstance(unidade, str) and unidade.startswith("R$"):
            return ["tratamento_monetario obrigatorio quando a unidade e monetaria (R$)"]
        return []
    if not isinstance(tratamento, dict) or tratamento.get("modo") not in MODOS_MONETARIOS:
        return [f"tratamento_monetario.modo deve ser um de {', '.join(MODOS_MONETARIOS)}"]
    if tratamento["modo"] != "reais_constantes":
        return []
    problemas: list[str] = []
    if not _texto_ok(tratamento.get("deflator")):
        problemas.append("tratamento_monetario.deflator obrigatorio em reais_constantes (texto nao vazio)")
    ano_base = tratamento.get("ano_base")
    if not (_inteiro(ano_base) or ano_base == ULTIMO_ANO):
        problemas.append(f"tratamento_monetario.ano_base obrigatorio em reais_constantes (ano inteiro ou {ULTIMO_ANO})")
    elif ano_base == ULTIMO_ANO and not (isinstance(unidade, str) and MARCA_ULTIMO_ANO in unidade):
        problemas.append(
            f"tratamento_monetario.ano_base {ULTIMO_ANO}: a unidade deve conter \"{MARCA_ULTIMO_ANO}\" "
            "(a versao completa troca o trecho pelo ano resolvido)"
        )
    return problemas


def _validar(dados: Any) -> list[str]:
    """Lista os problemas de completude e coerencia de uma ficha lida do YAML."""
    if not isinstance(dados, dict):
        return ["a ficha deve ser um mapa de campos"]
    problemas: list[str] = []
    for campo in _TEXTOS_FICHA:
        if not _texto_ok(dados.get(campo)):
            problemas.append(f"campo obrigatorio ausente ou vazio: {campo}")
    if dados.get("sentido") not in SENTIDOS:
        problemas.append(f"campo sentido deve ser um de {', '.join(SENTIDOS)}")

    limites = dados.get("limites")
    if not isinstance(limites, dict):
        problemas.append("campo obrigatorio ausente: limites (mapa com min e/ou max)")
    else:
        if not set(limites) <= {"min", "max"}:
            problemas.append("limites aceita apenas as chaves min e max")
        if not all(_numero(v) for v in limites.values()):
            problemas.append("limites.min e limites.max devem ser numeros")
        elif {"min", "max"} <= set(limites) and limites["min"] > limites["max"]:
            problemas.append("limites.min nao pode superar limites.max")

    calculada = dados.get("calculo") is not None
    problemas += _validar_comparacao(dados.get("comparacao"), calculada)
    if calculada:
        problemas += _validar_calculo(dados["calculo"], dados.get("series"))

    defasagem = dados.get("defasagem_meses")
    if not _inteiro(defasagem) or defasagem < 0:
        problemas.append("campo obrigatorio ausente ou invalido: defasagem_meses (inteiro >= 0)")

    problemas += _validar_tratamento_monetario(dados.get("tratamento_monetario"), dados.get("unidade"))

    if not isinstance(dados.get("auxiliar", False), bool):
        problemas.append("auxiliar deve ser true ou false")
    limiar = dados.get("limiar_salto_pct", 50.0)
    if not _numero(limiar) or limiar <= 0:
        problemas.append("limiar_salto_pct deve ser um numero positivo")

    series = dados.get("series")
    if not isinstance(series, list) or not series:
        problemas.append("campo obrigatorio ausente: series (ao menos uma serie)")
    else:
        for posicao, serie in enumerate(series):
            problemas += _validar_serie(serie, posicao)
        ids = [s.get("id") for s in series if isinstance(s, dict) and _texto_ok(s.get("id"))]
        for repetido in sorted({i for i in ids if ids.count(i) > 1}):
            problemas.append(f"serie duplicada na ficha: {repetido}")
    return problemas


def _montar(dados: dict) -> Ficha:
    comp = dados["comparacao"]
    comparacao = Comparacao(
        referencia=comp["referencia"], metodo=comp.get("metodo"),
        numerador=comp.get("numerador"), denominador=comp.get("denominador"),
        fator=float(comp.get("fator", 1.0)),
        precisao_oficial=float(comp["precisao_oficial"]) if "precisao_oficial" in comp else None,
    )
    series = tuple(
        Serie(
            **{campo: s[campo] for campo in Serie.__dataclass_fields__ if campo != "anos_sem_publicacao"},
            anos_sem_publicacao=tuple(sorted(s.get("anos_sem_publicacao", []))),
        )
        for s in dados["series"]
    )
    campos = {campo: dados[campo] for campo in _TEXTOS_FICHA}
    calculo = None
    if dados.get("calculo") is not None:
        c = dados["calculo"]
        calculo = Calculo(
            metodo=c["metodo"], numerador=c["numerador"]["indicador"], serie_numerador=c["numerador"]["serie"],
            denominador=c["denominador"]["indicador"],
            faixas=tuple(_ler_faixas(c["denominador"]["series_por_ano"])[0]), fator=float(c.get("fator", 1.0)),
        )
    return Ficha(
        **campos, sentido=dados["sentido"], limites=dict(dados["limites"]),
        comparacao=comparacao, defasagem_meses=dados["defasagem_meses"], series=series,
        tratamento_monetario=dados.get("tratamento_monetario"),
        auxiliar=dados.get("auxiliar", False),
        limiar_salto_pct=float(dados.get("limiar_salto_pct", 50.0)),
        calculo=calculo,
    )


def _ler(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as erro:
        raise ErroFicha(f"{path.name}: nao foi possivel ler a ficha ({erro})") from erro


def carregar_ficha(path: Path) -> Ficha:
    """Le e valida uma ficha; ErroFicha lista todos os problemas encontrados."""
    dados = _ler(path)
    problemas = _validar(dados)
    if problemas:
        raise ErroFicha(f"{path.name}: " + "; ".join(problemas))
    return _montar(dados)


def _examinar(diretorio: Path) -> tuple[dict[str, Ficha], list[str]]:
    fichas: dict[str, Ficha] = {}
    origem: dict[str, str] = {}
    declarados: set[str] = set()
    problemas: list[str] = []
    for path in sorted(diretorio.glob("*.yaml")):
        try:
            dados = _ler(path)
        except ErroFicha as erro:
            problemas.append(str(erro))
            continue
        if isinstance(dados, dict) and _texto_ok(dados.get("id")):
            declarados.add(dados["id"])
        achados = _validar(dados)
        if achados:
            problemas += [f"{path.name}: {m}" for m in achados]
            continue
        ficha = _montar(dados)
        if ficha.id in fichas:
            problemas.append(f"{path.name}: id duplicado {ficha.id!r} (ja usado em {origem[ficha.id]})")
            continue
        fichas[ficha.id], origem[ficha.id] = ficha, path.name
    for ficha in fichas.values():
        for termo in ("numerador", "denominador"):
            alvo = getattr(ficha.comparacao, termo)
            if alvo is not None and alvo not in declarados:
                problemas.append(
                    f"{origem[ficha.id]}: comparacao.{termo} aponta para ficha inexistente: {alvo}"
                )
        problemas += [f"{origem[ficha.id]}: {m}" for m in _insumos_do_calculo(ficha, fichas, declarados)]
    return fichas, problemas


def _insumos_do_calculo(ficha: Ficha, fichas: dict[str, Ficha], declarados: set[str]) -> list[str]:
    """Numerador e denominador do calculo existem, nao sao calculados, tem as series mapeadas e o ano fixo
    do denominador esta dentro da cobertura da serie do insumo."""
    calculo = ficha.calculo
    if calculo is None:
        return []
    problemas: list[str] = []
    termos = (
        ("numerador", calculo.numerador, {calculo.serie_numerador}),
        ("denominador", calculo.denominador, {f.serie for f in calculo.faixas}),
    )
    for termo, indicador, series in termos:
        if indicador not in declarados:
            problemas.append(f"calculo.{termo} aponta para ficha inexistente: {indicador}")
        elif indicador in fichas:  # ficha declarada mas invalida: os problemas dela ja foram listados
            insumo = fichas[indicador]
            if insumo.calculo is not None:
                problemas.append(f"calculo.{termo} aponta para outra ficha calculada: {indicador}")
            for serie in sorted(series - {s.id for s in insumo.series}):
                problemas.append(f"calculo.{termo} aponta para serie inexistente: {indicador}/{serie}")
    if calculo.denominador in fichas:
        insumo = fichas[calculo.denominador]
        for faixa in calculo.faixas:
            serie = next((s for s in insumo.series if s.id == faixa.serie), None)
            if faixa.ano is None or serie is None:
                continue
            if faixa.ano < serie.inicio or (serie.fim is not None and faixa.ano > serie.fim):
                problemas.append(
                    f"calculo.denominador: ano fixo {faixa.ano} da faixa {faixa.inicio}-{faixa.fim} esta fora "
                    f"da cobertura da serie {serie.id} ({serie.inicio} a {serie.fim if serie.fim is not None else 'em curso'})"
                )
    return problemas


def carregar_fichas(diretorio: Path) -> dict[str, Ficha]:
    """Carrega todas as fichas *.yaml do diretorio, indexadas por id.

    Confere tambem se numerador e denominador (da comparacao e do calculo) apontam para fichas e series
    existentes.
    """
    fichas, problemas = _examinar(diretorio)
    if problemas:
        raise ErroFicha("; ".join(problemas))
    return fichas


def verificar_fichas(diretorio: Path) -> list[str]:
    """Devolve uma mensagem por problema encontrado nas fichas, sem parar no primeiro."""
    return _examinar(diretorio)[1]
