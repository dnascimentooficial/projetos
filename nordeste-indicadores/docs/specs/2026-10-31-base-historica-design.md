# Base histórica de indicadores do Nordeste (2000–2026) — Design

**Subprojeto 1 de 3** · Data: 2026-10-31 · Status: aguardando revisão

## 1. Contexto e objetivo

O projeto "Indicadores do Nordeste, 2000 a 2026" tem três produtos: uma base histórica documentada, uma camada analítica com gráficos e uma dashboard pública. Foi dividido em três subprojetos, cada um com spec e plano próprios:

1. **Base histórica** (este documento): dicionário, metadados, tabela de governos, coletores, padronização, derivados, validação e publicação dos arquivos.
2. **Camada analítica**: gráficos exploratórios e leituras de convergência sobre a base.
3. **Dashboard**: narrativa guiada na frente e exploração com filtros atrás.

Os subprojetos 2 e 3 estão fora do escopo deste documento.

**Pergunta central do estudo:** a distância entre o Nordeste e o resto do país diminuiu, em quais indicadores e em quais períodos?

**Público:** geral (LinkedIn, newsletter, imprensa). Consequências para a base:

- Todo número precisa ser reprodutível a partir da fonte oficial.
- Toda mudança de número precisa ficar registrada.
- Dado de teste nunca pode chegar à base publicada.
- As faixas de governo são marco temporal, nunca explicação causal.

**Critério de sucesso:** qualquer pessoa consegue, para qualquer número da base, identificar a fonte, a data de coleta, o trecho de série a que ele pertence e as rupturas metodológicas, e consegue refazer o número a partir da fonte oficial.

## 2. Decisões tomadas

| Tema | Decisão |
|---|---|
| Escopo da primeira entrega | 15 indicadores (seção 4) |
| Comparação principal | "Brasil fora do Nordeste" onde o cálculo é exato; Brasil total nos demais |
| Categorias de dado | `observado`, `estimativa_oficial`, `derivado`, `indisponivel` |
| Arquitetura | Pipeline Python com arquivos versionados no Git, sem servidor |
| Acesso às fontes | Rede bloqueada no ambiente atual. Estrutura e testes com arquivos sintéticos agora; coleta real depois |
| Local no repositório | Pasta `nordeste-indicadores/` |
| Periodicidade | Somente anual nesta entrega |
| Valores monetários | Nunca em real corrente em série longa: razão/índice ou reais constantes com deflator declarado |
| Governos | Datas reais, incluindo a interinidade de Temer em 2016; ano de 2016 marcado como "transição" |

## 3. Princípios

1. **Sem interpolação e sem projeção.** Ano sem dado oficial fica sem valor.
2. **Ruptura é dado estruturado.** Cada trecho comparável tem um `serie_id`. Nenhuma linha de gráfico ou métrica atravessa dois `serie_id`.
3. **Falhar alto, nunca adivinhar.** Formato inesperado interrompe o processo com mensagem clara.
4. **Nada digitado à mão que possa ser gerado.** Datas de coleta, último ano disponível e versão completa para download são produzidos pelo pipeline.
5. **Causalidade política fora da base.** A base registra governos para cruzamento temporal; não contém nenhum campo de interpretação.

## 4. Indicadores da primeira entrega

As coberturas abaixo são a leitura inicial das bases. A primeira tarefa da implementação é confirmá-las na fonte oficial e registrar o resultado nas fichas; qualquer divergência é comunicada antes de seguir.

