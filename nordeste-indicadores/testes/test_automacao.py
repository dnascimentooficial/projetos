"""Automacao: coleta por agenda, brutos na release, avisos e verificacao da publicacao. Nenhum teste usa a rede:
servidores sao locais (127.0.0.1) e o `gh` e um executavel falso no PATH que registra os argumentos."""

import json
import stat
import sys
import threading
from dataclasses import replace
from datetime import date
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath

import pandas as pd
import pytest

from nordeste import automacao
from nordeste.automacao import (
    INDICADORES_INEP_PESADOS, ErroAutomacao, anos_novos, baixar_brutos, brutos_necessarios, caminho_do_anexo,
    coleta_do_inep, conferir_publicado, enviar_brutos, links_quebrados, nome_do_anexo, resumo_de_mudancas,
    site_mudou,
)
from nordeste.caminhos import Caminhos
from nordeste.cli import main
from nordeste.coletores.registro import Coleta, ler_registro, registrar
from nordeste.fichas import carregar_fichas

HOJE = ["--hoje", "2026-11-01"]


# --- servidor local ---


class _Servidor:
    """Servidor HTTP local de respostas combinadas: caminho -> (status, corpo); conta os pedidos por caminho."""

    def __init__(self, respostas: dict[str, list[tuple[int, str]]]):
        self.respostas = respostas
        self.pedidos: list[tuple[str, str]] = []  # (metodo, caminho)
        self.agentes: list[str | None] = []  # User-Agent de cada pedido
        servidor = self

        class Tratador(BaseHTTPRequestHandler):
            def _responder(self):
                servidor.pedidos.append((self.command, self.path))
                servidor.agentes.append(self.headers.get("User-Agent"))
                fila = servidor.respostas.get(self.path)
                if not fila:
                    status, corpo = 404, "nao existe"
                else:
                    status, corpo = fila.pop(0) if len(fila) > 1 else fila[0]
                dados = corpo.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(dados)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(dados)

            do_GET = do_HEAD = _responder

            def log_message(self, *_args):
                pass

        self._http = ThreadingHTTPServer(("127.0.0.1", 0), Tratador)
        threading.Thread(target=self._http.serve_forever, daemon=True).start()

    def url(self, caminho: str) -> str:
        return f"http://127.0.0.1:{self._http.server_port}{caminho}"

    def fechar(self) -> None:
        self._http.shutdown()
        self._http.server_close()


@pytest.fixture
def servidor():
    criados: list[_Servidor] = []

    def criar(respostas: dict[str, list[tuple[int, str]]]) -> _Servidor:
        criados.append(_Servidor(respostas))
        return criados[-1]

    yield criar
    for s in criados:
        s.fechar()


# --- links das series ---


def test_links_quebrados_com_servidor_local(projeto, servidor):
    s = servidor({"/boa": [(200, "ok")]})  # /ruim nao existe: 404
    fichas = carregar_fichas(projeto.fichas)
    pib, per_capita = fichas["pib_nominal"], fichas["amostra_per_capita"]
    fichas = {
        pib.id: replace(pib, series=tuple(replace(x, url=s.url("/boa")) for x in pib.series)),
        per_capita.id: replace(per_capita, series=tuple(replace(x, url=s.url("/ruim")) for x in per_capita.series)),
    }
    quebrados = links_quebrados(fichas, timeout_s=5)
    assert [(i, u) for i, u, _ in quebrados] == [("amostra_per_capita", s.url("/ruim"))]
    assert "404" in quebrados[0][2]


def test_links_quebrados_pergunta_de_novo_com_get_quando_o_servidor_recusa_head(projeto, servidor):
    class SoGet(BaseHTTPRequestHandler):
        def do_HEAD(self):
            self.send_response(405)
            self.end_headers()

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *_args):
            pass

    http = ThreadingHTTPServer(("127.0.0.1", 0), SoGet)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    try:
        ficha = carregar_fichas(projeto.fichas)["pib_nominal"]
        url = f"http://127.0.0.1:{http.server_port}/x"
        fichas = {ficha.id: replace(ficha, series=tuple(replace(x, url=url) for x in ficha.series))}
        assert links_quebrados(fichas, timeout_s=5) == []
    finally:
        http.shutdown()
        http.server_close()


def test_links_quebrados_lista_servidor_fora_do_ar(projeto):
    ficha = carregar_fichas(projeto.fichas)["pib_nominal"]
    fichas = {ficha.id: replace(ficha, series=tuple(replace(x, url="http://127.0.0.1:9/x") for x in ficha.series))}
    quebrados = links_quebrados(fichas, timeout_s=2)
    assert [i for i, _, _ in quebrados] == ["pib_nominal"] * len(quebrados) and quebrados[0][2]


