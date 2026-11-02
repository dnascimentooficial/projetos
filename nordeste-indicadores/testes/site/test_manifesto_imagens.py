"""Manifesto das imagens (`_imagens.json`) e reaproveitamento dos PNG da saida anterior (Ruling S-X).

O Chromium e trocado por um dublê que grava PNG de mentira: estes testes provam a logica do gerador (o que e
renderizado de novo e o que e copiado) sem abrir navegador.
"""

import json
import re
import shutil

import pytest
import yaml

from nordeste.caminhos import Caminhos
from nordeste.cli import main
from nordeste.site import gerar
from nordeste.site.gerar import gerar_site

from auxiliares import copiar_base

MANIFESTO = "_imagens.json"


class Renderizador:
    """Dublê de `renderizar`: cada PNG gravado tem bytes unicos, para provar a copia (bytes iguais) e a regravacao."""

    def __init__(self):
        self.chamadas: list[list[str]] = []  # nomes dos PNG pedidos em cada chamada
        self._n = 0

    def __call__(self, alvos, *, raiz=None):
        self.chamadas.append(sorted(a.png.name for a in alvos))
        for alvo in alvos:
            self._n += 1
            alvo.png.parent.mkdir(parents=True, exist_ok=True)
            alvo.png.write_bytes(f"PNG {self._n} {alvo.largura}x{alvo.altura}".encode())

    @property
    def renderizados(self) -> list[str]:
        return [nome for chamada in self.chamadas for nome in chamada]


@pytest.fixture
def renderizador(monkeypatch):
    r = Renderizador()
    monkeypatch.setattr(gerar, "renderizar", r)
    return r


@pytest.fixture
def base(tmp_path):
    return Caminhos(copiar_base(tmp_path / "repo"))


@pytest.fixture(scope="module")
def inicial(tmp_path_factory):
    """A primeira geracao (com imagens de mentira), feita uma vez; os testes so a leem ou a copiam."""
    raiz = tmp_path_factory.mktemp("inicial")
    caminhos = Caminhos(copiar_base(raiz / "repo"))
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(gerar, "renderizar", Renderizador())
        gerar_site(caminhos, raiz / "antes", imagens=True)
    return caminhos, raiz / "antes"


@pytest.fixture
def antes(inicial, tmp_path):
    """Copia gravavel da saida inicial."""
    shutil.copytree(inicial[1], tmp_path / "antes")
    return tmp_path / "antes"


def _pngs(saida):
    return sorted(p.relative_to(saida).as_posix() for p in saida.rglob("*.png"))


def test_o_manifesto_tem_um_hash_por_imagem_gerada(base, tmp_path, renderizador):
    saida = tmp_path / "saida"
    gerar_site(base, saida, imagens=True)
    manifesto = json.loads((saida / MANIFESTO).read_text(encoding="utf-8"))
    assert sorted(manifesto) == _pngs(saida) and len(manifesto) > 6
    assert all(re.fullmatch(r"[0-9a-f]{64}", h) for h in manifesto.values())
    assert len(set(manifesto.values())) == len(manifesto)  # cada imagem tem a sua entrada
    assert list(manifesto) == sorted(manifesto)  # ordem estavel: o manifesto e comparado byte a byte


def test_sem_imagens_nao_ha_manifesto(base, tmp_path, renderizador):
    saida = tmp_path / "saida"
    gerar_site(base, saida, imagens=False)
    assert not (saida / MANIFESTO).exists() and renderizador.chamadas == []


def test_o_manifesto_e_igual_em_duas_geracoes_da_mesma_base(base, tmp_path, renderizador):
    for nome in ("a", "b"):
        gerar_site(base, tmp_path / nome, imagens=True)
    assert (tmp_path / "a" / MANIFESTO).read_bytes() == (tmp_path / "b" / MANIFESTO).read_bytes()


def test_sem_saida_anterior_renderiza_tudo(base, tmp_path, renderizador):
    saida = tmp_path / "saida"
    gerar_site(base, saida, imagens=True)
    assert sorted(renderizador.renderizados) == sorted(p.rsplit("/", 1)[1] for p in _pngs(saida))


def test_com_a_saida_anterior_igual_nao_regrava_nenhum_png(inicial, tmp_path, renderizador):
    base, antes = inicial
    depois = tmp_path / "depois"
    gerar_site(base, depois, imagens=True, anterior=antes)
    assert renderizador.renderizados == []
    assert _pngs(depois) == _pngs(antes)
    for png in _pngs(antes):
        assert (depois / png).read_bytes() == (antes / png).read_bytes(), png  # copiado, nao refeito
    assert (depois / MANIFESTO).read_bytes() == (antes / MANIFESTO).read_bytes()


