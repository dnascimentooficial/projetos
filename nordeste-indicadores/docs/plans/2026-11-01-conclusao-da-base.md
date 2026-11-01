# Conclusão da base histórica — Plano de implementação

> **Para agentes:** SUB-SKILL OBRIGATÓRIA: use superpowers:subagent-driven-development para executar este plano tarefa a tarefa. Os passos usam checkbox (`- [ ]`).

**Objetivo:** fazer a primeira publicação real da base, depois de um ensaio real completo, da incorporação da coleta enxuta do INEP e do fechamento das lacunas viáveis.

**Arquitetura:** sem mudança de arquitetura; correções e acréscimos no pacote `nordeste` existente, fichas novas ou ampliadas em `metadados/indicadores/`, evidência em `docs/dicionario-verificacao.md`.

**Tecnologia:** a mesma da base (Python ≥ 3.12, pandas, pyarrow, pyyaml, requests, openpyxl, xlrd, numpy, certifi, pytest).

**Spec:** `nordeste-indicadores/docs/specs/2026-11-01-conclusao-da-base-design.md` (e, para tudo o que ela não muda, `docs/specs/2026-10-31-base-historica-design.md`).

## Restrições globais

- Comandos a partir de `nordeste-indicadores/`; suíte `python -m pytest -W error` verde e abaixo de ~3 min ao fim de cada tarefa; ensaio offline (`coletar --offline`, `consolidar`, `publicar --ensaio`) barrado só pela R01.
- `verificado: true` só com download real dos parâmetros exatos, padronizado pelo projeto, com evidência por ano no dicionário; série parcialmente verificada tem `inicio`/`fim` estreitados.
- Nada interpolado, projetado ou inventado. R01 sem forma de desligar. TLS nunca desligado. Não contornar bloqueio a robôs.
- Arquivos baixados: diretório novo no scratchpad da sessão, lidos com `python -I`, nunca commitados.
- Toda divergência em relação à spec da base vai para a lista de divergências do dicionário.
- Commits terminam com as linhas de atribuição da sessão de quem os escreve.

## Foco de revisão

1. Ensaio real: uma série com pendência não pode apagar nem alterar em silêncio as outras (conferir `pendencias.csv` e `mudancas.csv` do ensaio).
2. Merge da branch da outra sessão: nenhum teste ou regra da base pode ter sido afrouxado; R01, territórios esperados e pacote determinístico continuam valendo.
3. Fichas ampliadas: anos novos sem evidência real não podem entrar em `inicio..fim` de série verificada.
4. Publicação real: os arquivos publicados devem ser exatamente os que o ensaio aprovado mostrou (mesmo conteúdo da base de trabalho validada).
5. Linha de pobreza: nenhuma ficha de pobreza pode virar `verificado: true` sem a linha declarada e conferida contra uma publicação do IBGE. **Exceção decidida pelo usuário em 2026-11-01 (opção A):** a metadata do Ipeadata vale como confirmação da linha (US$ 8,30 e US$ 3,00/dia, PPC 2021), com nota explícita de origem e registro como divergência (tarefa C3b).

---

### Tarefa C1: Ensaio real completo

**Arquivos:** os que o ensaio revelar; testes correspondentes; `docs/dicionario-verificacao.md` (seção nova "Ensaio real de 2026-11").

- [ ] **Passo 1:** em cópia temporária do projeto (fora do repositório), rodar `python -m nordeste --raiz <cópia> coletar` com rede para todas as fichas verificadas, excluindo `matriculas_basica/educacenso` e `superior/censup` (use `--indicador` por ficha; para as duas fichas do INEP com séries grandes, colete só as séries pequenas ou pule a ficha e registre). Depois `consolidar`, `validar`, `publicar --ensaio`.
- [ ] **Passo 2:** registrar no relatório da tarefa: códigos de saída, `validacao.csv` (erros e avisos), `pendencias.csv`, `falhas_coleta.csv`, contagem de linhas por indicador e série.
- [ ] **Passo 3:** para cada erro bloqueante ou falha de integração: escrever o teste que reproduz (RED), corrigir (GREEN). Característica legítima da fonte vira registro no dicionário com motivo, não código. Avisos A01–A03: explicar cada um no dicionário (variação real, revisão, atraso de fonte) ou corrigir se for erro.
- [ ] **Passo 4:** repetir o ensaio até não haver erro bloqueante. Suíte completa e ensaio offline verdes.
- [ ] **Passo 5:** commit `fix(nordeste): ensaio real completo sem erro bloqueante` (ou `docs(...)` se só houve registro).