| # | Eixo | `indicador_id` | Indicador | Séries previstas (`serie_id`, cobertura aproximada) | Fonte | Comparação |
|---|---|---|---|---|---|---|
| 1 | Contexto | `populacao` | População residente | estimativas e censos IBGE, 2000+ | IBGE | Brasil fora do NE |
| 2 | Economia | `pib_volume` | PIB real, índice de volume | `scr_ref2010`, 2002–2023 | IBGE, Contas Regionais | Brasil fora do NE, se a fonte publicar PIB a preços do ano anterior por região; senão Brasil |
| 3 | Economia | `pib_per_capita` | PIB per capita | `scr_ref2010`, 2002–2023 | IBGE, Contas Regionais | Brasil fora do NE |
| 4 | Economia | `pib_participacao` | Participação do NE no PIB nacional | `scr_ref2010`, 2002–2023 | IBGE, Contas Regionais | `nenhuma` (a participação já é relativa) |
| 5 | Social | `idhm` | IDHM e componentes (renda, educação, longevidade) | `censo` (2000, 2010); `pnadc` (2012–2024) | PNUD/Ipea/FJP | Brasil |
| 6 | Social | `renda_dom_pc` | Renda domiciliar per capita | `pnad` (2001–2015); `pnadc` (2012+) | IBGE/Ipea | Brasil fora do NE, se houver totais publicados; senão Brasil |
| 7 | Social | `pobreza` | Pobreza e extrema pobreza (subindicadores) | `pnad`; `pnadc` | IBGE (SIS)/Ipea | Brasil fora do NE, se houver contagens absolutas por UF; senão Brasil |
| 8 | Social | `gini` | Índice de Gini da renda domiciliar per capita | `pnad`; `pnadc` | IBGE/Ipea | Brasil |
| 9 | Trabalho | `desocupacao` | Taxa de desocupação | `pnad` (2001–2015); `pnadc` (2012+) | IBGE | Brasil fora do NE (desocupados ÷ força de trabalho) |
| 10 | Trabalho | `informalidade` | Taxa de informalidade | `pnadc` (≈2016+) | IBGE | Brasil fora do NE, se houver contagens; senão Brasil |
| 11 | Trabalho | `rendimento_trabalho` | Rendimento médio real do trabalho | `pnadc` (2012+) | IBGE | Brasil |
| 12 | Educação básica | `matriculas_basica` | Matrículas por etapa e rede | `educacenso` (2007+); `censo_escolar_pre2007` (2000–2006) | INEP | Brasil fora do NE |
| 13 | Educação básica | `ideb` | IDEB anos iniciais, anos finais, ensino médio | `ideb` (2005–2023, bienal) | INEP | Brasil |
| 14 | Educação básica | `abandono_em` | Taxa de abandono no ensino médio | `indicadores_inep` (2007+) | INEP | Brasil |
| 15 | Educação superior | `superior` | Matrículas (pública/privada) e número de universidades vs. IES | `censup_pre2009`; `censup` (2009+) | INEP | Brasil fora do NE |

Segunda leva, fora desta entrega: SAEB detalhado, PIB por setor, estabelecimentos e infraestrutura escolar, pós-graduação (CAPES), RAIS e Novo Caged, expectativa de vida, mortalidade infantil, saneamento.

## 5. Arquitetura

### 5.1 Estrutura de pastas

```
nordeste-indicadores/
├── metadados/
│   ├── indicadores/          # uma ficha YAML por indicador
│   ├── territorios.csv
│   └── governos.csv
├── src/nordeste/
│   ├── coletores/            # sidra, ibge_arquivos, inep, ipeadata, pnud
│   ├── padronizacao/         # um padronizador por formato de fonte
│   ├── consolidacao.py
│   ├── derivados.py
│   ├── validacao.py
│   └── cli.py
├── dados/
│   ├── brutos/               # cache de downloads (fora do Git)
│   ├── base/                 # arquivos publicados (versionados)
│   └── relatorios/           # coletas, cobertura, validação, mudanças
├── testes/
│   └── fixtures/             # arquivos sintéticos (valores 99999)
└── docs/specs/
```

### 5.2 Componentes e contratos

| Componente | Entrada | Saída | Não faz |
|---|---|---|---|
| Coletor | Parâmetros da série na ficha | Arquivo bruto no cache + registro de coleta (data, URL, hash SHA-256, origem: `rede`, `cache` ou `fixture`) | Não interpreta conteúdo |
| Padronizador | Arquivo bruto + ficha | Tabela no formato da base (seção 6.1) | Não calcula derivados |
| Consolidação | Tabelas padronizadas | Base longa única | Não conhece fontes |
| Derivados | Base longa + fichas | Linhas `BR_FORA_NE` na base + `derivados.csv` | Não atravessa `serie_id` |
| Validação | Base, derivados, fichas, registro de coletas | Relatório; aprovação ou bloqueio | Não corrige dados |
| Publicação | Artefatos validados | Arquivos em `dados/base/` + relatório de mudanças | Não roda sem validação aprovada |

