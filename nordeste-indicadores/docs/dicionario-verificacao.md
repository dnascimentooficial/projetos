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

Bloco IBGE, partes A (população e PIB) e C (`pib_volume`, planilha `.xls`). Data de todas as verificações: 2026-11-01.

Reverificação de ponta a ponta, na mesma data, por outro executor: `python -m nordeste --raiz <tmp> coletar --indicador <id>`
(rede, só séries `verificado: true`), `consolidar` e `validar` sobre `populacao`, `pib_nominal` e `pib_participacao`.
Resultado: as 6 séries coletaram com os parâmetros das fichas, `validar` saiu com código 0 e sem nenhuma linha em
`validacao.csv` (nem regra bloqueante, nem aviso). `pib_per_capita` e `populacao_contas_regionais` ficaram como
"série pendente: sem coleta", como esperado de séries não verificadas.

## Resumo

| Indicador | Série | Tabela e variável | Cobertura confirmada | Verificada |
|---|---|---|---|---|
| `pib_nominal` (auxiliar) | `scr_ref2010` | SIDRA 5938, v37 | 2002 a 2023 | sim |
| `pib_participacao` | `scr_ref2010` | SIDRA 5938, v496 | 2002 a 2023 | sim |
| `populacao` | `estimativa_pre_censo2022` | SIDRA 6579, v9324 | 2001 a 2021, sem 2007 e 2010 | sim |
| `populacao` | `estimativa_pos_censo2022` | SIDRA 6579, v9324 | 2024 a 2026 | sim |
| `populacao` | `censo_2000_2010` | SIDRA 202, v93 | 2000 e 2010 | sim |
| `populacao` | `censo_2022` | SIDRA 4709, v93 | 2022 | sim |
| `populacao_contas_regionais` (auxiliar) | `scr_ref2010` | não encontrada | | não |
| `pib_per_capita` | `scr_ref2010` | não encontrada | | não |
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

## populacao_contas_regionais / scr_ref2010 (não verificada)

A ficha supõe uma população "das Contas Regionais" como denominador do PIB per capita. Procurado em:

- SIDRA 5938 e 21 (Contas Regionais): nenhuma variável de população ou de per capita.
- Planilhas das Contas Regionais 2023 (`https://ftp.ibge.gov.br/Contas_Regionais/2023/xls/`, pacotes `Especiais_*` e `Conta_da_Producao_*`): sem população.
- SIDRA 6579, 202, 4709: têm população, mas nenhuma tabela traz todos os anos de 2002 a 2023 numa só série (faltam 2007, 2010, 2022 e 2023 nas estimativas).
- Ipeadata `POP_PROJE` (projeção IBGE, revisão 2024) cobre todos os anos de 1980 a 2070 para Brasil, regiões e UFs, mas não é a população que o IBGE usou: com ela, PIB per capita do Brasil em 2023 sai R$ 51.693,88 contra R$ 53.886,67 publicado pelo IBGE (diferença de cerca de 4%).

Achado que ajuda a explicar a diferença, sem resolver a série: o PIB per capita do Brasil em 2023 publicado pelo IBGE
(R$ 53.886,67, segundo a matéria "PIB cresce em todos os 27 estados do país em 2023", Agência de Notícias do IBGE, achada por
busca e não baixada) é exatamente o PIB de 2023 da tabela 5938 (v37, R$ 10.943.345.439 mil) dividido pela população do
Censo 2022 (tabela 4709, 203.080.756): 53.886,67. Ou seja, nas Contas Regionais 2023 o denominador de 2023 é a contagem do
Censo 2022, e não a estimativa de 2023 (que o IBGE não publicou na 6579). Conferido só para o Brasil e só para 2023.
A SIDRA 6784 (Contas Nacionais anuais, só nível Brasil) traz população (211.695 mil em 2023) e PIB per capita
(R$ 51.693,92), mas é outro denominador e não tem região nem UF.

Conclusão: o denominador das Contas Regionais para 2002 a 2022 não está publicado numa série legível por máquina
(hipótese não confirmada: contagens e estimativas oficiais de cada ano). `verificado: false`, `parametros: {}`.

## pib_per_capita / scr_ref2010 (não verificada)

O PIB per capita por Brasil, região e UF não existe em nenhuma tabela SIDRA consultada (5938 não tem a variável) nem nas planilhas das Contas Regionais; só aparece nos informativos em PDF. Busca nos 4.075 metadados do Ipeadata (nome com "PIB"): sem PIB per capita corrente por região e UF. O Ipeadata tem `PIBPCE` (PIB estadual per capita a preços de 2010, só UFs) e `GAC_PIBCAPN` (só Brasil), que não servem à ficha (valores correntes, todos os territórios). `verificado: false`, `parametros: {}`.

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

## populacao_contas_regionais / scr_ref2010 (não verificada)

A ficha supõe uma população "das Contas Regionais" como denominador do PIB per capita. Procurado em:

- SIDRA 5938 e 21 (Contas Regionais): nenhuma variável de população ou de per capita.
- Planilhas das Contas Regionais 2023, pasta `https://ftp.ibge.gov.br/Contas_Regionais/2023/` (só `xls/` e `ods/`, com os mesmos quatro pacotes `Especiais_2002_2023`, `Especiais_2010_2023`, `Conta_da_Producao_2002_2023` e `Conta_da_Producao_2010_2023` e os respectivos `*_indice_das_tabelas.txt`): na 14c, as 1.056 abas dos quatro zips `xls` foram varridas por "capita", "popula" e "habitant" e não há ocorrência. Os índices de tabelas (Especiais: PIB corrente, participação, volume, VAB, volume do VAB por atividade, participação do VAB por atividade) também não listam população nem per capita.
- Outras publicações no FTP: as pastas de 2022, 2018 e 2016 trazem os mesmos pacotes (`Especiais_*`, `Conta_da_Producao_*`; 2018 e 2016 também `PIB_Otica_da_Renda.xlsx`, não aberto, que é a ótica da renda); a de 2013 tem `tab001.xls` a `tab007.xls` e `PIB_Regional_BR.xls`, abertos e sem ocorrência de "capita" nem "popula". São divulgações de outras revisões, não do vintage 2023, e não serviriam de série.
- SIDRA 6579, 202, 4709: têm população, mas nenhuma tabela traz todos os anos de 2002 a 2023 numa só série (faltam 2007, 2010, 2022 e 2023 nas estimativas).
- Ipeadata `POP_PROJE` (projeção IBGE, revisão 2024) cobre todos os anos de 1980 a 2070 para Brasil, regiões e UFs, mas não é a população que o IBGE usou: com ela, PIB per capita do Brasil em 2023 sai R$ 51.693,88 contra R$ 53.886,67 publicado pelo IBGE (diferença de cerca de 4%).

Achado que ajuda a explicar a diferença, sem resolver a série: o PIB per capita do Brasil em 2023 publicado pelo IBGE
(R$ 53.886,67, segundo a matéria "PIB cresce em todos os 27 estados do país em 2023", Agência de Notícias do IBGE, achada por
busca e não baixada) é exatamente o PIB de 2023 da tabela 5938 (v37, R$ 10.943.345.439 mil) dividido pela população do
Censo 2022 (tabela 4709, 203.080.756): 53.886,67. Ou seja, nas Contas Regionais 2023 o denominador de 2023 é a contagem do
Censo 2022, e não a estimativa de 2023 (que o IBGE não publicou na 6579). Conferido só para o Brasil e só para 2023.
A SIDRA 6784 (Contas Nacionais anuais, só nível Brasil) traz população (211.695 mil em 2023) e PIB per capita
(R$ 51.693,92), mas é outro denominador e não tem região nem UF.

Conclusão: o denominador das Contas Regionais para 2002 a 2022 não está publicado numa série legível por máquina
(hipótese não confirmada: contagens e estimativas oficiais de cada ano). `verificado: false`, `parametros: {}`.

Alternativas, não implementadas (decisão do controlador):

1. Denominador montado das tabelas SIDRA de população já verificadas (`populacao`): 6579 nos anos de estimativa, 202 em 2000 e 2010 (Censo) e 4709 em 2022 e 2023 (a hipótese acima, conferida só para o Brasil em 2023). Fica sem valor 2007 (a 6579 não tem o ano) e exigiria uma série nova, com limite declarado na ficha.
2. Ipeadata `POP_PROJE` como denominador, assumindo diferença de cerca de 4% do PIB per capita oficial; série nova e não igual à do IBGE.
3. Ipeadata `PIBPCE` (PIB estadual per capita a preços de 2010), só UFs, outra unidade; não cobre Brasil e regiões.
4. Transcrever o PIB per capita dos informativos em PDF do IBGE (não é legível por máquina; sem URL estável de dados).
5. Tirar o PIB per capita desta entrega e manter `pib_nominal` e `populacao` como insumos.

## pib_per_capita / scr_ref2010 (não verificada)

O PIB per capita por Brasil, região e UF não existe em nenhuma tabela SIDRA consultada (5938 não tem a variável) nem nas planilhas das Contas Regionais (varredura da 14c descrita em `populacao_contas_regionais`); só aparece nos informativos em PDF. Busca nos 4.075 metadados do Ipeadata (nome com "PIB"): sem PIB per capita corrente por região e UF. O Ipeadata tem `PIBPCE` (PIB estadual per capita a preços de 2010, só UFs) e `GAC_PIBCAPN` (só Brasil), que não servem à ficha (valores correntes, todos os territórios). A ficha calcula a razão `pib_nominal` ÷ `populacao_contas_regionais` x 1000, e o denominador não existe (ver a seção anterior e as alternativas). `verificado: false`, `parametros: {}`.

## Divergências em relação à seção 4 da spec

1. `populacao`: "estimativas e censos IBGE, 2000+" virou quatro séries (`estimativa_pre_censo2022`, `estimativa_pos_censo2022`, `censo_2000_2010`, `censo_2022`). O ano 2000 só existe como Censo; 2007, 2010, 2022 (nas estimativas) e 2023 (em nenhuma fonte) ficam sem valor.
2. `pib_volume`: série confirmada na fonte (2002 a 2023, 15 territórios, `Especiais_2002_2023_xls.zip`/`tab03.xls`), lida com o novo formato `xls`; a comparação é `brasil`, não `brasil_fora_ne` (spec admite: "senão Brasil"). A fonte traz o índice encadeado 2002 = 100 de cada território, sem variação anual em %.
3. `pib_per_capita`: a fonte não publica o PIB per capita por território em formato legível (varridas as 1.056 abas das planilhas de 2023); a ficha segue sem verificação.
4. `populacao_contas_regionais`: o denominador do IBGE não está publicado em nenhum arquivo da publicação Contas Regionais 2023; a ficha segue sem verificação (alternativas listadas na seção da série).
5. `pib_participacao`: sem divergência (2002 a 2023, comparação `nenhuma`).