def test_so_a_imagem_cuja_entrada_mudou_e_regravada(inicial, tmp_path, renderizador):
    antes = inicial[1]
    depois = tmp_path / "depois"
    base = Caminhos(shutil.copytree(inicial[0].raiz, tmp_path / "repo"))
    arquivo = base.metadados / "site" / "textos.yaml"
    textos = yaml.safe_load(arquivo.read_text(encoding="utf-8"))
    textos["paginas"]["sobre"]["titulo"] = "Revisado " + textos["paginas"]["sobre"]["titulo"]  # texto de og/sobre.png
    arquivo.write_text(yaml.safe_dump(textos, allow_unicode=True), encoding="utf-8")
    gerar_site(base, depois, imagens=True, anterior=antes)
    assert renderizador.renderizados == ["sobre.png"]
    assert (depois / "og" / "sobre.png").read_bytes() != (antes / "og" / "sobre.png").read_bytes()
    assert (depois / "og" / "index.png").read_bytes() == (antes / "og" / "index.png").read_bytes()
    anterior = json.loads((antes / MANIFESTO).read_text(encoding="utf-8"))
    novo = json.loads((depois / MANIFESTO).read_text(encoding="utf-8"))
    assert [k for k in novo if novo[k] != anterior[k]] == ["og/sobre.png"]


def test_estilo_ou_fonte_alterados_regravam_todas_as_imagens(inicial, tmp_path, renderizador, monkeypatch):
    base, antes = inicial
    depois = tmp_path / "depois"
    estaticos = tmp_path / "estaticos"
    shutil.copytree(gerar.PASTA_ESTATICOS, estaticos)
    fonte = next((estaticos / "fontes").rglob("*.woff2"))
    fonte.write_bytes(fonte.read_bytes() + b"\0")
    monkeypatch.setattr(gerar, "PASTA_ESTATICOS", estaticos)
    gerar_site(base, depois, imagens=True, anterior=antes)
    assert len(renderizador.renderizados) == len(_pngs(antes))


def test_png_que_falta_na_saida_anterior_e_regravado(inicial, antes, tmp_path, renderizador):
    base = inicial[0]
    depois = tmp_path / "depois"
    (antes / "og" / "estados.png").unlink()
    gerar_site(base, depois, imagens=True, anterior=antes)
    assert renderizador.renderizados == ["estados.png"]
    assert (depois / "og" / "estados.png").is_file()


def test_saida_anterior_sem_manifesto_renderiza_tudo(inicial, antes, tmp_path, renderizador):
    base = inicial[0]
    depois = tmp_path / "depois"
    (antes / MANIFESTO).unlink()
    gerar_site(base, depois, imagens=True, anterior=antes)
    assert len(renderizador.renderizados) == len(_pngs(depois))


def test_saida_anterior_inexistente_ou_com_manifesto_ilegivel_renderiza_tudo(inicial, tmp_path, renderizador):
    base = inicial[0]
    gerar_site(base, tmp_path / "a", imagens=True, anterior=tmp_path / "nao-existe")
    assert len(renderizador.renderizados) == len(_pngs(tmp_path / "a"))
    renderizador.chamadas.clear()
    (tmp_path / "ruim").mkdir()
    (tmp_path / "ruim" / MANIFESTO).write_text("{ isto nao e json", encoding="utf-8")
    gerar_site(base, tmp_path / "b", imagens=True, anterior=tmp_path / "ruim")
    assert len(renderizador.renderizados) == len(_pngs(tmp_path / "b"))


def test_a_saida_anterior_nao_pode_ser_a_propria_saida(inicial, antes, renderizador):
    base, saida = inicial[0], antes
    for anterior in (saida, saida / "og"):
        with pytest.raises(ValueError, match="anterior"):
            gerar_site(base, saida, imagens=True, anterior=anterior)
    assert (saida / "og" / "index.png").is_file()  # nada foi apagado


def test_anterior_so_vale_com_imagens(inicial, tmp_path, renderizador):
    base, antes = inicial
    gerar_site(base, tmp_path / "depois", imagens=False, anterior=antes)
    assert not (tmp_path / "depois" / MANIFESTO).exists()


def test_cli_site_aceita_anterior(inicial, tmp_path, renderizador):
    base, antes = inicial
    depois = tmp_path / "depois"
    assert main(["--raiz", str(base.raiz), "site", "--saida", str(depois), "--anterior", str(antes)]) == 0
    assert renderizador.renderizados == []
    assert (depois / "og" / "index.png").read_bytes() == (antes / "og" / "index.png").read_bytes()


def test_cli_site_anterior_igual_a_saida_e_erro_sem_traceback(inicial, antes, renderizador, capsys):
    saida = antes
    assert main(["--raiz", str(inicial[0].raiz), "site", "--saida", str(saida), "--anterior", str(saida)]) == 1
    assert "anterior" in capsys.readouterr().err
