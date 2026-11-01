# Base histórica de indicadores do Nordeste

Pipeline em Python que coleta indicadores oficiais (IBGE, INEP, Ipea) do Brasil, das cinco regiões e das nove
UFs do Nordeste, padroniza tudo numa base longa única, valida e publica em `dados/base/`. O desenho completo
está em `docs/specs/2026-10-31-base-historica-design.md`; as conferências feitas fonte a fonte, em
`docs/dicionario-verificacao.md`.

> **A base publicada ainda não existe.** `dados/base/` fica vazio até a primeira publicação real, que só sai
> depois da primeira coleta com rede liberada (roteiro abaixo). Nada no repositório é dado publicado: as
> fixtures de `testes/fixtures/` são sintéticas (valores derivados de 99999) e nunca chegam à base.

## Requisitos

- Python 3.12 ou mais novo.
- Dependências (instaladas pelo `pip`): `pandas`, `numpy`, `pyarrow`, `pyyaml`, `requests`, `certifi`,
  `openpyxl`, `xlrd`; para os testes, `pytest`.
- Recursos para a coleta real completa: as séries do INEP com dezenas de arquivos (`matriculas_basica/educacenso`
  e `superior/censup`) baixam ~2 GB cada e usam ~4 GB de RAM no `coletar` e no `consolidar`. Deixe disco livre
  para o cache em `dados/brutos/` (o pacote bruto de cada uma tem ~1,9 GB).

## Instalação

```
cd nordeste-indicadores
python -m pip install -e '.[dev]'
python -m pytest
```

Todos os comandos rodam a partir de `nordeste-indicadores/`.

## Os quatro comandos

```
python -m nordeste coletar   [--indicador ID] [--offline]
python -m nordeste consolidar
python -m nordeste validar
python -m nordeste publicar  [--ensaio]
```

- `coletar` baixa os arquivos brutos de cada série verificada para `dados/brutos/` e registra a coleta (data,
  URL, SHA-256, origem) em `dados/relatorios/coletas.csv`. Com `--indicador ID`, só as séries desse indicador.
  **Rode `coletar --indicador ID`, um indicador por vez**, nas séries grandes do INEP: a coleta de rede
  sequencial de `educacenso` e `censup` (50 a 60 minutos cada, a ~0,5 MB/s) não foi exercitada de ponta a ponta;
  os layouts foram conferidos sobre os arquivos reais baixados à parte.
- `consolidar` padroniza as coletas, deriva o Brasil fora do Nordeste e os indicadores calculados e grava o
  resultado em `dados/trabalho/` (fora do Git) e os relatórios de cobertura em `dados/relatorios/`.
- `validar` roda as regras sobre a base de trabalho sem publicar nada e grava `dados/relatorios/validacao.csv`.
- `publicar` valida e, se aprovada, grava `dados/base/` (`base_nordeste.csv` e `.parquet`, `derivados.csv` e
  `base_nordeste_completa.csv`, esta no padrão do Excel brasileiro: UTF-8 com BOM, `;` e vírgula decimal). Com
  `--ensaio`, executa tudo e gera os relatórios sem escrever em `dados/base/`.

Cada comando é idempotente. `coletar` só busca na rede séries com `verificado: true` na ficha: as demais
(hoje `pobreza` e `extrema_pobreza`) são puladas com um aviso em stderr e não contam como falha. Uma série que
falha na coleta não derruba as outras: o motivo vai para stderr e para `dados/relatorios/falhas_coleta.csv`
(`indicador_id`, `serie_id`, `motivo`; o cabeçalho sai sempre, e cada `coletar` reescreve o arquivo), o comando
sai com 1 e a série segue com a coleta anterior. No `consolidar`, série sem coleta, com arquivo bruto ausente
(os brutos ficam fora do Git: rode `coletar`) ou com layout inesperado vira pendência em
`dados/trabalho/pendencias.csv`, assim como o indicador cuja comparação usa um insumo pendente; na publicação,
as séries pendentes mantêm as linhas já publicadas.

## A regra R01 e por que não pode ser desligada

R01: **nenhuma linha da base pode vir de uma coleta cuja origem seja `fixture`**. Fixtures são arquivos
sintéticos usados nos testes; se uma só chegasse à base publicada, um número inventado passaria por dado
oficial. A regra também barra a linha derivada (Brasil fora do Nordeste, PIB per capita) cuja derivação usa
algum insumo de origem `fixture`: o registro de derivações lista as coletas usadas, e basta uma ser fixture.
Por isso a regra não tem parâmetro, opção de linha de comando nem variável de ambiente que a desligue,
e um teste ponta a ponta exige que o pipeline inteiro com fixtures seja barrado por ela. Ver o desenho da
validação (regras e avisos) na seção 8 da spec.

