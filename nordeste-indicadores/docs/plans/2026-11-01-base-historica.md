# Base histórica do Nordeste — Plano de implementação

> **Para agentes:** SUB-SKILL OBRIGATÓRIA: use superpowers:subagent-driven-development (recomendado) ou superpowers:executing-plans para executar este plano tarefa a tarefa. Os passos usam checkbox (`- [ ]`).

**Objetivo:** construir o pipeline que coleta, padroniza, deriva, valida e publica a base histórica de 15 indicadores do Nordeste, funcionando de ponta a ponta com arquivos sintéticos enquanto a rede para as fontes oficiais estiver bloqueada.

**Arquitetura:** pacote Python `nordeste` em `nordeste-indicadores/src/`. As fichas YAML comandam o pipeline: cada série declara coletor e parâmetros. As etapas se comunicam por arquivos em `dados/` (cache bruto, trabalho, base publicada, relatórios). As tarefas 1 a 12 entregam o PIB per capita de ponta a ponta; as tarefas 13 a 17 estendem para os outros 14 indicadores e para os testes contra as fontes reais.

**Tecnologia:** Python ≥ 3.12, pandas, pyarrow, pyyaml, requests, openpyxl, pytest.

**Spec:** `nordeste-indicadores/docs/specs/2026-10-31-base-historica-design.md`

## Restrições globais

- Todos os comandos rodam a partir de `nordeste-indicadores/`. Instalação: `python -m pip install -e '.[dev]'`.
- `requires-python = ">=3.12"`. Dependências: `pandas`, `pyarrow`, `pyyaml`, `requests`, `openpyxl`; dev: `pytest`. Nenhuma outra.
- Colunas da base, nesta ordem: `indicador_id, subindicador, etapa, rede, territorio_id, ano, valor, tipo_dado, serie_id, coleta_id, nota`.
- Chave única: `indicador_id, subindicador, etapa, rede, territorio_id, ano, serie_id`. Colunas opcionais de texto usam `""`, nunca nulo.
- `tipo_dado` ∈ {`observado`, `estimativa_oficial`, `derivado`, `indisponivel`}. `valor` nulo ⇔ `indisponivel`.
- Territórios: `BR, N, NE, SE, S, CO, MA, PI, CE, RN, PB, PE, AL, SE_UF, BA, BR_FORA_NE` (16).
- Sem interpolação, sem projeção. Nenhuma métrica atravessa `serie_id`.
- A regra R01 (dado de fixture bloqueia publicação) não tem parâmetro, flag nem variável de ambiente para desligar.
- Tolerâncias: 0,5% (`0.005` relativo) nas regras R07 e R08. Rede: 3 novas tentativas, esperas de 1, 2 e 4 segundos.
- Fixtures sintéticas usam valores derivados de 99999 e ficam em `testes/fixtures/<indicador_id>/<serie_id>.<ext>`.
- Mensagens de erro e nomes de domínio em português, sem acento em identificadores de código.
- Commits terminam com as linhas de atribuição definidas para a sessão.

## Desvios da spec (decididos neste plano, a relatar ao usuário)

1. Dependência extra `openpyxl`: o pandas precisa dela para ler as planilhas `.xlsx` do INEP e do PNUD.
2. `governos.csv` ganha a coluna `apelido` (FHC, Lula, Dilma, Temer, Bolsonaro), usada para montar `transicao_dilma_temer`.
3. Ficha ganha campos: `auxiliar` (insumo não exibido, ex.: PIB nominal), `comparacao.fator` (conversão de unidade, ex.: 1000 para R$ mil), `limiar_salto_pct` (aviso A01, padrão 50), `series[].verificado` (parâmetros confirmados na fonte) e `series[].parametros.anos_estimativa`.
4. Método `razao_encadeada` nomeia o cálculo do índice de volume descrito na seção 6.2 da spec.
5. Pasta `dados/trabalho/` (fora do Git) guarda o resultado de `consolidar` entre comandos.
6. `base_nordeste_completa.csv` sai no padrão do Excel brasileiro: UTF-8 com BOM, separador `;` e decimal `,`. A base principal segue o padrão de máquina: UTF-8, `,` e `.`.
7. Os coletores `ibge_arquivos`, `inep` e `pnud` da spec viram um coletor genérico `arquivo` (download por URL). O que muda entre as fontes é o formato, e isso fica no padronizador `planilha`.

## Foco de revisão

1. Planilhas com números em texto no formato brasileiro (`"1.234,5"`) e marcadores de ausência (`"-"`, `"--"`, `"..."`, `"…"`, `"x"`, `""`) → conversão correta ou `indisponivel`, nunca erro nem zero. Teste na Tarefa 13.
2. Leitor do público abrindo a versão completa no Excel → acentos e colunas corretos. Teste na Tarefa 11.
3. `coletar --offline` sem fixture para uma série → mensagem com indicador e série, sem traceback, código de saída 1. Teste na Tarefa 4 e na 12.
4. Publicar duas vezes sem mudança → arquivos idênticos e `mudancas.csv` vazio. Teste na Tarefa 11.
5. Ano com Nordeste presente e algum estado faltando → R07 e `dispersao_ufs` ignoram aquele ano, sem falso positivo. Testes nas Tarefas 8 e 9.

---

### Tarefa 1: Esqueleto, esquema e caminhos

**Arquivos:**
- Criar: `pyproject.toml`, `.gitignore`, `src/nordeste/__init__.py`, `src/nordeste/esquema.py`, `src/nordeste/caminhos.py`, `testes/conftest.py`
- Teste: `testes/test_esquema.py`, `testes/test_caminhos.py`

**Interfaces:**
- Produz:
  - `esquema.COLUNAS_BASE: list[str]`, `CHAVE_BASE: list[str]`, `TIPOS_DADO: tuple[str, ...]`, `REDES: tuple[str, ...]` (`total, publica, privada, federal, estadual, municipal`), `COLUNAS_DERIVADOS: list[str]` (`indicador_id, subindicador, etapa, rede, metrica, referencia, territorio_id, ano, valor, serie_id`), `METRICAS: tuple[str, ...]` (`razao, diferenca, variacao_acumulada, crescimento_relativo, posicao_regioes, dispersao_ufs`).
  - `esquema.normalizar_base(df: pd.DataFrame) -> pd.DataFrame`: ordena colunas como `COLUNAS_BASE`, preenche texto opcional com `""`, `ano` como `int`, `valor` como `float`; levanta `ValueError` se faltar coluna obrigatória.
  - `caminhos.Caminhos(raiz: Path)` (dataclass congelada) com propriedades `metadados`, `fichas`, `territorios_csv`, `governos_csv`, `brutos`, `trabalho`, `base`, `relatorios`, `fixtures`, `registro_coletas` (`relatorios/coletas.csv`), `registro_derivacoes` (`relatorios/derivacoes.csv`).
  - Fixture pytest `projeto(tmp_path) -> Caminhos`: copia `metadados/` e `testes/fixtures/` do repositório para `tmp_path`, quando existirem. As Tarefas 2 e 3 acrescentam ao mesmo `conftest.py` as fixtures `territorios(projeto)` e `fichas(projeto)`.

- [ ] **Passo 1: escrever os testes que falham**

```python
def test_colunas_base_na_ordem_da_spec():
    assert COLUNAS_BASE == ["indicador_id", "subindicador", "etapa", "rede", "territorio_id",
                            "ano", "valor", "tipo_dado", "serie_id", "coleta_id", "nota"]

def test_chave_e_tipos():
    assert CHAVE_BASE == ["indicador_id", "subindicador", "etapa", "rede", "territorio_id", "ano", "serie_id"]
    assert TIPOS_DADO == ("observado", "estimativa_oficial", "derivado", "indisponivel")

def test_normalizar_preenche_opcionais_com_vazio():
    df = pd.DataFrame([{"indicador_id": "x", "territorio_id": "NE", "ano": "2002", "valor": "1.5",
                        "tipo_dado": "observado", "serie_id": "s", "coleta_id": "c"}])
    out = normalizar_base(df)
    assert list(out.columns) == COLUNAS_BASE
    assert out.loc[0, "subindicador"] == "" and out.loc[0, "nota"] == ""
    assert out.loc[0, "ano"] == 2002 and out.loc[0, "valor"] == 1.5

def test_normalizar_rejeita_coluna_obrigatoria_ausente():
    with pytest.raises(ValueError, match="territorio_id"):
        normalizar_base(pd.DataFrame([{"indicador_id": "x"}]))

def test_caminhos(tmp_path):
    c = Caminhos(tmp_path)
    assert c.fichas == tmp_path / "metadados" / "indicadores"
    assert c.registro_coletas == tmp_path / "dados" / "relatorios" / "coletas.csv"
    assert c.trabalho == tmp_path / "dados" / "trabalho"
```

