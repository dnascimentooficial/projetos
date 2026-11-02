"""Workflows do GitHub Actions: estrutura dos YAML e comportamento dos passos em shell.

Os passos sao extraidos do YAML e rodados com `bash -eo pipefail`, como o Actions roda `shell: bash`. Nada usa a rede:
o `gh` e um executavel falso que registra as chamadas, o `python` falso responde com o codigo pedido por comando e a
publicacao do site roda num repositorio git local com um remoto `--bare`.
"""

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parents[1]
WORKFLOWS = RAIZ / ".github" / "workflows"
ABRIR_ISSUE = RAIZ / ".github" / "scripts" / "abrir-issue.sh"
NOMES = ("testes.yml", "atualizar.yml", "links.yml")
ACOES_PERMITIDAS = ("actions/checkout", "actions/setup-python")


def _carregar(nome: str) -> dict:
    return yaml.safe_load((WORKFLOWS / nome).read_text(encoding="utf-8"))


def _gatilhos(workflow: dict) -> dict:
    return workflow[True]  # o PyYAML le a chave `on:` como o booleano True


def _passos(workflow: dict) -> list[dict]:
    (job,) = workflow["jobs"].values()
    return job["steps"]


def _passo(nome_do_arquivo: str, id_: str) -> str:
    (passo,) = [p for p in _passos(_carregar(nome_do_arquivo)) if p.get("id") == id_]
    return passo["run"]


# --- estrutura ---

def test_workflows_tem_actions_fixadas_por_sha():
    usos = []
    for nome in NOMES:
        texto = (WORKFLOWS / nome).read_text(encoding="utf-8")
        _carregar(nome)  # YAML valido
        usos += [linha.strip() for linha in texto.splitlines() if re.match(r"\s*(-\s+)?uses:", linha)]
    assert usos
    for linha in usos:
        assert re.fullmatch(r"(- )?uses: ([\w./-]+)@[0-9a-f]{40} +# v\d+\.\d+\.\d+", linha), linha
        assert re.search(r"uses: ([\w./-]+)@", linha).group(1) in ACOES_PERMITIDAS, linha


def test_atualizar_tem_agenda_concorrencia_e_permissoes_minimas():
    workflow = _carregar("atualizar.yml")
    gatilhos = _gatilhos(workflow)
    assert gatilhos["schedule"] == [{"cron": "0 6 * * 1"}]
    assert "workflow_dispatch" in gatilhos
    assert workflow["concurrency"] == "atualizar"
    assert workflow["permissions"] == {"contents": "write", "issues": "write"}
    (job,) = workflow["jobs"].values()
    assert job["timeout-minutes"] == 340
    assert "permissions" not in job
    assert gatilhos["workflow_dispatch"]["inputs"]["coleta_completa"] == {
        "description": "Coletar tudo, inclusive o INEP fora da primeira semana do mês", "type": "boolean", "default": False,
    }
    (checkout,) = [p for p in job["steps"] if p.get("uses", "").startswith("actions/checkout@")]
    assert checkout["with"]["ref"] == "main"


def test_atualizar_chama_os_comandos_na_ordem():
    roteiro = "\n".join(p.get("run", "") for p in _passos(_carregar("atualizar.yml")))
    esperados = [
        r'pip install -e "\.\[site\]"',
        r"python -m playwright install --with-deps chromium",
        r"python -m nordeste\.automacao baixar-brutos",
        r"python -m nordeste\.automacao pular-inep",
        r"python -m nordeste coletar",
        r"python -m nordeste\.automacao enviar-brutos",  # logo depois da coleta (Ruling S-AD)
        r"python -m nordeste consolidar",
        r"python -m nordeste publicar --ensaio",
        r"cp dados/base/base_nordeste\.csv",
        r"python -m nordeste publicar\n",
        r"git status --porcelain dados/",
        r"git pull -q --rebase origin main",
        r"git push origin HEAD:main",
        r"python -m nordeste site --saida _site --relatorio site\.json --anterior _anterior",
        r"fechos_suprimidos",
        r"cards_suprimidos",
        r"python -m nordeste\.automacao anos-novos",
        r"python -m nordeste\.automacao resumo",
        r"python -m nordeste\.automacao site-mudou --anterior _anterior --novo _site",
        r"git -C _publicar push (-q )?origin site-publicado",
        r"python -m nordeste\.automacao conferir",
    ]
    posicao = 0
    for padrao in esperados:
        achado = re.compile(padrao).search(roteiro, posicao)
        assert achado, f"{padrao!r} ausente ou fora de ordem"
        posicao = achado.end()