### Tarefa C2: Incorporar a coleta enxuta da outra sessão

**Arquivos:** os da branch `claude/lucid-newton-fa3yjm`.

- [ ] **Passo 1 (controlador):** revisão independente de `git diff <merge-base>..origin/claude/lucid-newton-fa3yjm` contra os requisitos da seção 3.2 da spec: só o membro necessário no pacote, sha256 do zip original no manifesto, download em fluxo para disco, retomada, pacote determinístico, série registrada só com todas as partes, testes sem rede, nenhum teste/regra afrouxado.
- [ ] **Passo 2:** se aprovada: `git merge --no-ff origin/claude/lucid-newton-fa3yjm` na branch da base, resolver conflitos (sem reescrever histórico), suíte completa, ensaio offline. Se reprovada ou incompleta: implementar aqui o que faltar, com TDD, citando a branch como base.
- [ ] **Passo 3:** medir de verdade (uma coleta real de `superior/censup_pre2009` ou de uma série grande, conforme o tempo): tamanho do pacote e pico de memória do `coletar`/`consolidar`; atualizar README e `observacoes` com os números medidos.
- [ ] **Passo 4:** commit do merge e dos ajustes.

### Tarefa C3: Linha de pobreza

**Arquivos:** `metadados/indicadores/pobreza.yaml`, `extrema_pobreza.yaml`, dicionário, fixtures se mudarem.

- [ ] **Passo 1:** identificar, para as tabelas SIDRA 5877 e 5817 (ou outra tabela oficial com linha declarada, ex. Síntese de Indicadores Sociais em ftp.ibge.gov.br), qual linha de pobreza é usada (ex.: US$ 2,15 e US$ 6,85 PPC 2017; US$ 3,00 e US$ 8,30 PPC 2021; frações do salário mínimo). Evidência: descrição oficial da tabela (`desctabapi.aspx`), notas técnicas da SIS, e conferência de pelo menos 3 valores contra uma publicação do IBGE.
- [ ] **Passo 2:** se identificada e conferida: declarar a linha na `descricao`/`metodologia`/`unidade`, `verificado: true` no trecho conferido; se a fonte mudou de linha no tempo, separar em séries. Se não: manter `verificado: false` e registrar o que foi tentado.
- [ ] **Passo 3:** testes do dicionário, ensaio offline, suíte; commit.

### Tarefa C3b: Pobreza verificada pela confirmação do Ipeadata (decisão do usuário)

**Arquivos:** `metadados/indicadores/pobreza.yaml`, `extrema_pobreza.yaml`, dicionário, testes do dicionário.

**Contexto:** a C3 identificou a linha (US$ 8,30/dia na 5877 e US$ 3,00/dia na 5817, PPC 2021) pela metadata do Ipeadata, com 195/195 valores do SIDRA iguais aos do Ipeadata, e manteve `verificado: false` por falta de conferência contra publicação do IBGE (descrição SIDRA e biblioteca do IBGE recusam robôs). Em 2026-11-01 o usuário decidiu aceitar o Ipeadata como confirmação.

- [ ] **Passo 1:** nas duas fichas: `verificado: true`; `fim` fechado no último ano com download real conferido (2024, se a evidência da C3 cobrir até lá; conferir no dicionário); linha declarada em `descricao`/`unidade`/`metodologia`; nota explícita: "Linha declarada segundo o Ipeadata (metadados da série); não conferida contra publicação do IBGE, que recusa acesso automatizado; aceita como confirmação por decisão do usuário em 2026-11-01." Manter a nota da quebra de consolidação (primeiras entrevistas 2012–2019 e 2023–2024; quintas entrevistas 2020–2022).
- [ ] **Passo 2:** dicionário: evidência por ano já existente da C3 referenciada; nova entrada na lista de divergências (o foco de revisão 5 previa conferência contra o IBGE); risco registrado (se o IBGE trocar a linha e o Ipeadata não atualizar a metadata, a ficha fica desatualizada — reverificar a linha a cada atualização anual).
- [ ] **Passo 3:** testes do dicionário (pobreza verificada exige a nota de origem e a quebra de consolidação), ensaio offline, suíte; commit.

### Tarefa C4: Matrículas 2022–2025 e 2000–2002