- [ ] **Passo 2: rodar e confirmar a falha**
Comando: `python -m pytest testes/test_esquema.py testes/test_caminhos.py -v` → FALHA (`ModuleNotFoundError: nordeste`).

- [ ] **Passo 3: implementar**
`pyproject.toml` com layout `src/`, extras `dev = ["pytest"]` e `[tool.pytest.ini_options]` com `testpaths = ["testes"]`, `markers = ["rede: acessa fontes oficiais reais"]`, `addopts = "-m 'not rede'"`. `.gitignore`: `dados/brutos/`, `dados/trabalho/`, `__pycache__/`, `*.egg-info/`. Instalar com `python -m pip install -e '.[dev]'`.

- [ ] **Passo 4: rodar e confirmar que passa**
Comando: `python -m pytest -v` → todos PASSAM.

- [ ] **Passo 5: commit**
`git add nordeste-indicadores && git commit -m "feat(nordeste): esqueleto do pacote, esquema da base e caminhos"`

---

### Tarefa 2: Territórios e governos

**Arquivos:**
- Criar: `metadados/territorios.csv`, `metadados/governos.csv`, `src/nordeste/territorios.py`, `src/nordeste/governos.py`
- Teste: `testes/test_territorios.py`, `testes/test_governos.py`

**Interfaces:**
- Produz:
  - `territorios.carregar_territorios(path: Path) -> pd.DataFrame` (colunas `territorio_id, nome, tipo, codigo_ibge, regiao_id`, todas texto).
  - `territorios.territorio_por_codigo(territorios: pd.DataFrame, nivel: str, codigo: str) -> str | None`. `nivel` ∈ {`n1`, `n2`, `n3`}, mapeado a partir de `tipo` (`pais`→n1, `regiao`→n2, `uf`→n3).
  - `territorios.territorio_por_nome(territorios, nome: str) -> str | None`: compara sem acento e sem diferença de maiúsculas.
  - `UFS_NE: tuple[str, ...]` = `("MA", "PI", "CE", "RN", "PB", "PE", "AL", "SE_UF", "BA")`; `REGIOES: tuple[str, ...]` = `("N", "NE", "SE", "S", "CO")`.
  - `governos.carregar_governos(path: Path) -> pd.DataFrame` (datas como `datetime.date`).
  - `governos.atribuir_governo(ano: int, governos: pd.DataFrame) -> tuple[str, str]`: devolve `(presidente, mandato)` do governo que cobre de 1º/jan a 31/dez; sem cobertura integral, devolve `("transicao_" + "_".join(apelidos em ordem, minúsculos), "")`.

Conteúdo de `territorios.csv` (`codigo_ibge`): BR=1; N=1, NE=2, SE=3, S=4, CO=5 (`regiao_id` igual ao próprio id); MA=21, PI=22, CE=23, RN=24, PB=25, PE=26, AL=27, SE_UF=28, BA=29 (`regiao_id=NE`); BR_FORA_NE com `tipo=agregado_derivado` e código vazio. `governos.csv` reproduz a tabela da seção 6.3 da spec, acrescida de `apelido`.

- [ ] **Passo 1: escrever os testes que falham**

```python
def test_dezesseis_territorios_e_sergipe_separado_do_sudeste(projeto):
    t = carregar_territorios(projeto.territorios_csv)
    assert len(t) == 16
    assert t.set_index("territorio_id").loc["SE", "tipo"] == "regiao"
    assert t.set_index("territorio_id").loc["SE_UF", "nome"] == "Sergipe"

def test_codigo_1_depende_do_nivel(projeto):
    t = carregar_territorios(projeto.territorios_csv)
    assert territorio_por_codigo(t, "n1", "1") == "BR"
    assert territorio_por_codigo(t, "n2", "1") == "N"
    assert territorio_por_codigo(t, "n3", "28") == "SE_UF"
    assert territorio_por_codigo(t, "n3", "35") is None

def test_nome_sem_acento(projeto):
    assert territorio_por_nome(carregar_territorios(projeto.territorios_csv), "PIAUI") == "PI"

@pytest.mark.parametrize("ano,esperado", [
    (2000, ("Fernando Henrique Cardoso", "2")), (2003, ("Luiz Inácio Lula da Silva", "1")),
    (2015, ("Dilma Rousseff", "2")), (2016, ("transicao_dilma_temer", "")),
    (2017, ("Michel Temer", "")), (2026, ("Luiz Inácio Lula da Silva", "3"))])
def test_atribuicao_anual(projeto, ano, esperado):
    assert atribuir_governo(ano, carregar_governos(projeto.governos_csv)) == esperado

def test_todo_ano_tem_um_rotulo(projeto):
    g = carregar_governos(projeto.governos_csv)
    assert all(atribuir_governo(a, g)[0] for a in range(2000, 2027))

def test_interinidade_registrada(projeto):
    g = carregar_governos(projeto.governos_csv)
    interino = g[g.interino == "sim"].iloc[0]
    assert (interino.inicio, interino.fim) == (date(2016, 5, 12), date(2016, 8, 31))
```

- [ ] **Passo 2: rodar e confirmar a falha** — `python -m pytest testes/test_territorios.py testes/test_governos.py -v` → FALHA.
- [ ] **Passo 3: implementar** os dois CSVs e os dois módulos.
- [ ] **Passo 4: rodar e confirmar que passa** — mesmo comando → PASSA.
- [ ] **Passo 5: commit** — `git commit -m "feat(nordeste): tabelas de territórios e governos"`

---

### Tarefa 3: Fichas de indicador

**Arquivos:**
- Criar: `src/nordeste/fichas.py`, `metadados/indicadores/pib_per_capita.yaml`, `metadados/indicadores/pib_nominal.yaml`, `metadados/indicadores/populacao_contas_regionais.yaml`
- Teste: `testes/test_fichas.py`

**Interfaces:**
- Produz:
  - `Serie` (dataclass congelada): `id: str, inicio: int, fim: int | None, fonte: str, base_origem: str, url: str, coletor: str, parametros: dict, compatibilidade: str, verificado: bool`.
  - `Comparacao`: `referencia: str` (`brasil` | `brasil_fora_ne` | `nenhuma`), `metodo: str | None` (`soma` | `razao` | `razao_encadeada`), `numerador: str | None`, `denominador: str | None`, `fator: float = 1.0`.
  - `Ficha`: `id, nome, descricao, eixo, categoria, unidade, orgao, periodicidade, metodologia, observacoes, sentido` (`maior_melhor` | `menor_melhor`), `limites: dict` (chaves opcionais `min`, `max`), `comparacao: Comparacao`, `defasagem_meses: int`, `series: tuple[Serie, ...]`, `tratamento_monetario: dict | None`, `auxiliar: bool = False`, `limiar_salto_pct: float = 50.0`; método `serie(serie_id: str) -> Serie` (`KeyError` se não existir) e `serie_do_ano(ano: int) -> Serie | None`.
  - `class ErroFicha(ValueError)`.
  - `carregar_ficha(path: Path) -> Ficha`, `carregar_fichas(diretorio: Path) -> dict[str, Ficha]` (também confere se `numerador` e `denominador` apontam para fichas existentes), `verificar_fichas(diretorio: Path) -> list[str]` (uma mensagem por problema, sem parar no primeiro).