### Cuidado com `coletar --offline` no repositório

`coletar --offline` usa as fixtures em vez da rede e **grava no registro de coletas do repositório
(`dados/relatorios/coletas.csv`, versionado) coletas de origem `fixture`**. O `consolidar` usa a última coleta
de cada série: se ela for uma coleta de fixture (série sem coleta real, ou `--offline` rodado depois da coleta
de rede), a base de trabalho passa a ter dado de fixture e `publicar` é barrado pela R01. Para experimentar o
pipeline offline, use uma cópia do projeto e não o repositório de trabalho. `--raiz` (como `--hoje`) é opção
global e vem antes do subcomando:

```
python -m nordeste --raiz /caminho/da/copia coletar --offline
python -m nordeste --raiz /caminho/da/copia consolidar
```

## Domínios que precisam estar liberados na rede

### Usados pelo coletor

Os únicos hosts que `coletar` acessa (um teste confere esta lista contra as URLs que o coletor monta das fichas):

| Domínio | Para quê |
|---|---|
| `apisidra.ibge.gov.br` | tabelas do SIDRA (população, PIB, PNAD Contínua) |
| `ftp.ibge.gov.br` | arquivos das Contas Regionais (PIB em volume) |
| `www.ipeadata.gov.br` | séries do Ipeadata (Gini e desocupação da PNAD, IDHM) |
| `download.inep.gov.br` | arquivos do INEP (IDEB, abandono, matrículas, ensino superior) |

### Citados nas fichas ou de apoio

O coletor não os acessa; servem para conferir à mão as fontes citadas nas fichas e no dicionário de verificação:

| Domínio | Para quê |
|---|---|
| `www.gov.br` | páginas do INEP com as sinopses e os resultados |
| `www.atlasbrasil.org.br` | Atlas do Desenvolvimento Humano, base do IDHM |
| `secure.globalsign.com` | cadeia de certificação citada na conferência TLS do INEP |

### O `ca_extra`: a cadeia TLS incompleta do INEP

O servidor `download.inep.gov.br` não envia o certificado intermediário (RNP ICPEdu OV TLS CA 2025), e a
verificação TLS falha em quem não o tem. Para as séries do INEP, o parâmetro `ca_extra` da ficha aponta para o
certificado versionado em `metadados/certificados/`; o download monta um bundle com as autoridades em uso
(`REQUESTS_CA_BUNDLE` ou o `certifi`) mais esse certificado. A verificação segue ligada: o projeto nunca
desliga a verificação TLS (nada de `verify=False`).

## Roteiro da primeira coleta real

1. **Liberar os domínios** da tabela acima.
2. **`python -m pytest -m rede -v`**: testes de contrato; coletam cada série verificada da rede, padronizam e
   conferem Brasil, Nordeste e o ano inicial da ficha. As duas séries enormes do INEP (`educacenso` e `censup`)
   são puladas, com o motivo, a menos que `NORDESTE_CONTRATO_PESADO=1` esteja definida.
3. **Ajustar os padronizadores** se algum contrato falhar (formato real diferente do documentado).
4. **`python -m nordeste coletar`** (ou `coletar --indicador ID`, um por vez).
5. **`python -m nordeste consolidar`**
6. **`python -m nordeste publicar --ensaio`**: confira `dados/relatorios/validacao.csv` e `mudancas.csv`.
7. **`python -m nordeste publicar`**: a primeira publicação real.

### Anos fixos nas fichas: editar quando sair ano novo

Algumas fichas têm o último ano escrito à mão e precisam de edição quando o IBGE publicar um ano novo:

- **PIB** (`pib_nominal`, `pib_participacao`, `pib_volume` e `pib_per_capita`): `fim: 2023` na série
  `scr_ref2010`. Se a fonte trouxer 2024 com `fim: 2023`, a regra R05 (ano fora da cobertura da série) barra a
  publicação. Ao estender, suba o `fim` das quatro fichas e acrescente o ano novo em
  `calculo.denominador.series_por_ano` do `pib_per_capita` (sem o mapeamento, o ano fica sem valor).
- **População** (`populacao`, série `estimativa_pos_censo2022`): `periodos: 2024-2026` nos parâmetros do
  SIDRA. A série está em curso (`fim: null`), mas o coletor só pede esses anos: um ano novo não é coletado (nem
  avisado) até a faixa ser estendida.

