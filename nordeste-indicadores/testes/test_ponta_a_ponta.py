import shutil

import pandas as pd

from nordeste.cli import main
from nordeste.coletores.registro import ler_registro
from nordeste.derivados import COLUNAS_REGISTRO

HOJE = ["--hoje", "2026-11-01"]


def argumentos(projeto):
    return ["--raiz", str(projeto.raiz), *HOJE]


def ler_csv(caminho):
    return pd.read_csv(caminho, keep_default_na=False, na_values={"valor": [""]}, float_precision="round_trip")


def test_ponta_a_ponta_com_fixtures_e_barrado_so_pela_r01(projeto, capsys):
    raiz = argumentos(projeto)
    assert main(raiz + ["coletar", "--offline"]) == 0
    assert main(raiz + ["consolidar"]) == 0
    assert main(raiz + ["publicar"]) == 1
    assert "R01" in capsys.readouterr().err
    assert not (projeto.base / "base_nordeste.csv").exists()
    erros = pd.read_csv(projeto.relatorios / "validacao.csv").query("nivel == 'erro'")
    assert set(erros.regra) == {"R01"}


def test_br_fora_ne_do_amostra_per_capita(projeto):
    raiz = argumentos(projeto)
    main(raiz + ["coletar", "--offline"]); main(raiz + ["consolidar"])
    b = pd.read_csv(projeto.trabalho / "base.csv")
    sel = b.query("indicador_id == 'amostra_per_capita' and territorio_id == 'BR_FORA_NE' and ano == 2002")
    assert sel.valor.tolist() == [1000.0] and sel.tipo_dado.tolist() == ["derivado"]


def test_coletar_sem_fixture_sai_com_1(projeto, capsys):
    shutil.rmtree(projeto.fixtures / "pib_nominal")
    assert main(["--raiz", str(projeto.raiz), "coletar", "--offline"]) == 1
    err = capsys.readouterr().err
    assert "sem fixture para pib_nominal/scr_ref2010" in err and "Traceback" not in err
    coletados = set(ler_registro(projeto.registro_coletas).indicador_id)
    assert {"amostra_per_capita", "amostra_populacao"} <= coletados


def test_coletar_um_indicador_so_coleta_esse(projeto):
    assert main(argumentos(projeto) + ["coletar", "--offline", "--indicador", "pib_nominal"]) == 0
    assert set(ler_registro(projeto.registro_coletas).indicador_id) == {"pib_nominal"}


def test_coletar_indicador_desconhecido_sai_com_1(projeto, capsys):
    assert main(argumentos(projeto) + ["coletar", "--offline", "--indicador", "nao_existe"]) == 1
    err = capsys.readouterr().err
    assert "nao_existe" in err and "Traceback" not in err
    assert not projeto.registro_coletas.exists()


def test_coletar_sem_offline_nao_coleta_serie_nao_verificada(projeto, capsys):
    for ficha in projeto.fichas.glob("*.yaml"):  # a amostra tem serie verificada; aqui nenhuma pode estar
        ficha.write_text(ficha.read_text(encoding="utf-8").replace("verificado: true", "verificado: false"),
                         encoding="utf-8")
    assert main(argumentos(projeto) + ["coletar"]) == 1
    err = capsys.readouterr().err
    assert "série não verificada: pib_nominal/scr_ref2010" in err
    assert len(err.strip().splitlines()) == 3  # uma linha por serie, sem traceback


def test_consolidar_grava_os_cinco_arquivos(projeto):
    raiz = argumentos(projeto)
    main(raiz + ["coletar", "--offline"])
    assert main(raiz + ["consolidar"]) == 0
    base = ler_csv(projeto.trabalho / "base.csv")
    assert {"BR", "NE", "BR_FORA_NE"} <= set(base.territorio_id)
    derivados = ler_csv(projeto.trabalho / "derivados.csv")
    assert {"razao", "variacao_acumulada"} <= set(derivados.metrica)
    assert "BR_FORA_NE" in set(derivados.referencia)  # calculado sobre a base com o agregado
    pendencias = pd.read_csv(projeto.trabalho / "pendencias.csv", keep_default_na=False)
    assert list(pendencias.columns) == ["indicador_id", "serie_id", "motivo"] and pendencias.empty
    assert list(pd.read_csv(projeto.registro_derivacoes).columns) == COLUNAS_REGISTRO
    cobertura = pd.read_csv(projeto.relatorios / "cobertura.csv", keep_default_na=False)
    assert "amostra_per_capita" in set(cobertura.indicador_id)