Regras de completude: todos os campos obrigatórios da seção 6.2 da spec; `tratamento_monetario` obrigatório quando `unidade` começa com `"R$"`; `metodo` obrigatório quando `referencia = brasil_fora_ne`; `numerador` e `denominador` obrigatórios para `razao` e `razao_encadeada`; pelo menos uma série.

Fichas desta tarefa: `pib_per_capita` (comparação `brasil_fora_ne`, `razao`, numerador `pib_nominal`, denominador `populacao_contas_regionais`, `fator: 1000`, `tratamento_monetario: {modo: razao}`, `limites: {min: 0}`, `defasagem_meses: 23`); `pib_nominal` (unidade `R$ mil`, `auxiliar: true`, `tratamento_monetario: {modo: razao}`, comparação `brasil_fora_ne`/`soma`, `limites: {min: 0}`); `populacao_contas_regionais` (unidade `pessoas`, `auxiliar: true`, `soma`). As três têm a série `scr_ref2010` (2002–2023, coletor `sidra`, `verificado: false`, `parametros: {}`).

- [ ] **Passo 1: escrever os testes que falham**

```python
def test_carrega_pib_per_capita(projeto):
    f = carregar_fichas(projeto.fichas)["pib_per_capita"]
    assert f.comparacao == Comparacao("brasil_fora_ne", "razao", "pib_nominal", "populacao_contas_regionais", 1000.0)
    assert f.serie("scr_ref2010").inicio == 2002
    assert f.serie_do_ano(2001) is None

def test_campo_ausente_nomeia_o_campo(tmp_path, ficha_minima):
    del ficha_minima["sentido"]
    (tmp_path / "x.yaml").write_text(yaml.safe_dump(ficha_minima), encoding="utf-8")
    with pytest.raises(ErroFicha, match="sentido"):
        carregar_ficha(tmp_path / "x.yaml")

def test_unidade_monetaria_exige_tratamento(tmp_path, ficha_minima):
    ficha_minima["unidade"] = "R$ correntes"; ficha_minima.pop("tratamento_monetario", None)
    (tmp_path / "x.yaml").write_text(yaml.safe_dump(ficha_minima), encoding="utf-8")
    assert any("tratamento_monetario" in m for m in verificar_fichas(tmp_path))

def test_razao_exige_numerador(tmp_path, ficha_minima):
    ficha_minima["comparacao"] = {"referencia": "brasil_fora_ne", "metodo": "razao"}
    (tmp_path / "x.yaml").write_text(yaml.safe_dump(ficha_minima), encoding="utf-8")
    assert any("numerador" in m for m in verificar_fichas(tmp_path))

def test_serie_em_curso_aceita_fim_nulo(tmp_path, ficha_minima):
    ficha_minima["series"][0]["fim"] = None
    (tmp_path / "x.yaml").write_text(yaml.safe_dump(ficha_minima), encoding="utf-8")
    assert carregar_ficha(tmp_path / "x.yaml").series[0].fim is None
```
(`ficha_minima` é uma fixture local com um dicionário válido e completo.)

- [ ] **Passo 2: rodar e confirmar a falha** — `python -m pytest testes/test_fichas.py -v` → FALHA.
- [ ] **Passo 3: implementar** `fichas.py` e as três fichas.
- [ ] **Passo 4: rodar e confirmar que passa** — mesmo comando → PASSA.
- [ ] **Passo 5: commit** — `git commit -m "feat(nordeste): fichas de indicador e fichas do PIB per capita"`

---

### Tarefa 4: Coleta (HTTP, registro, SIDRA, modo offline)

**Arquivos:**
- Criar: `src/nordeste/coletores/__init__.py`, `http.py`, `registro.py`, `sidra.py`, `arquivo.py`
- Teste: `testes/test_coleta.py`

**Interfaces:**
- Consome: `Ficha`, `Serie` (Tarefa 3); `Caminhos` (Tarefa 1).
- Produz:
  - `class ErroColeta(RuntimeError)`.
  - `http.baixar(url: str, tentativas_extras: int = 3, espera_inicial: float = 1.0, esperar=time.sleep, sessao: requests.Session | None = None) -> bytes`: esperas `espera_inicial × 2^k`; esgotadas as tentativas, levanta `ErroColeta` com a URL.
  - `registro.Coleta` (dataclass congelada): `coleta_id, indicador_id, serie_id, url, data_coleta, sha256, origem, arquivo` (`origem` ∈ {`rede`, `fixture`}; `arquivo` relativo à raiz).
  - `registro.ler_registro(path: Path) -> pd.DataFrame`; `registro.registrar(path: Path, coleta: Coleta) -> Coleta` (se já houver linha com mesmo indicador, série e sha256, devolve a existente e não grava); `registro.ultima_coleta(registro: pd.DataFrame, indicador_id: str, serie_id: str) -> Coleta | None`.
  - `coleta_id` = `f"{indicador_id}.{serie_id}.{data_coleta}.{sha256[:8]}"`, com `data_coleta` em `AAAA-MM-DD`.
  - `sidra.url_sidra(parametros: dict) -> str`.
  - `coletores.coletar_serie(ficha: Ficha, serie: Serie, caminhos: Caminhos, offline: bool, hoje: date) -> Coleta`. Offline: reaproveita a última coleta de origem `rede` cujo arquivo exista; senão usa a única fixture `fixtures/<indicador>/<serie>.*`; senão `ErroColeta("sem fixture para <indicador>/<serie>")`. Com rede: série com `verificado: false` → `ErroColeta("série não verificada: <indicador>/<serie>")`. O arquivo vai para `brutos/<indicador>/<serie>/<sha256[:8]>.<ext>` (`json` para `sidra` e `ipeadata`; sufixo da URL para `arquivo`).

`url_sidra` monta `https://apisidra.ibge.gov.br/values/t/{tabela}/n1/all/n2/all/n3/21,22,23,24,25,26,27,28,29/v/{variavel}/p/{periodos}` + `/{classificacao}/{categoria}` para cada item de `classificacoes`, com `periodos` padrão `all`.

- [ ] **Passo 1: escrever os testes que falham**

```python
def test_url_sidra():
    assert url_sidra({"tabela": "1234", "variavel": "56", "classificacoes": {"c11255": "90707"}}) == (
        "https://apisidra.ibge.gov.br/values/t/1234/n1/all/n2/all/n3/"
        "21,22,23,24,25,26,27,28,29/v/56/p/all/c11255/90707")

def test_baixar_tenta_de_novo_e_desiste():
    esperas = []
    sessao = SessaoFalsa(falhas=10)
    with pytest.raises(ErroColeta, match="http://x"):
        baixar("http://x", esperar=esperas.append, sessao=sessao)
    assert esperas == [1.0, 2.0, 4.0] and sessao.chamadas == 4

def test_baixar_recupera_na_terceira():
    assert baixar("http://x", esperar=lambda s: None, sessao=SessaoFalsa(falhas=2, conteudo=b"ok")) == b"ok"

def test_offline_usa_fixture_e_marca_origem(projeto, fichas):
    f = fichas["pib_per_capita"]
    c = coletar_serie(f, f.serie("scr_ref2010"), projeto, offline=True, hoje=date(2026, 11, 1))
    assert c.origem == "fixture" and (projeto.raiz / c.arquivo).exists()
    assert c.coleta_id.startswith("pib_per_capita.scr_ref2010.2026-11-01.")

def test_mesmo_arquivo_nao_duplica_registro(projeto, fichas):
    f = fichas["pib_per_capita"]; s = f.serie("scr_ref2010")
    a = coletar_serie(f, s, projeto, offline=True, hoje=date(2026, 11, 1))
    b = coletar_serie(f, s, projeto, offline=True, hoje=date(2026, 11, 2))
    assert a == b and len(ler_registro(projeto.registro_coletas)) == 1

def test_sem_fixture_erro_claro(projeto, fichas):
    f = fichas["pib_nominal"]; shutil.rmtree(projeto.fixtures / "pib_nominal")
    with pytest.raises(ErroColeta, match="sem fixture para pib_nominal/scr_ref2010"):
        coletar_serie(f, f.serie("scr_ref2010"), projeto, offline=True, hoje=date(2026, 11, 1))

def test_rede_recusa_serie_nao_verificada(projeto, fichas):
    f = fichas["pib_per_capita"]
    with pytest.raises(ErroColeta, match="não verificada"):
        coletar_serie(f, f.serie("scr_ref2010"), projeto, offline=False, hoje=date(2026, 11, 1))
```
(`SessaoFalsa` é um dublê local com `get()` que levanta `requests.ConnectionError` nas primeiras `falhas` chamadas. Os testes offline dependem das fixtures da Tarefa 5. Enquanto ela não existe, crie em `testes/fixtures/pib_per_capita/scr_ref2010.json` e `testes/fixtures/pib_nominal/scr_ref2010.json` um arquivo `[]`, que a Tarefa 5 substitui.)