## Indicadores

A tabela abaixo é gerada das fichas em `metadados/indicadores/`, não é editada à mão. Para vê-la:
`python -m nordeste.tabela`; para regravá-la aqui depois de mudar uma ficha:
`python -m nordeste.tabela --atualizar-readme` (um teste falha se ela ficar desatualizada). "Cobertura efetiva"
são os anos das séries verificadas, sem os anos em que nenhuma delas tem pesquisa; `AAAA–` indica série em
curso. Indicadores `auxiliar` são insumos (denominadores e contagens) e não são exibidos.

<!-- tabela-indicadores:inicio (gerada por python -m nordeste.tabela --atualizar-readme) -->
| Indicador | Nome | Eixo | Papel | Séries | Cobertura efetiva | Situação |
|---|---|---|---|---|---|---|
| `abandono_em` | Taxa de abandono no ensino médio | educacao_basica | exibido | `indicadores_inep` | 2007–2025 | verificada |
| `desocupacao` | Taxa de desocupação | trabalho | exibido | `pnad`, `pnadc` | 2001–2009; 2011– | verificada |
| `desocupados` | Pessoas desocupadas | trabalho | auxiliar | `pnadc` | 2012– | verificada |
| `extrema_pobreza` | Extrema pobreza | social | exibido | `pnadc` | — | não verificada (fora da coleta) |
| `forca_trabalho` | Pessoas na força de trabalho | trabalho | auxiliar | `pnadc` | 2012– | verificada |
| `gini` | Índice de Gini da renda domiciliar per capita | social | exibido | `pnad`, `pnadc` | 2001–2009; 2011– | verificada |
| `ideb` | Índice de Desenvolvimento da Educação Básica (IDEB) | educacao_basica | exibido | `ideb` | 2005–2025 | verificada |
| `idhm` | Índice de Desenvolvimento Humano Municipal (IDHM) e componentes | social | exibido | `censo`, `pnadc` | 2000–2010; 2012–2024 | verificada |
| `informais` | Pessoas ocupadas em trabalho informal | trabalho | auxiliar | `pnadc` | 2016– | verificada |
| `informalidade` | Taxa de informalidade | trabalho | exibido | `pnadc` | 2016– | verificada |
| `massa_renda_dom_pc` | Massa de rendimento domiciliar per capita | economia | auxiliar | `pnadc` | 2012– | verificada |
| `matriculas_basica` | Matrículas na educação básica, por etapa e rede | educacao_basica | exibido | `censo_escolar_pre2007`, `educacenso` | 2005–2021 | verificada |
| `ocupados` | Pessoas ocupadas | trabalho | auxiliar | `pnadc` | 2016– | verificada |
| `pib_nominal` | PIB a preços correntes | economia | auxiliar | `scr_ref2010` | 2002–2023 | verificada |
| `pib_participacao` | Participação no PIB nacional | economia | exibido | `scr_ref2010` | 2002–2023 | verificada |
| `pib_per_capita` | PIB per capita | economia | exibido | `scr_ref2010` | 2002–2006; 2008–2023 | verificada, calculada pelo projeto |
| `pib_volume` | PIB real (índice de volume) | economia | exibido | `scr_ref2010` | 2002–2023 | verificada |
| `pobreza` | Pobreza | social | exibido | `pnadc` | — | não verificada (fora da coleta) |
| `populacao` | População residente | contexto | exibido | `estimativa_pre_censo2022`, `estimativa_pos_censo2022`, `censo_2000_2010`, `censo_2022` | 2000–2022; 2024– | verificada |
| `populacao_pnadc` | População residente da PNAD Contínua | contexto | auxiliar | `pnadc` | 2012– | verificada |
| `renda_dom_pc` | Renda domiciliar per capita | social | exibido | `pnadc` | 2012– | verificada |
| `rendimento_trabalho` | Rendimento médio real do trabalho | trabalho | exibido | `pnadc` | 2012– | verificada |
| `superior` | Ensino superior, matrículas de graduação e instituições | educacao_superior | exibido | `censup_pre2009`, `censup` | 2001–2019 | verificada |
<!-- tabela-indicadores:fim -->

## Testes

- `python -m pytest`: suíte padrão, offline, sem os testes de contrato.
- `python -m pytest -m rede -v`: contrato com as fontes reais (precisa de rede).
- `python -m pytest -m rede -k "per_capita or ancora" -v`: só a conferência do PIB per capita contra os pontos
  de fonte primária do IBGE e os valores-âncora de três séries leves (rápida, poucos downloads).
