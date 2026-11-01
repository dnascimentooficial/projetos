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

Bloco IBGE, partes A (população e PIB) e C (`pib_volume`, planilha `.xls`), e Tarefa 14d (`pib_per_capita` calculado
pelo projeto e conferido contra valores publicados). Data de todas as verificações: 2026-11-01.

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
| `pib_per_capita` | `scr_ref2010` | cálculo do projeto: SIDRA 5938 v37 ÷ população (6579 v9324; 202 e 4709 v93) × 1000 | 2002 a 2023, sem 2007 | sim (conferido) |
| `pib_volume` | `scr_ref2010` | `tab03.xls` (aba `Tabela3`) de `Especiais_2002_2023_xls.zip` | 2002 a 2023 | sim |

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
| 2002 a 2006, 2008, 2009, 2011 a 2021 | estimativa do próprio ano (`estimativa_pre_censo2022`) | 6579, v9324 | conferido em 2016 e 2021 (abaixo) |
| 2010 | Censo 2010 (`censo_2000_2010`) | 202, v93 | conferido em 2010; a 6579 não tem 2010 |
| 2022 | Censo 2022 (`censo_2022`) | 4709, v93 | conferido em 2022; a 6579 não tem 2022 |
| 2023 | Censo 2022 (`censo_2022`, ano fixo 2022) | 4709, v93 | conferido em 2023; o IBGE não publicou estimativa de 2023 |
| 2007 | sem valor | | ver abaixo |

Os anos de estimativa não conferidos um a um (2002 a 2006, 2008, 2009, 2011 a 2015, 2017 a 2020) seguem a mesma
regra dos conferidos (estimativa do próprio ano, a única população anual da 6579 para eles). Indício
adicional para 2002: a razão Nordeste/Brasil divulgada pelo IBGE é 0,47 (release "Contas Regionais 2016"); o
cálculo dá 3.989,09 ÷ 8.525,24 = 0,468.

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

Critério: diferença ≤ 0,5% em todos os pontos. Resultado: maior diferença absoluta 0,087% (Maranhão, 2010);
2021 e 2023 batem ao centavo. Diferença = (calculado − publicado) ÷ publicado.

| Ano | Território | Calculado (R$) | Publicado (R$) | Diferença | Fonte do publicado |
|---|---|---|---|---|---|
| 2010 | BR | 20.370,79 | 20.371,64 | −0,004% | [1] |
| 2010 | NE | 9.848,34 | 9.848,97 | −0,006% | [1] |
| 2010 | PE | 11.048,75 | 11.049,07 | −0,003% | [1] |
| 2010 | BA | 11.016,66 | 11.012,34 | +0,039% | [1] |
| 2010 | CE | 9.386,27 | 9.390,62 | −0,046% | [1] |
| 2010 | MA | 7.043,52 | 7.049,63 | −0,087% | [1] |
| 2010 | PI | 7.141,30 | 7.140,47 | +0,012% | [1] |
| 2016 | BR | 30.421,61 | 30.410 (R$ 30,41 mil) | +0,038% | [2] |
| 2016 | NE | 15.784,01 | 15.779,11 | +0,031% | [2], [3] |
| 2016 | CE | 15.442,63 | 15.438 | +0,030% | [3] |
| 2016 | PE | 17.783,11 | 17.777 | +0,034% | [2] |
| 2016 | BA | 16.936,99 | 16.931 | +0,035% | [2] |
| 2016 | MA | 12.267,70 | 12.264,28 | +0,028% | [4] |
| 2021 | BR | 42.247,52 | 42.247,52 | 0,000% | [5], [6] |
| 2021 | CE | 21.090,10 | 21.090,10 | 0,000% | [6] |
| 2021 | PE | 22.823,59 | 22.823,59 | 0,000% | [7] |
| 2021 | BA | 23.530,94 | 23.530,94 | 0,000% | [7] |
| 2021 | MA | 17.471,85 | 17.471,85 | 0,000% | [7] |
| 2022 | BR | 49.633,83 | 49.638 | −0,008% | [8] |
| 2022 | MA | 20.627,91 | 20.632,62 | −0,023% | [9] |
| 2023 | BR | 53.886,67 | 53.886,67 | 0,000% | [10] |
| 2023 | NE | 27.681,97 | 27.681,97 | 0,000% | [10] |
| 2023 | CE | 26.405,96 | 26.405,96 | 0,000% | [10] |
| 2023 | PE | 29.857,27 | 29.857,27 | 0,000% | [10] |
| 2023 | BA | 30.476,54 | 30.476,54 | 0,000% | [10] |
| 2023 | MA | 22.020,63 | 22.020,63 | 0,000% | [10] |
| 2023 | RN | 30.804,91 | 30.804,91 | 0,000% | [11] |