- [ ] **Passo 2: rodar e confirmar a falha** — `python -m pytest testes/test_coleta.py -v` → FALHA.
- [ ] **Passo 3: implementar** os módulos. `arquivo.py` baixa `parametros["url"]`.
- [ ] **Passo 4: rodar e confirmar que passa** — mesmo comando → PASSA.
- [ ] **Passo 5: commit** — `git commit -m "feat(nordeste): coleta com novas tentativas, registro e modo offline"`

---

### Tarefa 5: Padronizador SIDRA e fixtures do PIB per capita

**Arquivos:**
- Criar: `src/nordeste/padronizacao/__init__.py`, `src/nordeste/padronizacao/sidra.py`, `testes/fixtures/gerar_fixtures.py`, as três fixtures `testes/fixtures/{pib_nominal,populacao_contas_regionais,pib_per_capita}/scr_ref2010.json`
- Teste: `testes/test_padronizacao_sidra.py`

**Interfaces:**
- Consome: `Coleta` (Tarefa 4), `territorio_por_codigo` (Tarefa 2), `normalizar_base` (Tarefa 1).
- Produz:
  - `class ErroLayout(ValueError)`.
  - `padronizacao.padronizar(ficha: Ficha, serie: Serie, coleta: Coleta, caminhos: Caminhos, territorios: pd.DataFrame) -> pd.DataFrame`: escolhe o padronizador por `serie.parametros.get("padronizador", serie.coletor)` e depois marca como `estimativa_oficial` os anos de `parametros["anos_estimativa"]`.
  - `padronizacao.sidra.padronizar_sidra(conteudo: bytes, ficha: Ficha, serie: Serie, coleta_id: str, territorios: pd.DataFrame) -> pd.DataFrame` (formato da base).

Formato SIDRA: lista JSON em que o primeiro elemento é o cabeçalho (`{"NC": "Nível Territorial (Código)", "V": "Valor", "D1C": "... (Código)", ...}`). O nível vem de `NC` (`"1"`→n1, `"2"`→n2, `"3"`→n3). A coluna de período é a `D?C` cujo rótulo começa com `"Ano"`. A coluna de território é a `D?C` cujo rótulo contém `"Brasil"`, `"Grande Região"` ou `"Unidade da Federação"`. Ambas podem ser sobrescritas por `parametros["coluna_periodo"]` e `parametros["coluna_territorio"]`. Valores: número com ponto decimal → `observado`; `"-"` → `0.0` `observado`; `".."`, `"..."` e `"X"` → `indisponivel`, com nota `"SIDRA: <símbolo>"`. Território fora de `territorios` é descartado.

`gerar_fixtures.py` (rodar com `python testes/fixtures/gerar_fixtures.py`) gera 2002–2023, no formato acima, com: PIB nominal (R$ mil) de cada UF do NE e das regiões N, SE, S, CO = 99999; NE = 899991; BR = 1299987. População com os mesmos números. PIB per capita = 1000 em todos os territórios, exceto AL em 2010 = `"..."`.

- [ ] **Passo 1: escrever os testes que falham**

```python
def test_mapeia_niveis_e_valores(projeto, fichas, territorios):
    f = fichas["pib_per_capita"]
    df = padronizar_sidra(ler(projeto, "pib_per_capita"), f, f.serie("scr_ref2010"), "c1", territorios)
    ne_2002 = df[(df.territorio_id == "NE") & (df.ano == 2002)].iloc[0]
    assert ne_2002.valor == 1000.0 and ne_2002.tipo_dado == "observado" and ne_2002.coleta_id == "c1"
    assert set(df.territorio_id) == {"BR", "N", "NE", "SE", "S", "CO", "MA", "PI", "CE", "RN", "PB", "PE", "AL", "SE_UF", "BA"}

def test_reticencias_viram_indisponivel(projeto, fichas, territorios):
    f = fichas["pib_per_capita"]
    df = padronizar_sidra(ler(projeto, "pib_per_capita"), f, f.serie("scr_ref2010"), "c1", territorios)
    al = df[(df.territorio_id == "AL") & (df.ano == 2010)].iloc[0]
    assert pd.isna(al.valor) and al.tipo_dado == "indisponivel" and al.nota == "SIDRA: ..."

def test_traco_e_zero_e_uf_fora_do_ne_descartada(fichas, territorios):
    conteudo = json_sidra([("3", "26", "2002", "-"), ("3", "35", "2002", "5")])
    f = fichas["pib_nominal"]
    df = padronizar_sidra(conteudo, f, f.serie("scr_ref2010"), "c1", territorios)
    assert df.valor.tolist() == [0.0] and df.territorio_id.tolist() == ["PE"]

def test_layout_sem_coluna_de_ano(fichas, territorios):
    f = fichas["pib_nominal"]
    with pytest.raises(ErroLayout, match="coluna de período"):
        padronizar_sidra(json_sidra([], rotulo_periodo="Mês (Código)"), f, f.serie("scr_ref2010"), "c1", territorios)

def test_anos_estimativa(projeto, fichas, territorios):
    ...  # serie com parametros {"anos_estimativa": [2023]} → linhas de 2023 com tipo_dado == "estimativa_oficial"
```
(`json_sidra` é um ajudante de teste que monta o JSON com cabeçalho. Escreva o corpo do último teste com a mesma estrutura dos demais.)

- [ ] **Passo 2: rodar e confirmar a falha** — `python -m pytest testes/test_padronizacao_sidra.py -v` → FALHA.
- [ ] **Passo 3: implementar** o padronizador, o despachante e o gerador. Rodar o gerador e commitar as fixtures geradas.
- [ ] **Passo 4: rodar e confirmar que passa** — `python -m pytest -v` → PASSA, incluindo os testes da Tarefa 4.
- [ ] **Passo 5: commit** — `git commit -m "feat(nordeste): padronizador SIDRA e fixtures sintéticas do PIB"`

---

### Tarefa 6: Consolidação

**Arquivos:**
- Criar: `src/nordeste/consolidacao.py`
- Teste: `testes/test_consolidacao.py`

**Interfaces:**
- Consome: `ultima_coleta`, `ler_registro` (Tarefa 4); `padronizar` (Tarefa 5).
- Produz:
  - `Pendencia` (dataclass congelada): `indicador_id, serie_id, motivo`.
  - `consolidar(caminhos: Caminhos, fichas: dict[str, Ficha], territorios: pd.DataFrame) -> tuple[pd.DataFrame, list[Pendencia]]`: para cada série de cada ficha, usa só a última coleta. Série sem coleta vira `Pendencia(motivo="sem coleta")`. `ErroLayout` vira `Pendencia(motivo=<mensagem>)`. Devolve a base normalizada e ordenada por `CHAVE_BASE`.

- [ ] **Passo 1: escrever os testes que falham**

```python
def test_consolida_tres_fichas(projeto_coletado):
    base, pend = consolidar(projeto_coletado, fichas, territorios)
    assert set(base.indicador_id) == {"pib_per_capita", "pib_nominal", "populacao_contas_regionais"}
    assert pend == []

def test_usa_apenas_a_ultima_coleta(projeto_coletado):
    # registrar segunda coleta de pib_nominal com fixture alterada (valor do NE em 2002 = 1)
    base, _ = consolidar(projeto_coletado, fichas, territorios)
    sel = base[(base.indicador_id == "pib_nominal") & (base.territorio_id == "NE") & (base.ano == 2002)]
    assert sel.valor.tolist() == [1.0]

def test_serie_sem_coleta_vira_pendencia(projeto):
    _, pend = consolidar(projeto, fichas, territorios)
    assert Pendencia("pib_nominal", "scr_ref2010", "sem coleta") in pend
```
(`projeto_coletado` é uma fixture que roda `coletar_serie(..., offline=True)` para as três fichas.)