A ficha YAML comanda o pipeline: cada série declara `coletor` e `parametros`. Incluir um indicador exige uma ficha e, se o formato for novo, um padronizador.

### 5.3 Comandos

```
python -m nordeste coletar   [--indicador ID] [--offline]
python -m nordeste consolidar
python -m nordeste validar
python -m nordeste publicar  [--ensaio]
```

- `--offline` usa apenas cache e fixtures.
- `--ensaio` executa tudo e gera relatórios, sem escrever em `dados/base/`.
- Cada comando é idempotente.

### 5.4 Tecnologia

Python 3.12; dependências: `pandas`, `pyarrow`, `pyyaml`, `requests`, `pytest`. Sem framework.

## 6. Modelo de dados

### 6.1 Base principal — `dados/base/base_nordeste.csv` e `.parquet`

| Coluna | Tipo | Obrigatória | Descrição |
|---|---|---|---|
| `indicador_id` | texto | sim | Chave da ficha |
| `subindicador` | texto | não | Componente do IDHM, linha de pobreza, universidade/IES etc. |
| `etapa` | texto | não | Etapa de ensino |
| `rede` | texto | não | `total`, `publica`, `privada`, `federal`, `estadual`, `municipal` |
| `territorio_id` | texto | sim | Chave de `territorios.csv` |
| `ano` | inteiro | sim | Ano de referência |
| `valor` | decimal | condicional | Vazio somente quando `tipo_dado = indisponivel` |
| `tipo_dado` | texto | sim | `observado`, `estimativa_oficial`, `derivado`, `indisponivel` |
| `serie_id` | texto | sim | Trecho comparável, declarado na ficha |
| `coleta_id` | texto | sim | Chave do registro de coletas; para `derivado`, chave do registro de derivação, que lista os `coleta_id` dos insumos |
| `nota` | texto | não | Observação específica do ponto |

Chave única: (`indicador_id`, `subindicador`, `etapa`, `rede`, `territorio_id`, `ano`, `serie_id`).

Linhas `indisponivel` existem apenas para anos dentro da cobertura da série (ex.: PNAD 2010, ano de Censo).

### 6.2 Ficha do indicador — `metadados/indicadores/<indicador_id>.yaml`

Campos obrigatórios: `id`, `nome`, `descricao`, `eixo`, `categoria`, `unidade`, `orgao`, `periodicidade`, `metodologia`, `observacoes`, `sentido` (`maior_melhor` | `menor_melhor`), `limites` (mínimo e máximo plausíveis), `comparacao`, `defasagem_meses`, `tratamento_monetario` (quando a unidade for monetária), `series`.

Cada item de `series`: `id`, `inicio`, `fim`, `fonte`, `base_origem`, `url`, `coletor`, `parametros`, `compatibilidade` (texto sobre comparabilidade com as demais séries).

`comparacao`: `brasil`, `brasil_fora_ne` ou `nenhuma`. Quando `brasil_fora_ne`, declara `metodo` (`soma` ou `razao`) e, para `razao`, os indicadores ou variáveis de `numerador` e `denominador`. O índice de volume do PIB usa `razao` com numerador = PIB do ano a preços do ano anterior e denominador = PIB nominal do ano anterior, encadeado a partir do primeiro ano da série.

`tratamento_monetario`: `razao` (exibido como NE/referência) ou `reais_constantes` com `deflator` e `ano_base`.

Exemplo de estrutura (parâmetros de coleta a confirmar na tarefa de dicionário):

```yaml
id: pib_per_capita
nome: PIB per capita
eixo: economia
unidade: R$ correntes
sentido: maior_melhor
limites: {min: 0}
defasagem_meses: 23
tratamento_monetario: {modo: razao}
comparacao:
  referencia: brasil_fora_ne
  metodo: razao
  numerador: pib_nominal
  denominador: populacao_contas_regionais
series:
  - id: scr_ref2010
    inicio: 2002
    fim: 2023
    fonte: IBGE, Sistema de Contas Regionais (referência 2010)
    coletor: sidra
    parametros: {}   # tabela e variável confirmadas na implementação
    compatibilidade: Não comparável com a série referência 2002 (2000–2001).
```