def test_consolidar_registra_pendencia_de_serie_sem_coleta(projeto, capsys):
    raiz = argumentos(projeto)
    main(raiz + ["coletar", "--offline", "--indicador", "pib_nominal"])
    assert main(raiz + ["consolidar"]) == 0
    pendencias = pd.read_csv(projeto.trabalho / "pendencias.csv", keep_default_na=False)
    assert set(pendencias.indicador_id) == {"amostra_per_capita", "amostra_populacao"}
    assert set(pendencias.motivo) == {"sem coleta"}
    assert "amostra_per_capita/scr_ref2010" in capsys.readouterr().out


def test_consolidar_acrescenta_derivacoes_sem_duplicar_nem_apagar(projeto):
    raiz = argumentos(projeto)
    main(raiz + ["coletar", "--offline"]); main(raiz + ["consolidar"])
    antigo = {"coleta_id": "deriv.amostra_per_capita.scr_ref2010.antigo", "indicador_id": "amostra_per_capita",
              "serie_id": "scr_ref2010", "insumos": "coleta.antiga"}
    registro = pd.read_csv(projeto.registro_derivacoes, dtype=str, keep_default_na=False)
    registro = pd.concat([pd.DataFrame([antigo]), registro], ignore_index=True)
    registro.to_csv(projeto.registro_derivacoes, index=False)

    assert main(raiz + ["consolidar"]) == 0

    depois = pd.read_csv(projeto.registro_derivacoes, dtype=str, keep_default_na=False)
    assert depois.coleta_id.tolist() == registro.coleta_id.tolist()
    assert antigo["coleta_id"] in set(depois.coleta_id)


def test_validar_grava_relatorio_e_sai_com_1_se_reprovado(projeto, capsys):
    raiz = argumentos(projeto)
    main(raiz + ["coletar", "--offline"]); main(raiz + ["consolidar"])
    assert main(raiz + ["validar"]) == 1
    err = capsys.readouterr().err
    assert "R01" in err and "Traceback" not in err
    erros = pd.read_csv(projeto.relatorios / "validacao.csv").query("nivel == 'erro'")
    assert set(erros.regra) == {"R01"}
    assert not projeto.base.exists()


def test_validar_sem_consolidar_sai_com_1_sem_traceback(projeto, capsys):
    assert main(argumentos(projeto) + ["validar"]) == 1
    err = capsys.readouterr().err
    assert "consolidacao" in err and "Traceback" not in err


def test_publicar_aprovado_grava_a_base(projeto):
    raiz = argumentos(projeto)
    main(raiz + ["coletar", "--offline"]); main(raiz + ["consolidar"])
    coletas = ler_registro(projeto.registro_coletas)
    coletas["origem"] = "rede"  # simula dado oficial: a R01 so barra origem fixture
    coletas.to_csv(projeto.registro_coletas, index=False)

    assert main(raiz + ["publicar", "--ensaio"]) == 0
    assert not projeto.base.exists()
    assert main(raiz + ["publicar"]) == 0
    assert (projeto.base / "base_nordeste.csv").exists()


def test_ficha_invalida_sai_com_1_sem_traceback(projeto, capsys):
    (projeto.fichas / "pib_nominal.yaml").write_text("id: pib_nominal\n", encoding="utf-8")
    assert main(argumentos(projeto) + ["consolidar"]) == 1
    err = capsys.readouterr().err
    assert "pib_nominal.yaml" in err and "Traceback" not in err


def test_hoje_invalido_e_rejeitado(projeto, capsys):
    try:
        main(["--raiz", str(projeto.raiz), "--hoje", "ontem", "coletar"])
    except SystemExit as saida:
        assert saida.code == 2
    else:
        raise AssertionError("esperava SystemExit")
    assert "AAAA-MM-DD" in capsys.readouterr().err


def test_raiz_sem_fichas_sai_com_1(tmp_path, capsys):
    assert main(["--raiz", str(tmp_path), "coletar", "--offline"]) == 1
    err = capsys.readouterr().err
    assert "nenhuma ficha" in err and "Traceback" not in err