- [ ] **Passo 2: rodar e confirmar a falha** — `python -m pytest testes/test_consolidacao.py -v` → FALHA.
- [ ] **Passo 3: implementar.**
- [ ] **Passo 4: rodar e confirmar que passa** — mesmo comando → PASSA.
- [ ] **Passo 5: commit** — `git commit -m "feat(nordeste): consolidação da base a partir das últimas coletas"`

---

### Tarefa 7: Brasil fora do Nordeste

**Arquivos:**
- Criar: `src/nordeste/derivados.py` (parte 1)
- Teste: `testes/test_brasil_fora_ne.py`

**Interfaces:**
- Produz:
  - `class ErroSerie(ValueError)`.
  - `brasil_fora_ne(base: pd.DataFrame, fichas: dict[str, Ficha]) -> tuple[pd.DataFrame, pd.DataFrame]`: devolve (linhas `BR_FORA_NE` no formato da base com `tipo_dado="derivado"`; registro de derivações com colunas `coleta_id, indicador_id, serie_id, insumos`). `insumos` são os `coleta_id` usados, separados por `;` e ordenados. `coleta_id` da derivação = `f"deriv.{indicador_id}.{serie_id}.{sha256(insumos)[:8]}"`.

Regras:
- `soma`: `BR − NE` por (`subindicador`, `etapa`, `rede`, `ano`, `serie_id`), só com os dois valores presentes.
- `razao`: `(num_BR − num_NE) ÷ (den_BR − den_NE) × fator`, juntando por `ano`. A série do resultado é `ficha.serie_do_ano(ano)`; ano sem série não gera linha.
- `razao_encadeada`: fator anual `f_t = (num_BR,t − num_NE,t) ÷ (den_BR,t−1 − den_NE,t−1)`. O primeiro ano da série com denominador disponível recebe índice 100, e `índice_t = índice_t−1 × f_t`. A cadeia para no primeiro ano sem fator calculável.
- `referencia` diferente de `brasil_fora_ne` não gera linha.

- [ ] **Passo 1: escrever os testes que falham**

```python
def test_soma():
    out, _ = brasil_fora_ne(base_de({"x": {"BR": 10, "NE": 4}}), {"x": ficha("x", "soma")})
    assert out.valor.tolist() == [6.0] and out.tipo_dado.tolist() == ["derivado"]

def test_razao_com_fator():
    b = base_de({"num": {"BR": 100, "NE": 30}, "den": {"BR": 50, "NE": 10}, "pc": {"BR": 2, "NE": 3}})
    out, _ = brasil_fora_ne(b, {"pc": ficha("pc", "razao", "num", "den", fator=1000), "num": aux("num"), "den": aux("den")})
    assert out[out.indicador_id == "pc"].valor.tolist() == [1750.0]

def test_razao_encadeada():
    b = base_anos({"num": {2003: {"BR": 108, "NE": 20}}, "den": {2002: {"BR": 100, "NE": 20}}, "vol": {}})
    out, _ = brasil_fora_ne(b, {"vol": ficha("vol", "razao_encadeada", "num", "den", inicio=2002), ...})
    assert out.set_index("ano").valor.to_dict() == {2002: 100.0, 2003: 110.0}

def test_sem_metodo_exato_nao_gera():
    out, _ = brasil_fora_ne(base_de({"ideb": {"BR": 5, "NE": 4}}), {"ideb": ficha("ideb", referencia="brasil")})
    assert out.empty

def test_registro_lista_insumos():
    _, reg = brasil_fora_ne(base_de({"x": {"BR": 10, "NE": 4}}, coletas={"BR": "cA", "NE": "cB"}), {"x": ficha("x", "soma")})
    assert reg.insumos.tolist() == ["cA;cB"] and reg.coleta_id.iloc[0].startswith("deriv.x.s.")
```
(`base_de`, `base_anos`, `ficha` e `aux` são ajudantes locais que montam DataFrames e `Ficha` com série `s`.)

- [ ] **Passo 2: rodar e confirmar a falha** — `python -m pytest testes/test_brasil_fora_ne.py -v` → FALHA.
- [ ] **Passo 3: implementar.**
- [ ] **Passo 4: rodar e confirmar que passa** — mesmo comando → PASSA.
- [ ] **Passo 5: commit** — `git commit -m "feat(nordeste): agregado Brasil fora do Nordeste com registro de derivação"`

---

### Tarefa 8: Métricas de convergência e cobertura

**Arquivos:**
- Modificar: `src/nordeste/derivados.py` (parte 2)
- Criar: `src/nordeste/cobertura.py`
- Teste: `testes/test_metricas.py`, `testes/test_cobertura.py`

**Interfaces:**
- Consome: `ErroSerie` (Tarefa 7), `UFS_NE`, `REGIOES` (Tarefa 2).
- Produz:
  - `metricas_convergencia(base: pd.DataFrame, fichas: dict[str, Ficha], territorios: pd.DataFrame) -> pd.DataFrame` (`COLUNAS_DERIVADOS`). Ignora fichas `auxiliar` e linhas `indisponivel`.
  - Funções públicas, cada uma recebendo as linhas de **uma** série e levantando `ErroSerie` se `serie_id.nunique() > 1`: `variacao_acumulada(df) -> pd.Series`, `crescimento_relativo(df_territorio, df_referencia) -> pd.Series`.
  - `cobertura.proxima_publicacao(ultimo_ano: int, defasagem_meses: int) -> str` (`"AAAA-MM"`, contando a partir de dezembro do último ano).
  - `cobertura.relatorio_cobertura(base: pd.DataFrame, fichas: dict[str, Ficha]) -> pd.DataFrame`, colunas `indicador_id, serie_id, territorio_id, primeiro_ano, ultimo_ano, anos_faltantes, proxima_publicacao`. `anos_faltantes` são os anos entre `inicio` e `fim` (ou o último ano disponível, se `fim` for nulo) sem valor, separados por `;`.

Definições: `razao` = território ÷ referência × 100; `diferenca` = território − referência; `variacao_acumulada` = (v ÷ v_primeiro − 1) × 100; `crescimento_relativo` = diferença, em pontos percentuais, entre as variações de observações consecutivas; `posicao_regioes` = posição do NE entre as 5 regiões (1 = melhor, conforme `sentido`), só nos anos com as 5 presentes; `dispersao_ufs` = desvio padrão populacional ÷ média × 100 das 9 UFs, só nos anos com as 9 presentes, com `territorio_id="NE"`. `referencia` = `"BR"` ou `"BR_FORA_NE"` segundo a ficha; com `nenhuma`, só saem `variacao_acumulada`, `posicao_regioes` e `dispersao_ufs`. `razao`, `diferenca` e `crescimento_relativo` saem para NE e para as 9 UFs.

- [ ] **Passo 1: escrever os testes que falham**

