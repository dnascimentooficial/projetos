# Dicionário de indicadores: verificação das séries

Registro, série a série, do que foi confirmado na fonte. Uma série só vira `verificado: true` quando
a resposta da fonte foi baixada de verdade com exatamente os parâmetros da ficha, passou pelo
padronizador do projeto e trouxe Brasil, as 5 regiões, o Nordeste e as 9 UFs nos anos declarados.
Sem isso, a ficha fica `verificado: false` e o motivo está aqui.

Método de cada verificação: `coletar_serie(..., offline=False)` (coletor do projeto, que monta a URL
a partir dos `parametros` da ficha), seguido de `padronizar` e de `consolidar` + `validar` sobre os
arquivos baixados, numa raiz temporária fora do repositório. Os arquivos baixados não são
versionados. Na `validar`, nenhuma regra (inclusive R07, soma das UFs e das regiões, tolerância de
0,5%) nem aviso A01 disparou com os dados reais.

Observação sobre a página de descrição das tabelas do SIDRA
(`apisidra.ibge.gov.br/desctabapi.aspx?c=<tabela>`): ela responde com um desafio anti-robô e não foi
consultada. Variáveis e classificações foram lidas nos cabeçalhos e nos valores devolvidos pela API
de valores (`/values/t/<tabela>/.../v/all`), que é a própria fonte dos dados.

Bloco IBGE, partes A (população e PIB) e C (`pib_volume`, planilha `.xls`), Tarefa 14d (`pib_per_capita` calculado
pelo projeto e conferido contra valores publicados) e parte B (renda, pobreza, Gini, desocupação, informalidade e
rendimento do trabalho, PNAD antiga e PNAD Contínua). Data de todas as verificações: 2026-11-01.

Reverificação de ponta a ponta, na mesma data, por outro executor: `python -m nordeste --raiz <tmp> coletar --indicador <id>`
(rede, só séries `verificado: true`), `consolidar` e `validar` sobre `populacao`, `pib_nominal` e `pib_participacao`.
Resultado: as 6 séries coletaram com os parâmetros das fichas, `validar` saiu com código 0 e sem nenhuma linha em
`validacao.csv` (nem regra bloqueante, nem aviso). `pib_per_capita` e `populacao_contas_regionais` ficaram como
"série pendente: sem coleta", como esperado de séries não verificadas (situação anterior à Tarefa 14d, que tornou o
`pib_per_capita` um cálculo do projeto e removeu a `populacao_contas_regionais`).

## Resumo

| Indicador | Série | Tabela e variável | Cobertura confirmada | Verificada |
|---|---|---|---|---|
| `pib_nominal` (auxiliar) | `scr_ref2010` | SIDRA 5938, v37 | 2002 a 2023 | sim |
| `pib_participacao` | `scr_ref2010` | SIDRA 5938, v496 | 2002 a 2023 | sim |
| `populacao` | `estimativa_pre_censo2022` | SIDRA 6579, v9324 | 2001 a 2021, sem 2007 e 2010 | sim |
| `populacao` | `estimativa_pos_censo2022` | SIDRA 6579, v9324 | 2024 a 2026 | sim |
| `populacao` | `censo_2000_2010` | SIDRA 202, v93 | 2000 e 2010 | sim |
| `populacao` | `censo_2022` | SIDRA 4709, v93 | 2022 | sim |
| `pib_per_capita` | `scr_ref2010` | cálculo do projeto: SIDRA 5938 v37 ÷ população (6579 v9324; 202 e 4709 v93) × 1000 | 2002 a 2023, sem 2007 | sim (32 pontos conferidos em 2002, 2010, 2013-2018 e 2021-2023; 2003-2009 sem conferência) |
| `pib_volume` | `scr_ref2010` | `tab03.xls` (aba `Tabela3`) de `Especiais_2002_2023_xls.zip` | 2002 a 2023 | sim |
| `renda_dom_pc` | `pnadc` | SIDRA 7533, v10816 | 2012 a 2025 | sim |
| `massa_renda_dom_pc` (auxiliar) | `pnadc` | SIDRA 7427, v10495 | 2012 a 2025 | sim |
| `populacao_pnadc` (auxiliar) | `pnadc` | SIDRA 7436, v606 | 2012 a 2025 | sim |
| `pobreza` | `pnadc` | SIDRA 5877, v9948 | 2012 a 2024 | **não** (linha de pobreza não confirmada) |
| `extrema_pobreza` | `pnadc` | SIDRA 5817, v9617 | 2012 a 2024 | **não** (linha de pobreza não confirmada) |
| `gini` | `pnad` | Ipeadata `PGINI` (janela 2001-2014) | 2001 a 2014; 2010 `indisponivel` (ano sem pesquisa) | sim |
| `gini` | `pnadc` | SIDRA 7435, v10681 | 2012 a 2025 | sim |
| `desocupacao` | `pnad` | Ipeadata `Dese_Pnad` (janela 2001-2014) | 2001 a 2014; 2010 `indisponivel` (ano sem pesquisa) | sim |
| `desocupacao` | `pnadc` | SIDRA 4562, v4099 | 2012 a 2025 | sim |
| `desocupados` (auxiliar) | `pnadc` | SIDRA 10364, v4092, c2/6794 | 2012 a 2019 e 2023 a 2025 (2020 a 2022 só Brasil) | sim |
| `forca_trabalho` (auxiliar) | `pnadc` | SIDRA 10364, v4088, c2/6794 | 2012 a 2019 e 2023 a 2025 (2020 a 2022 só Brasil) | sim |
| `informalidade` | `pnadc` | SIDRA 4708, v12466 | 2016 a 2025 | sim |
| `informais` (auxiliar) | `pnadc` | SIDRA 4680, v4090, c1350/57303 | 2016 a 2025 | sim |
| `ocupados` (auxiliar) | `pnadc` | SIDRA 4680, v4090, c1350/57302 | 2016 a 2025 | sim |
| `rendimento_trabalho` | `pnadc` | SIDRA 4566, v5935 | 2012 a 2025 | sim |
| `idhm` | `censo` | Ipeadata `IDHM`, `IDHMRE`, `IDHMED`, `IDHMLO` (janela 2000-2010) | 2000 e 2010, só Brasil e 9 UFs (sem regiões e sem NE) | sim (para o subconjunto declarado) |
| `idhm` | `pnadc` | Ipeadata `IDHM`, `IDHMRE`, `IDHMED`, `IDHMLO` (janela 2012-2024) | 2012 a 2024, 15 territórios | sim (fonte Ipeadata; não cotejada com o arquivo oficial do Radar IDHM) |
| `ideb` | `ideb` | INEP, `divulgacao_regioes_ufs_ideb_2025.zip` e `divulgacao_brasil_ideb_2025.zip` (6 abas, linha "Total") | 2005 a 2025, anos ímpares, 15 territórios, 3 etapas | sim |
| `abandono_em` | `indicadores_inep` | INEP, Taxas de Rendimento Escolar, 19 zips (coluna do total do ensino médio, localização e rede "Total") | 2007 a 2025, 15 territórios | sim |
| `matriculas_basica` | `censo_escolar_pre2007` | INEP, Censo Escolar 2005 e 2006 (`.xls`, tabelas 1.1, 1.6, 1.12, 1.18 e 1.43) | 2005 e 2006, 15 territórios, 6 etapas, rede total e 4 redes | sim (só 2005 e 2006; 2000 a 2004 pendentes) |
| `matriculas_basica` | `educacenso` | INEP, Sinopses da Educação Básica 2007 a 2021 (tabelas 1.1, 1.5 e 1.14) | 2007 a 2021, 15 territórios, 8 etapas | sim (só 2007 a 2021; 2022 a 2025 pendentes) |
| `superior` | `censup_pre2009` | INEP, Sinopses da Educação Superior 2001 a 2008 (`.xls`, tabelas 1.1 e 5.1) | 2001 a 2008, 15 territórios; IES, universidades e matrículas totais | sim (só 2001 a 2008; 2000 só em PDF) |
| `superior` | `censup` | INEP, Sinopses da Educação Superior 2009 a 2019 (sinopse por município, tabelas 1.1 e 5.1) | 2009 a 2019, 15 territórios; IES, universidades e matrículas (total, pública, privada) | sim (só 2009 a 2019; 2020 a 2024 pendentes) |

## pib_nominal / scr_ref2010

- Página oficial: https://www.ibge.gov.br/estatisticas/economicas/contas-nacionais/9054-contas-regionais-do-brasil.html
- URL de coleta: `https://apisidra.ibge.gov.br/values/t/5938/n1/all/n2/all/n3/21,22,23,24,25,26,27,28,29/v/37/p/all`
- Variável 37: "Produto Interno Bruto a preços correntes", unidade Mil Reais.
- Obtido: 330 linhas = 22 anos (2002 a 2023) x 15 territórios (Brasil, 5 regiões, 9 UFs). Nenhum valor indisponível.
- Exemplo: Brasil 2023 = 10.943.345.439; Nordeste 2023 = 1.513.055.124 (R$ mil).
- Brasil fora do Nordeste: exato, por soma (BR menos NE). A soma das UFs fecha o NE e a das regiões fecha o Brasil dentro de 0,5% (R07).
- A tabela 5938 é a das Contas Regionais com os municípios; os níveis Brasil, Grande Região e UF respondem na mesma consulta.

## pib_participacao / scr_ref2010

- Página oficial: a mesma de `pib_nominal`.
- URL de coleta: `https://apisidra.ibge.gov.br/values/t/5938/n1/all/n2/all/n3/21,22,23,24,25,26,27,28,29/v/496/p/all`
- Variável 496: "Participação do produto interno bruto a preços correntes no produto interno bruto a preços correntes do Brasil", unidade %.
  As variáveis 530 (participação na grande região) e 497 (na UF) não servem: o indicador é a fatia do território no PIB nacional.
- Obtido: 330 linhas, 2002 a 2023, 15 territórios, sem valor indisponível. Brasil vale 100,00 em todos os anos.
- Exemplo: Nordeste 13,09% em 2002 e 13,83% em 2023.
- Comparação `nenhuma`, como na seção 4 da spec.

## populacao

Quatro séries, porque cada fonte tem base própria e nenhuma métrica atravessa `serie_id`:

### populacao / estimativa_pre_censo2022

- Página oficial: https://sidra.ibge.gov.br/pesquisa/estimapop/tabelas
- URL de coleta: `https://apisidra.ibge.gov.br/values/t/6579/n1/all/n2/all/n3/21,22,23,24,25,26,27,28,29/v/9324/p/2001-2021`
- Variável 9324: "População residente estimada", unidade Pessoas.
- Obtido: 285 linhas = 19 anos x 15 territórios: 2001 a 2006, 2008, 2009 e 2011 a 2021. Todos marcados `estimativa_oficial`.
- Lacunas: 2007 (Contagem), 2010 (Censo). A tabela 6579 não tem 2000 nem esses anos; não há interpolação.
- Exemplo: Brasil 2001 = 172.385.826; Nordeste 2021 = 57.667.842.
- Brasil fora do Nordeste: exato, por soma.

### populacao / estimativa_pos_censo2022

- URL de coleta: `https://apisidra.ibge.gov.br/values/t/6579/n1/all/n2/all/n3/21,22,23,24,25,26,27,28,29/v/9324/p/2024-2026`
- Obtido: 45 linhas = 3 anos (2024, 2025, 2026) x 15 territórios, todos `estimativa_oficial`. Série em curso (`fim: null`).
- A tabela 6579 não tem 2022 (Censo) nem 2023 (o IBGE não publicou estimativa).
- Exemplo: Brasil 2024 = 212.583.750 e 2026 = 214.211.951. O salto entre 2021 (213.317.639) e 2024 vem da troca da base (Censo 2022), por isso as duas estimativas são séries separadas.

### populacao / censo_2000_2010

- Página oficial: https://sidra.ibge.gov.br/tabela/202
- URL de coleta: `https://apisidra.ibge.gov.br/values/t/202/n1/all/n2/all/n3/21,22,23,24,25,26,27,28,29/v/93/p/2000,2010/c1/0/c2/0`
- Variável 93: "População residente"; classificações c1 (situação do domicílio) e c2 (sexo) fixadas em 0 (Total).
- Obtido: 30 linhas = 2 anos x 15 territórios, `observado`. Exemplo: Brasil 2000 = 169.799.170; 2010 = 190.755.799.

### populacao / censo_2022

- Página oficial: https://sidra.ibge.gov.br/pesquisa/censo-demografico/demografico-2022/primeiros-resultados-populacao-e-domicilios
- URL de coleta: `https://apisidra.ibge.gov.br/values/t/4709/n1/all/n2/all/n3/21,22,23,24,25,26,27,28,29/v/93/p/2022`
- Variável 93: "População residente" (a tabela traz também as variáveis 5936 e 10605, não usadas).
- Obtido: 15 linhas, 2022, `observado`. Exemplo: Brasil = 203.080.756; Nordeste = 54.658.515.
- A tabela 9514 (por sexo e idade) dá o mesmo total, mas exige três classificações; a 4709 dispensa.

## pib_per_capita / scr_ref2010 (calculado pelo projeto, conferido)

Tarefa 14d. Data da conferência: 2026-11-01.

O IBGE não publica o PIB per capita de regiões e UFs em formato legível por máquina (a busca está registrada
abaixo, em "Histórico"). Decisão do usuário: o projeto calcula o per capita a partir de séries oficiais já
verificadas, com a metodologia declarada como fonte, desde que o resultado seja o mesmo que o IBGE divulga.

- Ficha: `calculo: {metodo: razao_por_ano}`. Numerador `pib_nominal/scr_ref2010` (SIDRA 5938, v37, R$ mil);
  denominador `populacao`, com a série escolhida por ano; fator 1000. Não há coleta própria (`coletor: calculo`,
  sem fixture): as linhas saem do `consolidar`, com `tipo_dado = derivado`, `serie_id = scr_ref2010` e um
  `coleta_id` de derivação cujo registro (`dados/relatorios/derivacoes.csv`) lista os coleta_id do PIB e das
  populações usadas.
- Fonte declarada na série: "Cálculo do projeto com dados do IBGE: PIB a preços correntes (Contas Regionais,
  SIDRA 5938) ÷ população residente (estimativas SIDRA 6579; Censos SIDRA 202 e 4709) × 1000".
- Brasil fora do Nordeste: (PIB BR − PIB NE) ÷ (população BR − população NE) × 1000, com o mesmo mapeamento.
  Não passa pela R08 (não há valor oficial do per capita para comparar).

### Mapeamento ano → população

| Anos | População (série da ficha `populacao`) | Tabela SIDRA | Como foi deduzido |
|---|---|---|---|
| 2002 a 2006, 2008, 2009, 2011 a 2021 | estimativa do próprio ano (`estimativa_pre_censo2022`) | 6579, v9324 | conferido em 2002, 2013 a 2018 e 2021 (abaixo); 2003 a 2006, 2008, 2009, 2011, 2012, 2019 e 2020 sem conferência |
| 2010 | Censo 2010 (`censo_2000_2010`) | 202, v93 | conferido em 2010; a 6579 não tem 2010 |
| 2022 | Censo 2022 (`censo_2022`) | 4709, v93 | conferido em 2022; a 6579 não tem 2022 |
| 2023 | Censo 2022 (`censo_2022`, ano fixo 2022) | 4709, v93 | conferido em 2023; o IBGE não publicou estimativa de 2023 |
| 2007 | sem valor | | ver abaixo |

Os anos de estimativa sem conferência seguem a regra dos conferidos (estimativa do próprio ano, a única população
anual da 6579 para eles). Ponto de atenção: o PIB de 2002 a 2009 da referência 2010 é retropolado, e não se sabe
se o IBGE usou, nesses anos, as estimativas originais da 6579 ou outra população. 2002 foi conferido (Brasil e
Ceará, a até 0,003%; razão Nordeste/Brasil divulgada de 0,47, contra 0,468 no cálculo), o que sustenta as
estimativas originais. 2003 a 2009 não têm valor publicado conferido.

