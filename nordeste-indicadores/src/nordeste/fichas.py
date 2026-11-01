"""Fichas de indicador: leitura, validacao de completude e consulta das series."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

SENTIDOS: tuple[str, ...] = ("maior_melhor", "menor_melhor")
REFERENCIAS: tuple[str, ...] = ("brasil", "brasil_fora_ne", "nenhuma")
METODOS: tuple[str, ...] = ("soma", "razao", "razao_encadeada")
MODOS_MONETARIOS: tuple[str, ...] = ("razao", "reais_constantes")

_METODOS_COM_TERMOS = ("razao", "razao_encadeada")
_TEXTOS_FICHA = (
    "id", "nome", "descricao", "eixo", "categoria", "unidade", "orgao",
    "periodicidade", "metodologia", "observacoes",
)
_TEXTOS_SERIE = ("id", "fonte", "base_origem", "url", "coletor", "compatibilidade")


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


@dataclass(frozen=True)
class Comparacao:
    referencia: str
    metodo: str | None = None
    numerador: str | None = None
    denominador: str | None = None
    fator: float = 1.0


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


def _validar_comparacao(comp: Any) -> list[str]:
    if not isinstance(comp, dict):
        return ["comparacao deve ser um mapa"]
    problemas: list[str] = []
    referencia, metodo = comp.get("referencia"), comp.get("metodo")
    if referencia not in REFERENCIAS:
        problemas.append(f"comparacao.referencia deve ser um de {', '.join(REFERENCIAS)}")
    if referencia == "brasil_fora_ne" and metodo is None:
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
    if not isinstance(serie.get("parametros"), dict):
        problemas.append(f"{nome}.parametros obrigatorio (mapa, pode ser vazio)")
    if not isinstance(serie.get("verificado"), bool):
        problemas.append(f"{nome}.verificado obrigatorio (true ou false)")
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

    problemas += _validar_comparacao(dados.get("comparacao"))

    defasagem = dados.get("defasagem_meses")
    if not _inteiro(defasagem) or defasagem < 0:
        problemas.append("campo obrigatorio ausente ou invalido: defasagem_meses (inteiro >= 0)")

    tratamento = dados.get("tratamento_monetario")
    unidade = dados.get("unidade")
    if tratamento is None:
        if isinstance(unidade, str) and unidade.startswith("R$"):
            problemas.append("tratamento_monetario obrigatorio quando a unidade e monetaria (R$)")
    elif not isinstance(tratamento, dict) or tratamento.get("modo") not in MODOS_MONETARIOS:
        problemas.append(f"tratamento_monetario.modo deve ser um de {', '.join(MODOS_MONETARIOS)}")

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
    )
    series = tuple(
        Serie(**{campo: s[campo] for campo in Serie.__dataclass_fields__}) for s in dados["series"]
    )
    campos = {campo: dados[campo] for campo in _TEXTOS_FICHA}
    return Ficha(
        **campos, sentido=dados["sentido"], limites=dict(dados["limites"]),
        comparacao=comparacao, defasagem_meses=dados["defasagem_meses"], series=series,
        tratamento_monetario=dados.get("tratamento_monetario"),
        auxiliar=dados.get("auxiliar", False),
        limiar_salto_pct=float(dados.get("limiar_salto_pct", 50.0)),
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
    return fichas, problemas


def carregar_fichas(diretorio: Path) -> dict[str, Ficha]:
    """Carrega todas as fichas *.yaml do diretorio, indexadas por id.

    Confere tambem se numerador e denominador apontam para fichas existentes.
    """
    fichas, problemas = _examinar(diretorio)
    if problemas:
        raise ErroFicha("; ".join(problemas))
    return fichas


def verificar_fichas(diretorio: Path) -> list[str]:
    """Devolve uma mensagem por problema encontrado nas fichas, sem parar no primeiro."""
    return _examinar(diretorio)[1]
