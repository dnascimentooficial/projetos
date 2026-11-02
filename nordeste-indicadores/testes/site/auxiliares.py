"""Apoio dos testes do site: leitura do HTML gerado e copia da base publicada para pastas temporarias."""

import shutil
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
VOID = {"meta", "link", "br", "img", "input", "hr", "col", "source", "area", "base", "wbr"}


class Arvore(HTMLParser):
    """Elementos do HTML gerado (tag, atributos, texto) e o texto visivel (sem script e style)."""

    def __init__(self, html: str):
        super().__init__(convert_charrefs=True)
        self.elementos: list[dict] = []
        self.visivel: list[str] = []
        self._pilha: list[dict] = []
        self.feed(html)
        self.close()

    def handle_starttag(self, tag, attrs):
        elemento = {"tag": tag, "attrs": dict(attrs), "texto": []}
        self.elementos.append(elemento)
        if tag not in VOID:
            self._pilha.append(elemento)

    def handle_endtag(self, tag):
        while self._pilha:
            if self._pilha.pop()["tag"] == tag:
                return

    def handle_data(self, data):
        for elemento in self._pilha:
            elemento["texto"].append(data)
        if not any(e["tag"] in ("script", "style") for e in self._pilha):
            self.visivel.append(data)

    def achar(self, tag: str | None = None, classe: str | None = None, **attrs) -> list[dict]:
        achados = []
        for e in self.elementos:
            if tag is not None and e["tag"] != tag:
                continue
            if classe is not None and classe not in e["attrs"].get("class", "").split():
                continue
            if any(e["attrs"].get(k.replace("_", "-")) != v for k, v in attrs.items()):
                continue
            achados.append(e)
        return achados

    @staticmethod
    def texto(elemento: dict) -> str:
        return " ".join("".join(elemento["texto"]).split())

    def texto_visivel(self) -> str:
        return " ".join("".join(self.visivel).split())


def copiar_base(destino: Path) -> Path:
    """Copia o que o site le: metadados e a base publicada (nao a de trabalho, nem os brutos)."""
    shutil.copytree(RAIZ / "metadados", destino / "metadados")
    for pasta, arquivos in (("base", ("base_nordeste.csv", "derivados.csv")), ("relatorios", ("cobertura.csv", "coletas.csv"))):
        (destino / "dados" / pasta).mkdir(parents=True)
        for arquivo in arquivos:
            shutil.copy(RAIZ / "dados" / pasta / arquivo, destino / "dados" / pasta / arquivo)
    return destino


def alterar_base(raiz: Path, alterar) -> None:
    arquivo = raiz / "dados" / "base" / "base_nordeste.csv"
    base = pd.read_csv(arquivo, dtype=str, keep_default_na=False)
    alterar(base).to_csv(arquivo, index=False)