2007: a Contagem da População 2007 existe no SIDRA (tabela 793, variável 93, "população residente" em 1º de
abril de 2007; `https://apisidra.ibge.gov.br/values/t/793/n1/all/n2/all/n3/21,22,23,24,25,26,27,28,29/v/93/p/2007`,
consultada: Brasil 183.987.291, Nordeste 51.534.406, 15 territórios). Com ela, o per capita de 2007 seria
Brasil 14.785,06 e Nordeste 6.876,81, mas não foi achado nenhum valor publicado de 2007 na referência 2010 para
conferir (os de 2007 encontrados, Brasil R$ 14.465 e Nordeste R$ 6.749, são da referência 2002, com outro PIB).
Sem conferência, 2007 fica sem valor e a série `populacao` não ganhou a tabela 793.

### Execução real

Numa raiz temporária fora do repositório, com as fichas do repositório: `python -m nordeste --raiz <tmp> --hoje
2026-11-01 coletar` (rede: as 7 séries verificadas de `pib_nominal`, `pib_participacao`, `pib_volume` e
`populacao`, pelas URLs já registradas nas seções delas), `consolidar` e `validar`: os três com código 0 e
`validacao.csv` sem nenhuma linha (nem regra, nem aviso). `pib_per_capita` saiu com 336 linhas = 21 anos (2002 a
2023, sem 2007) × 16 territórios (BR, 5 regiões, 9 UFs e BR_FORA_NE), todas `derivado`. Exemplo: Brasil fora do
Nordeste 2023 = 63.536,91; 2010 = 24.427,86.

### Conferência contra valores publicados

Critério: diferença ≤ 0,5% em todos os pontos conferidos. Resultado: **32 pontos conferidos**, maior diferença
absoluta 0,050% (Ceará, 2010); 2021 e 2023 batem ao centavo. Diferença = (calculado − publicado) ÷ publicado.

Conferência repetível (revisão final, I7): `python -m pytest -m rede -k "per_capita or ancora"` coleta `pib_nominal` e
`populacao` da rede, refaz o cálculo e compara com os 7 pontos de fonte primária do IBGE abaixo, a até 0,5%
(`testes/contrato/test_ancoras.py`; na execução de 2026-11-01, os seis de 2023 bateram ao centavo e Maranhão 2016 deu
12.267,70 contra 12.264,28, +0,028%). O mesmo arquivo confere valores-âncora de três séries leves (IDEB NE anos iniciais
2023 = 5,6; desocupação NE `pnadc` 2012 = 9,6; participação do NE no PIB 2002 = 13,09), para pegar coluna, ano ou
território deslocado.

Natureza da evidência (ler antes da tabela):

- **Nenhum valor publicado foi baixado.** Os sites de notícias e da biblioteca do IBGE
  (`agenciadenoticias.ibge.gov.br`, `biblioteca.ibge.gov.br`, `www.ibge.gov.br`) e os demais sites citados
  (Ipea, BNB, Ipece, Fapespa, imprensa) estavam bloqueados no ambiente da conferência. Os números foram lidos nos
  trechos devolvidos pela busca na web, com as URLs abaixo.
- **Fonte primária do IBGE: 7 dos 32 pontos** (os 6 de 2023 da matéria [10] e Maranhão 2016 do release [4]).
  **Reproduções do número do IBGE: 25 pontos** (Ipea, BNB, Ipece, Fapespa, IMESC e imprensa).
- **Anos de PIB retropolado (2002 a 2009):** só 2002 foi conferido (2 pontos, ambos reproduções arredondadas
  ao real). 2003 a 2009 não têm nenhum ponto conferido; supõe-se a estimativa original da 6579 em cada ano,
  como em 2002.
- **Não contados** (marcados "ano não confirmado"): Maranhão e Piauí 2010, da tabela do Ipea [1]. O trecho
  da busca não repetiu o ano nessas linhas, e atribuir o ano pela proximidade com o próprio cálculo seria
  raciocínio circular. O Ceará 2010 desse mesmo trecho também foi descartado; o ponto do Ceará 2010 que conta
  vem do Ipece [13], com o ano explícito.

| Ano | Território | Calculado (R$) | Publicado (R$) | Diferença | Fonte do publicado | Tipo |
|---|---|---|---|---|---|---|
| 2002 | BR | 8.525,24 | 8.525 | +0,003% | [12] | reprodução |
| 2002 | CE | 3.751,87 | 3.752 | −0,003% | [13] (também "44,01% do Brasil"; cálculo: 44,009%) | reprodução |
| 2010 | BR | 20.370,79 | 20.371,64 | −0,004% | [1] (o BNB [12] dá 20.372) | reprodução |
| 2010 | NE | 9.848,34 | 9.848,97 | −0,006% | [1] | reprodução |
| 2010 | PE | 11.048,75 | 11.049,07 | −0,003% | [1] | reprodução |
| 2010 | BA | 11.016,66 | 11.012,34 | +0,039% | [1] | reprodução |
| 2010 | CE | 9.386,27 | 9.391 | −0,050% | [13] | reprodução |
| 2013 | BR | 26.521,15 | 26.521 | +0,001% | [12] | reprodução |
| 2014 | BR | 28.500,24 | 28.500 | +0,001% | [12] | reprodução |
| 2015 | BR | 29.326,42 | 29.326 | +0,001% | [12] | reprodução |
| 2016 | BR | 30.421,61 | 30.411 | +0,035% | [12] (o [2] dá R$ 30,41 mil) | reprodução |
| 2016 | NE | 15.784,01 | 15.779,11 | +0,031% | [2], [3] | reprodução |
| 2016 | CE | 15.442,63 | 15.438 | +0,030% | [3] | reprodução |
| 2016 | PE | 17.783,11 | 17.777 | +0,034% | [2] | reprodução |
| 2016 | BA | 16.936,99 | 16.931 | +0,035% | [2] | reprodução |
| 2016 | MA | 12.267,70 | 12.264,28 | +0,028% | [4] | IBGE |
| 2017 | CE | 16.398,45 | 16.398 | +0,003% | [13] | reprodução |
| 2018 | CE | 17.178,26 | 17.178 | +0,001% | [13] | reprodução |
| 2021 | BR | 42.247,52 | 42.247,52 | 0,000% | [6] (também citado como do informativo [5]) | reprodução |
| 2021 | CE | 21.090,10 | 21.090,10 | 0,000% | [6] | reprodução |
| 2021 | PE | 22.823,59 | 22.823,59 | 0,000% | [7] | reprodução |
| 2021 | BA | 23.530,94 | 23.530,94 | 0,000% | [7] | reprodução |
| 2021 | MA | 17.471,85 | 17.471,85 | 0,000% | [7] | reprodução |
| 2022 | BR | 49.633,83 | 49.638 | −0,008% | [8] | reprodução |
| 2022 | MA | 20.627,91 | 20.632,62 | −0,023% | [9] | reprodução |
| 2023 | BR | 53.886,67 | 53.886,67 | 0,000% | [10] | IBGE |
| 2023 | NE | 27.681,97 | 27.681,97 | 0,000% | [10] | IBGE |
| 2023 | CE | 26.405,96 | 26.405,96 | 0,000% | [10] | IBGE |
| 2023 | PE | 29.857,27 | 29.857,27 | 0,000% | [10] | IBGE |
| 2023 | BA | 30.476,54 | 30.476,54 | 0,000% | [10] | IBGE |
| 2023 | MA | 22.020,63 | 22.020,63 | 0,000% | [10] | IBGE |
| 2023 | RN | 30.804,91 | 30.804,91 | 0,000% | [11] | reprodução |
| 2010 | MA | 7.043,52 | 7.049,63 | (−0,087%) | [1] | **ano não confirmado, não contado** |
| 2010 | PI | 7.141,30 | 7.140,47 | (+0,012%) | [1] | **ano não confirmado, não contado** |

Cobertura mínima pedida (Brasil, Nordeste e 3 UFs do NE em 3 anos espalhados): 2010 (BR, NE, PE, BA, CE),
2016 (BR, NE, CE, PE, BA, MA) e 2023 (BR, NE, CE, PE, BA, MA).

Leitura das diferenças: 2021 e 2023 vêm da edição das Contas Regionais em que o ano é o mais recente, e o PIB
desses anos é o mesmo da tabela 5938 atual; batem exatamente. Os valores de 2010, 2016 e 2022 são de edições
anteriores (2010: série de referência 2010 divulgada em 2015 e 2016; 2016: Contas Regionais 2016, de 2018; 2022:
Contas Regionais 2022, de 2024), e o PIB desses anos foi revisado nas edições seguintes. Isso explica as
diferenças de até 0,05%. Um denominador de outra fonte daria diferenças de outra ordem (com a projeção
`POP_PROJE` do Ipeadata, cerca de 4% no Brasil em 2023).

Fontes dos valores publicados (achadas por busca na web em 2026-11-01; nenhuma pôde ser baixada nesta sessão:
`agenciadenoticias.ibge.gov.br`, `biblioteca.ibge.gov.br`, `www.ibge.gov.br`, `portalantigo.ipea.gov.br`,
`bnb.gov.br` e os demais sites abaixo estão fora da rede liberada; os números foram lidos nos trechos que a busca
devolveu):