def test_links_quebrados_consulta_cada_url_uma_vez(projeto, servidor):
    s = servidor({"/boa": [(200, "ok")]})
    fichas = carregar_fichas(projeto.fichas)
    fichas = {i: replace(f, series=tuple(replace(x, url=s.url("/boa")) for x in f.series)) for i, f in fichas.items()}
    assert links_quebrados(fichas, timeout_s=5) == []
    assert len(s.pedidos) == 1


def test_links_quebrados_e_conferir_publicado_se_identificam(projeto, servidor):
    s = servidor({"/boa": [(200, _pagina("x"))]})
    ficha = carregar_fichas(projeto.fichas)["pib_nominal"]
    fichas = {ficha.id: replace(ficha, series=tuple(replace(x, url=s.url("/boa")) for x in ficha.series))}
    links_quebrados(fichas, timeout_s=5)
    conferir_publicado(s.url("/boa"), "x", tentativas=1, espera_s=0)
    assert len(s.agentes) >= 2 and set(s.agentes) == {automacao.USER_AGENT}
    assert "nordeste.dnascimento.com.br" in automacao.USER_AGENT


class _RespostaOk:
    status_code = 200

    def close(self):
        pass


def _capturar_verify(monkeypatch) -> list[dict]:
    """Troca requests.head/get por dublês que registram os argumentos e leem o arquivo de `verify` na hora."""
    vistos: list[dict] = []

    def falso(url, **kwargs):
        verify = kwargs.get("verify")
        conteudo = Path(verify).read_text(encoding="utf-8") if isinstance(verify, str) else None
        vistos.append({"url": url, "verify": verify, "conteudo": conteudo})
        return _RespostaOk()

    monkeypatch.setattr(automacao.requests, "head", falso)
    monkeypatch.setattr(automacao.requests, "get", falso)
    return vistos


def test_links_quebrados_usa_o_bundle_do_coletor_quando_a_serie_declara_ca_extra(projeto, tmp_path, monkeypatch):
    padrao = tmp_path / "padrao.pem"
    padrao.write_text("CERTIFICADOS-PADRAO\n", encoding="utf-8")
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(padrao))
    (projeto.raiz / "metadados" / "certificados").mkdir(exist_ok=True)
    (projeto.raiz / "metadados" / "certificados" / "extra.pem").write_text("CERTIFICADO-EXTRA\n", encoding="utf-8")
    ficha = carregar_fichas(projeto.fichas)["pib_nominal"]
    base = ficha.series[0]
    sem = replace(base, url="https://exemplo.test/sem")
    com = replace(base, url="https://exemplo.test/com", parametros={**base.parametros, "ca_extra": "metadados/certificados/extra.pem"})
    fichas = {ficha.id: replace(ficha, series=(sem, com))}
    vistos = _capturar_verify(monkeypatch)
    assert links_quebrados(fichas, timeout_s=5, raiz=projeto.raiz) == []
    por_url = {v["url"]: v for v in vistos}
    assert por_url["https://exemplo.test/sem"]["verify"] is None  # padrao do requests
    com_bundle = por_url["https://exemplo.test/com"]
    assert com_bundle["conteudo"] == "CERTIFICADOS-PADRAO\nCERTIFICADO-EXTRA\n"  # bundle em uso mais o extra
    assert com_bundle["verify"] is not False


def test_links_quebrados_com_ca_extra_inexistente_lista_o_motivo(projeto, monkeypatch):
    ficha = carregar_fichas(projeto.fichas)["pib_nominal"]
    serie = replace(ficha.series[0], url="https://exemplo.test/x", parametros={"ca_extra": "metadados/nao-existe.pem"})
    vistos = _capturar_verify(monkeypatch)
    quebrados = links_quebrados({ficha.id: replace(ficha, series=(serie,))}, timeout_s=5, raiz=projeto.raiz)
    assert [(i, u) for i, u, _ in quebrados] == [("pib_nominal", "https://exemplo.test/x")]
    assert "nao-existe.pem" in quebrados[0][2] and vistos == []  # sem o certificado, nem tenta (e nao desliga o TLS)


# --- agenda do INEP ---


def test_coleta_do_inep_so_na_primeira_semana():
    assert [coleta_do_inep(date(2026, 11, d)) for d in (1, 7, 8, 30)] == [True, True, False, False]
    assert INDICADORES_INEP_PESADOS == ("matriculas_basica", "superior")


# --- anexos da release ---


def test_nome_do_anexo_ida_e_volta():
    relativo = PurePosixPath("matriculas_basica/educacenso/b08dea69.zip")
    assert nome_do_anexo(relativo) == "matriculas_basica__educacenso__b08dea69.zip"
    assert caminho_do_anexo("matriculas_basica__educacenso__b08dea69.zip") == relativo
    assert caminho_do_anexo(nome_do_anexo(PurePosixPath("ideb/ideb/037ed475.zip"))) == PurePosixPath("ideb/ideb/037ed475.zip")