```python
def test_razao_e_diferenca():
    m = metricas_convergencia(base_de({"x": {"NE": 40, "BR": 80}}), {"x": ficha("x", referencia="brasil")}, territorios)
    ne = m[(m.territorio_id == "NE")].set_index("metrica").valor
    assert ne["razao"] == 50.0 and ne["diferenca"] == -40.0

def test_variacao_acumulada():
    assert variacao_acumulada(serie_anos({2002: 100, 2003: 150})).tolist() == [0.0, 50.0]

def test_crescimento_relativo_em_pontos():
    r = crescimento_relativo(serie_anos({2002: 100, 2003: 110}), serie_anos({2002: 100, 2003: 105}))
    assert r.round(6).tolist() == [5.0]

def test_recusa_series_misturadas():
    with pytest.raises(ErroSerie):
        variacao_acumulada(pd.concat([serie_anos({2012: 1}, serie="pnad"), serie_anos({2013: 2}, serie="pnadc")]))

@pytest.mark.parametrize("sentido,pos", [("maior_melhor", 2), ("menor_melhor", 4)])
def test_posicao(sentido, pos):
    b = base_de({"x": {"N": 1, "NE": 4, "SE": 5, "S": 3, "CO": 2}})
    m = metricas_convergencia(b, {"x": ficha("x", sentido=sentido)}, territorios)
    assert m[m.metrica == "posicao_regioes"].valor.tolist() == [pos]

def test_dispersao_exige_as_nove_ufs():
    nove = dict(zip(UFS_NE, range(1, 10)))
    m = metricas_convergencia(base_de({"x": nove}), {"x": ficha("x")}, territorios)
    assert m[m.metrica == "dispersao_ufs"].valor.round(2).tolist() == [51.64]
    oito = {k: v for k, v in nove.items() if k != "BA"}
    assert metricas_convergencia(base_de({"x": oito}), {"x": ficha("x")}, territorios).query("metrica == 'dispersao_ufs'").empty

def test_proxima_publicacao():
    assert proxima_publicacao(2023, 23) == "2025-11"

def test_anos_faltantes():
    c = relatorio_cobertura(base_anos_ne({2002: 1, 2004: 1}, indisponivel=[2003]), {"x": ficha("x", inicio=2002, fim=2004)})
    assert c.iloc[0].anos_faltantes == "2003"
```

- [ ] **Passo 2: rodar e confirmar a falha** — `python -m pytest testes/test_metricas.py testes/test_cobertura.py -v` → FALHA.
- [ ] **Passo 3: implementar.**
- [ ] **Passo 4: rodar e confirmar que passa** — mesmo comando → PASSA.
- [ ] **Passo 5: commit** — `git commit -m "feat(nordeste): métricas de convergência e relatório de cobertura"`

---

### Tarefa 9: Validação bloqueante (R01–R10)

**Arquivos:**
- Criar: `src/nordeste/validacao.py`
- Teste: `testes/test_validacao.py`

**Interfaces:**
- Consome: `verificar_fichas` (Tarefa 3), `ler_registro` (Tarefa 4).
- Produz:
  - `Falha` (dataclass congelada): `regra: str, mensagem: str`.
  - `ResultadoValidacao` (dataclass): `erros: list[Falha]`, `avisos: list[Falha]`, propriedade `aprovado: bool`, método `para_dataframe() -> pd.DataFrame` (colunas `nivel, regra, mensagem`, com `nivel` ∈ {`erro`, `aviso`}).
  - `validar(base, derivados, fichas, falhas_fichas: list[str], territorios, coletas, derivacoes, base_publicada: pd.DataFrame | None, hoje: date) -> ResultadoValidacao`.

Regras (ids exatos): `R01` linha cujo `coleta_id`, direto ou pelos `insumos` da derivação, tem `origem == "fixture"`; `R02` esquema (colunas, `tipo_dado`, territórios e indicadores conhecidos); `R03` chave duplicada; `R04` valor nulo ⇔ `indisponivel`; `R05` série não declarada ou ano fora de `[inicio, fim]`; `R06` valor fora de `limites`; `R07` em fichas `soma`, soma das 9 UFs ≠ NE ou soma das 5 regiões ≠ BR acima de 0,5%, só em anos completos; `R08` em fichas `razao`, `|oficial_NE − num_NE ÷ den_NE × fator| ÷ oficial_NE > 0.005`; `R09` `coleta_id` ausente dos dois registros; `R10` uma falha por mensagem de `falhas_fichas`. Cada mensagem cita indicador, território e ano, quando houver.

- [ ] **Passo 1: escrever os testes que falham**
Um teste por regra, cada um partindo de `base_valida()` (uma base pequena e coerente, com coleta `origem="rede"`, aprovada) e quebrando um único ponto:

```python
def test_base_valida_aprova():
    assert validar(**cenario()).aprovado

@pytest.mark.parametrize("regra,quebra", [
    ("R01", marcar_coleta_como_fixture), ("R01", marcar_insumo_de_derivacao_como_fixture),
    ("R02", trocar_territorio_por("XX")), ("R03", duplicar_primeira_linha),
    ("R04", valor_nulo_com_tipo_observado), ("R05", ano_antes_do_inicio),
    ("R06", valor_negativo_com_min_zero), ("R07", ne_diferente_da_soma_das_ufs),
    ("R08", per_capita_ne_divergente), ("R09", coleta_id_inexistente), ("R10", falha_de_ficha)])
def test_regra_bloqueia(regra, quebra):
    r = validar(**quebra(cenario()))
    assert not r.aprovado and regra in {f.regra for f in r.erros}

def test_r07_ignora_ano_com_uf_faltando():
    r = validar(**remover_uf_de_um_ano(cenario(), "BA", 2003))
    assert "R07" not in {f.regra for f in r.erros}

def test_r01_nao_tem_como_desligar():
    assert set(inspect.signature(validar).parameters) == {
        "base", "derivados", "fichas", "falhas_fichas", "territorios", "coletas", "derivacoes", "base_publicada", "hoje"}
```

- [ ] **Passo 2: rodar e confirmar a falha** — `python -m pytest testes/test_validacao.py -v` → FALHA.
- [ ] **Passo 3: implementar** uma função privada por regra, chamadas em sequência por `validar`.
- [ ] **Passo 4: rodar e confirmar que passa** — mesmo comando → PASSA.
- [ ] **Passo 5: commit** — `git commit -m "feat(nordeste): regras de validação que bloqueiam a publicação"`

---

### Tarefa 10: Avisos (A01–A03)

**Arquivos:**
- Modificar: `src/nordeste/validacao.py`
- Teste: `testes/test_avisos.py`

**Interfaces:**
- Consome: `proxima_publicacao` (Tarefa 8).
- Produz: `validar` passa a preencher `avisos`.
  - `A01`: variação entre observações consecutivas da mesma série e território acima de `ficha.limiar_salto_pct` por cento.
  - `A02`: contagem de valores alterados em relação a `base_publicada` (mensagem `"<n> valores alterados"`).
  - `A03`: série com `fim` nulo cujo `proxima_publicacao(último ano do NE)` já passou em relação a `hoje`.

- [ ] **Passo 1: escrever os testes que falham**

```python
def test_a01_salto():
    r = validar(**cenario_com_valores_ne({2002: 100, 2003: 200}))  # limiar padrão 50
    assert any(a.regra == "A01" for a in r.avisos) and r.aprovado

def test_a02_alteracoes():
    c = cenario(); c["base_publicada"] = c["base"].assign(valor=c["base"].valor + 1)
    assert any(a.regra == "A02" and a.mensagem.startswith(f"{len(c['base'])} valores") for a in validar(**c).avisos)

def test_a03_atraso_so_em_serie_em_curso():
    assert any(a.regra == "A03" for a in validar(**cenario(fim=None, ultimo_ano=2020, hoje=date(2026, 11, 1))).avisos)
    assert not any(a.regra == "A03" for a in validar(**cenario(fim=2020, ultimo_ano=2020, hoje=date(2026, 11, 1))).avisos)
```

- [ ] **Passo 2: rodar e confirmar a falha** — `python -m pytest testes/test_avisos.py -v` → FALHA.
- [ ] **Passo 3: implementar.**
- [ ] **Passo 4: rodar e confirmar que passa** — `python -m pytest -v` → PASSA.
- [ ] **Passo 5: commit** — `git commit -m "feat(nordeste): avisos de salto, revisão e atraso de fonte"`

---

### Tarefa 11: Publicação

**Arquivos:**
- Criar: `src/nordeste/publicacao.py`
- Teste: `testes/test_publicacao.py`

