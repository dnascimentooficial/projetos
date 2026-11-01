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

Bloco IBGE, parte A (população e PIB). Data de todas as verificações: 2026-11-01.

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
| `pib_volume` | `scr_ref2010` | arquivo `.xls` do IBGE | 2002 a 2023 (no arquivo) | ficha não criada |

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

## pib_volume (ficha não criada)

- Fonte oficial confirmada: `https://ftp.ibge.gov.br/Contas_Regionais/2023/xls/Especiais_2002_2023_xls.zip`, arquivo `tab03.xls`, aba `Tabela3`: "Série encadeada do volume do Produto Interno Bruto, segundo Brasil, Grandes Regiões e Unidades da Federação" (base 2002 = 100).
- Conteúdo conferido (lido com `xlrd` fora do projeto): 22 colunas de ano (2002 a 2023) e 33 linhas de território (Brasil, 5 regiões, 27 UFs, nomes com espaços à esquerda), título nas 3 primeiras linhas, anos na linha 4. Brasil 2023 = 158,20; Nordeste 2023 = 163,40.
- Bloqueio: o arquivo é `.xls` (formato antigo), e o IBGE publica só `.xls` e `.ods` nessa pasta. O padronizador `planilha` lê `xlsx` e `csv`, e a única dependência que lê `.xls` (`xlrd`) está fora da lista permitida. A tabela 5938 e as demais do SIDRA não trazem o índice de volume regional.
- Alternativa descartada: Ipeadata `PIBE` (PIB estadual a preços de 2010). Reproduz o índice oficial para o Brasil (158,198 contra 158,198), mas não para o Nordeste (167,13 contra 163,40 em 2023) nem para as UFs (Bahia 2010: 138,14 contra 140,13). Usá-la seria publicar um índice diferente do oficial.
- Comparação (decidida pela pesquisa): `brasil`. O IBGE não publica o PIB a preços do ano anterior por região; a aba de Conta da Produção traz "valor do ano anterior" só para valor bruto da produção, consumo intermediário e valor adicionado bruto (VAB), não para o PIB, então `razao_encadeada` com PIB a preços do ano anterior não é possível com o publicado.
- Pasta do IBGE conferida: `xls/` e `ods/` (e só elas) em `https://ftp.ibge.gov.br/Contas_Regionais/2023/`; nenhum `.xlsx` nem `.csv`. O índice de volume do PIB por região também não está no SIDRA (5938, 21 e 6784 sem essa variável; a 6784 é só Brasil).
- Parâmetros que a ficha teria, quando houver leitor de `.xls` (não escritos na ficha: sem fixture legível, `coletar --offline` quebraria):
  `coletor: arquivo`, `url: https://ftp.ibge.gov.br/Contas_Regionais/2023/xls/Especiais_2002_2023_xls.zip`, `padronizador: planilha`,
  `arquivo_no_zip: tab03.xls`, `aba: Tabela3`, linha de anos na 4ª linha da aba (`linha_cabecalho: 4`), 22 `colunas` (2002 a 2023).
  Cobertura de territórios do arquivo: 33 linhas (Brasil, 5 regiões e 27 UFs), com nomes recuados por espaços (o padronizador tira os espaços).
- Pendente de decisão: ler `.xls` (dependência `xlrd` e `formato: xls` no padronizador `planilha`) ou obter o arquivo em outro formato.

## Divergências em relação à seção 4 da spec

1. `populacao`: "estimativas e censos IBGE, 2000+" virou quatro séries (`estimativa_pre_censo2022`, `estimativa_pos_censo2022`, `censo_2000_2010`, `censo_2022`). O ano 2000 só existe como Censo; 2007, 2010, 2022 (nas estimativas) e 2023 (em nenhuma fonte) ficam sem valor.
2. `pib_volume`: série confirmada na fonte (2002 a 2023), mas a ficha não foi criada porque o arquivo é `.xls`; comparação seria `brasil`, não `brasil_fora_ne`.
3. `pib_per_capita`: a fonte não publica o PIB per capita por território em formato legível; a ficha segue sem verificação.
4. `populacao_contas_regionais`: o denominador do IBGE não é legível por máquina; a ficha segue sem verificação.
5. `pib_participacao`: sem divergência (2002 a 2023, comparação `nenhuma`).