@pytest.mark.parametrize("ruim", ["a__b/s/h.zip", "a/s/h.zip/extra.zip", "so_um.zip"])
def test_nome_do_anexo_recusa_o_que_nao_volta(ruim):
    with pytest.raises(ValueError):
        nome_do_anexo(PurePosixPath(ruim))


@pytest.mark.parametrize("ruim", ["a__s.zip", "a__s__b__c.zip", "a____h.zip"])
def test_caminho_do_anexo_recusa_nome_fora_do_padrao(ruim):
    with pytest.raises(ValueError):
        caminho_do_anexo(ruim)


def _coleta(indicador: str, serie: str, sha: str, origem: str, data: str = "2026-11-01", extensao: str = "zip") -> Coleta:
    return Coleta(
        coleta_id=f"{indicador}.{serie}.{data}.{sha[:8]}", indicador_id=indicador, serie_id=serie, url="http://x",
        data_coleta=data, sha256=sha * 8, origem=origem, arquivo=f"dados/brutos/{indicador}/{serie}/{sha[:8]}.{extensao}",
    )


def test_brutos_necessarios_pega_a_ultima_coleta_de_rede(tmp_path):
    caminhos = Caminhos(tmp_path)
    for coleta in (
        _coleta("a", "s1", "11111111", "rede", "2026-10-01"),
        _coleta("a", "s1", "22222222", "rede", "2026-10-08"),  # a ultima de rede de a/s1
        _coleta("a", "s1", "33333333", "fixture", "2026-10-15"),  # fixture depois: nao vale
        _coleta("a", "s2", "44444444", "fixture"),  # so fixture: nao ha o que baixar
        _coleta("b", "s1", "55555555", "rede", extensao="json"),
        _coleta("b", "s1", "55555555", "rede", extensao="json"),  # repetida: o registro nao a grava de novo
    ):
        registrar(caminhos.registro_coletas, coleta)
    assert brutos_necessarios(caminhos) == [PurePosixPath("a/s1/22222222.zip"), PurePosixPath("b/s1/55555555.json")]


def test_brutos_necessarios_sem_registro_e_vazio(tmp_path):
    assert brutos_necessarios(Caminhos(tmp_path)) == []


# --- gh falso ---

GH_FALSO = """#!{python}
import json, os, shutil, sys
from pathlib import Path

args = sys.argv[1:]
with open(os.environ["GH_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(args) + "\\n")
estado = Path(os.environ["GH_ESTADO"])
if args[:2] == ["release", "view"]:
    if not (estado / "existe").exists():
        print("release not found", file=sys.stderr)
        sys.exit(1)
    anexos = sorted(p.name for p in (estado / "anexos").iterdir())
    print(json.dumps({{"assets": [{{"name": n}} for n in anexos]}}))
elif args[:2] == ["release", "create"]:
    (estado / "existe").write_text("1")
elif args[:2] == ["release", "download"]:
    destino = Path(args[args.index("--dir") + 1])
    padroes = [args[i + 1] for i, a in enumerate(args) if a == "--pattern"]
    for nome in padroes:
        origem = estado / "anexos" / nome
        if not origem.exists():
            print("no assets match the file pattern " + nome, file=sys.stderr)
            sys.exit(1)
        shutil.copy(origem, destino / nome)
elif args[:2] == ["release", "upload"]:
    resto = args[3:]
    while resto:
        if resto[0] == "--repo":
            resto = resto[2:]
        elif resto[0] == "--clobber":
            resto = resto[1:]
        else:
            shutil.copy(resto[0], estado / "anexos" / Path(resto[0]).name)
            resto = resto[1:]
else:
    sys.exit(2)
"""