**Arquivos:** `metadados/indicadores/matriculas_basica.yaml`, fixtures, dicionário; código só se indispensável (parar e reportar antes de criar recurso novo no padronizador).

- [ ] **Passo 1:** 2022–2025: ler os layouts novos das Sinopses (cabeçalho e numeração de tabelas mudaram), acrescentar partes por ano com `territorios_esperados`, verificar ano a ano. Ampliar `fim` da série `educacenso` só até o último ano verificado em sequência.
- [ ] **Passo 2:** 2000–2002: ler as abas com numeração própria; se verificados, ampliar `inicio` da série `censo_escolar_pre2007` (2003 e 2004 só em PDF: o trecho 2000–2002 vira série própria, `censo_escolar_2000_2002`, porque não pode haver buraco silencioso dentro de uma série — ou declare 2003–2004 em `anos_sem_publicacao` com nota "só em PDF", se isso for mais fiel; justifique a escolha no dicionário).
- [ ] **Passo 3:** testes, ensaio offline, suíte; commit.

### Tarefa C5: Ensino superior 2020–2024

**Arquivos:** `metadados/indicadores/superior.yaml`, fixtures, dicionário.

- [ ] **Passo 1:** com a coleta enxuta (C2), acrescentar as partes de 2020–2024 à série `censup` com `territorios_esperados`; verificar ano a ano; ampliar `fim` só até o último ano verificado em sequência. 2025 ainda não publicado: registrar.
- [ ] **Passo 2:** testes, ensaio offline, suíte; commit.

### Tarefa C6: Lacunas IBGE/Ipea (PIB per capita 2007, PNAD antiga, PIB 2024)

**Arquivos:** `metadados/indicadores/populacao.yaml`, `pib_per_capita.yaml`, fichas de renda e pobreza, fichas do PIB, dicionário, testes de contrato se aplicável.

- [ ] **Passo 1:** Contagem da População 2007 (SIDRA 793): se verificada, acrescentá-la a `populacao` como série própria e mapear 2007 no `calculo` do per capita **somente** se houver valor publicado de PIB per capita 2007 (referência 2010) para conferir (≤ 0,5%); senão, 2007 segue sem valor e o motivo fica registrado.
- [ ] **Passo 2:** PNAD antiga 2001–2011 para renda domiciliar per capita e pobreza: nova busca (Ipeadata social por UF e região; SIDRA PNAD). Se existir com verificação real, nova série `pnad` (nunca unida à `pnadc`), com `anos_sem_publicacao: [2010]`. Senão, registrar como inexistente.
- [ ] **Passo 3:** PIB 2024: conferir se as Contas Regionais 2024 já saíram (SIDRA 5938 com 2024; FTP `Contas_Regionais/2024/`). Se sim: ampliar `fim` das fichas do PIB (nominal, participação, volume) com verificação, mapear 2024 no per capita com a população adequada e conferir contra valor publicado; atualizar o teste de contrato do per capita. Se não: nada a fazer.
- [ ] **Passo 4:** testes, ensaio offline, suíte; commit.

### Tarefa C7: Primeira publicação real

**Arquivos:** `dados/base/*`, `dados/relatorios/*` (passam a ser versionados), README (seção "Situação da publicação").

- [ ] **Passo 1:** na raiz real do projeto (não em cópia): `coletar` com rede (todas as fichas verificadas, inclusive as séries grandes do INEP com a coleta enxuta), `consolidar`, `publicar --ensaio`. Registrar contagens, avisos e pendências.
- [ ] **Passo 2 (controlador):** montar o resumo para o usuário (seção 3.4 da spec): indicadores e séries, cobertura efetiva, avisos explicados, razão NE/referência no último ano de cada indicador, amostra de 10 valores com link da fonte. **Parar e pedir aprovação explícita.**
- [ ] **Passo 3:** com a aprovação: `publicar`. Conferir que o conteúdo publicado é idêntico ao do ensaio aprovado (mesmo sha256 da base de trabalho validada). Commit `data(nordeste): primeira publicação real da base` com `dados/base/` e `dados/relatorios/`; confirmar que `dados/brutos/` e `dados/trabalho/` seguem fora do Git.

### Tarefa C8: Revisão final

- [ ] **Passo 1 (controlador):** revisão da branch desde 508c343, com triagem dos adiados, uma rodada única de correções e re-revisão.
- [ ] **Passo 2:** apresentar ao usuário o destino da branch (juntar, PR ou manter) e retomar o site.