def test_nenhum_run_interpola_expressao_do_actions():
    """Texto vindo de `${{ }}` nunca entra no shell: o que o passo precisa chega por variavel de ambiente."""
    for nome in NOMES:
        for passo in _passos(_carregar(nome)):
            assert "${{" not in passo.get("run", ""), (nome, passo.get("name"))


def test_testes_roda_a_suite_e_o_navegador():
    workflow = _carregar("testes.yml")
    assert set(_gatilhos(workflow)) == {"push", "pull_request"}
    assert workflow["permissions"] == {"contents": "read"}
    passos = _passos(workflow)
    (python,) = [p for p in passos if p.get("uses", "").startswith("actions/setup-python@")]
    assert python["with"]["python-version"] == "3.12"
    roteiro = "\n".join(p.get("run", "") for p in passos)
    for comando in ('pip install -e ".[dev,site,ferramentas]"', "python -m playwright install --with-deps chromium",
                    "python -m pytest -W error", "python -m pytest -m navegador -W error"):
        assert comando in roteiro


def test_links_e_mensal_e_so_avisa():
    workflow = _carregar("links.yml")
    gatilhos = _gatilhos(workflow)
    assert gatilhos["schedule"] == [{"cron": "0 9 1 * *"}]
    assert "workflow_dispatch" in gatilhos
    assert workflow["permissions"] == {"contents": "read", "issues": "write"}


# --- passos em shell ---