class GhFalso:
    def __init__(self, raiz: Path, monkeypatch):
        self.estado = raiz / "gh-estado"
        (self.estado / "anexos").mkdir(parents=True)
        bin_ = raiz / "gh-bin"
        bin_.mkdir()
        gh = bin_ / "gh"
        gh.write_text(GH_FALSO.format(python=sys.executable), encoding="utf-8")
        gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
        self.log = raiz / "gh.log"
        monkeypatch.setenv("PATH", f"{bin_}:{__import__('os').environ['PATH']}")
        monkeypatch.setenv("GH_LOG", str(self.log))
        monkeypatch.setenv("GH_ESTADO", str(self.estado))

    def release_existe(self) -> None:
        (self.estado / "existe").write_text("1")

    def anexar(self, nome: str, conteudo: bytes) -> None:
        (self.estado / "anexos" / nome).write_bytes(conteudo)

    @property
    def chamadas(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        return [json.loads(linha) for linha in self.log.read_text(encoding="utf-8").splitlines()]

    def anexos(self) -> dict[str, bytes]:
        return {p.name: p.read_bytes() for p in (self.estado / "anexos").iterdir()}


@pytest.fixture
def gh(tmp_path, monkeypatch):
    return GhFalso(tmp_path / "falso", monkeypatch)


def _projeto_com_brutos(raiz: Path, arquivos: dict[str, bytes], **extras) -> Caminhos:
    """Raiz com registro de coletas de rede e, para cada caminho relativo a dados/brutos, o arquivo bruto."""
    caminhos = Caminhos(raiz)
    for relativo, conteudo in arquivos.items():
        indicador, serie, arquivo = relativo.split("/")
        sha = arquivo.split(".")[0]
        registrar(caminhos.registro_coletas, _coleta(indicador, serie, sha, "rede", extensao=arquivo.split(".")[1]))
        if conteudo is not None:
            destino = caminhos.brutos / relativo
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(conteudo)
    return caminhos


def test_enviar_brutos_cria_a_release_e_sobe_os_anexos_com_nome_plano(tmp_path, gh):
    caminhos = _projeto_com_brutos(tmp_path / "raiz", {"a/s1/aaaaaaaa.zip": b"um", "b/s2/bbbbbbbb.json": b"dois"})
    enviar_brutos("dono/repo", caminhos)
    verbos = [c[:2] for c in gh.chamadas]
    assert verbos == [["release", "view"], ["release", "create"], ["release", "upload"]]
    visao, criar, subir = gh.chamadas
    assert visao[2:5] == ["brutos", "--repo", "dono/repo"]
    assert criar[2] == "brutos" and criar[criar.index("--repo") + 1] == "dono/repo"
    assert subir[2] == "brutos" and subir[subir.index("--repo") + 1] == "dono/repo" and "--clobber" in subir
    assert gh.anexos() == {"a__s1__aaaaaaaa.zip": b"um", "b__s2__bbbbbbbb.json": b"dois"}


def test_enviar_brutos_so_sobe_o_que_a_release_ainda_nao_tem(tmp_path, gh):
    gh.release_existe()
    gh.anexar("a__s1__aaaaaaaa.zip", b"um")
    caminhos = _projeto_com_brutos(tmp_path / "raiz", {"a/s1/aaaaaaaa.zip": b"um", "b/s2/bbbbbbbb.json": b"dois"})
    enviar_brutos("dono/repo", caminhos)
    assert [c[:2] for c in gh.chamadas] == [["release", "view"], ["release", "upload"]]  # release existia: nao cria
    subidos = [Path(a).name for a in gh.chamadas[1] if a.endswith(".json") or a.endswith(".zip")]
    assert subidos == ["b__s2__bbbbbbbb.json"]


def test_enviar_brutos_sem_novidade_nao_chama_o_upload(tmp_path, gh):
    gh.release_existe()
    gh.anexar("a__s1__aaaaaaaa.zip", b"um")
    caminhos = _projeto_com_brutos(tmp_path / "raiz", {"a/s1/aaaaaaaa.zip": b"um"})
    enviar_brutos("dono/repo", caminhos)
    assert [c[:2] for c in gh.chamadas] == [["release", "view"]]


def test_enviar_brutos_ignora_o_que_o_registro_nao_pede(tmp_path, gh):
    gh.release_existe()
    caminhos = _projeto_com_brutos(tmp_path / "raiz", {"a/s1/aaaaaaaa.zip": b"um"})
    velho = caminhos.brutos / "a" / "s1" / "00000000.zip"  # coleta antiga: nao e a ultima de rede
    velho.write_bytes(b"velho")
    enviar_brutos("dono/repo", caminhos)
    assert set(gh.anexos()) == {"a__s1__aaaaaaaa.zip"}


def test_baixar_brutos_baixa_so_o_que_falta_e_poe_no_lugar(tmp_path, gh):
    gh.release_existe()
    gh.anexar("a__s1__aaaaaaaa.zip", b"um")
    gh.anexar("b__s2__bbbbbbbb.json", b"dois")
    caminhos = _projeto_com_brutos(tmp_path / "raiz", {"a/s1/aaaaaaaa.zip": b"um", "b/s2/bbbbbbbb.json": None})
    baixar_brutos("dono/repo", caminhos)
    (visao, baixar) = gh.chamadas
    assert visao[:2] == ["release", "view"]
    assert baixar[:3] == ["release", "download", "brutos"] and baixar[baixar.index("--repo") + 1] == "dono/repo"
    assert "--clobber" in baixar
    padroes = [baixar[i + 1] for i, a in enumerate(baixar) if a == "--pattern"]
    assert padroes == ["b__s2__bbbbbbbb.json"]  # o primeiro ja estava no disco
    assert (caminhos.brutos / "b" / "s2" / "bbbbbbbb.json").read_bytes() == b"dois"
    assert (caminhos.brutos / "a" / "s1" / "aaaaaaaa.zip").read_bytes() == b"um"


def test_baixar_brutos_sem_o_que_falta_nao_chama_o_gh(tmp_path, gh):
    caminhos = _projeto_com_brutos(tmp_path / "raiz", {"a/s1/aaaaaaaa.zip": b"um"})
    baixar_brutos("dono/repo", caminhos)
    assert gh.chamadas == []


def test_baixar_brutos_cria_a_release_se_faltar_e_avisa_do_anexo_ausente(tmp_path, gh):
    caminhos = _projeto_com_brutos(tmp_path / "raiz", {"a/s1/aaaaaaaa.zip": None})
    with pytest.raises(ErroAutomacao, match="a__s1__aaaaaaaa.zip"):
        baixar_brutos("dono/repo", caminhos)
    assert [c[:2] for c in gh.chamadas][:2] == [["release", "view"], ["release", "create"]]


def test_gh_que_falha_vira_erro_de_automacao_com_a_mensagem(tmp_path, monkeypatch):
    vazio = tmp_path / "vazio"
    vazio.mkdir()
    monkeypatch.setenv("PATH", str(vazio))  # sem gh no PATH
    caminhos = _projeto_com_brutos(tmp_path / "raiz", {"a/s1/aaaaaaaa.zip": b"um"})
    with pytest.raises(ErroAutomacao, match="gh"):
        enviar_brutos("dono/repo", caminhos)


# --- resumo das mudancas ---


def _mudancas(linhas: list[dict]) -> pd.DataFrame:
    base = {"subindicador": "", "etapa": "", "rede": "", "serie_id": "pnad", "valor_anterior": "", "valor_novo": "",
            "tipo": "alterado"}
    return pd.DataFrame([{**base, **linha} for linha in linhas]).astype(str)


def test_resumo_ordena_pelas_maiores_variacoes():
    mudancas = _mudancas([
        {"indicador_id": "pobreza", "territorio_id": "NE", "ano": 2024, "valor_anterior": "40.0", "valor_novo": "42.0"},
        {"indicador_id": "gini", "territorio_id": "BR", "ano": 2023, "valor_anterior": "0.50", "valor_novo": "0.10"},
        {"indicador_id": "renda", "territorio_id": "NE", "ano": 2022, "valor_anterior": "1000", "valor_novo": "1500"},
        {"indicador_id": "ideb", "territorio_id": "PE", "ano": 2021, "valor_anterior": "1", "valor_novo": "9"},  # estado
        {"indicador_id": "pib", "territorio_id": "NE", "ano": 2025, "valor_novo": "10", "tipo": "novo"},
    ])
    resumo = resumo_de_mudancas(mudancas)
    linhas = [l for l in resumo.splitlines() if l.startswith("| ") and "---" not in l][1:]  # sem o cabecalho
    assert [l.split("|")[1].strip() for l in linhas] == ["gini", "renda", "pobreza"]
    assert "ideb" not in resumo and "| pib " not in resumo  # estado fora; "novo" nao tem antes nem variacao
    assert linhas[0].split("|")[2:7] == [" Brasil ", " 2023 ", " 0,50 ", " 0,10 ", " -80,0% "]
    assert "+50,0%" in linhas[1] and "1.000" in linhas[1] and "1.500" in linhas[1]
    assert "+5,0%" in linhas[2]
    assert resumo.splitlines()[0].startswith("| Indicador | Território | Ano | Antes | Depois | Variação |")


def test_resumo_respeita_o_limite_e_diz_quantas_ficaram_de_fora():
    linhas = [
        {"indicador_id": f"i{n}", "territorio_id": "NE", "ano": 2020, "valor_anterior": "100", "valor_novo": str(100 + n)}
        for n in range(1, 6)
    ]
    resumo = resumo_de_mudancas(_mudancas(linhas), limite=2)
    assert "i5" in resumo and "i4" in resumo and "i3" not in resumo
    assert "mais 3" in resumo


def test_resumo_identifica_a_dimensao_do_indicador():
    mudancas = _mudancas([{
        "indicador_id": "matriculas_basica", "subindicador": "anos_iniciais", "etapa": "fundamental", "rede": "publica",
        "territorio_id": "NE", "ano": 2024, "valor_anterior": "100", "valor_novo": "110",
    }])
    assert "matriculas_basica (anos_iniciais, fundamental, publica)" in resumo_de_mudancas(mudancas)


def test_resumo_sem_mudancas_de_valor_diz_isso():
    vazio = resumo_de_mudancas(_mudancas([
        {"indicador_id": "pib", "territorio_id": "NE", "ano": 2025, "valor_novo": "10", "tipo": "novo"},
    ]))
    assert "Nenhum valor" in vazio and "|" not in vazio
    assert "Nenhum valor" in resumo_de_mudancas(pd.DataFrame(columns=_mudancas([{"indicador_id": "x", "territorio_id": "NE",
                                                                                 "ano": 1}]).columns))


def test_resumo_com_antes_zero_nao_divide_por_zero():
    resumo = resumo_de_mudancas(_mudancas([
        {"indicador_id": "zero", "territorio_id": "NE", "ano": 2020, "valor_anterior": "0", "valor_novo": "5"},
        {"indicador_id": "um", "territorio_id": "NE", "ano": 2020, "valor_anterior": "10", "valor_novo": "11"},
    ]))
    assert "zero" in resumo and "um" in resumo and "inf" not in resumo.lower() and "nan" not in resumo.lower()


# --- anos novos ---


def test_anos_novos():
    mudancas = _mudancas([
        {"indicador_id": "pib", "territorio_id": "NE", "ano": 2025, "valor_novo": "10", "tipo": "novo"},
        {"indicador_id": "pib", "territorio_id": "BA", "ano": 2025, "valor_novo": "10", "tipo": "novo"},  # mesmo ano: uma vez
        {"indicador_id": "pib", "territorio_id": "NE", "ano": 2022, "valor_anterior": "9", "valor_novo": "8"},  # revisao
        {"indicador_id": "pib", "territorio_id": "AL", "ano": 2010, "valor_novo": "1", "tipo": "novo"},  # preenche buraco
        {"indicador_id": "gini", "territorio_id": "NE", "ano": 2024, "valor_novo": "0.5", "tipo": "novo"},
        {"indicador_id": "gini", "territorio_id": "NE", "ano": 2023, "valor_anterior": "0.6", "valor_novo": "0.5"},
        {"indicador_id": "ideb", "territorio_id": "NE", "ano": 2020, "valor_anterior": "5", "valor_novo": "", "tipo": "removido"},
        {"indicador_id": "ideb", "territorio_id": "NE", "ano": 2019, "valor_novo": "", "tipo": "novo"},  # novo sem valor: nada
    ])
    # sem a base anterior, o ultimo ano publicado vem das linhas que ja existiam (alterado/removido)
    assert anos_novos(mudancas) == [("gini", 2024), ("pib", 2025)]


def test_anos_novos_com_a_base_publicada_antes():
    mudancas = _mudancas([
        {"indicador_id": "pib", "territorio_id": "NE", "ano": 2025, "valor_novo": "10", "tipo": "novo"},
        {"indicador_id": "pib", "territorio_id": "AL", "ano": 2010, "valor_novo": "1", "tipo": "novo"},
        {"indicador_id": "idhm", "territorio_id": "NE", "ano": 2021, "valor_novo": "0.7", "tipo": "novo"},
    ])
    anterior = pd.DataFrame({"indicador_id": ["pib", "pib", "idhm"], "ano": ["2024", "2023", "2021"], "valor": ["1", "1", "0.7"]})
    assert anos_novos(mudancas, publicada=anterior) == [("pib", 2025)]  # idhm 2021 nao passa do ultimo publicado (2021)


def test_anos_novos_vazio():
    assert anos_novos(_mudancas([{"indicador_id": "x", "territorio_id": "NE", "ano": 2020, "valor_anterior": "1",
                                  "valor_novo": "2"}])) == []


# --- conferir o que foi publicado ---

SHA_NOVO = "a" * 64
SHA_ANTIGO = "b" * 64


def _pagina(sha: str) -> str:
    return f'<html><body><footer>sha256 da base: <code class="nn-sha-base">{sha}</code></footer></body></html>'


def test_conferir_publicado_detecta_sha_antigo(servidor):
    s = servidor({"/antigo": [(200, _pagina(SHA_ANTIGO))], "/novo": [(200, _pagina(SHA_NOVO))]})
    assert conferir_publicado(s.url("/antigo"), SHA_NOVO, tentativas=2, espera_s=0) is False
    assert len([p for p in s.pedidos if p[1] == "/antigo"]) == 2  # tentou de novo antes de desistir
    assert conferir_publicado(s.url("/novo"), SHA_NOVO, tentativas=2, espera_s=0) is True


def test_conferir_publicado_espera_o_hpanel_puxar_a_publicacao(servidor):
    s = servidor({"/p": [(200, _pagina(SHA_ANTIGO)), (200, _pagina(SHA_ANTIGO)), (200, _pagina(SHA_NOVO))]})
    assert conferir_publicado(s.url("/p"), SHA_NOVO, tentativas=5, espera_s=0) is True
    assert len(s.pedidos) == 3  # parou na primeira que bateu


def test_conferir_publicado_espera_entre_as_tentativas_e_nao_depois_da_ultima(servidor, monkeypatch):
    esperas: list[float] = []
    monkeypatch.setattr(automacao.time, "sleep", esperas.append)
    s = servidor({"/antigo": [(200, _pagina(SHA_ANTIGO))]})
    assert conferir_publicado(s.url("/antigo"), SHA_NOVO, tentativas=3, espera_s=30) is False
    assert esperas == [30, 30]


def test_conferir_publicado_erro_http_ou_servidor_fora_conta_como_nao_publicado(servidor):
    s = servidor({"/erro": [(500, _pagina(SHA_NOVO))]})
    assert conferir_publicado(s.url("/erro"), SHA_NOVO, tentativas=1, espera_s=0) is False
    assert conferir_publicado("http://127.0.0.1:9/", SHA_NOVO, tentativas=1, espera_s=0) is False


def test_conferir_publicado_exige_o_sha_inteiro(servidor):
    s = servidor({"/p": [(200, _pagina(SHA_NOVO[:40]))]})
    assert conferir_publicado(s.url("/p"), SHA_NOVO, tentativas=1, espera_s=0) is False


# --- site mudou ---


def _site(raiz: Path, arquivos: dict[str, bytes]) -> Path:
    for relativo, conteudo in arquivos.items():
        destino = raiz / relativo
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(conteudo)
    return raiz


BASE_DO_SITE = {"index.html": b"<html>", "estilo.css": b"a{}", "og/index.png": b"PNG-1", "_imagens.json": b'{"og/index.png": "h1"}'}


def test_site_mudou_falso_para_sites_iguais(tmp_path):
    assert site_mudou(_site(tmp_path / "a", BASE_DO_SITE), _site(tmp_path / "b", BASE_DO_SITE)) is False


def test_site_mudou_com_byte_diferente_em_arquivo_que_nao_e_png(tmp_path):
    novo = {**BASE_DO_SITE, "index.html": b"<html>!"}
    assert site_mudou(_site(tmp_path / "a", BASE_DO_SITE), _site(tmp_path / "b", novo)) is True


def test_site_mudou_ignora_bytes_do_png_quando_o_manifesto_e_o_mesmo(tmp_path):
    novo = {**BASE_DO_SITE, "og/index.png": b"PNG-2, outro Chromium"}
    assert site_mudou(_site(tmp_path / "a", BASE_DO_SITE), _site(tmp_path / "b", novo)) is False


def test_site_mudou_com_manifesto_diferente(tmp_path):
    novo = {**BASE_DO_SITE, "_imagens.json": b'{"og/index.png": "h2"}', "og/index.png": b"PNG-2"}
    assert site_mudou(_site(tmp_path / "a", BASE_DO_SITE), _site(tmp_path / "b", novo)) is True


def test_site_mudou_quando_aparece_ou_some_arquivo(tmp_path):
    a = _site(tmp_path / "a", BASE_DO_SITE)
    assert site_mudou(a, _site(tmp_path / "b", {**BASE_DO_SITE, "novo.html": b"x"})) is True
    assert site_mudou(a, _site(tmp_path / "c", {k: v for k, v in BASE_DO_SITE.items() if k != "estilo.css"})) is True
    assert site_mudou(a, _site(tmp_path / "d", {**BASE_DO_SITE, "og/outra.png": b"PNG"})) is True  # PNG a mais
    assert site_mudou(a, _site(tmp_path / "e", {k: v for k, v in BASE_DO_SITE.items() if k != "og/index.png"})) is True


def test_site_mudou_sem_site_anterior(tmp_path):
    assert site_mudou(tmp_path / "nao-existe", _site(tmp_path / "b", BASE_DO_SITE)) is True


# --- CLI do pipeline: --pular-indicador ---


def _raiz(projeto) -> list[str]:
    return ["--raiz", str(projeto.raiz), *HOJE]


def test_cli_pula_indicador(projeto):
    assert main(_raiz(projeto) + ["coletar", "--offline", "--pular-indicador", "pib_nominal"]) == 0
    coletados = set(ler_registro(projeto.registro_coletas).indicador_id)
    assert "pib_nominal" not in coletados and {"amostra_per_capita", "amostra_populacao"} <= coletados


def test_cli_pula_mais_de_um_indicador(projeto):
    args = ["coletar", "--offline", "--pular-indicador", "pib_nominal", "--pular-indicador", "amostra_populacao"]
    assert main(_raiz(projeto) + args) == 0
    assert set(ler_registro(projeto.registro_coletas).indicador_id) == {"amostra_per_capita"}


def test_cli_pular_indicador_desconhecido_sai_com_1_sem_coletar(projeto, capsys):
    assert main(_raiz(projeto) + ["coletar", "--offline", "--pular-indicador", "nao_existe"]) == 1
    err = capsys.readouterr().err
    assert "nao_existe" in err and "Traceback" not in err
    assert not projeto.registro_coletas.exists()


def test_cli_sem_pular_continua_coletando_tudo(projeto):
    assert main(_raiz(projeto) + ["coletar", "--offline"]) == 0
    assert "pib_nominal" in set(ler_registro(projeto.registro_coletas).indicador_id)


# --- CLI auxiliar ---


def test_cli_auxiliar_resumo_e_anos_novos(tmp_path, capsys):
    arquivo = tmp_path / "mudancas.csv"
    _mudancas([
        {"indicador_id": "pobreza", "territorio_id": "NE", "ano": 2024, "valor_anterior": "40", "valor_novo": "42"},
        {"indicador_id": "pib", "territorio_id": "NE", "ano": 2025, "valor_novo": "10", "tipo": "novo"},
    ]).to_csv(arquivo, index=False)
    assert automacao.main(["resumo", "--mudancas", str(arquivo)]) == 0
    assert "| pobreza |" in capsys.readouterr().out
    assert automacao.main(["anos-novos", "--mudancas", str(arquivo)]) == 0
    assert capsys.readouterr().out.split() == ["pib:2025"]


def test_cli_auxiliar_conferir_devolve_o_codigo_de_saida(servidor, capsys):
    s = servidor({"/p": [(200, _pagina(SHA_NOVO))]})
    base = ["conferir", "--url", s.url("/p"), "--tentativas", "1", "--espera", "0"]
    assert automacao.main([*base, "--sha256", SHA_NOVO]) == 0
    assert automacao.main([*base, "--sha256", SHA_ANTIGO]) == 1


def test_cli_auxiliar_links_lista_e_sai_com_1_se_ha_quebrado(projeto, servidor, capsys):
    s = servidor({"/boa": [(200, "ok")]})
    for ficha in projeto.fichas.glob("*.yaml"):
        texto = ficha.read_text(encoding="utf-8")
        ficha.write_text(
            "\n".join(f"    url: {s.url('/boa')}" if linha.startswith("    url:") else linha for linha in texto.splitlines()) + "\n",
            encoding="utf-8",
        )
    assert automacao.main(["links", "--raiz", str(projeto.raiz), "--timeout", "5"]) == 0
    assert capsys.readouterr().out == ""
    ficha = next(projeto.fichas.glob("pib_nominal.yaml"))
    ficha.write_text(ficha.read_text(encoding="utf-8").replace("/boa", "/ruim"), encoding="utf-8")
    assert automacao.main(["links", "--raiz", str(projeto.raiz), "--timeout", "5"]) == 1
    assert "pib_nominal" in capsys.readouterr().out


def test_cli_auxiliar_site_mudou(tmp_path, capsys):
    a = _site(tmp_path / "a", BASE_DO_SITE)
    igual = _site(tmp_path / "igual", {**BASE_DO_SITE, "og/index.png": b"outro Chromium"})
    outro = _site(tmp_path / "outro", {**BASE_DO_SITE, "index.html": b"<html>!"})
    assert automacao.main(["site-mudou", "--anterior", str(a), "--novo", str(igual)]) == 1
    assert capsys.readouterr().out == "igual\n"
    assert automacao.main(["site-mudou", "--anterior", str(a), "--novo", str(outro)]) == 0
    assert capsys.readouterr().out == "mudou\n"
    assert automacao.main(["site-mudou", "--anterior", str(tmp_path / "nao-existe"), "--novo", str(a)]) == 0
    assert capsys.readouterr().out == "mudou\n"


def test_cli_auxiliar_site_mudou_com_site_novo_inexistente_e_erro_distinto(tmp_path, capsys):
    a = _site(tmp_path / "a", BASE_DO_SITE)
    assert automacao.main(["site-mudou", "--anterior", str(a), "--novo", str(tmp_path / "nao-existe")]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "não existe" in captured.err


def test_cli_auxiliar_pular_inep(capsys):
    assert automacao.main(["pular-inep", "--hoje", "2026-11-15"]) == 0
    assert capsys.readouterr().out.splitlines() == ["--pular-indicador matriculas_basica", "--pular-indicador superior"]
    for dia in ("2026-11-01", "2026-11-07"):  # primeira semana: coleta tudo, nada a pular
        assert automacao.main(["pular-inep", "--hoje", dia]) == 0
        assert capsys.readouterr().out == ""


def test_cli_auxiliar_pular_inep_sem_hoje_usa_a_data_de_hoje(capsys, monkeypatch):
    class Hoje(date):
        @classmethod
        def today(cls):
            return cls(2026, 11, 20)

    monkeypatch.setattr(automacao, "date", Hoje)
    assert automacao.main(["pular-inep"]) == 0
    assert len(capsys.readouterr().out.splitlines()) == 2


def test_cli_auxiliar_ajuda_do_anos_novos_avisa_que_sem_base_anterior_e_aproximado(capsys):
    with pytest.raises(SystemExit):
        automacao.main(["anos-novos", "--help"])
    assert "aproximado" in capsys.readouterr().out