**Interfaces:**
- Consome: `validar` (Tarefas 9 e 10), `atribuir_governo` (Tarefa 2), `Pendencia` (Tarefa 6).
- Produz:
  - `class ErroPublicacao(RuntimeError)`.
  - `mudancas(nova: pd.DataFrame, publicada: pd.DataFrame | None) -> pd.DataFrame`: colunas `CHAVE_BASE + ["valor_anterior", "valor_novo", "tipo"]`, com `tipo` ∈ {`alterado`, `novo`, `removido`}.
  - `versao_completa(base, fichas, territorios, governos) -> pd.DataFrame`: base + `territorio_nome, indicador_nome, unidade, fonte, orgao, url, periodicidade, presidente, mandato, compatibilidade`.
  - `publicar(caminhos: Caminhos, hoje: date, ensaio: bool = False) -> ResultadoValidacao`. Lê `trabalho/base.csv`, `trabalho/derivados.csv` e `trabalho/pendencias.csv`; para cada pendência, reaproveita as linhas daquela série na base publicada; valida; grava `relatorios/validacao.csv` e `relatorios/mudancas.csv` sempre. Reprovado e sem ensaio → `ErroPublicacao` com as regras violadas, sem tocar em `dados/base/`. Com ensaio → devolve o resultado, sem tocar em `dados/base/`. Aprovado → grava `base_nordeste.csv` (UTF-8, `,`, `.`), `base_nordeste.parquet`, `derivados.csv` e `base_nordeste_completa.csv` (`encoding="utf-8-sig"`, `sep=";"`, `decimal=","`), tudo ordenado por chave.

- [ ] **Passo 1: escrever os testes que falham**

```python
def test_reprovado_nao_toca_na_base(trabalho_com_fixture):
    with pytest.raises(ErroPublicacao, match="R01"):
        publicar(trabalho_com_fixture, hoje=date(2026, 11, 1))
    assert not (trabalho_com_fixture.base / "base_nordeste.csv").exists()

def test_ensaio_nunca_grava_base(trabalho_aprovado):
    assert publicar(trabalho_aprovado, hoje=date(2026, 11, 1), ensaio=True).aprovado
    assert not (trabalho_aprovado.base / "base_nordeste.csv").exists()

def test_publica_e_versao_completa_para_excel(trabalho_aprovado):
    publicar(trabalho_aprovado, hoje=date(2026, 11, 1))
    bruto = (trabalho_aprovado.base / "base_nordeste_completa.csv").read_bytes()
    assert bruto.startswith(b"\xef\xbb\xbf") and b";" in bruto.splitlines()[0]
    completa = pd.read_csv(trabalho_aprovado.base / "base_nordeste_completa.csv", sep=";", decimal=",", encoding="utf-8-sig")
    assert completa.query("ano == 2016").presidente.unique().tolist() == ["transicao_dilma_temer"]
    assert "Pernambuco" in set(completa.territorio_nome)

def test_republicar_sem_mudanca_e_idempotente(trabalho_aprovado):
    publicar(trabalho_aprovado, hoje=date(2026, 11, 1)); antes = (trabalho_aprovado.base / "base_nordeste.csv").read_bytes()
    publicar(trabalho_aprovado, hoje=date(2026, 11, 1))
    assert (trabalho_aprovado.base / "base_nordeste.csv").read_bytes() == antes
    assert pd.read_csv(trabalho_aprovado.relatorios / "mudancas.csv").empty

def test_mudancas():
    m = mudancas(base_com_valor(2.0), base_com_valor(1.0))
    assert m[["valor_anterior", "valor_novo", "tipo"]].values.tolist() == [[1.0, 2.0, "alterado"]]

def test_pendencia_mantem_dado_publicado(trabalho_aprovado_com_publicacao_anterior_e_pendencia):
    ...  # a série pendente aparece na nova base com os valores da publicação anterior
```
(`trabalho_aprovado` grava em `dados/trabalho/` uma base coerente cujas coletas têm `origem="rede"`, e os registros correspondentes. `trabalho_com_fixture`, a mesma base com `origem="fixture"`.)

- [ ] **Passo 2: rodar e confirmar a falha** — `python -m pytest testes/test_publicacao.py -v` → FALHA.
- [ ] **Passo 3: implementar.**
- [ ] **Passo 4: rodar e confirmar que passa** — mesmo comando → PASSA.
- [ ] **Passo 5: commit** — `git commit -m "feat(nordeste): publicação com versão completa e relatório de mudanças"`

---

### Tarefa 12: CLI e ensaio de ponta a ponta do PIB per capita

**Arquivos:**
- Criar: `src/nordeste/cli.py`, `src/nordeste/__main__.py`
- Teste: `testes/test_ponta_a_ponta.py`

**Interfaces:**
- Consome: `coletar_serie`, `consolidar`, `brasil_fora_ne`, `metricas_convergencia`, `relatorio_cobertura`, `validar`, `publicar`.
- Produz: `cli.main(argv: list[str] | None = None) -> int`. Opções globais `--raiz PATH` (padrão: diretório `nordeste-indicadores/`) e `--hoje AAAA-MM-DD` (padrão: hoje). Subcomandos:
  - `coletar [--indicador ID] [--offline]`: coleta todas as séries; uma série com `ErroColeta` não interrompe as demais. Ao final, lista as falhas em stderr e sai com 1 se houve alguma.
  - `consolidar`: grava `trabalho/base.csv` (base + linhas `BR_FORA_NE`), `trabalho/derivados.csv`, `trabalho/pendencias.csv`, `relatorios/derivacoes.csv` e `relatorios/cobertura.csv`.
  - `validar`: grava `relatorios/validacao.csv`.
  - `publicar [--ensaio]`

  Código de saída 0 se tudo deu certo, 1 em `ErroColeta`, `ErroFicha`, `ErroPublicacao` ou validação reprovada. A mensagem vai para stderr, sem traceback.

- [ ] **Passo 1: escrever os testes que falham**

```python
def test_ponta_a_ponta_com_fixtures_e_barrado_so_pela_r01(projeto, capsys):
    raiz = ["--raiz", str(projeto.raiz), "--hoje", "2026-11-01"]
    assert main(raiz + ["coletar", "--offline"]) == 0
    assert main(raiz + ["consolidar"]) == 0
    assert main(raiz + ["publicar"]) == 1
    assert "R01" in capsys.readouterr().err
    assert not (projeto.base / "base_nordeste.csv").exists()
    erros = pd.read_csv(projeto.relatorios / "validacao.csv").query("nivel == 'erro'")
    assert set(erros.regra) == {"R01"}

def test_br_fora_ne_do_pib_per_capita(projeto):
    raiz = ["--raiz", str(projeto.raiz), "--hoje", "2026-11-01"]
    main(raiz + ["coletar", "--offline"]); main(raiz + ["consolidar"])
    b = pd.read_csv(projeto.trabalho / "base.csv")
    sel = b.query("indicador_id == 'pib_per_capita' and territorio_id == 'BR_FORA_NE' and ano == 2002")
    assert sel.valor.tolist() == [1000.0] and sel.tipo_dado.tolist() == ["derivado"]

def test_coletar_sem_fixture_sai_com_1(projeto, capsys):
    shutil.rmtree(projeto.fixtures / "pib_nominal")
    assert main(["--raiz", str(projeto.raiz), "coletar", "--offline"]) == 1
    err = capsys.readouterr().err
    assert "sem fixture para pib_nominal/scr_ref2010" in err and "Traceback" not in err
    coletados = set(ler_registro(projeto.registro_coletas).indicador_id)
    assert {"pib_per_capita", "populacao_contas_regionais"} <= coletados
```

- [ ] **Passo 2: rodar e confirmar a falha** — `python -m pytest testes/test_ponta_a_ponta.py -v` → FALHA.
- [ ] **Passo 3: implementar.**
- [ ] **Passo 4: rodar e confirmar que passa** — `python -m pytest -v` → todos PASSAM.
- [ ] **Passo 5: commit** — `git commit -m "feat(nordeste): CLI e ensaio de ponta a ponta do PIB per capita"`

**Ponto de controle:** ao fim desta tarefa, relatar ao usuário o estado do pipeline antes de seguir para as fichas restantes.

---

### Tarefa 13: Coletor Ipeadata e padronizadores de planilha e Ipeadata