Campos gerados pelo pipeline, nunca digitados: data de extração e último ano disponível (em `dados/relatorios/`).

### 6.3 Governos — `metadados/governos.csv`

Colunas: `presidente`, `inicio`, `fim`, `mandato`, `interino`, `partido` (vazio nesta entrega).

| presidente | inicio | fim | mandato | interino |
|---|---|---|---|---|
| Fernando Henrique Cardoso | 1999-01-01 | 2002-12-31 | 2 | não |
| Luiz Inácio Lula da Silva | 2003-01-01 | 2006-12-31 | 1 | não |
| Luiz Inácio Lula da Silva | 2007-01-01 | 2010-12-31 | 2 | não |
| Dilma Rousseff | 2011-01-01 | 2014-12-31 | 1 | não |
| Dilma Rousseff | 2015-01-01 | 2016-05-12 | 2 | não |
| Michel Temer | 2016-05-12 | 2016-08-31 | — | sim |
| Michel Temer | 2016-08-31 | 2018-12-31 | — | não |
| Jair Bolsonaro | 2019-01-01 | 2022-12-31 | 1 | não |
| Luiz Inácio Lula da Silva | 2023-01-01 | 2026-12-31 | 3 | não |

Regra anual: o ano pertence ao governo que ocupou a Presidência o ano inteiro. O ano de 2016 recebe o rótulo `transicao_dilma_temer`. A atribuição é feita por cruzamento na publicação, não gravada na base principal.

### 6.4 Territórios — `metadados/territorios.csv`

Colunas: `territorio_id`, `nome`, `tipo` (`pais`, `regiao`, `uf`, `agregado_derivado`), `codigo_ibge`, `regiao_id`.

16 linhas (Brasil, 5 regiões, 9 UFs, 1 agregado derivado): `BR`, `N`, `NE`, `SE`, `S`, `CO`, `MA`, `PI`, `CE`, `RN`, `PB`, `PE`, `AL`, `SE_UF`, `BA`, `BR_FORA_NE`.

A sigla da UF Sergipe colide com a da região Sudeste: a UF usa `SE_UF` e a região usa `SE`.

### 6.5 Versão completa para download — `dados/base/base_nordeste_completa.csv`

Gerada na publicação. Junta à base principal: nome do território, nome do indicador, unidade, fonte, órgão, URL, periodicidade, presidente e mandato (ou `transicao_dilma_temer`), nota metodológica da série e status de comparabilidade. Nunca é editada à mão.

## 7. Fluxo e derivados

```
coletar → padronizar → consolidar → derivar → validar → publicar
```

### 7.1 Brasil fora do Nordeste

- `metodo: soma` → `valor(BR) − valor(NE)`.
- `metodo: razao` → `(num(BR) − num(NE)) ÷ (den(BR) − den(NE))`.
- O denominador é sempre a variável usada pela própria fonte (ex.: população publicada com as Contas Regionais).
- Indicadores sem método exato (IDHM, IDEB, Gini e os que dependerem de contagens não publicadas) não recebem `BR_FORA_NE`.
- Linhas resultantes: `territorio_id = BR_FORA_NE`, `tipo_dado = derivado`.

### 7.2 Métricas de convergência — `dados/base/derivados.csv`

Colunas: `indicador_id`, `subindicador`, `etapa`, `rede`, `metrica`, `referencia`, `territorio_id`, `ano`, `valor`, `serie_id`.

| `metrica` | Definição |
|---|---|
| `razao` | valor(território) ÷ valor(referência) × 100 |
| `diferenca` | valor(território) − valor(referência) |
| `variacao_acumulada` | valor(ano) ÷ valor(primeiro ano da série) − 1 |
| `crescimento_relativo` | variação entre observações consecutivas do território − a mesma variação da referência (para séries bienais, como o IDEB, a variação é entre edições) |
| `posicao_regioes` | posição do NE entre as 5 regiões, conforme `sentido` |
| `dispersao_ufs` | coeficiente de variação entre as 9 UFs (território `NE`) |