Leitura das diferenças: 2021 e 2023 vêm da edição das Contas Regionais em que o ano é o mais recente, e o PIB
desses anos é o mesmo da tabela 5938 atual; batem exatamente. Em 2010, 2016 e 2022 os valores publicados são de
edições anteriores (2010: série de referência 2010 divulgada em 2015/2016; 2016: Contas Regionais 2016, de 2018;
2022: Contas Regionais 2022, de 2024), e o PIB desses anos foi revisado nas edições seguintes, o que explica as
diferenças de até 0,09%. Um denominador de outra fonte daria diferenças de outra ordem (com a projeção
`POP_PROJE` do Ipeadata, cerca de 4% no Brasil em 2023).

Fontes dos valores publicados (achadas por busca na web em 2026-11-01; nenhuma pôde ser baixada nesta sessão:
`agenciadenoticias.ibge.gov.br`, `biblioteca.ibge.gov.br`, `www.ibge.gov.br`, `portalantigo.ipea.gov.br`,
`bnb.gov.br` e os demais sites abaixo estão fora da rede liberada; os números foram lidos nos trechos que a busca
devolveu):

1. Ipea, Boletim Regional, Urbano e Ambiental nº 15, "Indicadores territoriais" (tabela de PIB per capita das UFs
   com dados das Contas Regionais do IBGE): https://portalantigo.ipea.gov.br/agencia/images/stories/PDFs/boletim_regional/160906_bru15_indicadores01_regionais.pdf
   (cópia: https://repositorio.ipea.gov.br/bitstreams/0f75c28f-35f2-4c22-814b-ae23ac0f45f6/download).
   Brasil, Nordeste, Pernambuco e Bahia apareceram no trecho como valores de 2010; Maranhão, Piauí e Ceará vieram
   da mesma tabela, mas o trecho não repetiu o ano (o cálculo de 2010 é o único que se aproxima: os de 2009 e
   2011 diferem dos valores publicados em mais de 8%).
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

Pontos de fonte primária do IBGE: todos os de 2023 menos o Rio Grande do Norte ([10]), Maranhão 2016 ([4]) e Brasil
2021 ([5]). Os demais são reproduções do número do IBGE por órgãos públicos (Ipea, BNB, Ipece, Fapespa, IMESC) ou
pela imprensa.

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

## Divergências em relação à seção 4 da spec

1. `populacao`: "estimativas e censos IBGE, 2000+" virou quatro séries (`estimativa_pre_censo2022`, `estimativa_pos_censo2022`, `censo_2000_2010`, `censo_2022`). O ano 2000 só existe como Censo; 2007, 2010, 2022 (nas estimativas) e 2023 (em nenhuma fonte) ficam sem valor.
2. `pib_volume`: série confirmada na fonte (2002 a 2023, 15 territórios, `Especiais_2002_2023_xls.zip`/`tab03.xls`), lida com o novo formato `xls`; a comparação é `brasil`, não `brasil_fora_ne` (spec admite: "senão Brasil"). A fonte traz o índice encadeado 2002 = 100 de cada território, sem variação anual em %.
3. `pib_per_capita`: o IBGE não publica o PIB per capita por território em formato legível; a spec previa coletá-lo das Contas Regionais, e o projeto passou a calculá-lo (PIB 5938 ÷ população do ano que o IBGE usou × 1000), conferido contra valores publicados (diferença máxima 0,087%). Cobre 2002 a 2023 sem 2007 (sem denominador conferido); a fonte da série declara o cálculo.
4. `populacao_contas_regionais`: removida (a spec a previa como denominador do PIB per capita); o denominador agora são as séries de `populacao`, escolhidas por ano no `calculo` da ficha `pib_per_capita`.
5. `pib_participacao`: sem divergência (2002 a 2023, comparação `nenhuma`).