**Arquivos:**
- Criar: `src/nordeste/coletores/ipeadata.py`, `src/nordeste/padronizacao/planilha.py`, `src/nordeste/padronizacao/ipeadata.py`; ampliar `testes/fixtures/gerar_fixtures.py` com geradores `xlsx` e `ipeadata`
- Teste: `testes/test_padronizacao_planilha.py`, `testes/test_padronizacao_ipeadata.py`

**Interfaces:**
- Produz:
  - `ipeadata.url_ipeadata(parametros: dict) -> str` = `f"https://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='{codigo}')"`.
  - `padronizar_ipeadata(conteudo, ficha, serie, coleta_id, territorios) -> pd.DataFrame`: lê `{"value": [{"VALDATA", "VALVALOR", "NIVNOME", "TERCODIGO"}]}`; `NIVNOME` `"Brasil"`→n1 com código `"1"`, `"Regiões"`→n2, `"Estados"`→n3; `ano = int(VALDATA[:4])`; `VALVALOR` nulo → `indisponivel`.
  - `padronizar_planilha(conteudo, ficha, serie, coleta_id, territorios) -> pd.DataFrame`. Parâmetros: `formato` (`xlsx` | `csv`), `arquivo_no_zip` (opcional), `aba`, `linha_cabecalho` (contada a partir de 1), `coluna_territorio` (nomes casados por `territorio_por_nome`), `colunas`: lista de `{coluna, ano, subindicador?, etapa?, rede?}`. Coluna ausente → `ErroLayout` citando arquivo, aba e coluna.
  - `numero_br(texto) -> float | None`: `"1.234,5"`→1234.5; `"-"`, `"--"`, `"..."`, `"…"`, `"x"`, `"X"`, `""`, `"n/d"` → `None`.

- [ ] **Passo 1: escrever os testes que falham**

```python
@pytest.mark.parametrize("entrada,esperado", [("1.234,5", 1234.5), ("12", 12.0), (3.5, 3.5),
                                              ("-", None), ("--", None), ("...", None), ("…", None), ("x", None), ("", None)])
def test_numero_br(entrada, esperado):
    assert numero_br(entrada) == esperado

def test_planilha_xlsx_por_nome_de_territorio(projeto, ficha_planilha, territorios):
    df = padronizar_planilha(xlsx_sintetico(), ficha_planilha, ficha_planilha.series[0], "c1", territorios)
    assert df.query("territorio_id == 'PI' and ano == 2019").valor.tolist() == [99999.0]
    assert df.query("valor.isna()").tipo_dado.unique().tolist() == ["indisponivel"]

def test_planilha_dentro_de_zip(...): ...  # mesmo resultado com arquivo_no_zip

def test_planilha_coluna_ausente(ficha_planilha, territorios):
    with pytest.raises(ErroLayout, match="IDEB 2023"):
        padronizar_planilha(xlsx_sem_coluna("IDEB 2023"), ficha_planilha, ficha_planilha.series[0], "c1", territorios)

def test_ipeadata(fichas, territorios):
    df = padronizar_ipeadata(json_ipea([("Regiões", "2", "2001-01-01T00:00:00-02:00", 99999.0),
                                        ("Brasil", "", "2001-01-01T00:00:00-02:00", None)]), ...)
    assert df.set_index("territorio_id").tipo_dado.to_dict() == {"NE": "observado", "BR": "indisponivel"}
```

- [ ] **Passo 2: rodar e confirmar a falha** — `python -m pytest testes/test_padronizacao_planilha.py testes/test_padronizacao_ipeadata.py -v` → FALHA.
- [ ] **Passo 3: implementar** e registrar `planilha` e `ipeadata` no despachante da Tarefa 5 e em `coletar_serie`.
- [ ] **Passo 4: rodar e confirmar que passa** — `python -m pytest -v` → PASSA.
- [ ] **Passo 5: commit** — `git commit -m "feat(nordeste): coletor Ipeadata e padronizadores de planilha e Ipeadata"`

---

### Tarefas 14, 15 e 16: Dicionário (fichas verificadas e fixtures)

Uma tarefa por bloco de fonte, todas com a mesma estrutura:

| Tarefa | Fichas (`indicador_id`) | Fichas auxiliares necessárias |
|---|---|---|
| 14 — IBGE e Ipeadata | `populacao`, `pib_volume`, `pib_participacao`, `renda_dom_pc`, `pobreza`, `gini`, `desocupacao`, `informalidade`, `rendimento_trabalho` | `pib_precos_ano_anterior` (para `razao_encadeada`), `desocupados`, `forca_trabalho`; contagens de pobres e de informais, se publicadas por UF |
| 15 — INEP | `matriculas_basica`, `ideb`, `abandono_em`, `superior` | — |
| 16 — PNUD | `idhm` | — |

**Arquivos (cada tarefa):** `metadados/indicadores/<id>.yaml`, fixtures geradas por `gerar_fixtures.py`, `docs/dicionario-verificacao.md` (uma seção por série).

**Interfaces:** consome `Ficha` (Tarefa 3), padronizadores (Tarefas 5 e 13). Não cria código novo, exceto se a fonte exigir um formato que nenhum padronizador cobre. Nesse caso, parar e relatar.

- [ ] **Passo 1: pesquisar cada série na fonte oficial**, com WebSearch e o agente web-fetch, e registrar em `docs/dicionario-verificacao.md`: cobertura confirmada (início e fim), URL da página oficial consultada, parâmetros de coleta (tabela e variável do SIDRA, código Ipeadata, URL do arquivo, aba e colunas) e se o "Brasil fora do NE" é exato, conforme a coluna "Comparação" da seção 4 da spec.
- [ ] **Passo 2: escrever as fichas.** `verificado: true` somente quando os parâmetros foram confirmados em página oficial citada no passo 1. Nos demais casos, `verificado: false` e `parametros` com o que se sabe. Comparação, `sentido`, `limites`, `defasagem_meses` e `series` seguem a seção 4 da spec e o resultado da pesquisa.
- [ ] **Passo 3: gerar as fixtures** com valores derivados de 99999, coerentes entre si (somas das UFs e regiões fecham; razões batem com os insumos).
- [ ] **Passo 4: rodar o ensaio** — `python -m pytest -v` e `python -m nordeste --raiz <tmp com cópia> coletar --offline && ... consolidar && ... publicar --ensaio`. Esperado: testes PASSAM, e o ensaio reprova **somente** por R01.
- [ ] **Passo 5: commit** — `git commit -m "feat(nordeste): fichas verificadas do bloco <fonte>"`
- [ ] **Passo 6: relatar divergências** entre a cobertura confirmada e a seção 4 da spec, para o controlador repassar ao usuário.

---

### Tarefa 17: Testes de contrato com as fontes reais e README

**Arquivos:**
- Criar: `testes/contrato/test_fontes_reais.py`, `README.md`

**Interfaces:** consome `carregar_fichas`, `coletar_serie`, `padronizar`.

- [ ] **Passo 1: escrever os testes de contrato** — marcados com `@pytest.mark.rede` e parametrizados por toda série com `verificado: true`. Cada teste coleta com `offline=False` em diretório temporário, padroniza e verifica `{"BR", "NE"} <= set(df.territorio_id)` e `df.ano.min() <= serie.inicio`.
- [ ] **Passo 2: confirmar que ficam fora da execução padrão** — `python -m pytest -v` → os testes de contrato aparecem como *deselected*. `python -m pytest -m rede -v` → falham com `ErroColeta` enquanto a rede estiver bloqueada (resultado esperado neste ambiente).
- [ ] **Passo 3: escrever o `README.md`** — instalação, os quatro comandos, o que é a regra R01 e por que não pode ser desligada, a lista de domínios da seção 10 da spec, o aviso de que `coletar --offline` no repositório grava coletas de fixture no registro, e o roteiro da primeira coleta real (liberar domínios → `pytest -m rede` → ajustar padronizadores → `coletar` → `consolidar` → `publicar --ensaio` → `publicar`).
- [ ] **Passo 4: rodar tudo** — `python -m pytest -v` → PASSA.
- [ ] **Passo 5: commit** — `git commit -m "test(nordeste): testes de contrato com fontes reais e README"`