@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    """Pasta de trabalho com `gh` e `python` falsos no PATH; devolve (pasta, log do gh, configuracao do python)."""
    trabalho, bin_ = tmp_path / "repo", tmp_path / "bin"
    trabalho.mkdir()
    bin_.mkdir()
    (trabalho / ".github" / "scripts").mkdir(parents=True)
    (trabalho / ".github" / "scripts" / "abrir-issue.sh").symlink_to(ABRIR_ISSUE)
    log_gh, issues, config_py = tmp_path / "gh.log", tmp_path / "issues.json", tmp_path / "python.json"
    issues.write_text("[]")
    config_py.write_text("{}")
    _executavel(bin_ / "gh", f"""#!{sys.executable}
import json, sys
with open({str(log_gh)!r}, "a") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
if sys.argv[1:3] == ["issue", "list"]:
    print(open({str(issues)!r}).read())
""")
    _executavel(bin_ / "python", f"""#!{sys.executable}
import json, os, pathlib, sys
argv = sys.argv[1:]
if argv[:1] != ["-m"]:  # python - <<'PY' e afins: o interpretador de verdade
    os.execv(sys.executable, [sys.executable, *argv])
comando = next(a for a in argv[2:] if not a.startswith("-"))
with open({str(tmp_path / "python.log")!r}, "a") as log:
    log.write(json.dumps(argv) + "\\n")
resposta = json.load(open({str(config_py)!r})).get(comando, {{}})
for arquivo, conteudo in resposta.get("cria", {{}}).items():
    pathlib.Path(arquivo).write_text(conteudo)
print(resposta.get("saida", ""), end="")
sys.exit(resposta.get("codigo", 0))
""")
    _executavel(bin_ / "python3", f"#!/bin/sh\nexec {sys.executable} \"$@\"\n")
    monkeypatch.setenv("PATH", f"{bin_}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    return trabalho, log_gh, issues, config_py


def _executavel(caminho: Path, texto: str) -> None:
    caminho.write_text(texto)
    caminho.chmod(caminho.stat().st_mode | stat.S_IXUSR)


def _rodar(roteiro: str, pasta: Path, **env: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", roteiro], cwd=pasta,
                          env={**os.environ, **env}, capture_output=True, text=True, check=False)


def _chamadas(log: Path) -> list[list[str]]:
    return [json.loads(linha) for linha in log.read_text().splitlines()] if log.exists() else []


def _issues_abertas(log: Path) -> list[tuple[str, str]]:
    """(titulo, corpo) de cada `gh issue create`."""
    chamadas = [c for c in _chamadas(log) if c[:2] == ["issue", "create"]]
    return [(c[c.index("--title") + 1], Path(c[c.index("--body-file") + 1]).read_text()) for c in chamadas]


def test_abrir_issue_comenta_na_aberta_de_mesmo_titulo(ambiente, tmp_path):
    pasta, log, issues, _ = ambiente
    corpo = tmp_path / "corpo.md"
    corpo.write_text("texto")
    issues.write_text(json.dumps([{"number": 7, "title": "Site não atualizou (outro)"},
                                  {"number": 9, "title": "Site não atualizou"}]))
    assert _rodar(f'.github/scripts/abrir-issue.sh "Site não atualizou" {corpo}', pasta).returncode == 0
    assert _chamadas(log)[-1] == ["issue", "comment", "9", "--body-file", str(corpo)]

    issues.write_text(json.dumps([{"number": 7, "title": "Site não atualizou (outro)"}]))
    assert _rodar(f'.github/scripts/abrir-issue.sh "Site não atualizou" {corpo}', pasta).returncode == 0
    assert _chamadas(log)[-1] == ["issue", "create", "--title", "Site não atualizou", "--body-file", str(corpo)]


def test_abrir_issue_so_se_nova_nao_comenta_na_aberta(ambiente, tmp_path):
    pasta, log, issues, _ = ambiente
    corpo = tmp_path / "corpo.md"
    corpo.write_text("texto")
    issues.write_text(json.dumps([{"number": 9, "title": "O card seca deixou de valer"}]))
    roteiro = f'.github/scripts/abrir-issue.sh --so-se-nova "O card seca deixou de valer" {corpo}'
    assert _rodar(roteiro, pasta).returncode == 0
    assert [c[:2] for c in _chamadas(log)] == [["issue", "list"]]

    issues.write_text("[]")
    assert _rodar(roteiro, pasta).returncode == 0
    assert _chamadas(log)[-1] == ["issue", "create", "--title", "O card seca deixou de valer", "--body-file", str(corpo)]


@pytest.mark.parametrize(("codigo", "incompletos"), [(0, "nao"), (1, "sim"), (2, None)])
def test_baixar_brutos_incompleto_pede_coleta_completa_e_erro_falha(ambiente, tmp_path, codigo, incompletos):
    pasta, _, _, config = ambiente
    config.write_text(json.dumps({"baixar-brutos": {"codigo": codigo}}))
    env_arquivo = tmp_path / "github_env"
    env_arquivo.write_text("")
    resultado = _rodar(_passo("atualizar.yml", "baixar_brutos"), pasta, GITHUB_ENV=str(env_arquivo), GH_REPO="dono/repo")
    assert resultado.returncode == (0 if incompletos else codigo)
    assert env_arquivo.read_text() == (f"BRUTOS_INCOMPLETOS={incompletos}\n" if incompletos else "")
    (chamada,) = _chamadas(tmp_path / "python.log")
    assert chamada == ["-m", "nordeste.automacao", "baixar-brutos", "--repo", "dono/repo"]


@pytest.mark.parametrize("env", [{"BRUTOS_INCOMPLETOS": "sim"}, {"COLETA_COMPLETA": "true"}])
def test_coletar_tudo_com_brutos_incompletos_ou_coleta_completa(ambiente, env):
    pasta, _, _, config = ambiente
    (pasta / "dados" / "relatorios").mkdir(parents=True)
    config.write_text(json.dumps({"pular-inep": {"saida": "--pular-indicador a\n"}}))
    padrao = {"BRUTOS_INCOMPLETOS": "nao", "COLETA_COMPLETA": "false"}
    resultado = _rodar(_passo("atualizar.yml", "coletar"), pasta, **{**padrao, **env})
    assert resultado.returncode == 0, resultado.stderr
    assert _chamadas(pasta.parent / "python.log") == [["-m", "nordeste", "coletar"]]  # sem pular-inep


@pytest.mark.parametrize(("codigo", "cria_falhas", "passa"), [(0, True, True), (1, True, True), (1, False, False), (2, True, False)])
def test_coletar_segue_com_serie_que_falhou_mas_nao_com_erro(ambiente, codigo, cria_falhas, passa):
    """Saida 1 com falhas_coleta.csv novo e serie fora do ar (as outras seguem); sem o relatorio, e erro da etapa."""
    pasta, _, _, config = ambiente
    (pasta / "dados" / "relatorios").mkdir(parents=True)
    (pasta / "dados" / "relatorios" / "falhas_coleta.csv").write_text("antigo\n")  # o da semana anterior nao vale
    falhas = {str(pasta / "dados" / "relatorios" / "falhas_coleta.csv"): "x\n"} if cria_falhas else {}
    config.write_text(json.dumps({"pular-inep": {"saida": "--pular-indicador a\n--pular-indicador b\n"},
                                  "coletar": {"codigo": codigo, "cria": falhas}}))
    resultado = _rodar(_passo("atualizar.yml", "coletar"), pasta, BRUTOS_INCOMPLETOS="nao", COLETA_COMPLETA="false")
    assert (resultado.returncode == 0) is passa, resultado.stderr
    coletar = [c for c in _chamadas(pasta.parent / "python.log") if "coletar" in c]
    assert coletar == [["-m", "nordeste", "coletar", "--pular-indicador", "a", "--pular-indicador", "b"]]


def test_coletar_falha_se_a_agenda_do_inep_falha(ambiente):
    pasta, _, _, config = ambiente
    config.write_text(json.dumps({"pular-inep": {"codigo": 2}}))
    assert _rodar(_passo("atualizar.yml", "coletar"), pasta).returncode != 0
    assert not [c for c in _chamadas(pasta.parent / "python.log") if "coletar" in c]


@pytest.mark.parametrize(("codigo", "cria_validacao", "issue"), [(0, True, False), (1, True, True), (1, False, False)])
def test_ensaio_reprovado_abre_issue_e_encerra(ambiente, codigo, cria_validacao, issue):
    """Reprovado e saida 1 com um validacao.csv novo; sem ele (o antigo nao vale), e erro da etapa, sem a issue."""
    pasta, log, _, config = ambiente
    validacao = pasta / "dados" / "relatorios" / "validacao.csv"
    validacao.parent.mkdir(parents=True)
    validacao.write_text("nivel,regra,mensagem\naviso,A01,da semana anterior\n")
    novo = {str(validacao): "nivel,regra,mensagem\nerro,V07,valor negativo\n"} if cria_validacao else {}
    config.write_text(json.dumps({"publicar": {"codigo": codigo, "cria": novo}}))
    resultado = _rodar(_passo("atualizar.yml", "ensaio"), pasta)
    assert resultado.returncode == codigo
    abertas = _issues_abertas(log)
    assert [t for t, _ in abertas] == (["Publicação barrada"] if issue else [])
    if issue:
        assert "erro,V07,valor negativo" in abertas[0][1]


def _base(pasta: Path) -> str:
    (pasta / "dados" / "base").mkdir(parents=True, exist_ok=True)
    (pasta / "dados" / "base" / "base_nordeste.csv").write_text("indicador_id\n")
    return hashlib.sha256(b"indicador_id\n").hexdigest()


def test_suprimidos_abrem_uma_issue_por_id_sem_repetir_a_aberta(ambiente):
    pasta, log, issues, _ = ambiente
    sha = _base(pasta)
    (pasta / "site.json").write_text(json.dumps(
        {"paginas": [], "fechos_suprimidos": ["pobreza", "abertura_numeros"], "cards_suprimidos": ["seca"]}))
    issues.write_text(json.dumps([{"number": 3, "title": "O fecho de pobreza deixou de valer"}]))
    resultado = _rodar(_passo("atualizar.yml", "avisar_suprimidos"), pasta)
    assert resultado.returncode == 0, resultado.stderr
    abertas = _issues_abertas(log)
    assert [t for t, _ in abertas] == ["O fecho de abertura_numeros deixou de valer", "O card seca deixou de valer"]
    assert all(sha in corpo for _, corpo in abertas)
    assert not [c for c in _chamadas(log) if c[:2] == ["issue", "comment"]]  # a aberta nao ganha comentario semanal


def test_sem_suprimidos_nenhuma_issue(ambiente):
    pasta, log, _, _ = ambiente
    _base(pasta)
    (pasta / "site.json").write_text(json.dumps({"paginas": [], "fechos_suprimidos": [], "cards_suprimidos": []}))
    assert _rodar(_passo("atualizar.yml", "avisar_suprimidos"), pasta).returncode == 0
    assert _chamadas(log) == []


@pytest.mark.parametrize("com_base_anterior", [True, False])
def test_anos_novos_abrem_issue_com_o_resumo(ambiente, tmp_path, com_base_anterior):
    pasta, log, _, config = ambiente
    if com_base_anterior:
        (tmp_path / "base_anterior.csv").write_text("indicador_id\n")
    config.write_text(json.dumps({"anos-novos": {"saida": "pib_per_capita:2024\n"},
                                  "resumo": {"saida": "| Indicador | Território |\n"}}))
    resultado = _rodar(_passo("atualizar.yml", "avisar_anos_novos"), pasta)
    assert resultado.returncode == 0, resultado.stderr
    ((titulo, corpo),) = _issues_abertas(log)
    assert titulo == "Ano novo na base: releia os textos"
    assert "pib_per_capita:2024" in corpo and "| Indicador | Território |" in corpo
    (chamada,) = [c for c in _chamadas(tmp_path / "python.log") if "anos-novos" in c]
    anterior = ["--base-anterior", str(tmp_path / "base_anterior.csv")] if com_base_anterior else []
    assert chamada == ["-m", "nordeste.automacao", "anos-novos", "--mudancas", "dados/relatorios/mudancas.csv", *anterior]


@pytest.mark.parametrize(("codigo", "saida", "aberta", "issue"),
                         [(0, "", False, False), (0, "pib:2024\n", True, False), (2, "", False, False)])
def test_anos_novos_sem_novidade_aberta_ou_erro_nao_abrem_issue(ambiente, codigo, saida, aberta, issue):
    pasta, log, issues, config = ambiente
    if aberta:
        issues.write_text(json.dumps([{"number": 4, "title": "Ano novo na base: releia os textos"}]))
    config.write_text(json.dumps({"anos-novos": {"codigo": codigo, "saida": saida}}))
    resultado = _rodar(_passo("atualizar.yml", "avisar_anos_novos"), pasta)
    assert resultado.returncode == codigo
    assert _issues_abertas(log) == []
    assert not [c for c in _chamadas(log) if c[:2] == ["issue", "comment"]]


@pytest.mark.parametrize(("codigo", "saida", "issue"), [(0, 0, False), (1, 1, True), (2, 2, False)])
def test_conferir_abre_issue_so_no_nao(ambiente, codigo, saida, issue):
    """Foco 5: o sha256 antigo no rodape (saida 1) abre "Site não atualizou"; erro da etapa (2) nunca vira "nao"."""
    pasta, log, _, config = ambiente
    sha = _base(pasta)
    config.write_text(json.dumps({"conferir": {"codigo": codigo}}))
    resultado = _rodar(_passo("atualizar.yml", "conferir"), pasta, URL_DO_SITE="https://nordeste.dnascimento.com.br/")
    assert resultado.returncode == saida
    assert [t for t, _ in _issues_abertas(log)] == (["Site não atualizou"] if issue else [])
    (chamada,) = [c for c in _chamadas(pasta.parent / "python.log") if "conferir" in c]
    assert chamada[chamada.index("--sha256") + 1] == sha
    assert chamada[chamada.index("--url") + 1] == "https://nordeste.dnascimento.com.br/"


@pytest.mark.parametrize(("codigo", "saida", "issue"), [(0, 0, False), (1, 0, True), (2, 2, False)])
def test_links_quebrados_so_avisam(ambiente, codigo, saida, issue):
    pasta, log, _, config = ambiente
    config.write_text(json.dumps({"links": {"codigo": codigo, "saida": "pib\thttps://x.gov.br\tHTTP 404\n"}}))
    resultado = _rodar(_passo("links.yml", "links"), pasta)
    assert resultado.returncode == saida
    abertas = _issues_abertas(log)
    assert [t for t, _ in abertas] == (["Links quebrados nas fontes"] if issue else [])
    if issue:
        assert "https://x.gov.br" in abertas[0][1]


# --- publicacao na branch site-publicado ---

def _git(pasta: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=pasta, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def remoto(tmp_path, monkeypatch):
    """Remoto `--bare` com a main (codigo e dados); cada `nova_execucao` e um clone novo, como no Actions."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("PATH", f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}")
    bare = tmp_path / "remoto.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    inicial = tmp_path / "inicial"
    _git(tmp_path, "clone", "-q", str(bare), str(inicial))
    (inicial / "README.md").write_text("codigo\n")
    (inicial / "dados").mkdir()
    (inicial / "dados" / "base.csv").write_text("a\n")
    _git(inicial, "add", ".")
    _git(inicial, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "inicial")
    _git(inicial, "push", "-q", "origin", "main")
    return bare


def _executar_publicacao(tmp_path: Path, bare: Path, n: int, site: dict[str, str]) -> tuple[Path, str]:
    """Roda os passos `site_anterior` e `publicar_site` num clone novo com `_site` = `site`; devolve (clone, GITHUB_OUTPUT)."""
    clone = tmp_path / f"execucao{n}"
    _git(tmp_path, "clone", "-q", "--depth", "1", "-b", "main", f"file://{bare}", str(clone))
    env_arquivo, saida = tmp_path / f"env{n}", tmp_path / f"saida{n}"
    env_arquivo.write_text("")
    saida.write_text("")
    resultado = _rodar(_passo("atualizar.yml", "site_anterior"), clone, GITHUB_ENV=str(env_arquivo))
    assert resultado.returncode == 0, resultado.stderr
    env = dict(linha.split("=", 1) for linha in env_arquivo.read_text().splitlines())
    for nome, conteudo in site.items():
        (clone / "_site" / nome).parent.mkdir(parents=True, exist_ok=True)
        (clone / "_site" / nome).write_text(conteudo)
    resultado = _rodar(_passo("atualizar.yml", "publicar_site"), clone, GITHUB_OUTPUT=str(saida), **env)
    assert resultado.returncode == 0, resultado.stderr
    return clone, saida.read_text()


def _arvore(bare: Path, ref: str = "site-publicado") -> dict[str, str]:
    nomes = _git(bare, "ls-tree", "-r", "--name-only", ref).split()
    return {nome: _git(bare, "show", f"{ref}:{nome}") for nome in nomes}


def test_site_publicado_orfa_so_com_o_site_e_so_quando_muda(tmp_path, remoto):
    site = {"index.html": "<p>1</p>\n", ".htaccess": "Header x\n", "og/inicio.png": "png1", "css/estilo.css": "a{}\n"}
    clone, saida = _executar_publicacao(tmp_path, remoto, 1, site)
    assert "publicado=sim" in saida
    assert not any((clone / "_anterior").iterdir())  # primeira vez: nada publicado antes
    assert _arvore(remoto) == site  # sem README, dados nem .git: so o site
    assert _git(remoto, "rev-list", "--count", "site-publicado").strip() == "1"  # orfa
    autor = _git(remoto, "log", "-1", "--format=%an <%ae>", "site-publicado").strip()
    assert autor == "github-actions[bot] <41898283+github-actions[bot]@users.noreply.github.com>"

    # mesmo site (o PNG com outros bytes conta como igual, Ruling S-X): nada publicado
    clone, saida = _executar_publicacao(tmp_path, remoto, 2, {**site, "og/inicio.png": "png1-outro-chromium"})
    assert "publicado=sim" not in saida
    assert sorted(p.relative_to(clone / "_anterior").as_posix() for p in (clone / "_anterior").rglob("*") if p.is_file()) \
        == sorted(site)  # o anterior e so o site, sem .git
    assert _git(remoto, "rev-list", "--count", "site-publicado").strip() == "1"

    novo = {"index.html": "<p>2</p>\n", ".htaccess": "Header x\n", "og/inicio.png": "png1", "novo.html": "n\n"}
    _, saida = _executar_publicacao(tmp_path, remoto, 3, novo)
    assert "publicado=sim" in saida
    assert _arvore(remoto) == novo  # o css que saiu do site sai da branch
    assert _git(remoto, "rev-list", "--count", "site-publicado").strip() == "2"
    assert _arvore(remoto, "main") == {"README.md": "codigo\n", "dados/base.csv": "a\n"}  # a main nao muda


def test_commit_dos_dados_rebase_sobre_a_main_nova_e_so_se_mudou(tmp_path, remoto):
    clone = tmp_path / "execucao"
    _git(tmp_path, "clone", "-q", "--depth", "1", "-b", "main", f"file://{remoto}", str(clone))
    # durante a execucao, alguem empurra outro commit para a main
    outro = tmp_path / "outro"
    _git(tmp_path, "clone", "-q", f"file://{remoto}", str(outro))
    (outro / "README.md").write_text("codigo novo\n")
    _git(outro, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "outro")
    _git(outro, "push", "-q", "origin", "main")

    (clone / "dados" / "base.csv").write_text("b\n")
    (clone / "site.json").write_text("{}")  # fora de dados/: nao entra
    resultado = _rodar(_passo("atualizar.yml", "commit_dados"), clone)
    assert resultado.returncode == 0, resultado.stderr
    assert _arvore(remoto, "main") == {"README.md": "codigo novo\n", "dados/base.csv": "b\n"}
    autor = _git(remoto, "log", "-1", "--format=%an <%ae>|%s", "main").strip()
    assert autor == "github-actions[bot] <41898283+github-actions[bot]@users.noreply.github.com>|dados: publicação automática da base"

    topo = _git(remoto, "rev-parse", "main")
    assert _rodar(_passo("atualizar.yml", "commit_dados"), clone).returncode == 0  # nada mudou em dados/
    assert _git(remoto, "rev-parse", "main") == topo