1. Ipea, Boletim Regional, Urbano e Ambiental nº 15, "Indicadores territoriais" (tabela de PIB per capita das UFs
   com dados das Contas Regionais do IBGE): https://portalantigo.ipea.gov.br/agencia/images/stories/PDFs/boletim_regional/160906_bru15_indicadores01_regionais.pdf
   (cópia: https://repositorio.ipea.gov.br/bitstreams/0f75c28f-35f2-4c22-814b-ae23ac0f45f6/download).
   Brasil, Nordeste, Pernambuco e Bahia apareceram no trecho como valores de 2010. Maranhão, Piauí e Ceará
   vieram da mesma tabela, mas o trecho não repetiu o ano, e por isso esses pontos não contam.
2. BNB, "Desempenho da Economia Regional: 2002 a 2016" (Tabela 6, PIB per capita, citando o IBGE):
   https://bnb.gov.br/documents/45799/1057811/Desempenho+da+Economia+Regional+2002+a+2016.pdf
   e estudo do BNB sobre o Piauí 2002-2016 (Nordeste 15.779 em 2016).
3. Ipece, "PIB do Ceará nas óticas da produção e da renda 2016":
   https://www.ipece.ce.gov.br/wp-content/uploads/sites/45/2019/03/PIB_Ceara_nas_Oticas_Producao_e_Renda_2016.pdf
   (Nordeste R$ 15.779, Ceará R$ 15.438,00; o Nordeste com dois decimais, 15.779,11, aparece na Wikipédia
   "Economia da Região Nordeste do Brasil").
4. IBGE, release "Contas Regionais 2016: entre as 27 unidades da federação, somente Roraima teve crescimento do PIB"
   (Maranhão R$ 12.264,28): https://agenciadenoticias.ibge.gov.br/agencia-sala-de-imprensa/2013-agencia-de-noticias/releases/23038-contas-regionais-2016-entre-as-27-unidades-da-federacao-somente-roraima-teve-crescimento-do-pib
5. IBGE, informativo "Sistema de Contas Regionais: Brasil 2021": https://biblioteca.ibge.gov.br/visualizacao/livros/liv102045_informativo.pdf
6. O Povo, "Ceará teve o 4º menor PIB per capita do Brasil em 2021, diz IBGE" (Ceará R$ 21.090,10; Brasil R$ 42.247,52):
   https://www.opovo.com.br/noticias/economia/2023/11/17/ceara-teve-o-4-menor-pib-per-capita-do-brasil-em-2021-diz-ibge.html
7. Reportagens sobre as Contas Regionais 2021 citando o IBGE (Pernambuco R$ 22.823,59; Bahia R$ 23.530,94;
   Maranhão R$ 17.471,85): https://oantagonista.com.br/brasil/quais-os-estados-mais-pobres-do-brasil-veja-ranking/ ,
   https://www.jornalopcao.com.br/ultimas-noticias/nove-estados-do-nordeste-e-um-do-norte-estao-na-lista-dos-mais-pobres-do-brasil-em-2024-642798/
8. Fapespa, "Relatório PIB Pará 2022" (Brasil R$ 49.638 em 2022, com dados do IBGE):
   https://www.fapespa.pa.gov.br/wp-content/uploads/2024/11/Relatorio-PIB-Para-2022.pdf
9. O Imparcial, "Economia maranhense cresce 3,4% em 2022" (IMESC em parceria com o IBGE; Maranhão R$ 20.632,62):
   https://oimparcial.com.br/noticias/2024/11/economia-maranhense-cresce-34-em-2022-superando-media-nacional/
10. IBGE, Agência de Notícias, "PIB cresce em todos os 27 estados do país em 2023" (tabela "Ranking para Grandes
    Regiões e Unidades da Federação - Produto Interno Bruto per capita / 2023"):
    https://agenciadenoticias.ibge.gov.br/agencia-noticias/2012-agencia-de-noticias/noticias/45142-pib-cresce-em-todos-os-27-estados-do-pais-em-2023
11. Movimento Econômico, "PIB do Nordeste cresce 2,9%, mas renda per capita segue a menor do país" (citando o IBGE):
    https://movimentoeconomico.com.br/economia/2025/11/14/pib-do-nordeste-cresce-29-mas-renda-per-capita-segue-a-menor-do-pais/
12. BNB, "A Economia do Ceará: Uma Análise Setorial no Período 2002-2018" (tabela de PIB per capita a preços
    correntes, com dados do IBGE; linha Brasil: 8.525 em 2002, 20.372 em 2010, 26.521, 28.500, 29.326 e 30.411 de
    2013 a 2016): https://www.bnb.gov.br/documents/45799/1057811/A+Economia+do+Cear%C3%A1+Uma+An%C3%A1lise+Setorial+no+Per%C3%ADodo+2002-2018.pdf/004160b9-f414-dc46-d7d9-f3ba9c4d40fe?t=1648743925838&download=true
13. Ipece, "PIB dos Municípios Cearenses 2002-2018" (Ceará: 3.752 em 2002, 9.391 em 2010, 16.398 em 2017 e
    17.178 em 2018; 2002 = 44,01% do Brasil): https://www.ipece.ce.gov.br/wp-content/uploads/sites/45/2020/12/PIB_dos_Municipios_Cearenses_2002_2018.pdf ;
    2002 também em TrendsCE, "PIB histórico mostra potencial de crescimento da economia do Ceará":
    https://www.trendsce.com.br/2020/07/06/pib-historico-mostra-potencial-de-crescimento-da-economia-do-ceara/
    (e 2018 no comunicado do Ipece de 13/11/2020: https://www.ipece.ce.gov.br/2020/11/13/estudo-revela-numeros-do-pib-do-ceara-de-2018-com-base-nos-dados-consolidados-divulgados-pelo-ibge/).

Contagem: 7 pontos de fonte primária do IBGE (2023 menos o Rio Grande do Norte, [10]; Maranhão 2016, [4]) e 25
reproduções do número do IBGE por órgãos públicos (Ipea, BNB, Ipece, Fapespa, IMESC) ou pela imprensa. O Brasil 2021
aparece atribuído ao informativo [5] num trecho de busca, mas sem confirmação de que o trecho seja do próprio
informativo, e foi contado como reprodução.

### Histórico: a busca de uma série pronta (Tarefas 14A e 14c)

A ficha antiga supunha uma população "das Contas Regionais" (`populacao_contas_regionais`, removida nesta tarefa)
e um PIB per capita publicado. Nenhum dos dois existe em formato legível por máquina:

- SIDRA 5938 e 21 (Contas Regionais): nenhuma variável de população nem de per capita.
- Planilhas das Contas Regionais 2023 (`https://ftp.ibge.gov.br/Contas_Regionais/2023/`, pacotes `Especiais_*` e
  `Conta_da_Producao_*`, xls e ods): as 1.056 abas dos quatro zips `xls` varridas por "capita", "popula" e
  "habitant", sem ocorrência; os índices de tabelas também não listam população nem per capita. As pastas de 2022,
  2018, 2016 e 2013 trazem outras revisões, sem per capita.
- Ipeadata: nos 4.075 metadados com "PIB" no nome, nenhum PIB per capita corrente por região e UF (`PIBPCE` é a
  preços de 2010 e só UFs; `GAC_PIBCAPN` só Brasil). `POP_PROJE` (projeção IBGE, revisão 2024) dá o PIB per capita
  do Brasil 2023 de R$ 51.693,88 contra R$ 53.886,67 publicado (cerca de 4%): não é a população usada.
- SIDRA 6784 (Contas Nacionais, só Brasil) traz população (211.695 mil em 2023) e PIB per capita (R$ 51.693,92),
  mas é outro denominador e não tem região nem UF.

## pib_volume / scr_ref2010

Bloco IBGE, parte C (Tarefa 14c). Data da verificação: 2026-11-01.

- Página oficial: https://www.ibge.gov.br/estatisticas/economicas/contas-nacionais/9054-contas-regionais-do-brasil.html
- URL de coleta: `https://ftp.ibge.gov.br/Contas_Regionais/2023/xls/Especiais_2002_2023_xls.zip` (388.533 bytes; `Last-Modified` do servidor: 17/11/2025; sha256 `75281f8f40113cf947aa1ccd22892f50b76d937a918c4bfd43aa0ef4fa85d97b`).
- Arquivo no zip: `tab03.xls` (o zip tem `tab01.xls` a `tab07.xls`), aba `Tabela3`: "Série encadeada do volume do Produto Interno Bruto, segundo Brasil, Grandes Regiões e Unidades da Federação - 2002-2023", com o cabeçalho "(base:2002 = 100)".
- Layout: título na linha 1, cabeçalho de colunas na linha 4 (`linha_cabecalho: 4`), 22 colunas de ano (2002 a 2023) a partir da segunda coluna, 33 linhas de território logo abaixo (Brasil, 5 regiões e 27 UFs) e nota de fonte na última linha. A célula do canto do cabeçalho é vazia, por isso o pandas a nomeia `Unnamed: 0` (é o valor de `coluna_territorio` na ficha). O Brasil e as regiões vêm com o nome recuado por espaços (o padronizador tira) e "Mato Grosso " tem espaço no fim.
- Formato `.xls` (BIFF8): lido por `padronizar_planilha` com `formato: xls` (pandas + `xlrd`, dependência acrescentada na Tarefa 14c).
- Método: o coletor do projeto (`python -m nordeste --raiz <tmp> coletar --indicador pib_volume`, com a URL montada a partir da ficha) baixou o zip; `consolidar` e `validar` sobre ele saíram com código 0, sem nenhuma linha em `validacao.csv`.
- Obtido: 330 linhas = 22 anos (2002 a 2023) x 15 territórios (BR, N, NE, SE, S, CO e as 9 UFs do Nordeste), todas `observado`, nenhuma indisponível. As outras 18 UFs do arquivo não casam com os territórios do projeto e são descartadas.
- Exemplo (2023): Brasil 158,1977; Nordeste 163,3951; Bahia 149,7738; 2002 vale 100 em todos os territórios.
- Unidade e tratamento: índice de volume encadeado, 2002 = 100 em cada território. A tabela não traz variação anual em %, só o índice. Sem valor monetário (`tratamento_monetario` ausente). Cada território tem a sua base 2002 = 100: o nível do índice não compara territórios, só a evolução.
- Comparação: `brasil` (razão NE/BR dos índices = crescimento acumulado do Nordeste frente ao do país desde 2002). Não há "Brasil fora do Nordeste": o IBGE não publica o PIB a preços do ano anterior por região. A aba de Conta da Produção traz "valor do ano anterior" só para valor bruto da produção, consumo intermediário e valor adicionado bruto (VAB), não para o PIB, e uma varredura das 1.056 abas dos quatro zips `xls` da publicação (`Especiais_2002_2023`, `Especiais_2010_2023`, `Conta_da_Producao_2002_2023`, `Conta_da_Producao_2010_2023`) não achou PIB a preços do ano anterior.
- Alternativa descartada (da 14A): Ipeadata `PIBE` (PIB estadual a preços de 2010) reproduz o índice oficial só para o Brasil; para o Nordeste (167,13 contra 163,40 em 2023) e para as UFs diverge do oficial.

## Bloco IBGE, parte B: PNAD antiga e PNAD Contínua

Tarefa 14b. Data da verificação: 2026-11-01. Método: `python -I -m nordeste --raiz <tmp> --hoje 2026-11-01 coletar
--indicador <id>` (o coletor do projeto monta a URL a partir dos `parametros` da ficha), `consolidar` e `validar`, numa
raiz temporária fora do repositório, com as fichas do repositório. Para as duas séries de pobreza, que estão
`verificado: false` e por isso o coletor recusa, a mesma execução foi feita numa cópia temporária das fichas com
`verificado: true` (o arquivo do repositório não foi alterado).

Resultado do `validar` com os dados reais das 13 fichas: código 0, nenhuma regra bloqueante (inclusive R07, soma das UFs
e das regiões, e R08, razão contra o valor oficial do Nordeste) e nenhum aviso, com os limiares de A01 declarados nas
fichas `desocupacao` (60%) e `extrema_pobreza` (100%), explicados nas seções delas. Com o limiar padrão de 50%, A01 aponta
1 caso em `desocupacao/pnad` (Alagoas 2008 a 2009, +51,5%) e 7 em `extrema_pobreza/pnadc` (2020 a 2021).

Observação sobre as páginas oficiais: a página de cada tabela, `https://sidra.ibge.gov.br/tabela/<n>`, é a que a ficha
registra como `url`; o ambiente da verificação não alcança `sidra.ibge.gov.br`, então a evidência é a própria resposta
da API de valores, que é a fonte dos dados. A descrição das tabelas (`apisidra.ibge.gov.br/desctabapi.aspx`) responde com
desafio anti-robô e não foi usada. Tabelas, variáveis e categorias foram achadas varrendo a API de valores do SIDRA
(tabelas 1 a cerca de 11.800, pelo rótulo das variáveis e das classificações) e lidas nos cabeçalhos das respostas.

Séries da PNAD antiga (`pnad`, 2001 a 2015) e da PNAD Contínua (`pnadc`, 2012 em diante) são sempre `serie_id` diferentes;
as duas se sobrepõem em 2012 a 2014 com valores distintos e nunca são unidas.

Sobre `defasagem_meses` das fichas desta parte: são estimativas do ritmo de divulgação (taxas e informalidade saem com o quarto trimestre, cerca de 2 meses
depois do ano; rendimento de todas as fontes, cerca de 5; pobreza, cerca de 12, pelo último ano que as tabelas ODS tinham em 2026-11-01). Nenhuma foi
confirmada por calendário oficial; só alimentam o aviso A03.

### Resultado da busca pela PNAD antiga (2001 a 2015)

- Só `gini` e `desocupacao` têm série da PNAD antiga por região e UF, as duas no Ipeadata (`PGINI` e `Dese_Pnad`, ambas
  marcadas inativas, calculadas pelo Ipea). Os 4.075 metadados do Ipeadata foram baixados e varridos (nomes e comentários):
  não há renda domiciliar per capita nem pobreza da PNAD antiga por UF. As demais séries `PNADS_*` (todas as fontes) e
  `DISOC_*` são de nível país (código `BRA` no metadado; a resposta de `PNADS_GINI` só traz o Brasil).
- O SIDRA tem a PNAD antiga (tabelas de 2001 a 2015 sem 2010, como 1867 e 1868), mas as tabelas por UF achadas são de
  população economicamente ativa e pessoas que procuraram trabalho, não de renda domiciliar per capita, pobreza nem
  contagem de desocupados.
- A Síntese de Indicadores Sociais antiga (`ftp.ibge.gov.br`) foi examinada só no índice da edição de 2016, que não lista
  série anual de renda domiciliar per capita ou de pobreza por UF; as demais edições (2004 a 2017) não foram abertas.
- Consequência: `renda_dom_pc`, `pobreza`, `extrema_pobreza`, `informalidade` e `rendimento_trabalho` ficam só com a série
  `pnadc`, e `desocupacao/pnad` fica sem Brasil fora do Nordeste (ver abaixo).

### Mudança de código desta tarefa

O Ipeadata devolve a série inteira (o `PGINI` vem desde 1976 e o `Dese_Pnad`, desde 1992). A base só aceita anos dentro da
cobertura da série (regra R05) e a tabela de governos começa em 1999 (`versao_completa` falha antes disso), então os anos
anteriores a 2001 precisavam ser cortados. Foi acrescentado ao padronizador do Ipeadata o parâmetro opcional `periodos`
(`"AAAA"` ou `"AAAA-AAAA"`, como o `periodos` do SIDRA), com testes em `testes/test_padronizacao_ipeadata.py`. Sem o
parâmetro, o comportamento é o de antes. Reportado ao controlador como mudança fora do escopo de pura ficha.

### 2010 na série `pnad`: `anos_sem_publicacao`

A PNAD não foi a campo em 2010 e o Ipeadata não devolve linha para o ano. Por decisão do controlador (fix round 1), a série pode declarar
`anos_sem_publicacao: [2010]` (lista de anos dentro de `inicio` a `fim`, validada em `fichas.py`), e o despachante `padronizar` gera, para cada
grupo e território que a série tem, uma linha `indisponivel` (valor nulo, nota "ano sem pesquisa (Censo)") nos anos listados em que a fonte não
trouxe linha. Aplicado em `gini/pnad` e `desocupacao/pnad`: 2010 tem 15 linhas `indisponivel` em cada uma, e o relatório de cobertura passa a listar 2010
em `anos_faltantes`. Valor trazido pela fonte nunca é sobrescrito. Não há auxiliares da `pnad`.

### Conferência R08 e precisão do valor oficial (fix round 1)

A taxa de desocupação oficial (tabela 4562) vem com uma casa decimal, e o erro de arredondamento de até 0,05 ponto percentual passa de 0,5% relativo
quando a taxa é menor que 10%. Testado se o SIDRA dá mais casas: o sufixo `/d/m` (casas decimais máximas) e `/d/s` devolvem os mesmos valores com uma
casa (7.4, 9.6, 7.9); `/d/3` só completa com zeros (7.400). O dado está guardado com uma casa, então não há ganho em acrescentar o sufixo, e `url_sidra`
não foi alterado. Em vez disso a ficha declara `comparacao.precisao_oficial: 0.1` e a R08 só reprova se |calculado − oficial| passar do maior entre 0,5% do
oficial e `precisao_oficial` ÷ 2. Sem o campo, a regra é a de antes. Com os dados reais, a maior diferença do Nordeste é 0,04 ponto percentual (2012, 2014),
dentro da meia casa (0,05), em 11 anos conferidos.

### renda_dom_pc / pnadc

- Página oficial: https://sidra.ibge.gov.br/tabela/7533
- URL de coleta: `https://apisidra.ibge.gov.br/values/t/7533/n1/all/n2/all/n3/21,22,23,24,25,26,27,28,29/v/10816/p/all`
- Variável 10816: "Rendimento médio mensal real domiciliar per capita, a preços médios do último ano", Reais. A tabela 7533 é
  a de rendimento de todas as fontes por classes de percentual das pessoas; a consulta sem classificação devolve a
  categoria Total (código 49243).
- Obtido: 210 linhas = 14 anos (2012 a 2025) x 15 territórios, todas `observado`. Brasil 2012 = 1.782 e 2025 = 2.264; Nordeste
  2012 = 1.088 e 2025 = 1.470 (reais de 2025).
- Preços: "médios do último ano" da divulgação (2025 hoje); a série inteira é reapresentada a cada ano novo. A variante "a preços
  médios do ano" (tabela 7531, v10824) não deflaciona entre anos e não foi usada. A ficha declara `reais_constantes` com
  `ano_base: ultimo_ano` (revisão final, decisão R-AE: a série é reapresentada a cada divulgação, então nenhum ano fixo é
  gravado na ficha; a unidade diz "a preços médios do último ano da série" e a versão completa troca o trecho pelo maior ano
  com valor da série na base publicada, hoje "de 2025"), com o deflator descrito como o da PNAD Contínua (a nota da tabela não
  pôde ser consultada para nomear o índice). O mesmo vale para `massa_renda_dom_pc` e `rendimento_trabalho`.
- Brasil fora do Nordeste: exato, por razão das diferenças, (massa BR − massa NE) ÷ (população BR − população NE) × 1000, com as
  séries auxiliares abaixo. O valor oficial do Nordeste confere com a razão em todos os 14 anos, a até 0,14% (2012). Brasil fora do Nordeste:
  2.043 em 2012 e 2.554 em 2025.
- Não bate com o destaque do IBGE: o rendimento domiciliar per capita divulgado pelo IBGE para 2025 é R$ 2.316 (Brasil; valor lido em resultado de busca
  na web da nota https://agenciadenoticias.ibge.gov.br/agencia-sala-de-imprensa/2013-agencia-de-noticias/releases/45942-ibge-divulga-rendimento-domiciliar-per-capita-2025-para-brasil-e-unidades-da-federacao,
  que o ambiente não alcança), contra R$ 2.264 aqui, cerca de 2% a mais; as tabelas de rendimento de todas as fontes trabalham com outro universo (ver
  `observacoes` da ficha). Maranhão, 2025: R$ 1.219 na nota e R$ 1.231 na tabela.
- PNAD antiga: sem série (ver a busca acima).

### massa_renda_dom_pc / pnadc

- Página oficial: https://sidra.ibge.gov.br/tabela/7427
- URL de coleta: `https://apisidra.ibge.gov.br/values/t/7427/n1/all/n2/all/n3/21,22,23,24,25,26,27,28,29/v/10495/p/all`
- Variável 10495: "Massa de rendimento mensal real domiciliar per capita, a preços médios do último ano", Milhões de Reais (categoria Total,
  código 49243, é o padrão da consulta).
- Obtido: 210 linhas = 14 anos x 15 territórios, `observado`. Brasil 2025 = 481.389; Nordeste = 83.874 (R$ milhões). A soma das UFs fecha o NE
  (até 0,003%) e a das regiões fecha o Brasil (R07). Auxiliar: numerador da renda domiciliar per capita.

### populacao_pnadc / pnadc

- Página oficial: https://sidra.ibge.gov.br/tabela/7436
- URL de coleta: `https://apisidra.ibge.gov.br/values/t/7436/n1/all/n2/all/n3/21,22,23,24,25,26,27,28,29/v/606/p/all`
- Variável 606: "População", Mil pessoas.
- Obtido: 210 linhas = 14 anos x 15 territórios, `observado`. Brasil 2025 = 212.683; Nordeste = 57.069 (mil pessoas). Soma das UFs e das
  regiões fecham (R07). Auxiliar: denominador da renda domiciliar per capita; não substitui a ficha `populacao`.

### pobreza / pnadc

**Série não verificada (`verificado: false`).** Os dados foram baixados e passaram pelo padronizador, mas a linha de pobreza da
tabela não está confirmada.

- Página oficial: https://sidra.ibge.gov.br/tabela/5877
- URL de coleta (usada na evidência, com a cópia temporária da ficha): `https://apisidra.ibge.gov.br/values/t/5877/n1/all/n2/all/n3/21,22,23,24,25,26,27,28,29/v/9948/p/all`
- Variável 9948: "Proporção da população abaixo da linha de pobreza nacional", Proporção (%) (indicador 1.2.1 dos ODS).
- Obtido: 195 linhas = 13 anos (2012 a 2024) x 15 territórios, `observado`, sem indisponíveis. Brasil 2012 = 36,8% e 2024 = 26,5%; Nordeste
  2012 = 58,8% e 2024 = 44,7%.
- Por que não está verificada: a resposta da API não traz o valor da linha e a nota da tabela não pôde ser lida. A Síntese de Indicadores
  Sociais 2025 (`ftp.ibge.gov.br`, `2_Distribuicao_Renda_xls.zip`, planilha `Tabela 2.18 (Pobr_Geo).xls`) usa US$ 6,85 por dia em PPC 2017
  (R$ 2,3273771 por US$ 1,00 PPC, valores mensais) e dá 27,3% para o Brasil em 2023 e 23,1% em 2024, contra 29,8% e 26,5% desta tabela.
  Os números diferem, então a linha ou o tratamento do rendimento da tabela 5877 não é o da Síntese. Também é a mesma série do Ipeadata
  `PNADCA_TXPNUF` ("Taxa de pobreza nacional (SIS/IBGE)", 2012 a 2025, Brasil, regiões e estados), que dá os mesmos valores
  (Brasil 29,8% em 2023). Para promover a `verificado: true` basta confirmar a linha na nota da tabela (ou trocar por tabela com a linha
  documentada).
- A ficha `pobreza` é só a medida de pobreza; a extrema pobreza é a ficha `extrema_pobreza` (tabela 5817), porque cada série do projeto vem
  de uma única tabela e uma ficha não junta duas tabelas em subindicadores.
- Brasil fora do Nordeste: não há (a tabela só traz a proporção e não foi achada contagem de pobres por UF em série anual); comparação com o
  Brasil. PNAD antiga: sem série.

### extrema_pobreza / pnadc

**Série não verificada (`verificado: false`).** Mesmo motivo da `pobreza`.

- Página oficial: https://sidra.ibge.gov.br/tabela/5817
- URL de coleta (usada na evidência, com a cópia temporária da ficha): `https://apisidra.ibge.gov.br/values/t/5817/n1/all/n2/all/n3/21,22,23,24,25,26,27,28,29/v/9617/p/all`
- Variável 9617: "Proporção da população abaixo da linha de pobreza internacional", Proporção (%) (indicador 1.1.1 dos ODS).
- Obtido: 195 linhas = 13 anos (2012 a 2024) x 15 territórios, `observado`. Brasil 2012 = 8,8% e 2024 = 4,7%; Nordeste 2012 = 18,5% e 2024 = 9,1%.
- Linha: não confirmada. A Síntese 2025 (planilha 2.18) usa US$ 2,15 PPC 2017 por dia e dá 4,4% para o Brasil em 2023 e 3,5% em 2024, contra 5,8% e
  4,7% desta tabela. Ipeadata `PNADCA_TXPIUF` ("Taxa de pobreza internacional (SIS/IBGE)") repete os valores da tabela.
- Aviso A01: com o limiar padrão (50%), 7 casos em 2020 a 2021 (alta depois do auxílio emergencial, por exemplo Rio Grande do Norte de 9,2% para
  17,9%); a ficha usa 100%.
- Brasil fora do Nordeste: não há; comparação com o Brasil. PNAD antiga: sem série.

### gini / pnad

- Página oficial: https://www.ipeadata.gov.br/ExibeSerieR.aspx?serid=1422364745
- URL de coleta: `https://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='PGINI')`
- Série `PGINI`, "Índice de Gini (Pnad/IBGE) - INATIVA" (Ipea, última atualização do metadado em 2016): desigualdade da renda domiciliar per capita
  entre os indivíduos, calculada a partir das respostas da PNAD.
- A resposta traz 1976 a 2014 (sem os anos sem PNAD: 1980, 1991, 1994, 2000 e 2010), com Brasil, 5 regiões e 27 UFs. O parâmetro `periodos: "2001-2014"`
  guarda só a janela da ficha (ver "Mudança de código").
- Obtido (já com a janela): 195 linhas observadas = 13 anos (2001 a 2009 e 2011 a 2014) x 15 territórios, mais 15 `indisponivel` em 2010. Brasil 2001 = 0,596 e 2014 = 0,518;
  Nordeste 2001 = 0,600 e 2014 = 0,516. Escala de 0 a 1, a mesma da PNAD Contínua.
- 2015: a PNAD de 2015 existe, mas a série do Ipeadata termina em 2014; a série fica com `fim: 2014`. Divergência com a spec (2001 a 2015).
- 2010: `anos_sem_publicacao: [2010]`; 15 linhas `indisponivel` (nota "ano sem pesquisa (Censo)"), 2010 aparece em `anos_faltantes`.
- Brasil fora do Nordeste: não há (o Gini não se recompõe a partir de totais); comparação com o Brasil.

### gini / pnadc

- Página oficial: https://sidra.ibge.gov.br/tabela/7435
- URL de coleta: `https://apisidra.ibge.gov.br/values/t/7435/n1/all/n2/all/n3/21,22,23,24,25,26,27,28,29/v/10681/p/all`
- Variável 10681: "Índice de Gini do rendimento domiciliar per capita, a preços médios do ano", Índice. Os valores conferem com os do Ipeadata
  `PNADCA_GINIUF` (Brasil 2012 = 0,540; Nordeste 2024 = 0,499) e com a planilha 2.13 da Síntese 2025 (Brasil 2024 = 0,504405, SIDRA = 0,504).
- Obtido: 210 linhas = 14 anos (2012 a 2025) x 15 territórios, `observado`. Brasil 2012 = 0,540 e 2025 = 0,511; Nordeste 2012 = 0,546 e 2025 = 0,503.
- Brasil fora do Nordeste: não há; comparação com o Brasil.

### desocupacao / pnad

- Página oficial: https://www.ipeadata.gov.br/ExibeSerieR.aspx?serid=199442121
- URL de coleta: `https://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='Dese_Pnad')`
- Série `Dese_Pnad`, "Taxa de desemprego (IBGE/Pnad) - INATIVA": percentual das pessoas que procuraram e não encontraram ocupação entre as economicamente ativas,
  de 10 anos ou mais, na semana de referência; elaboração Disoc/Ipea, série descontinuada.
- A resposta traz 1992 a 2014 (sem 1994, 2000 e 2010), com Brasil, regiões, UFs e áreas metropolitanas (descartadas). `periodos: "2001-2014"` guarda a janela da ficha.
- Obtido (já com a janela): 195 linhas observadas = 13 anos (2001 a 2009 e 2011 a 2014) x 15 territórios, mais 15 `indisponivel` em 2010. Brasil 2001 = 10,05% e 2014 = 7,54%;
  Nordeste 2001 = 9,72% e 2014 = 9,33%.
- 2015: série do Ipeadata termina em 2014 (divergência com a spec, 2001 a 2015). 2010: `anos_sem_publicacao: [2010]`, 15 linhas `indisponivel`.
- Brasil fora do Nordeste: **não há na série `pnad`**. Faltam as contagens: o SIDRA traz as pessoas que procuraram trabalho (tabela 1868), que inclui
  ocupadas que também procuraram, e não os desocupados; o Ipeadata só publica a taxa. A razão não se recompõe, e a comparação da ficha vale só
  para a `pnadc`.
- Aviso A01: Alagoas 2008 a 2009 (+51,5%), no valor da fonte; a ficha usa limiar 60%.

### desocupacao / pnadc

- Página oficial: https://sidra.ibge.gov.br/tabela/4562
- URL de coleta: `https://apisidra.ibge.gov.br/values/t/4562/n1/all/n2/all/n3/21,22,23,24,25,26,27,28,29/v/4099/p/all`
- Variável 4099: "Taxa de desocupação, na semana de referência, das pessoas de 14 anos ou mais de idade", %. Tabela 4562 é anual (média).
- Obtido: 210 linhas = 14 anos (2012 a 2025) x 15 territórios, `observado`, sem indisponíveis. Brasil 2012 = 7,4% e 2025 = 5,6%; Nordeste 2012 = 9,6% e 2025 = 7,9%.
- Brasil fora do Nordeste: por razão, (desocupados BR − NE) ÷ (força de trabalho BR − NE) × 100, com as séries `desocupados` e `forca_trabalho`
  (tabela 10364). Sai em 11 dos 14 anos (2012 a 2019 e 2023 a 2025): em 2020, 2021 e 2022 as contagens por região e UF não são publicadas
  (só o Brasil), e esses anos ficam sem Brasil fora do Nordeste. Brasil fora do Nordeste: 6,65% em 2012 e 4,96% em 2025.
- R08: o valor oficial do Nordeste confere com a razão nos 11 anos, a até 0,04 ponto percentual (2012 e 2014). A taxa oficial vem com uma casa decimal, então a
  ficha declara `precisao_oficial: 0.1` e a regra desconta a meia casa (ver "Conferência R08 e precisão do valor oficial").

### desocupados / pnadc

- Página oficial: https://sidra.ibge.gov.br/tabela/10364
- URL de coleta: `https://apisidra.ibge.gov.br/values/t/10364/n1/all/n2/all/n3/21,22,23,24,25,26,27,28,29/v/4092/p/all/c2/6794`
- Variável 4092: "Pessoas de 14 anos ou mais de idade, desocupadas na semana de referência", Mil pessoas; classificação 2 (sexo), categoria 6794 (Total).
  A tabela 10364 tem as mesmas variáveis em 14 anos; as tabelas irmãs 10359 (sexo, sem 2020 a 2022) e 10360 a 10363 (outros recortes) não foram usadas.
- Obtido: 210 linhas = 14 anos x 15 territórios; 168 `observado` e **42 `indisponivel`** (2020, 2021 e 2022, 14 territórios cada; só o Brasil tem valor, os demais
  vêm como "..."). Brasil 2019 = 12.511 e 2025 = 6.150; Nordeste 2019 = 3.510 e 2025 = 1.991 (mil pessoas).
- Auxiliar da `desocupacao/pnadc`. Brasil fora do Nordeste por soma: 9.001 em 2019 e 4.159 em 2025.

### forca_trabalho / pnadc

- Página oficial: https://sidra.ibge.gov.br/tabela/10364
- URL de coleta: `https://apisidra.ibge.gov.br/values/t/10364/n1/all/n2/all/n3/21,22,23,24,25,26,27,28,29/v/4088/p/all/c2/6794`
- Variável 4088: "Pessoas de 14 anos ou mais de idade, na força de trabalho, na semana de referência", Mil pessoas; sexo total.
- Obtido: 210 linhas = 14 anos x 15 territórios; 168 `observado` e **42 `indisponivel`** (2020 a 2022, só Brasil tem valor). Brasil 2019 = 106.046 e 2025 = 109.132;
  Nordeste 2019 = 24.671 e 2025 = 25.240.
- Auxiliar da `desocupacao/pnadc`. Brasil fora do Nordeste por soma: 81.375 em 2019 e 83.892 em 2025.

### informalidade / pnadc

- Página oficial: https://sidra.ibge.gov.br/tabela/4708
- URL de coleta: `https://apisidra.ibge.gov.br/values/t/4708/n1/all/n2/all/n3/21,22,23,24,25,26,27,28,29/v/12466/p/all`
- Variável 12466: "Taxa de informalidade das pessoas de 14 anos ou mais de idade ocupadas na semana de referência", %.
- Obtido: 150 linhas = 10 anos (2016 a 2025) x 15 territórios, `observado`. Brasil 2016 = 39,1% e 2025 = 38,1%; Nordeste 2016 = 53,3% e 2025 = 50,8%.
- Brasil fora do Nordeste: por razão, informais ÷ ocupados × 100 (tabela 4680): 34,79% em 2016 e 34,40% em 2025, nos 10 anos. R08: o Nordeste confere com a razão
  a até 0,077% (2023). A informalidade só é apurada desde 2016; não há série da PNAD antiga.

### informais / pnadc

- Página oficial: https://sidra.ibge.gov.br/tabela/4680
- URL de coleta: `https://apisidra.ibge.gov.br/values/t/4680/n1/all/n2/all/n3/21,22,23,24,25,26,27,28,29/v/4090/p/all/c1350/57303`
- Variável 4090: "Pessoas de 14 anos ou mais de idade ocupadas na semana de referência", Mil pessoas; classificação 1350 (situação de informalidade), categoria 57303
  (Informais). A classificação 1350 foi achada varrendo os códigos de classificação aceitos pela tabela; as categorias são 57302 (Total) e 57303 (Informais).
- Obtido: 150 linhas = 10 anos x 15 territórios, `observado`. Brasil 2025 = 39.237; Nordeste = 11.809 (mil pessoas); soma das UFs e das regiões fecha (R07).
  Auxiliar da `informalidade`.

### ocupados / pnadc

- Página oficial: https://sidra.ibge.gov.br/tabela/4680
- URL de coleta: `https://apisidra.ibge.gov.br/values/t/4680/n1/all/n2/all/n3/21,22,23,24,25,26,27,28,29/v/4090/p/all/c1350/57302`
- Variável 4090, classificação 1350, categoria 57302 (Total de ocupados).
- Obtido: 150 linhas = 10 anos x 15 territórios, `observado`. Brasil 2025 = 102.983; Nordeste = 23.249. Auxiliar da `informalidade`.

### rendimento_trabalho / pnadc

- Página oficial: https://sidra.ibge.gov.br/tabela/4566
- URL de coleta: `https://apisidra.ibge.gov.br/values/t/4566/n1/all/n2/all/n3/21,22,23,24,25,26,27,28,29/v/5935/p/all`
- Variável 5935: "Rendimento médio mensal real das pessoas de 14 anos ou mais de idade ocupadas na semana de referência com rendimento de trabalho, efetivamente recebido
  em todos os trabalhos", Reais. A tabela traz também o nominal (5931) e os coeficientes de variação, não usados. O valor real de 2025 (Brasil 3.694) difere do
  nominal (3.674), então o real não está em preços de 2025 exatos do ano; a ficha declara `ano_base: ultimo_ano` (resolvido na versão completa; ver `renda_dom_pc`) e o deflator da PNAD Contínua, sem nomear o índice.
- Obtido: 210 linhas = 14 anos (2012 a 2025) x 15 territórios, `observado`. Brasil 2012 = 3.114 e 2025 = 3.694; Nordeste 2012 = 2.074 e 2025 = 2.528.
- Comparação: Brasil (seção 4 da spec); não se recompõe Brasil fora do Nordeste.

## Divergências em relação à seção 4 da spec

1. `populacao`: "estimativas e censos IBGE, 2000+" virou quatro séries (`estimativa_pre_censo2022`, `estimativa_pos_censo2022`, `censo_2000_2010`, `censo_2022`). O ano 2000 só existe como Censo; 2007, 2010, 2022 (nas estimativas) e 2023 (em nenhuma fonte) ficam sem valor.
2. `pib_volume`: série confirmada na fonte (2002 a 2023, 15 territórios, `Especiais_2002_2023_xls.zip`/`tab03.xls`), lida com o novo formato `xls`; a comparação é `brasil`, não `brasil_fora_ne` (spec admite: "senão Brasil"). A fonte traz o índice encadeado 2002 = 100 de cada território, sem variação anual em %.
3. `pib_per_capita`: o IBGE não publica o PIB per capita por território em formato legível; a spec previa coletá-lo das Contas Regionais, e o projeto passou a calculá-lo (PIB 5938 ÷ população do ano que o IBGE usou × 1000), conferido contra valores publicados (32 pontos, diferença máxima 0,050%; 2003 a 2009 sem conferência). Cobre 2002 a 2023 sem 2007 (sem denominador conferido); a fonte da série declara o cálculo.
4. `populacao_contas_regionais`: removida (a spec a previa como denominador do PIB per capita); o denominador agora são as séries de `populacao`, escolhidas por ano no `calculo` da ficha `pib_per_capita`.
5. `pib_participacao`: sem divergência (2002 a 2023, comparação `nenhuma`).
6. `renda_dom_pc`: só a série `pnadc` (2012 a 2025). A PNAD antiga (`pnad`, 2001 a 2015) não tem renda domiciliar per capita por UF em tabela do SIDRA nem no
   Ipeadata. Brasil fora do Nordeste é exato (massa ÷ população), que a spec previa "se houver totais publicados". O valor não é o destaque do IBGE (R$ 2.264 contra
   R$ 2.316 em 2025): universo das tabelas de rendimento de todas as fontes.
7. `pobreza` (e a nova `extrema_pobreza`): a spec previa pobreza e extrema pobreza como subindicadores de uma ficha; viraram **duas fichas**, porque cada série do projeto vem de
   uma única tabela e as duas medidas estão em tabelas diferentes do SIDRA (5877 e 5817), com padronizador sem subindicador (decisão do controlador: manter duas fichas).
   Só `pnadc` (2012 a 2024), e as duas **não verificadas**: a linha de pobreza das tabelas ODS do SIDRA (5877 e 5817) não pôde ser
   confirmada e os valores não coincidem com a Síntese de Indicadores Sociais (US$ 6,85 e US$ 2,15 PPC 2017). Sem `pnad` (PNAD antiga) e sem Brasil fora do Nordeste (não há contagem de pobres por UF em série
   anual).
8. `gini`: `pnad` de 2001 a 2014 (spec: 2001 a 2015), do Ipeadata `PGINI` (a PNAD de 2015 não está na série), com 2010 `indisponivel`; `pnadc` de 2012 a 2025. Comparação com o Brasil, como na spec.
9. `desocupacao`: `pnad` de 2001 a 2014 (spec: 2001 a 2015), do Ipeadata `Dese_Pnad`, com 2010 `indisponivel` e **sem Brasil fora do Nordeste** (não há contagem de desocupados da PNAD
   antiga); `pnadc` de 2012 a 2025, com Brasil fora do Nordeste exato em 11 anos (faltam 2020, 2021 e 2022, sem contagem regional). R08 usa a precisão publicada da taxa (0,1).
10. `informalidade`: só `pnadc` (2016 a 2025), com Brasil fora do Nordeste exato nos 10 anos (informais ÷ ocupados).
11. `rendimento_trabalho`: só `pnadc` (2012 a 2025), comparação com o Brasil, como na spec.
12. Mudanças de código desta tarefa: o parâmetro `periodos` do padronizador do Ipeadata (corta os anos anteriores a 2001); o campo `anos_sem_publicacao` da série
    (linhas `indisponivel` no ano sem pesquisa, 2010 na `pnad`); o campo `comparacao.precisao_oficial` e a tolerância correspondente na R08.
13. `ideb`: série `ideb` de 2005 a **2025** (spec: 2005–2023), porque o INEP divulgou a edição de 2025 em 05/08/2026; bienal, só a rede `total`
    (spec não fixa a rede), comparação com o Brasil, como na spec (Tarefa 15A).
14. `abandono_em`: série `indicadores_inep` de 2007 a **2025** (spec: 2007 em diante), completa e verificada; só o total do ensino médio, na localização e na rede "Total" (spec não fixa o recorte); comparação com o Brasil, como na spec (Tarefa 15B).
15. `matriculas_basica`: a spec previa `educacenso` (2007+) e `censo_escolar_pre2007` (2000-2006). Verificadas `educacenso` de 2007 a **2021** (2022 a 2025 pendentes: a sinopse de 2022 tem 309 MB e passa de cinco minutos, e o cabeçalho das de 2023 a 2025 mudou) e `censo_escolar_pre2007` só de **2005 e 2006** (2003 e 2004 existem só em PDF e 2000 a 2002 têm layout de abas próprio, não lido). A etapa e a rede variam por série: ensino fundamental e ensino médio por rede só até 2006; anos iniciais e anos finais por rede só de 2007 em diante; ensino médio de 2007 em diante só no total (as tabelas por dependência vêm por série, sem soma). Brasil fora do Nordeste por soma, como na spec (Tarefa 15B).
16. `superior`: a spec previa `censup_pre2009` e `censup` (2009+). Verificadas `censup_pre2009` de **2001 a 2008** (2000 só em PDF; matrículas só totais e só de cursos presenciais, porque as linhas de Pública e Privada vêm sem o nome do território) e `censup` de 2009 a **2019** (2020 a 2024 pendentes por tamanho: de 284 a 397 MB; 2025 ainda não publicada). Subindicadores `matriculas` (rede `total`, `publica`, `privada`), `ies` e `universidades`; Brasil fora do Nordeste por soma, como na spec (Tarefa 15B).
17. Tarefa 15B: nenhuma mudança no código de coleta nem de padronização. A única mudança de código é do gerador de fixtures (`xls_abas`, `.xls` com várias abas, e o montador de pacotes a partir das partes da ficha).

## Bloco PNUD: IDHM

Tarefa 16. Data da verificação: 2026-11-01. Método: `python -I -m nordeste --raiz <tmp> --hoje 2026-11-01 coletar
--indicador idhm` (o coletor do projeto monta as quatro URLs a partir dos `parametros` da ficha), `consolidar` e `validar`,
numa raiz temporária fora do repositório. `validar` saiu com código 0 e sem nenhuma linha em `validacao.csv`
(nem regra bloqueante nem aviso, com o limiar de A01 em 100% explicado abaixo).

Fonte: Ipeadata, séries encadeadas do Ipea a partir do Atlas do Desenvolvimento Humano no Brasil. O Ipeadata descreve as
séries como "Série encadeada, 1991-2010 (Censo) e 2012-2024 (Pnad)", atualizadas em 2026-05-29. Cada código é um
subindicador; a API OData não aceita vários códigos numa consulta (`Valores?$filter=...` responde 404).

| Subindicador | Código Ipeadata | Página no Ipeadata |
|---|---|---|
| `idhm` | `IDHM` | https://www.ipeadata.gov.br/ExibeSerieR.aspx?serid=40037 |
| `renda` | `IDHMRE` | https://www.ipeadata.gov.br/ExibeSerieR.aspx?serid=40040 |
| `educacao` | `IDHMED` | https://www.ipeadata.gov.br/ExibeSerieR.aspx?serid=40039 |
| `longevidade` | `IDHMLO` | https://www.ipeadata.gov.br/ExibeSerieR.aspx?serid=40038 |

Mecanismo novo (Tarefa 16, `parametros.codigos`): o coletor `ipeadata` aceita `codigos` (mapa subindicador → código),
além do `codigo` único. Baixa cada código e grava um único arquivo bruto JSON por série,
`{"subindicadores": {"idhm": <resposta OData do IDHM>, "renda": <...>, ...}}`, na ordem do mapa, com uma coleta e um
sha256 por série. A `url` registrada em `coletas.csv` é a lista das quatro URLs, separadas por um espaço, na ordem do mapa.
O padronizador `ipeadata` lê esse formato, confere que as chaves são as do mapa e preenche `subindicador`. Como as
séries `censo` e `pnadc` usam os mesmos quatro downloads e diferem só na janela (`periodos`), o arquivo bruto das duas é o
mesmo (mesmo sha256, em pastas de séries diferentes).

Os dois subconjuntos de séries do Ipeadata não se completam: as regiões (N, NE, SE, S, CO) só existem de 2012 em diante
nos quatro códigos. Nem as séries do Atlas por Censo (`ADH_IDHM`, `ADH_IDHM_E`, `ADH_IDHM_L`, `ADH_IDHM_R`: só Brasil e
UFs, em 1991, 2000 e 2010) trazem regiões. O IDHM não se recalcula a partir das UFs, e não há Brasil fora do Nordeste.

Cotejo com o Atlas por Censo (códigos `ADH_*`, baixados na mesma data): Brasil e UFs de 1991, 2000 e 2010, 84 pontos por
componente (`IDHM`/`ADH_IDHM`, `IDHMRE`/`ADH_IDHM_R`, `IDHMED`/`ADH_IDHM_E`, `IDHMLO`/`ADH_IDHM_L`), diferença zero em todos.

### idhm / censo

- Página oficial: https://www.ipeadata.gov.br/ExibeSerieR.aspx?serid=40037 (a base é o Atlas, https://www.atlasbrasil.org.br/).
- URLs de coleta (uma por subindicador, na ordem da ficha): `https://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='IDHM') https://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='IDHMRE') https://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='IDHMED') https://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='IDHMLO')`
- Janela: `periodos: "2000-2010"`; o Ipeadata traz também 1991, que fica fora.
- Obtido: 80 linhas = 2 anos (2000 e 2010) x 10 territórios (BR e as 9 UFs do Nordeste) x 4 subindicadores, todas
  `observado`. Exemplo: Brasil 2000 = 0,612 e 2010 = 0,727; Ceará 2010 = 0,682.
- **Sem regiões e sem Nordeste.** O Ipeadata não publica o IDHM das regiões em 2000 e 2010, e o índice não se recalcula a
  partir das UFs: o Nordeste fica sem valor nesses anos, sem estimativa e sem linha `indisponivel`. A verificação vale para o
  subconjunto Brasil + 9 UFs, que a ficha declara em `observacoes` e em `compatibilidade`.
- Série decenal: não há linhas para 2001 a 2009 (nem 1991 na série).
- Aviso A01: de 2000 a 2010 o componente educação subiu até 84% nas UFs do Nordeste (Alagoas, de 0,282 a 0,520);
  é variação real, por isso a ficha declara `limiar_salto_pct: 100` (com o padrão de 50%, o aviso apontaria 9 casos).
- Comparação `brasil`; não há Brasil fora do Nordeste.

### idhm / pnadc

- Página oficial: https://www.ipeadata.gov.br/ExibeSerieR.aspx?serid=40037 (Radar IDHM, PNUD: relatório de 26/05/2026, "Radar
  IDHM: evolução do IDHM e de seus componentes, período de 2012 a 2024").
- URLs de coleta (uma por subindicador, na ordem da ficha): `https://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='IDHM') https://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='IDHMRE') https://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='IDHMED') https://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='IDHMLO')`
- Janela: `periodos: "2012-2024"`.
- Obtido: 780 linhas = 13 anos (2012 a 2024) x 15 territórios (BR, 5 regiões e as 9 UFs) x 4 subindicadores, todas
  `observado`. Exemplo: Brasil 2012 = 0,744 e 2024 = 0,805; Nordeste 2012 = 0,687 e 2024 = 0,762.
- **Não cotejada com o arquivo oficial do Radar IDHM.** O site do PNUD (`www.undp.org`) responde 403 e a busca na web só
  achou o relatório em PDF, sem planilha. Os arquivos da Biblioteca do Atlas vêm de uma API de CMS que o ambiente negou
  (e que não foi usada). O Ipeadata descreve a série 2012-2024 como "Pnad" do Atlas; é a fonte acessível, e a ficha diz
  isso. O que passou pela regra de verificação foi o download real das quatro respostas com os parâmetros da ficha, o
  padronizador do projeto e a cobertura completa (15 territórios, 2012 a 2024).
- Série fechada em 2024 (`fim: 2024`): uma edição nova do Radar exige rever `fim` e `periodos` da ficha.
- Não comparável com `censo` (pesquisa e método diferentes); sem variação calculada entre as duas.
- Comparação `brasil`; não há Brasil fora do Nordeste.

## Bloco INEP: acesso confirmado (Tarefa 15), IDEB (Tarefa 15A), abandono, matrículas e superior (Tarefa 15B)

Data: 2026-11-01. Na Tarefa 15 nenhuma ficha do INEP foi escrita: os arquivos reais do INEP não cabiam no mecanismo de coleta e
padronização (uma série = uma URL, uma aba, sem filtro de linhas). A Tarefa 15A acrescentou as séries com partes (abaixo) e a ficha
`ideb`, e a Tarefa 15B escreveu as fichas `abandono_em`, `matriculas_basica` e `superior` (seções ao fim do bloco). Detalhes do que foi baixado e lido na Tarefa 15:

**Acesso.** `download.inep.gov.br` responde com a cadeia TLS incompleta (só a folha `*.inep.gov.br`); falta a intermediária
"RNP ICPEdu GR46 OV TLS CA 2025" (emitida por GlobalSign Root R46, sha256
`E1:07:47:D4:DA:7B:AB:09:CB:A9:95:2F:01:9D:35:34:CB:9F:BA:07:0B:F1:3D:87:91:B1:69:9C:D2:FF:59:DD`). A intermediária pública está em
`metadados/certificados/rnp-icpedu-gr46-ov-tls-ca-2025.pem` e o parâmetro de série `ca_extra` (caminho relativo à raiz) faz o
`baixar` verificar com o bundle em uso (REQUESTS_CA_BUNDLE, senão certifi) mais essa intermediária; a verificação TLS nunca é
desligada. Com `ca_extra`, os downloads abaixo funcionaram. Os arquivos grandes de `informacoes_estatisticas/sinopses_estatisticas/...`
(sinopses de 2010 e 2024, Censo Escolar 2025) ficaram pendurados por mais de dois minutos e não foram lidos.

**IDEB** (`https://www.gov.br/inep/pt-br/areas-de-atuacao/pesquisas-estatisticas-e-indicadores/ideb/resultados/2005-2025`).
Há resultados de 2005 a **2025** (publicado em 05/08/2026), não só até 2023. Arquivos lidos:
`https://download.inep.gov.br/ideb/resultados/divulgacao_regioes_ufs_ideb_2025.zip` (regiões e UFs) e
`.../divulgacao_brasil_ideb_2025.zip` (Brasil). Layout: uma pasta `.xlsx` por arquivo, com três abas (anos iniciais, anos finais, ensino
médio), cabeçalho em quatro linhas (a linha 10 traz códigos como `VL_OBSERVADO_2023`; as linhas 7 a 9 trazem rótulos como
`IDEB\n2023\n(N x P)`; o rótulo de 2021 está digitado `20215` por causa de uma chamada de nota), várias linhas por território, uma por
`Rede` (`Total`, `Pública`, `Privada`, `Estadual`, `Municipal`, com marcas de nota no texto: `Total (3)(4)`, `Total (4)`), e o Brasil
num arquivo à parte. O IDEB de cada território e ano está nas colunas `VL_OBSERVADO_<ano>`.

**abandono_em.** Taxas de rendimento escolar: um zip por ano, `https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/<ano>/tx_rend_brasil_regioes_ufs_<ano>.zip`
(2025, 2015 em outro caminho; 2007 em três `.xls` separados: regiões, Brasil e UFs). Cada arquivo tem um só ano na coluna `NU_ANO_CENSO`,
uma linha por unidade geográfica x localização x dependência administrativa, e as taxas de aprovação, reprovação e abandono por etapa em
colunas (`1_CAT_FUN`, ...).

**matriculas_basica.** Sinopses estatísticas da educação básica: um arquivo por ano, de caminhos diferentes (2000 a 2006:
`download/censo/<ano>/...`, com `.xls` de ~350 abas, uma tabela por aba; 2007 a 2019: `informacoes_estatisticas/.../sinopse_estatistica_da_educacao_basica_<ano>.zip`;
2020 a 2025: `dados_abertos/sinopses_estatisticas/...`). Lida: `https://download.inep.gov.br/download/censo/2006/resultados_censo_escolar2006.zip`
(`Resultados Censo Escolar 2006.xls`, 353 abas `1.1`...`1.60`... com matrículas por etapa, dependência e UF em abas diferentes).

**superior.** Sinopses da educação superior: um arquivo por ano (2009 a 2024 em
`informacoes_estatisticas/sinopses_estatisticas/sinopses_educacao_superior/sinopse_educacao_superior_<ano>.zip`; 2004 a 2008 em outros caminhos). Lida:
`https://download.inep.gov.br/download/superior/censo/2006/Sinopse_EducacaoSuperior_2006.zip` (um `.xls` de 12 MB com 37 abas de tabelas
nacionais, por UF e por organização acadêmica).

Conclusão: nenhuma série do INEP tem uma só URL com os anos em colunas. Faltam, para escrever as fichas, a série com várias URLs (uma por ano),
o mapa de aba e coluna por ano, o filtro de linhas (`Rede = Total`) e, no IDEB, mais de uma aba e mais de um arquivo por série.

### Mecanismo de séries com partes (Tarefa 15A)

- Coleta (`coletor: arquivo`): `parametros.partes` é uma lista; cada parte tem `url` e os parâmetros de leitura da planilha. O coletor
  baixa cada URL distinta uma vez (abas diferentes do mesmo arquivo não repetem o download), com o `ca_extra` da série, e grava **um**
  arquivo bruto por série: um zip determinístico (sem compressão, data, ordem, sistema de origem e atributos fixos, para que o sha256 não
  mude com a plataforma nem com o zlib) com `manifesto.json` (`{"arquivos": [{"url", "nome"}]}`, na
  ordem da primeira aparição da URL nas partes) e um arquivo por URL (`01_<nome do arquivo na URL>`, `02_...`). Uma coleta e um sha256
  por série; a `url` registrada em `coletas.csv` são as URLs distintas separadas por um espaço. Falha em qualquer URL: `ErroColeta` da
  série, sem arquivo parcial e sem linha no registro.
- Padronização (`padronizador: planilha`): cada parte é lida como uma planilha independente (`formato`, `arquivo_no_zip`, `aba`,
  `linha_cabecalho`, `coluna_territorio`, `colunas` com `subindicador`/`etapa`/`rede`) e o resultado é a concatenação. Novos parâmetros
  de leitura (valem também no modo de uma URL): `filtro_linhas` (mapa coluna → valor aceito; compara sem acento, sem maiúsculas e sem
  marcas de nota, `Total (3)(4)` = `Total`) e `nomes_territorio` (mapa nome como a planilha escreve → `territorio_id`, para abreviações
  como `R. G. do Norte`). Marcas de nota (`(1)`, `(3)(4)`, `*`) saem do nome do território e do texto do filtro. Duas linhas com a mesma
  chave (filtro ausente ou partes sobrepostas) são erro de layout, e uma parte sem nenhuma linha aceita também (um "Total" renomeado
  não apaga um subindicador em silêncio). `territorios_esperados` (lista de `territorio_id`, conferida contra os 15 territórios da
  fonte ao carregar a ficha) faz a ausência de qualquer um deles no resultado da parte virar erro de layout. Os valores de
  `filtro_linhas` só podem ser texto ou número (a ficha recusa nulo, booleano e listas). Rótulos com chamada de nota (`IDEB\n20215\n(N x P)`) são declarados
  na ficha exatamente como estão, coluna a coluna.

### ideb / ideb

- Página oficial: https://www.gov.br/inep/pt-br/areas-de-atuacao/pesquisas-estatisticas-e-indicadores/ideb/resultados/2005-2025
  (resultados de 2005 a 2025; a página lista os dois arquivos abaixo, além dos de municípios, escolas e ensino médio integrado, que não entram).
- URLs de coleta (uma por arquivo, na ordem do pacote): `https://download.inep.gov.br/ideb/resultados/divulgacao_regioes_ufs_ideb_2025.zip https://download.inep.gov.br/ideb/resultados/divulgacao_brasil_ideb_2025.zip`
- Método: `python -I -m nordeste --raiz <tmp> --hoje 2026-11-01 coletar --indicador ideb` (coletor do projeto, com os `parametros` da
  ficha e o `ca_extra` da RNP), `consolidar` e `validar`, numa raiz temporária fora do repositório. `validar` saiu com código 0 e sem
  nenhuma linha em `validacao.csv` (nem regra bloqueante nem aviso). Data: 2026-11-01.
- Arquivos baixados: `divulgacao_regioes_ufs_ideb_2025.zip` (sha256 `a8ecdb2c...0a87`, 757.970 bytes) e
  `divulgacao_brasil_ideb_2025.zip` (sha256 `c841dcbe...b348`, 85.519 bytes); o md5 de cada `.xlsx` confere com o arquivo `md5_*.txt`
  que o INEP põe no zip. Pacote gravado pela coleta: `e6974a5c....zip` (sha256 `e6974a5c2d363cdc...f403`, formato sem
  compressão do fix round 1; a primeira verificação, com o pacote comprimido, gravou `88ff10bf....zip` com os mesmos dois zips).
  Reverificação no fix round 1 (mesma data, ficha com `territorios_esperados`): mesmos 495 linhas, `validar` sem nenhuma linha;
  conferência do revisor: Nordeste, anos iniciais, 2023 = 5,6.
- Partes (6): abas `UF e Regiões (AI)`, `UF e Regiões (AF)`, `UF e Regiões (EM)` do `.xlsx` de regiões e UFs e `Brasil (Anos Iniciais)`,
  `Brasil (Anos Finais)`, `Brasil (EM)` do `.xlsx` do Brasil. Cabeçalho na linha 7 (rótulos `IDEB\n<ano>\n(N x P)`; a linha 10 traz os
  códigos `VL_OBSERVADO_<ano>`, mas na aba `Brasil (Anos Finais)` a coluna de 2023 não tem código, por isso a ficha usa os rótulos).
  Rótulos de 2021 como estão nos arquivos: `IDEB\n20215\n(N x P)` (regiões e UFs, as três abas), `IDEB\n20212\n(N x P)` (Brasil, anos
  iniciais) e `IDEB\n20211\n(N x P)` (Brasil, anos finais e ensino médio). Filtro `Rede = Total` (o texto real é `Total`, `Total (4)` ou
  `Total (3)(4)`); `R. G. do Norte` declarado como RN em `nomes_territorio`. `territorios_esperados`: `BR` nas partes do Brasil;
  N, NE, SE, S, CO e as 9 UFs do Nordeste nas partes de regiões e UFs.
- Obtido: 495 linhas = 3 etapas x 11 edições (2005, 2007, ..., 2025) x 15 territórios (BR, 5 regiões e as 9 UFs), todas `observado`,
  nenhuma indisponível. Anos pares não têm edição nem linha. Exemplos: Brasil, anos iniciais, 3,8 (2005) e 6,3 (2025); Nordeste,
  anos iniciais, 2,9 (2005) e 6,0 (2025); Nordeste, anos finais, 2,9 e 5,0; Nordeste, ensino médio, 3,0 e 4,3.
- Rede: só `total`. A aba de regiões e UFs do ensino médio não traz a linha da rede pública (só `Total`, `Privada` e `Estadual`), por isso
  pública e privada ficaram de fora (opcionais no brief). As metas do primeiro ciclo (`VL_PROJECAO_*`) não entram.
- 2021: edição afetada pela pandemia; a ficha registra a cautela em `observacoes` (nota informativa do Ideb 2021).
- Comparação `brasil`; não há Brasil fora do Nordeste (o IDEB não se recalcula a partir das UFs).
- Série fechada em 2025 (`fim: 2025`): uma edição nova exige rever `fim`, as URLs e as colunas das partes.

### Tarefa 15B: abandono, matrículas e ensino superior

Data: 2026-11-01. Método comum: os parâmetros de cada série vêm da ficha; a coleta é a do projeto (`coletar_serie`, que baixa cada URL distinta
com o `ca_extra` da RNP e grava um pacote único), seguida de `consolidar` e `validar` numa raiz temporária fora do repositório. Os arquivos
baixados não são versionados. As tabelas por ano abaixo trazem o tamanho e o sha256 (8 primeiros caracteres) de cada zip baixado e valores
de conferência lidos da base consolidada.

Limite de tempo e de tamanho. Os zips das sinopses são grandes (112 a 397 MB) e o servidor do INEP serve cerca de 0,5 MB/s por conexão (medido:
26 MB em 50 s, uma conexão). O `abandono_em` e as séries pequenas (`censup_pre2009`, `censo_escolar_pre2007`) foram coletados pela rede pelo coletor do
projeto (`python -I -m nordeste --raiz <tmp> --hoje 2026-11-01 coletar --indicador <id>`, com `verificado: true` só na cópia temporária das fichas).
Os zips das sinopses `censup` (2009 a 2019) e `educacenso` (2007 a 2021) foram baixados com `curl` (mesmas URLs da ficha, mesma CA), 12 a 16 de
cada vez, cada um em menos de cinco minutos (124 a 259 s), e a coleta do projeto rodou sobre esses arquivos (sessão HTTP que serve os arquivos locais, com o
`empacotar_partes` e o registro de coletas reais). Não se repetiu a coleta sequencial de rede dessas duas séries: 11 e 15 zips de 112 a 240 MB a 0,5 MB/s
levam de 50 a 60 minutos cada. `consolidar` de `censup` levou 4 min 54 s (CPU) e 4,2 GB de memória; o de `educacenso`, 2 min 53 s e 3,9 GB.

Atualização de 2026-11-01, pacote reduzido. O coletor passou a guardar de cada zip só o membro declarado em `arquivo_no_zip`
(bytes comprimidos copiados do original) e, nos `.xlsx` lidos por aba, só as abas da ficha; o manifesto registra o
`sha256_original` de cada zip baixado. Sobre os mesmos zips reais (os 15 do `educacenso` e os 11 do `censup`, baixados de novo
com `curl`, oito conexões em paralelo), o pacote bruto caiu de 1.857 MB para 28,3 MB (`educacenso`) e de 1.937 MB para 25,1 MB
(`censup`), e a padronização das 90 e das 44 partes deu as mesmas linhas com o pacote reduzido e com o de zips inteiros
(`pandas.testing.assert_frame_equal`). `coletar` dessas séries sobre os arquivos locais: pico de 148 MB e 351 MB; `consolidar`
das seis séries do INEP juntas (`ideb` e `abandono_em` coletados pela rede): 299 s e 439 MB. A coleta sequencial do `educacenso` pela rede, enfim
exercitada de ponta a ponta (`python -m nordeste --raiz <tmp> coletar --indicador matriculas_basica`), levou 2.073 s (~0,9 MB/s)
com pico de 147 MB e gerou o mesmo pacote (sha256 `43bd033c`) montado sobre os arquivos locais. A do `censup` pela rede não foi
repetida.

Medição da Tarefa C2 (2026-11-01), depois da incorporação do pacote reduzido à base e das correções da revisão (download menor que o
`Content-Length`, arquivo que não é zip ou sem o membro declarado viram falha de coleta; xlsx podado só quando menor que o membro original).
Coleta de rede numa cópia temporária do projeto, com o pico de memória lido de `getrusage` do processo filho:
`python -m nordeste --raiz <tmp> --hoje 2026-11-01 coletar --indicador matriculas_basica` (`censo_escolar_pre2007` e `educacenso`) levou
2.034 s (1.857 MB do `educacenso`, ~0,9 MB/s) com pico de 144 MB; o pacote do `educacenso` tem 28.280.513 bytes e o mesmo sha256 `43bd033c` de antes,
e os 15 `sha256_original` do manifesto são os da tabela do `educacenso`. `coletar --indicador superior` com só o `censup_pre2009` (o `censup` marcado
como não verificado na cópia) levou 71 s com pico de 123 MB; o pacote tem 31.929.693 bytes (sha256 `1cb64f0e`), quase o tamanho dos 8 zips
(31.925.742 bytes), porque cada zip só traz o `.xls` lido e `.xls` não é podado; os 8 `sha256_original` são os da tabela do `censup_pre2009`.
`consolidar` dessas três séries: 107 s e pico de 323 MB; `validar`, código 0. A do `censup` pela rede continua não repetida.

Mecanismos de leitura usados, todos já existentes (nenhuma mudança de código): `partes` com `filtro_linhas` (incluindo o valor vazio, para escolher a linha de total
quando o município ou a UF está em branco, e o ano do arquivo, conferido na própria planilha), `nomes_territorio` (`Total Bahia` como BA, `R. G. do Norte` como RN, siglas de UF como
`MA`), `territorios_esperados` em toda parte, colunas por rótulo ou por posição (`Unnamed: n`, quando a célula de cabeçalho está vazia) e `linha_cabecalho` numa linha em branco
quando o cabeçalho tem várias linhas. Os nomes dos arquivos dentro dos zips antigos vêm como o Python os decodifica (CP437): `Taxas de Rendimento_ REGIσES_ 2007.xls`,
`Sinopse_Estatistica_da_Educaç╞o_Basica_2013.xlsx`, e a ficha os declara assim.

### abandono_em / indicadores_inep

- Página oficial: https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/indicadores-educacionais/taxas-de-rendimento-escolar (uma página por ano, com os
  arquivos de Brasil, regiões e UFs, de municípios e de escolas; só o primeiro entra).
- URLs de coleta (um zip por ano, na ordem do pacote): `https://download.inep.gov.br/informacoes_estatisticas/2011/indicadores_educacionais/taxa_rendimento/2007/tx_rendimento_brasil_regioes_UFs_2007.zip https://download.inep.gov.br/informacoes_estatisticas/2011/indicadores_educacionais/taxa_rendimento/2008/tx_rendimento_brasil_regioes_UFs_2008.zip https://download.inep.gov.br/informacoes_estatisticas/2011/indicadores_educacionais/taxa_rendimento/2009/tx_rendimento_brasil_regioes_UFs_2009.zip https://download.inep.gov.br/informacoes_estatisticas/2011/indicadores_educacionais/taxa_rendimento/2010/tx_rendimento_brasil_regioes_UFs_2010.zip https://download.inep.gov.br/informacoes_estatisticas/2011/indicadores_educacionais/taxa_rendimento/2011/tx_rendimento_brasil_regioes_UFs_2011_2.zip https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/2012/taxas_rendimento/tx_rendimento_brasil_regioes_UFs_2012.zip https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/2013/taxa_rendimento/tx_rendimento_brasil_regioes_UFs_2013.zip https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/2014/taxa_rendimento/tx_rendimento_brasil_regioes_UFs_2014.zip https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/2015/taxa_rendimento/tx_rendimento_brasil_regioes_UFs_2015.zip https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/2016/TAXA_REND_2016_BRASIL_REGIOES_UFS.zip https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/2017/TAXA_REND_2017_BRASIL_REGIOES_UFS.zip https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/2018/TX_REND_BRASIL_REGIOES_UFS_2018.zip https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/2019/tx_rend_brasil_regioes_ufs_2019.zip https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/2020/tx_rend_brasil_regioes_ufs_2020.zip https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/2021/tx_rend_brasil_regioes_ufs_2021.zip https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/2022/tx_rend_brasil_regioes_ufs_2022.zip https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/2023/tx_rend_brasil_regioes_ufs_2023.zip https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/2024/tx_rend_brasil_regioes_ufs_2024.zip https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/2025/tx_rend_brasil_regioes_ufs_2025.zip`
- Coleta de rede pelo coletor do projeto em 54 s, 19 zips; `validar` saiu com código 0, sem regra bloqueante e com um aviso A01 em 32 casos
  (passagens de 2019 para 2020, de 2020 para 2021, de 2022 para 2023 e de 2024 para 2025; é variação real em taxas pequenas e do ensino remoto da pandemia, sem salto de método).
- Valor lido: taxa de abandono do total do ensino médio, na localização e na rede ("dependência administrativa") "Total". Cada arquivo traz as taxas de aprovação, de
  reprovação e de abandono por série; a ficha escolhe só a coluna do total do ensino médio da taxa de abandono.
- Layout por era (cada ano é um arquivo de layout próprio; 39 partes):
  - 2007 a 2010: três `.xls` (Brasil, regiões, UFs), cabeçalho na linha 8, colunas sem rótulo de cabeçalho exceto as de dados (`Unnamed: n`); o total está em "Total Abandono - Médio"
    (coluna 57, ou 58 no arquivo das UFs de 2007). Cuidado: a coluna que a linha 7 chama de "Taxa de Abandono - Ensino Médio" é a da 1ª série, não a do total; por isso o
    cabeçalho é a linha 8. Região "Centro - Oeste" em 2007 e 2008 (`nomes_territorio`), UFs por sigla.
  - 2011 a 2015: três arquivos (`.xls` e `.xlsx`, conforme o ano), cabeçalho na linha 7, total em "Taxa de Abandono - Ensino Médio" (a linha 8 confere: "Total Abandono Médio"); UFs por sigla até 2014 e por nome em 2015.
  - 2016: três `.xlsx`, cabeçalho de códigos na linha 9, total em `tab_MED`, filtros `TIPOLOCA` e `DEPENDAD` (`Dependad` no Brasil); o arquivo das UFs traz a região na coluna 1 e a UF em `no_cod`.
  - 2017 a 2020: um `.xlsx` com Brasil, regiões e UFs (aba `BRASIL_REGIOES_UFS ` com espaço no fim), cabeçalho de códigos na linha 9, território na coluna sem rótulo, total em `tab_MED`.
  - 2021 a 2025: um `.xlsx` (mesma aba), códigos novos (`NU_ANO_CENSO`, `UNIDGEO`, `NO_CATEGORIA`, `NO_DEPENDENCIA`), total em `3_CAT_MED`.
- Conferência independente (leitura direta dos arquivos com pandas, fora do padronizador): Pernambuco 2012 = 7,4, Bahia 2008 = 19,8 e Nordeste 2019 = 5,2, iguais aos da base.
- Obtido: 285 linhas = 19 anos (2007 a 2025) x 15 territórios (BR, 5 regiões e as 9 UFs), todas `observado`. Comparação com o Brasil (não há Brasil fora do Nordeste).

| Ano | Zip (bytes) | sha256 | Brasil | Nordeste | Bahia | Pernambuco |
|---|---|---|---|---|---|---|
| 2007 | 161.927 | `cb482954` | 13,2 | 19,3 | 19,9 | 22,0 |
| 2008 | 147.935 | `c98805d4` | 12,8 | 18,1 | 19,8 | 18,0 |
| 2009 | 148.569 | `29d57dc2` | 11,5 | 16,4 | 18,5 | 14,0 |
| 2010 | 146.826 | `fef00458` | 10,3 | 14,2 | 15,7 | 11,1 |
| 2011 | 134.571 | `4cbdb787` | 9,5 | 13,3 | 12,5 | 10,1 |
| 2012 | 229.990 | `8dc1092c` | 9,1 | 12,5 | 14,1 | 7,4 |
| 2013 | 230.519 | `aff888ce` | 8,1 | 9,7 | 8,6 | 4,7 |
| 2014 | 229.458 | `dbd866e5` | 7,6 | 9,3 | 10,0 | 3,2 |
| 2015 | 482.450 | `56be48a4` | 6,8 | 8,0 | 7,5 | 2,3 |
| 2016 | 526.989 | `32be97b4` | 6,6 | 7,8 | 7,4 | 1,6 |
| 2017 | 403.520 | `d6a8f808` | 6,1 | 7,0 | 8,5 | 1,5 |
| 2018 | 369.426 | `4a6d0f21` | 6,1 | 6,7 | 9,0 | 1,2 |
| 2019 | 367.101 | `24a0b247` | 4,8 | 5,2 | 7,1 | 1,4 |
| 2020 | 381.215 | `febf857b` | 2,3 | 2,2 | 1,0 | 0,3 |
| 2021 | 400.223 | `f2a5cd3c` | 5,0 | 6,3 | 10,6 | 1,4 |
| 2022 | 407.358 | `1ff22afb` | 5,7 | 6,7 | 11,7 | 1,5 |
| 2023 | 389.928 | `544353af` | 3,4 | 3,4 | 4,8 | 0,9 |
| 2024 | 388.235 | `669ee147` | 3,2 | 3,5 | 5,8 | 0,7 |
| 2025 | 376.867 | `cb6ba9fc` | 2,2 | 1,9 | 2,7 | 0,6 |

### matriculas_basica / censo_escolar_pre2007

- Páginas oficiais: https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/sinopses-estatisticas/educacao-basica (sinopses de 1995 a 2025).
- URLs de coleta (um zip por ano): `https://download.inep.gov.br/download/censo/2005/Censo2005.zip https://download.inep.gov.br/download/censo/2006/resultados_censo_escolar2006.zip`
- Coleta de rede pelo coletor do projeto; `validar` saiu com código 0, sem regra bloqueante e com A01 em 6 casos (redes federal e estadual com poucas matrículas, como creche estadual
  do RN, de 2005 para 2006).
- Layout: um `.xls` por ano (`Censo2005/Censo Escolar 2005.xls`, `Resultados Censo Escolar 2006.xls`) com uma aba por tabela e uma linha por território (nomes "R. G. do Norte", "Centro-Oeste"; declarados
  em `nomes_territorio`). Abas lidas: `1.1` (educação básica, infantil, fundamental e médio), `1.6` (creche, total e por rede), `1.12` (pré-escola), `1.18` (ensino fundamental por rede) e
  `1.43` (ensino médio por rede); o cabeçalho é a linha em branco acima da linha do Brasil (linha 8 ou 9, conforme a aba e o ano). Redes: federal, estadual, municipal e privada.
- Obtido: 704 linhas = 2 anos x 15 territórios x 22 grupos de etapa e rede (660 observadas e 44 do Brasil fora do Nordeste por soma). Brasil, educação básica, 55.942.047 (2006).
- Pendência: 2000 a 2002 (arquivos `.xls` com abas de numeração própria, não lidos), 2003 e 2004 (só PDF). Uma série só é verificada se todos os anos declarados passaram, por isso a série declara 2005 e 2006.

| Ano | Zip (bytes) | sha256 | Educação básica Brasil | Ensino médio Brasil | Ensino médio Nordeste |
|---|---|---|---|---|---|
| 2005 | 647.527 | `9b0ef400` | 56.471.622 | 9.031.302 | 2.669.335 |
| 2006 | 609.162 | `5967a7a7` | 55.942.047 | 8.906.820 | 2.692.512 |

### matriculas_basica / educacenso

- URLs de coleta (um zip por ano, na ordem do pacote; 2007 a 2019 em `informacoes_estatisticas/.../sinopses_educacao_basica/`, 2020 e 2021 em `dados_abertos/sinopses_estatisticas/`): `https://download.inep.gov.br/informacoes_estatisticas/sinopses_estatisticas/sinopses_educacao_basica/sinopse_estatistica_da_educacao_basica_2007.zip https://download.inep.gov.br/informacoes_estatisticas/sinopses_estatisticas/sinopses_educacao_basica/sinopse_estatistica_da_educacao_basica_2008.zip https://download.inep.gov.br/informacoes_estatisticas/sinopses_estatisticas/sinopses_educacao_basica/sinopse_estatistica_da_educacao_basica_2009.zip https://download.inep.gov.br/informacoes_estatisticas/sinopses_estatisticas/sinopses_educacao_basica/sinopse_estatistica_da_educacao_basica_2010.zip https://download.inep.gov.br/informacoes_estatisticas/sinopses_estatisticas/sinopses_educacao_basica/sinopse_estatistica_da_educacao_basica_2011.zip https://download.inep.gov.br/informacoes_estatisticas/sinopses_estatisticas/sinopses_educacao_basica/sinopse_estatistica_da_educacao_basica_2012.zip https://download.inep.gov.br/informacoes_estatisticas/sinopses_estatisticas/sinopses_educacao_basica/sinopse_estatistica_da_educacao_basica_2013.zip https://download.inep.gov.br/informacoes_estatisticas/sinopses_estatisticas/sinopses_educacao_basica/sinopse_estatistica_da_educacao_basica_2014.zip https://download.inep.gov.br/informacoes_estatisticas/sinopses_estatisticas/sinopses_educacao_basica/sinopse_estatistica_da_educacao_basica_2015.zip https://download.inep.gov.br/informacoes_estatisticas/sinopses_estatisticas/sinopses_educacao_basica/sinopse_estatistica_da_educacao_basica_2016.zip https://download.inep.gov.br/informacoes_estatisticas/sinopses_estatisticas/sinopses_educacao_basica/sinopse_estatistica_da_educacao_basica_2017.zip https://download.inep.gov.br/informacoes_estatisticas/sinopses_estatisticas/sinopses_educacao_basica/sinopse_estatistica_da_educacao_basica_2018.zip https://download.inep.gov.br/informacoes_estatisticas/sinopses_estatisticas/sinopses_educacao_basica/sinopse_estatistica_educacao_basica_2019.zip https://download.inep.gov.br/dados_abertos/sinopses_estatisticas/sinopses_estatisticas_censo_escolar_2020.zip https://download.inep.gov.br/dados_abertos/sinopses_estatisticas/sinopses_estatisticas_censo_escolar_2021.zip`
- `validar` saiu com código 0, sem regra bloqueante e com A01 em 110 casos (redes federal e estadual com poucas matrículas, como os anos finais federais do Piauí, de 2008 para 2009).
- Layout: um `.xlsx` por ano, de cerca de 83 a 105 MB, com as três tabelas lidas em abas de nome estável de 2007 a 2021 (`Educação Básica 1.1`, `Educação Infantil 1.5`, `Ensino Fundamental 1.14`; as 15 sinopses têm o cabeçalho
  idêntico nas três). Cada aba traz uma linha por município, com as linhas de Brasil, de região (UF e município em branco) e de UF (município em branco) entre elas; por isso cada aba entra em duas partes:
  Brasil e regiões (filtro: coluna da UF vazia) e UFs (filtro: coluna do município vazia). Células em branco vêm com espaços; o filtro compara sem espaços. Cabeçalho: linha 10, em branco (colunas por posição).
- Colunas: `1.1` (rede total): educação básica, educação infantil, creche, pré-escola, ensino fundamental, anos iniciais, anos finais, ensino médio; `1.5`: creche e pré-escola por rede (federal, estadual, municipal,
  privada); `1.14`: anos iniciais e anos finais por rede. O total de cada etapa vem só da 1.1 (as tabelas por rede repetem o total, que não entra duas vezes). O ensino médio por rede e o ensino fundamental por rede
  não existem nessas tabelas (as de ensino médio por dependência vêm por série, sem total).
- Obtido: 5.760 linhas = 15 anos x 15 territórios x 24 grupos de etapa e rede (5.400 observadas e 360 do Brasil fora do Nordeste por soma).
- Pendência: 2022 a 2025. A sinopse de 2022 (309 MB) não terminou de baixar em 290 s; as de 2023 (152 MB), 2024 (145 MB) e 2025 (232 MB) baixaram, mas mudam o cabeçalho das abas 1.1, 1.5 e 1.14 (2023 e 2024) ou renumeram as tabelas
  (2025, arquivo `..._2025_V2`), e a série precisa ser contínua. Ficam para uma nova tarefa.

| Ano | Zip (bytes) | sha256 | Educação básica Brasil | Ensino médio Brasil | Ensino médio Nordeste |
|---|---|---|---|---|---|
| 2007 | 119.449.617 | `0efe1688` | 53.028.928 | 8.372.175 | 2.526.908 |
| 2008 | 122.211.895 | `9510b4b6` | 53.232.868 | 8.368.868 | 2.537.971 |
| 2009 | 120.740.810 | `82b62128` | 52.580.452 | 8.338.423 | 2.512.928 |
| 2010 | 121.686.114 | `8cd07f99` | 51.549.889 | 8.358.647 | 2.425.022 |
| 2011 | 129.226.183 | `b5da8f49` | 50.972.619 | 8.401.829 | 2.401.630 |
| 2012 | 133.568.931 | `36501f31` | 50.545.050 | 8.377.942 | 2.354.470 |
| 2013 | 124.080.071 | `1829eacb` | 50.042.448 | 8.314.048 | 2.311.536 |
| 2014 | 124.053.690 | `98ebac1e` | 49.771.371 | 8.301.380 | 2.267.412 |
| 2015 | 125.109.515 | `3c548144` | 48.796.512 | 8.076.150 | 2.214.168 |
| 2016 | 124.172.601 | `334e8815` | 48.817.479 | 8.133.040 | 2.245.524 |
| 2017 | 124.595.719 | `094278d0` | 48.608.093 | 7.930.384 | 2.220.128 |
| 2018 | 124.244.538 | `19c3d786` | 48.455.867 | 7.709.929 | 2.183.818 |
| 2019 | 120.447.577 | `fbdff686` | 47.874.246 | 7.465.891 | 2.112.466 |
| 2020 | 120.550.648 | `a252b0e5` | 47.295.294 | 7.550.753 | 2.130.375 |
| 2021 | 123.101.397 | `66861b1e` | 46.668.401 | 7.770.557 | 2.246.336 |

### superior / censup_pre2009

- Páginas oficiais: https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/sinopses-estatisticas/educacao-superior (sinopses de 1995 a 2024).
- URLs de coleta (um zip por ano, na ordem do pacote): `https://download.inep.gov.br/download/censo/2001/Superior/Sinopse_Superior_2001.zip https://download.inep.gov.br/download/censo/2002/sinopse/Sinopse_2002_censosuperior.zip https://download.inep.gov.br/download/superior/2004/SES2003.zip https://download.inep.gov.br/download/superior/2004/Sinopse_2004_010206.zip https://download.inep.gov.br/download/superior/2005/Sinopse_2005a.zip https://download.inep.gov.br/download/superior/censo/2006/Sinopse_EducacaoSuperior_2006.zip https://download.inep.gov.br/download/superior/censo/2007/Sinopse2007.zip https://download.inep.gov.br/download/censo/2008/sinop_sup_2008_versao_preliminar.zip`
- Coleta de rede pelo coletor do projeto; `validar` saiu com código 0, sem regra bloqueante e com A01 em um caso (universidades de Alagoas, de 1 para 2 entre 2004 e 2005).
- Layout: um `.xls` por ano (um arquivo de 6 a 28 MB dentro do zip), com as abas `1.1` (instituições por organização acadêmica) e `5.1` (matrículas em cursos de graduação presenciais). Uma linha por território na
  coluna 0, seguida de linhas de Pública e Privada (e das categorias) sem nome de território; por isso só se lê a linha do território, que traz o total geral (coluna 3) e o das universidades (coluna 6). Cabeçalho: a linha em
  branco antes do Brasil (linha 8). A ficha lê `ies` (1.1, coluna 3), `universidades` (1.1, coluna 6) e `matriculas` rede `total` (5.1, coluna 3).
- Obtido: 384 linhas = 8 anos x 15 territórios x 3 subindicadores (360 observadas e 24 do Brasil fora do Nordeste por soma). Valores do Brasil conferem com os da sinopse: 1.391 IES e 3.030.754 matrículas em 2001; 5.080.056 matrículas em 2008.
- Pendência: 2000 só existe em PDF; matrículas por rede (pública e privada) não são lidas porque as linhas de Pública e Privada não trazem o nome do território.

| Ano | Zip (bytes) | sha256 | IES Brasil | Universidades Brasil | Matrículas totais Brasil |
|---|---|---|---|---|---|
| 2001 | 1.362.455 | `ea7fea96` | 1.391 | 156 | 3.030.754 |
| 2002 | 2.087.120 | `e84ee70a` | 1.637 | 162 | 3.479.913 |
| 2003 | 7.663.258 | `bc951cd2` | 1.859 | 163 | 3.887.022 |
| 2004 | 10.625.168 | `f70fbaa8` | 2.013 | 169 | 4.163.733 |
| 2005 | 2.374.053 | `9e9b4509` | 2.165 | 176 | 4.453.156 |
| 2006 | 2.511.415 | `8531aab3` | 2.270 | 178 | 4.676.646 |
| 2007 | 2.277.774 | `3e595b02` | 2.281 | 183 | 4.880.381 |
| 2008 | 3.024.499 | `5129e5cd` | 2.252 | 183 | 5.080.056 |

### superior / censup

- URLs de coleta (um zip por ano, na ordem do pacote): `https://download.inep.gov.br/informacoes_estatisticas/sinopses_estatisticas/sinopses_educacao_superior/sinopse_educacao_superior_2009.zip https://download.inep.gov.br/informacoes_estatisticas/sinopses_estatisticas/sinopses_educacao_superior/sinopse_educacao_superior_2010.zip https://download.inep.gov.br/informacoes_estatisticas/sinopses_estatisticas/sinopses_educacao_superior/sinopse_educacao_superior_2011.zip https://download.inep.gov.br/informacoes_estatisticas/sinopses_estatisticas/sinopses_educacao_superior/sinopse_educacao_superior_2012.zip https://download.inep.gov.br/informacoes_estatisticas/sinopses_estatisticas/sinopses_educacao_superior/sinopse_educacao_superior_2013.zip https://download.inep.gov.br/informacoes_estatisticas/sinopses_estatisticas/sinopses_educacao_superior/sinopse_educacao_superior_2014.zip https://download.inep.gov.br/informacoes_estatisticas/sinopses_estatisticas/sinopses_educacao_superior/sinopse_educacao_superior_2015.zip https://download.inep.gov.br/informacoes_estatisticas/sinopses_estatisticas/sinopses_educacao_superior/sinopse_educacao_superior_2016.zip https://download.inep.gov.br/informacoes_estatisticas/sinopses_estatisticas/sinopses_educacao_superior/sinopse_educacao_superior_2017.zip https://download.inep.gov.br/informacoes_estatisticas/sinopses_estatisticas/sinopses_educacao_superior/sinopse_educacao_superior_2018.zip https://download.inep.gov.br/informacoes_estatisticas/sinopses_estatisticas/sinopses_educacao_superior/sinopse_educacao_superior_2019.zip`
- `validar` saiu com código 0, sem regra bloqueante e com A01 em um caso (universidades do Maranhão, de 2 para 4 entre 2011 e 2012).
- Layout: cada zip de 112 a 240 MB traz a sinopse por município (`Sinopse_Educação_Superior_Municipio_<ano>.xlsx`, 39 a 53 MB) e três anexos de dados por curso, que não entram. A sinopse tem as abas `1.1` (instituições por
  organização acadêmica e dependência administrativa) e `5.1` (matrículas de graduação e sequenciais, presenciais e a distância), com cabeçalho idêntico em 2009 a 2019. Uma linha por município, com as linhas
  "Total Brasil", "Total <região>" e "Total <UF>" entre elas; cada aba entra em duas partes (Brasil e regiões, filtro: UF vazia; UFs, filtro: município vazio) e `nomes_territorio` mapeia `Total Maranhão` e as demais.
  Na `5.1`, só as linhas de nível acadêmico "Graduação" (a tabela traz também "Sequencial de Formação Específica"). Cabeçalho: linha 10, em branco (colunas por posição). Colunas: `1.1`, total de instituições (coluna 4) e total das universidades
  (coluna 12); `5.1`, matrículas totais (coluna 5), de instituições públicas (coluna 6) e privadas (coluna 10).
- Obtido: 880 linhas = 11 anos x 15 territórios x 5 grupos (825 observadas e 55 do Brasil fora do Nordeste por soma).
- Pendência: 2020 a 2024 (284 a 397 MB; os cinco não terminaram em 280 s com 16 conexões e levam de 9 a 13 min a 0,5 MB/s) e 2025 (ainda não publicada: a página do INEP, atualizada em 14/07/2026, lista até 2024).

| Ano | Zip (bytes) | sha256 | IES Brasil | Universidades Brasil | Matrículas totais Brasil | Matrículas públicas Brasil | Matrículas privadas Brasil |
|---|---|---|---|---|---|---|---|
| 2009 | 112.339.526 | `894e938e` | 2.314 | 186 | 5.954.021 | 1.523.864 | 4.430.157 |
| 2010 | 144.991.282 | `e51d33ec` | 2.378 | 190 | 6.379.299 | 1.643.298 | 4.736.001 |
| 2011 | 150.932.494 | `1b022fff` | 2.365 | 190 | 6.739.689 | 1.773.315 | 4.966.374 |
| 2012 | 158.792.747 | `16d0ab56` | 2.416 | 193 | 7.037.688 | 1.897.376 | 5.140.312 |
| 2013 | 160.038.569 | `244ffcea` | 2.391 | 195 | 7.305.977 | 1.932.527 | 5.373.450 |
| 2014 | 175.031.945 | `0252f97f` | 2.368 | 195 | 7.828.013 | 1.961.002 | 5.867.011 |
| 2015 | 177.238.126 | `d9021543` | 2.364 | 195 | 8.027.297 | 1.952.145 | 6.075.152 |
| 2016 | 190.009.870 | `57752936` | 2.407 | 197 | 8.048.701 | 1.990.078 | 6.058.623 |
| 2017 | 222.515.082 | `e20edd41` | 2.448 | 199 | 8.286.663 | 2.045.356 | 6.241.307 |
| 2018 | 205.366.920 | `6bce5a85` | 2.537 | 199 | 8.450.755 | 2.077.481 | 6.373.274 |
| 2019 | 239.663.783 | `18f8d16e` | 2.608 | 198 | 8.603.824 | 2.080.146 | 6.523.678 |

## Ensaio real de 2026-11

Tarefa C1 da conclusão da base. Data: 2026-11-01. Primeira execução do pipeline inteiro com dados reais de uma vez: `coletar` (rede) das fichas verificadas, `consolidar`, `validar` e
`publicar --ensaio`, numa cópia temporária do projeto fora do repositório (`python -m nordeste --raiz <cópia> ...`, pacote instalado em modo editável apontando para o código do repositório). As
duas séries grandes do INEP, `matriculas_basica/educacenso` e `superior/censup`, ficaram de fora (dependem da coleta enxuta, Tarefa C2): na cópia, e só nela, essas duas séries tiveram
`verificado` posto em `false`, de modo que o `coletar` as pulou. `pobreza` e `extrema_pobreza` seguem `verificado: false` e foram puladas como sempre. Os arquivos baixados não são versionados.

### Execução

| Passo | Código de saída | Tempo |
|---|---|---|
| `coletar` (todas as fichas, 4 séries puladas) | 0 | 3 min 03 s |
| `consolidar` | 0 | 25 s |
| `validar` | 0 | 8 s |
| `publicar --ensaio` | 0 | 7 s |

Segunda rodada completa (`coletar` de novo, `consolidar`, `validar`, `publicar --ensaio`): todos com código 0, `coletas.csv` sem linhas novas (mesmos 26 registros, mesmos sha256), `base.csv` e `validacao.csv`
byte a byte iguais aos da primeira. O ensaio é idempotente com dados reais.

- `falhas_coleta.csv`: só o cabeçalho (nenhuma série falhou; as 26 séries de rede coletaram na primeira tentativa).
- `pendencias.csv`: quatro séries, todas esperadas: `extrema_pobreza/pnadc` e `pobreza/pnadc` (não verificadas, linha de pobreza não confirmada) e `matriculas_basica/educacenso` e `superior/censup` (fora desta tarefa).
  Nenhum indicador ficou pendente por insumo e nenhuma série tem layout inesperado.
- `validacao.csv`: **nenhuma regra bloqueante** (R01 a R10 sem disparo; a R01 não dispara porque nenhuma coleta é de origem `fixture`), nenhum A02 (não há base publicada para comparar), nenhum A03 (nenhuma série em curso
  passou da próxima publicação prevista em 2026-11-01) e **três A01**, explicados abaixo.
- `derivacoes.csv`: 18 registros (um por série de cada indicador, `pib_per_capita` com os 5 insumos de PIB e população).
- `mudancas.csv`: tudo `novo` (primeira base). `cobertura.csv`: 417 linhas (indicador, série, território), sem lacuna além das já registradas (2010 na PNAD antiga; 2020 a 2022 nas contagens da PNAD Contínua;
  2007 do PIB per capita).

### Linhas da base de trabalho

Total: 7.131 linhas (6.131 `observado`, 556 `derivado`, 330 `estimativa_oficial`, 114 `indisponivel`) e 15.129 linhas de métricas em `derivados.csv`.

| Indicador | Série | Linhas | Anos | Derivadas | Estimativa oficial | Indisponível |
|---|---|---|---|---|---|---|
| `abandono_em` | `indicadores_inep` | 285 | 2007–2025 | 0 | 0 | 0 |
| `desocupacao` | `pnad` | 210 | 2001–2014 | 0 | 0 | 15 |
| `desocupacao` | `pnadc` | 221 | 2012–2025 | 11 | 0 | 0 |
| `desocupados` | `pnadc` | 221 | 2012–2025 | 11 | 0 | 42 |
| `forca_trabalho` | `pnadc` | 221 | 2012–2025 | 11 | 0 | 42 |
| `gini` | `pnad` | 210 | 2001–2014 | 0 | 0 | 15 |
| `gini` | `pnadc` | 210 | 2012–2025 | 0 | 0 | 0 |
| `ideb` | `ideb` | 495 | 2005–2025 | 0 | 0 | 0 |
| `idhm` | `censo` | 80 | 2000–2010 | 0 | 0 | 0 |
| `idhm` | `pnadc` | 780 | 2012–2024 | 0 | 0 | 0 |
| `informais` | `pnadc` | 160 | 2016–2025 | 10 | 0 | 0 |
| `informalidade` | `pnadc` | 160 | 2016–2025 | 10 | 0 | 0 |
| `massa_renda_dom_pc` | `pnadc` | 224 | 2012–2025 | 14 | 0 | 0 |
| `matriculas_basica` | `censo_escolar_pre2007` | 704 | 2005–2006 | 44 | 0 | 0 |
| `ocupados` | `pnadc` | 160 | 2016–2025 | 10 | 0 | 0 |
| `pib_nominal` | `scr_ref2010` | 352 | 2002–2023 | 22 | 0 | 0 |
| `pib_participacao` | `scr_ref2010` | 330 | 2002–2023 | 0 | 0 | 0 |
| `pib_per_capita` | `scr_ref2010` | 336 | 2002–2023 (sem 2007) | 336 | 0 | 0 |
| `pib_volume` | `scr_ref2010` | 330 | 2002–2023 | 0 | 0 | 0 |
| `populacao` | `censo_2000_2010` | 32 | 2000, 2010 | 2 | 0 | 0 |
| `populacao` | `censo_2022` | 16 | 2022 | 1 | 0 | 0 |
| `populacao` | `estimativa_pos_censo2022` | 48 | 2024–2026 | 3 | 45 | 0 |
| `populacao` | `estimativa_pre_censo2022` | 304 | 2001–2021 (sem 2007 e 2010) | 19 | 285 | 0 |
| `populacao_pnadc` | `pnadc` | 224 | 2012–2025 | 14 | 0 | 0 |
| `renda_dom_pc` | `pnadc` | 224 | 2012–2025 | 14 | 0 | 0 |
| `rendimento_trabalho` | `pnadc` | 210 | 2012–2025 | 0 | 0 | 0 |
| `superior` | `censup_pre2009` | 384 | 2001–2008 | 24 | 0 | 0 |

As linhas `derivado` são o Brasil fora do Nordeste (soma ou razão dos insumos) e o `pib_per_capita` inteiro (calculado pelo projeto). As `indisponivel` são os anos sem pesquisa (2010 da PNAD antiga) e as
contagens regionais que a PNAD Contínua não publicou em 2020 a 2022. Nenhuma linha é interpolada ou projetada.

### Os três avisos A01

Aviso A01 é "variação acima do limiar da ficha entre observações consecutivas da mesma série e território"; não bloqueia e pede explicação. Nos três casos a variação está **no arquivo da fonte** (o projeto
só padroniza; os valores foram conferidos lendo o arquivo bruto direto, fora do padronizador), e nenhum é erro de leitura.

1. **`abandono_em` / `indicadores_inep`: 32 casos, limiar 50%.** Por transição: 2019→2020 em 10 territórios, 2020→2021 em 9, 2021→2022 em 4, 2022→2023 em 5, 2024→2025 em 4; todos na rede `total`.
   - Leitura do arquivo bruto: Bahia 7,1% (2019), 1,0% (2020), 10,6% (2021), 11,7% (2022), 4,8% (2023), 2,7% (2025); Brasil 4,8, 2,3, 5,0, 5,7 e 3,4 (2019 a 2023) e 2,2 (2025), iguais aos da base. No mesmo arquivo de 2020,
     a aprovação total do ensino fundamental da Bahia sobe de 86,7% (2019) para 97,2%, e a do Brasil de 94,2% (2022) para 95,8% (2023): o movimento aparece nas três taxas do INEP, não só na de abandono do médio.
   - 2020 e 2021: é o par de anos do ensino remoto da pandemia (o abandono despenca em 2020 e volta em 2021); a ficha do `ideb` já registra a nota da pandemia. A explicação do contexto não vem de nota do INEP lida aqui, e sim
     da coincidência com o período; o valor, porém, é o oficial.
   - 2022→2023 e 2024→2025: quedas fortes e generalizadas (Bahia 11,7 para 4,8; Nordeste e Brasil também). O documento do INEP "Taxas de Rendimento Escolar" (2023,
     `https://download.inep.gov.br/publicacoes/institucionais/estatisticas_e_indicadores/taxas_de_rendimento_escolar_2023.pdf`, sha256 `06836ea9`, 8 páginas, baixado com a CA da RNP) define a taxa de abandono como
     ABA / (APR + REP + ABA) × 100, a mesma fórmula de todos os anos, e não anuncia mudança de método. Não foi encontrada nota do INEP que atribua a queda a uma causa; fica registrada como **variação da fonte, de causa
     não documentada**, que a série trata como observação oficial. Quem for comparar 2023 em diante com os anos anteriores deve ler a série com essa ressalva.
   - Em taxas pequenas (0,3% a 3%) uma diferença de décimos já passa de 50%; é o caso de Pernambuco (0,3 para 1,4) e do Rio Grande do Norte (0,6 para 14,7).
2. **`matriculas_basica` / `censo_escolar_pre2007`: 6 casos, limiar 50%**, todos de 2005 para 2006 e em redes pequenas: creche estadual do PI (66 para 0) e do RN (147 para 649), ensino fundamental federal do RN (36 para 67),
   pré-escola estadual do PI (2.866 para 891), pré-escola federal do CO (40 para 0) e da PB (75 para 212). Com poucas matrículas na rede, a variação de dezenas já passa de 50%. Os totais do território e da etapa variam bem menos
   (PI, pré-escola total: 109.619 para 110.199, a redução da rede estadual aparece na municipal, de 75.842 para 78.368; RN, creche total: 40.953 para 44.657) e a regra R07 (soma das UFs e das regiões) passa. Característica da
   fonte (redistribuição de matrículas entre redes, redes minúsculas), não erro.
3. **`superior` / `censup_pre2009`: 1 caso, limiar 50%**: universidades de Alagoas, de 1 (2004) para 2 (2005). A contagem tem valores de 1 a 3 por UF, e uma universidade a mais é 100%. A série de Alagoas continua 1, 1, 1, 1, 2, 2, 3, 3
   (2001 a 2008), crescente e sem reversão. Variação real da contagem, não erro.

### Mudança de código desta tarefa

Uma: a leitura de planilhas (`padronizacao/planilha.py`) silencia o aviso do openpyxl "Cannot parse header or footer so it will be ignored". A planilha `TX_REND_REG_2015.xlsx` (taxas de rendimento de 2015, regiões, do INEP)
traz o rodapé de impressão em formato fora do padrão do Excel; o aviso é só sobre cabeçalho e rodapé de impressão e não afeta nenhum dado lido, mas saía no stderr do `consolidar` e, sob `python -W error`, derrubava a
série `abandono_em` com "não foi possível ler" (virava pendência). Teste: `test_rodape_de_impressao_ilegivel_nao_atrapalha_a_leitura` (planilha sintética com rodapé sem os códigos `&L`, `&C`, `&R`, lida com avisos como erro).
Depois da correção, o ensaio completo roda com `python -W error` sem saída de aviso e com a mesma base, byte a byte.

### O que o ensaio não exercitou

- `matriculas_basica/educacenso` e `superior/censup` (Tarefa C2). Por isso `matriculas_basica` e `superior` foram ensaiados só com as séries antigas (2005 e 2006; 2001 a 2008), e a leitura conjunta das séries do mesmo
  indicador, com as junções 2006/2007 e 2008/2009, fica para o ensaio após a C2.
- `pobreza` e `extrema_pobreza` (não verificadas, fora da coleta).
- Comparação com base publicada (A02) e `publicar` sem ensaio: não há base publicada; a primeira publicação real é da Tarefa C8.
