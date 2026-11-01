"""README: cobre o que o usuario precisa para a primeira coleta real e a tabela de indicadores nunca fica velha."""

import shutil
from pathlib import Path
from urllib.parse import urlparse

from nordeste.coletores.arquivo import urls_arquivo
from nordeste.coletores.ipeadata import urls_ipeadata
from nordeste.coletores.sidra import url_sidra
from nordeste.fichas import carregar_fichas
from nordeste.tabela import FIM_TABELA, INICIO_TABELA, atualizar_readme, main, tabela_markdown

RAIZ = Path(__file__).resolve().parent.parent
README = RAIZ / "README.md"
DOMINIOS = (
    "apisidra.ibge.gov.br", "ftp.ibge.gov.br", "www.ipeadata.gov.br", "www.gov.br",
    "download.inep.gov.br", "www.atlasbrasil.org.br", "secure.globalsign.com",
)


def _texto() -> str:
    return README.read_text(encoding="utf-8")


def _hosts_do_coletor() -> set[str]:
    hosts = set()
    for ficha in carregar_fichas(RAIZ / "metadados" / "indicadores").values():
        for serie in (s for s in ficha.series if s.coletor != "calculo"):
            if serie.coletor == "arquivo":
                urls = urls_arquivo(serie.parametros)
            elif serie.coletor == "sidra":
                urls = [url_sidra(serie.parametros)]
            else:
                urls = list(urls_ipeadata(serie.parametros).values())
            hosts |= {urlparse(u).netloc for u in urls}
    return hosts


def _dominios_da_secao(texto: str, titulo: str) -> set[str]:
    secao = texto.split(titulo, 1)[1].split("\n#", 1)[0]
    return {linha.split("`")[1] for linha in secao.splitlines() if linha.startswith("| `")}


def test_readme_lista_os_dominios_necessarios_e_todos_os_hosts_das_fichas():
    texto = _texto()
    for dominio in DOMINIOS:
        assert f"`{dominio}`" in texto, dominio
    assert _hosts_do_coletor() <= set(DOMINIOS), _hosts_do_coletor() - set(DOMINIOS)


def test_readme_separa_dominios_do_coletor_dos_citados():
    texto = _texto()
    usados = _dominios_da_secao(texto, "### Usados pelo coletor")
    citados = _dominios_da_secao(texto, "### Citados nas fichas ou de apoio")
    assert usados == _hosts_do_coletor()  # exatamente os hosts que o coletor acessa
    assert citados == set(DOMINIOS) - usados


def test_readme_avisa_anos_fixos_r01_de_derivacao_e_opcao_global():
    texto = _texto()
    assert "python -m nordeste --raiz /caminho/da/copia coletar --offline" in texto
    assert "periodos: 2024-2026" in texto and "fim: 2023" in texto and "R05" in texto
    assert "derivação" in texto.split("## A regra R01", 1)[1].split("\n## ", 1)[0]


def test_readme_documenta_comandos_regra_r01_e_roteiro():
    texto = _texto()
    for comando in ("coletar", "consolidar", "validar", "publicar"):
        assert f"python -m nordeste {comando}" in texto
    assert "R01" in texto and "não pode ser desligada" in texto
    assert "coletar --offline" in texto and "fixture" in texto
    assert "pytest -m rede" in texto and "publicar --ensaio" in texto
    assert "NORDESTE_CONTRATO_PESADO=1" in texto
    assert "coletar --indicador" in texto


def test_readme_explica_ca_extra_recursos_e_que_a_base_publicada_ainda_nao_existe():
    texto = _texto()
    assert "ca_extra" in texto and "cadeia" in texto and "nunca" in texto and "verify=False" in texto
    assert "~2 GB" in texto and "~4 GB de RAM" in texto and "Python 3.12" in texto
    for dependencia in ("pandas", "pyarrow", "pyyaml", "requests", "openpyxl", "xlrd", "certifi", "numpy"):
        assert dependencia in texto, dependencia
    assert "primeira publicação real" in texto


def test_tabela_do_readme_e_a_gerada_das_fichas():
    texto = _texto()
    assert INICIO_TABELA in texto and FIM_TABELA in texto
    bloco = texto.split(INICIO_TABELA, 1)[1].split(FIM_TABELA, 1)[0].strip()
    esperada = tabela_markdown(carregar_fichas(RAIZ / "metadados" / "indicadores"))
    assert bloco == esperada, "tabela velha: rode `python -m nordeste.tabela --atualizar-readme`"


def test_atualizar_readme_troca_so_o_bloco_entre_os_marcadores(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(f"antes\n{INICIO_TABELA}\nvelho\n{FIM_TABELA}\ndepois\n", encoding="utf-8")
    atualizar_readme(readme, "| nova |")
    assert readme.read_text(encoding="utf-8") == f"antes\n{INICIO_TABELA}\n| nova |\n{FIM_TABELA}\ndepois\n"


def test_comando_atualiza_o_readme_da_raiz(tmp_path, capsys):
    (tmp_path / "metadados").mkdir()
    shutil.copytree(RAIZ / "metadados" / "indicadores", tmp_path / "metadados" / "indicadores")
    (tmp_path / "README.md").write_text(f"{INICIO_TABELA}\n{FIM_TABELA}\n", encoding="utf-8")
    assert main(["--raiz", str(tmp_path), "--atualizar-readme"]) == 0
    assert "| `populacao` |" in (tmp_path / "README.md").read_text(encoding="utf-8")
    assert capsys.readouterr().out == ""


def test_dependencias_importadas_diretamente_estao_declaradas():
    import tomllib
    declaradas = set(tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"])
    assert {"pandas", "numpy", "pyarrow", "pyyaml", "requests", "certifi", "openpyxl", "xlrd"} <= declaradas
