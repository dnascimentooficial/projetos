# Base histórica de indicadores do Nordeste

Pipeline em Python que coleta indicadores oficiais (IBGE, INEP, Ipea) do Brasil, das cinco regiões e das nove
UFs do Nordeste, padroniza tudo numa base longa única, valida e publica em `dados/base/`. O desenho completo
está em `docs/specs/2026-10-31-base-historica-design.md`; as conferências feitas fonte a fonte, em
`docs/dicionario-verificacao.md`.

> **Primeira publicação real em 2026-11-01** (ver "Situação da publicação", abaixo). As fixtures de
> `testes/fixtures/` continuam sintéticas (valores derivados de 99999) e nunca chegam à base: a regra R01 barra.

## Site e licença

O site **Nordeste em Números** (https://nordeste.dnascimento.com.br) é gerado a partir desta base pelo comando
`python -m nordeste site` e atualizado toda semana pelo workflow `.github/workflows/atualizar.yml`, que publica
na branch `site-publicado`. A compilação está sob **CC BY 4.0**; exceções (fontes, axe-core, foto da abertura)
em [`LICENSE.md`](LICENSE.md).

## Situação da publicação

| Item | Valor |
|---|---|
| Data | 2026-11-01, aprovada pelo usuário depois do resumo do ensaio (`publicar --ensaio`) |
| Conteúdo | 23 indicadores, 32 séries, todas `verificado: true`; 17.057 linhas na base e 43.430 de métricas derivadas |
| Validação | nenhum erro; 6 avisos A01 (variação acima de 50%), explicados em `docs/dicionario-verificacao.md` |
| Base publicada | `dados/base/base_nordeste.csv`, sha256 `f572acb05c16193b788e78433abaea3ad481a2f36ec8b2ced64537fe50913b9d` (idêntica à base de trabalho validada no ensaio) |
| Métricas | `dados/base/derivados.csv`, sha256 `6a305a42a81128b6b3c910fae40faacd7819cb0f3b92622f1acff19d0503455c` |
| Rastro | `dados/relatorios/coletas.csv` (uma linha por coleta, com URL, data e sha256 do arquivo bruto) |

Versionados: `dados/base/` e `dados/relatorios/`. Fora do Git: `dados/brutos/` e `dados/trabalho/`.

**Divergência desta publicação (decisão do usuário, 2026-11-01):** os pacotes das cinco séries do INEP
(`matriculas_basica`: `educacenso`, `censo_escolar_pre2007`, `censo_escolar_2000_2002`; `superior`: `censup`,
`censup_pre2009`) não foram baixados de novo na raiz da publicação. São os pacotes coletados com rede no mesmo
dia, nas Tarefas C4 e C5, reaproveitados depois de conferir que as fichas não mudaram e que o sha256 de cada
pacote é o do registro de coletas. As demais séries foram coletadas de novo, com rede, na raiz da publicação.
O ganho foi evitar cerca de duas horas de download; os pacotes usados são os do registro de coletas, com sha256 conferido.

**O que falta e está declarado:** PIB per capita de 2007 (sem valor publicado para conferir o cálculo);
matrículas de 2003 e 2004 (sinopses só em PDF); renda e pobreza antes de 2012 (PNAD antiga não incorporada);
PIB de 2024 (Contas Regionais 2024 ainda não divulgadas em 2026-11-01); PNAD de 2010 (ano sem pesquisa).
Ressalvas: a queda do abandono no ensino médio em 2022→2023 e 2024→2025 está na fonte do INEP, com causa não
documentada; a linha de pobreza foi confirmada pelo Ipeadata, não por publicação do IBGE (decisão do usuário).

## Requisitos

- Python 3.12 ou mais novo.
- Dependências (instaladas pelo `pip`): `pandas`, `numpy`, `pyarrow`, `pyyaml`, `requests`, `certifi`,
  `openpyxl`, `xlrd`; para os testes, `pytest`.
- Recursos para a coleta real completa: as séries do INEP com dezenas de arquivos (`matriculas_basica/educacenso`
  e `superior/censup`) ainda baixam ~2,7 GB (`educacenso`, ~49 minutos a 0,9 MB/s) e ~3,7 GB (`censup`, ~72
  minutos a 0,85 MB/s), porque cada zip passa inteiro pelo disco para o SHA-256 da fonte ficar registrado.
  Mas o pacote bruto guardado em `dados/brutos/` tem ~37 MB (`educacenso`) e ~38 MB (`censup`), e nem `coletar`
  nem `consolidar` passam de ~450 MB de RAM. Durante a
  coleta, deixe livre em disco ~500 MB (o maior zip, de 397 MB, e a planilha extraída dele, apagados assim que reduzidos).

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
  Nas séries grandes do INEP, prefira `coletar --indicador ID`, um indicador por vez: a coleta de rede de
  `educacenso` e `censup` é sequencial e leva de 49 a 72 minutos cada (a de `educacenso`, com 19 zips, levou
  49 minutos, a ~0,9 MB/s, e a de `censup`, com 16 zips, 72 minutos, a ~0,85 MB/s, ambas em 2026-11-01). Se a rede cair no meio, as partes que já
  chegaram ficam em `dados/trabalho/partes/` e o próximo `coletar` baixa só as que faltam (ver
  [Séries com partes](#séries-com-partes-o-pacote-reduzido)).
- `consolidar` padroniza as coletas, deriva o Brasil fora do Nordeste e os indicadores calculados e grava o
  resultado em `dados/trabalho/` (fora do Git) e os relatórios de cobertura em `dados/relatorios/`.
- `validar` roda as regras sobre a base de trabalho sem publicar nada e grava `dados/relatorios/validacao.csv`.
- `publicar` valida e, se aprovada, grava `dados/base/` (`base_nordeste.csv` e `.parquet`, `derivados.csv` e
  `base_nordeste_completa.csv`, esta no padrão do Excel brasileiro: UTF-8 com BOM, `;` e vírgula decimal). Com
  `--ensaio`, executa tudo e gera os relatórios sem escrever em `dados/base/`.

Cada comando é idempotente. `coletar` só busca na rede séries com `verificado: true` na ficha; as séries
com `verificado: false`, se houver (hoje nenhuma), são puladas com um aviso em stderr e não contam como falha. Uma série que
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

### Séries com partes: o pacote reduzido

As séries com `partes` (as do INEP: um zip por ano, às vezes vários por série) gravam um único arquivo bruto por
série: um zip sem compressão, com data e atributos fixos (o mesmo conteúdo da fonte dá sempre o mesmo SHA-256),
que traz `manifesto.json` e um arquivo por URL. Desde novembro de 2026 o pacote não guarda o zip baixado:

- de cada URL cujas partes declaram `arquivo_no_zip`, fica um zip reduzido só com os membros declarados, com os
  bytes comprimidos copiados do original (nada é recomprimido; os dados comprimidos do reduzido nunca passam dos do original, mas os cabeçalhos
  do zip são regravados, e o arquivo pode ficar alguns bytes maior, por exemplo quando o nome do membro não é
  ASCII e passa de CP437 para UTF-8);
- um membro `.xlsx` lido só por partes com `aba` também é podado: ficam as abas declaradas e o que elas usam
  (estilos, textos compartilhados, tema), com as folhas copiadas byte a byte. O podado só entra se for menor
  que o membro comprimido do zip baixado (senão vai o membro como estava). O nome do membro não muda, e o
  padronizador `planilha` lê o pacote como antes;
- o manifesto registra, por URL, o `sha256_original` e o `bytes_original` do zip baixado (a fonte segue
  rastreável) e, em `membros`, o que foi guardado de cada um (`abas`, quando houve poda);
- se a poda não é segura (aba que não existe, estrutura de planilha desconhecida), o membro segue inteiro e o
  erro de layout aparece no `consolidar`, como antes;
- se o arquivo baixado não é um zip legível ou não tem o membro declarado (download cortado, página de erro
  servida com status 200), a URL falha na coleta e nada é guardado dela; um download com menos bytes que o
  `Content-Length` anunciado (sem `Content-Encoding`) também conta como falha e é tentado de novo.

| Série | Baixado | Pacote bruto antes | Pacote bruto agora |
|---|---|---|---|
| `matriculas_basica/educacenso` (19 zips) | 2,70 GB | ~2,7 GB | 37 MB |
| `superior/censup` (16 zips) | 3,66 GB | ~3,7 GB | 38 MB |

Medido em 2026-11-01 sobre os zips reais: o `consolidar` caiu de ~4 GB de memória (3,9 GB no `educacenso`, 4,2 GB
no `censup`) para ~440 MB com as seis séries do INEP juntas, em 5 minutos. O `coletar` fica entre ~150 MB
(`educacenso`) e ~350 MB (`censup`, cujas planilhas têm muito texto compartilhado), porque cada zip vai em blocos
de 1 MB para o disco em vez de ficar inteiro na memória. A padronização das 90 partes do `educacenso` (então 2007 a 2021) e das 44 do
`censup` dá exatamente as mesmas linhas com o pacote reduzido e com o pacote de zips inteiros.

Coleta de rede medida em 2026-11-01, numa cópia temporária do projeto:

- `coletar --indicador matriculas_basica` com `censo_escolar_pre2007` e `educacenso` de 2007 a 2021 (15 zips,
  1.857 MB): 2.034 s (~0,9 MB/s), pico de 144 MB de RAM, pacote do `educacenso` de 28,3 MB (sha256 `43bd033c`),
  o mesmo montado antes sobre os arquivos locais; `consolidar` das três séries então coletadas: 107 s, pico de
  323 MB;
- o mesmo comando com as três séries de `matriculas_basica` (`censo_escolar_2000_2002`, `censo_escolar_pre2007` e
  `educacenso` de 2007 a 2025, 19 zips, 2.696 MB): 2.946 s, pico de 145 MB, pacote do `educacenso` de 37,1 MB;
  `consolidar` das três séries: 129 s, pico de 270 MB;
- `superior/censup_pre2009` (8 zips, 32 MB): 71 s, pico de 123 MB; o pacote tem os mesmos 32 MB, porque cada zip só
  traz o `.xls` lido (que não é podado);
- `coletar --indicador superior` com as duas séries (`censup_pre2009` e `censup` de 2009 a 2024, 16 zips do
  `censup`, 3.664 MB): 4.296 s (~72 minutos, ~0,85 MB/s; durante os primeiros ~35 minutos rodava, em outra
  conexão, um segundo download dos cinco zips de 2020 a 2024), pico de 344 MB de RAM, pacote do `censup` de 37,7 MB
  (sha256 `ceefe706`); `consolidar` das duas séries: 375 s, pico de 426 MB.

Retomada: cada parte reduzida fica em `dados/trabalho/partes/<indicador>/<série>/` assim que chega. Se uma URL
falha (depois das três novas tentativas), as outras seguem; a série não é registrada e o próximo `coletar`
reaproveita as partes guardadas há até 7 dias, com a mesma receita (mesmos membros e abas na ficha) e o
arquivo íntegro, e baixa só o resto. Com todas as partes, o pacote é gravado, registrado e as partes guardadas
saem. Pacotes coletados antes da redução continuam legíveis.

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
| `extrema_pobreza` | Extrema pobreza | social | exibido | `pnadc` | 2012–2024 | verificada |
| `forca_trabalho` | Pessoas na força de trabalho | trabalho | auxiliar | `pnadc` | 2012– | verificada |
| `gini` | Índice de Gini da renda domiciliar per capita | social | exibido | `pnad`, `pnadc` | 2001–2009; 2011– | verificada |
| `ideb` | Índice de Desenvolvimento da Educação Básica (IDEB) | educacao_basica | exibido | `ideb` | 2005–2025 | verificada |
| `idhm` | Índice de Desenvolvimento Humano Municipal (IDHM) e componentes | social | exibido | `censo`, `pnadc` | 2000–2010; 2012–2024 | verificada |
| `informais` | Pessoas ocupadas em trabalho informal | trabalho | auxiliar | `pnadc` | 2016– | verificada |
| `informalidade` | Taxa de informalidade | trabalho | exibido | `pnadc` | 2016– | verificada |
| `massa_renda_dom_pc` | Massa de rendimento domiciliar per capita | economia | auxiliar | `pnadc` | 2012– | verificada |
| `matriculas_basica` | Matrículas na educação básica, por etapa e rede | educacao_basica | exibido | `censo_escolar_2000_2002`, `censo_escolar_pre2007`, `educacenso` | 2000–2002; 2005–2025 | verificada |
| `ocupados` | Pessoas ocupadas | trabalho | auxiliar | `pnadc` | 2016– | verificada |
| `pib_nominal` | PIB a preços correntes | economia | auxiliar | `scr_ref2010` | 2002–2023 | verificada |
| `pib_participacao` | Participação no PIB nacional | economia | exibido | `scr_ref2010` | 2002–2023 | verificada |
| `pib_per_capita` | PIB per capita | economia | exibido | `scr_ref2010` | 2002–2006; 2008–2023 | verificada, calculada pelo projeto |
| `pib_volume` | PIB real (índice de volume) | economia | exibido | `scr_ref2010` | 2002–2023 | verificada |
| `pobreza` | Pobreza | social | exibido | `pnadc` | 2012–2024 | verificada |
| `populacao` | População residente | contexto | exibido | `estimativa_pre_censo2022`, `estimativa_pos_censo2022`, `censo_2000_2010`, `censo_2022` | 2000–2022; 2024– | verificada |
| `populacao_pnadc` | População residente da PNAD Contínua | contexto | auxiliar | `pnadc` | 2012– | verificada |
| `renda_dom_pc` | Renda domiciliar per capita | social | exibido | `pnadc` | 2012– | verificada |
| `rendimento_trabalho` | Rendimento médio real do trabalho | trabalho | exibido | `pnadc` | 2012– | verificada |
| `superior` | Ensino superior, matrículas de graduação e instituições | educacao_superior | exibido | `censup_pre2009`, `censup` | 2001–2024 | verificada |
<!-- tabela-indicadores:fim -->

## Imagens do site

`python -m nordeste site --saida <pasta>` gera, além das páginas, `og/<pagina>.png` (1200 por 630, a prévia de
compartilhamento de cada página que não é de card) e `cards/<id>.png` (1080 por 1350, o próprio card). As imagens saem
de um Chromium sem tela, pelo Playwright: `python -m pip install -e '.[site]'` e, se o navegador não foi instalado
pelo `playwright install chromium`, `PLAYWRIGHT_CHROMIUM=<caminho do chromium>`. Com `--sem-imagens` nada disso é
preciso. Os testes que abrem o navegador ficam fora da suíte padrão: `python -m pytest -m navegador`.

**Contorno do Nordeste** (`metadados/site/nordeste-contorno.svg`, desenho das prévias): as nove UFs dissolvidas pela
`ferramentas/gerar_contorno.py` (`python -m pip install -e '.[ferramentas]'`). A malha vem da malha municipal do IBGE
redistribuída em CC0 pelo repositório `tbrugz/geodata-br` (`geojson/geojs-21-mun.json` a `geojs-29-mun.json`, em
`raw.githubusercontent.com`), baixada em 2026-11-02; o `geoftp.ibge.gov.br` estava bloqueado na rede de quem gerou.
O contorno é só desenho: baías e frestas estreitas (falhas da malha) são fechadas e a ilha de Fernando de Noronha
não aparece. A origem e a data também estão no comentário no topo do SVG.

**Foto da abertura** (opcional): a chave `foto: {credito, url}` de `metadados/site/textos.yaml` põe a imagem
`src/nordeste/site/estaticos/foto-abertura.webp` (até 200 KB) na abertura e o crédito, com link para a página da
licença, no rodapé e em Sobre os dados. Sem a chave, não há foto nem crédito, e o arquivo não vai para o site.

## Testes

- `python -m pytest`: suíte padrão, offline, sem os testes de contrato.
- `python -m pytest -m rede -v`: contrato com as fontes reais (precisa de rede).
- `python -m pytest -m rede -k "per_capita or ancora" -v`: só a conferência do PIB per capita contra os pontos
  de fonte primária do IBGE e os valores-âncora de três séries leves (rápida, poucos downloads).
- `python -m pytest -m navegador`: o site gerado aberto no Chromium (precisa do extra `site`; leva uns 3 minutos).
  `testes/navegador/` confere acessibilidade com o axe-core (cópia fixa em `testes/navegador/axe.min.js`, licença MPL 2.0
  ao lado), largura a 390 e 1280 px, o site sem JavaScript, movimento reduzido, o peso da página inicial e o Explorar,
  inclusive que o gráfico redesenhado pelo `site.js` é igual ao do Python; `testes/site/` tem os de imagens e do modal.