Regras:

- Todas as métricas são calculadas dentro de um único `serie_id`; o código rejeita cálculos entre séries.
- `referencia` segue o campo `comparacao` da ficha.
- A razão é a métrica principal para comunicação ao público.

### 7.3 Relatório de cobertura — `dados/relatorios/cobertura.csv`

Por indicador, série e território: primeiro ano, último ano, anos faltantes, próxima publicação esperada, isto é, a do ano seguinte ao último disponível (dezembro de último ano + 1, mais `defasagem_meses`).

## 8. Validação e erros

### 8.1 Regras bloqueantes

1. Nenhuma linha com coleta de origem `fixture`. Sem opção de desligar.
2. Esquema: colunas, tipos, domínio de `tipo_dado`, `territorio_id` e `indicador_id` existentes.
3. Chave única sem duplicatas.
4. `valor` vazio ⇔ `tipo_dado = indisponivel`.
5. `ano` dentro da cobertura da série.
6. `valor` dentro dos `limites` da ficha.
7. Para indicadores com `comparacao.metodo = soma`: soma das 9 UFs = NE e soma das 5 regiões = BR, tolerância 0,5%.
8. PIB per capita do NE recalculado pela fórmula de razão a até 0,5% do valor oficial.
9. Todo `coleta_id` existe no registro de coletas ou no registro de derivação.
10. Fichas com todos os campos obrigatórios.

### 8.2 Avisos

- Variação anual muito acima do histórico do indicador (limiar configurável na ficha).
- Valores alterados em relação à última base publicada → `dados/relatorios/mudancas.csv`.
- Fonte sem dado novo após a data esperada de publicação.

### 8.3 Erros de coleta

- Falha de rede: 3 novas tentativas com intervalo crescente. Persistindo, o indicador mantém os dados publicados anteriormente e a falha vai para o relatório; os demais seguem.
- Layout inesperado: o padronizador interrompe com mensagem indicando arquivo, aba e coluna esperados.

## 9. Testes

- **Padronizadores:** fixtures sintéticas no formato documentado de cada fonte, valores 99999.
- **Derivados:** casos com resultado calculado à mão (ex.: BR = 10, NE = 4 → 6; razão (100 − 30) ÷ (50 − 10) = 1,75); teste de recusa de cálculo entre séries.
- **Validação:** uma base quebrada por regra, provando o bloqueio.
- **Governos:** 2016 como transição; período interino; cada ano de 2000 a 2026 atribuído a exatamente um rótulo.
- **Ponta a ponta com fixtures:** o pipeline deve falhar na regra 1. Passar seria defeito.
- **Contrato com fontes reais:** marcados com `pytest -m rede`, fora da execução padrão; rodam quando a rede for liberada.

## 10. Definição de pronto

Concluído neste subprojeto:

- Estrutura, 15 fichas, `territorios.csv`, `governos.csv`, coletores, padronizadores, derivados, validação, publicação e CLI.
- Todos os testes padrão passando.
- `dados/base/` sem dados publicados.

Pendente, dependente de liberação de rede (domínios: `apisidra.ibge.gov.br`, `servicodados.ibge.gov.br`, `ftp.ibge.gov.br`, `download.inep.gov.br`, `www.gov.br`, `www.ipeadata.gov.br`, `www.atlasbrasil.org.br`, `www.undp.org`):

- Rodar testes de contrato, ajustar padronizadores e realizar a primeira publicação.

## 11. Riscos

| Risco | Mitigação |
|---|---|
| Formato real das fontes difere do documentado | Padronizadores isolados; testes de contrato antes da primeira publicação |
| Dado de teste publicado | Regra bloqueante 1 + teste de ponta a ponta que exige a falha |
| Leitura causal das faixas de governo | Base sem campos interpretativos; regra de 2016; datas reais de interinidade |
| Revisões silenciosas das fontes | Hash por arquivo e relatório de mudanças |
| Formato da ficha mal definido | Implementação começa com um indicador de ponta a ponta (PIB per capita) antes dos demais |
| Microdados pesados esgotam disco | Uso de arquivos agregados (SIDRA, Sinopses, planilhas IDEB) nesta entrega |
