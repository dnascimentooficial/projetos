# Conclusão da base histórica — Design

**Complemento do subprojeto 1** · Data: 2026-11-01 · Status: aprovado em conversa, aguardando revisão do texto

## 1. Objetivo

Levar a base histórica do estado "pipeline pronto, nunca publicado" ao estado "primeira publicação real, com as lacunas viáveis fechadas". Só depois disso o site (subprojeto 3) é retomado, a partir das decisões registradas em `docs/decisoes-dashboard.md`.

Escopo decidido pelo usuário: primeira publicação real + lacunas viáveis dos 16 indicadores atuais. A segunda leva do plano original (SAEB, PIB por setor, escolas, CAPES, RAIS/Caged, expectativa de vida, mortalidade infantil, saneamento) fica para um ciclo próprio.

## 2. Princípios (herdados da spec da base)

- Nada interpolado, nada projetado, nada inventado.
- `verificado: true` só depois de download real com os parâmetros exatos da ficha, passado pelo padronizador do projeto, com evidência em `docs/dicionario-verificacao.md`. Série parcialmente verificada tem `inicio`/`fim` estreitados ao trecho verificado.
- R01 continua sem forma de ser desligada. Verificação TLS nunca é desligada.
- Ferramentas novas só se indispensáveis, com registro como desvio.

## 3. Etapas

### 3.1 Ensaio real completo

Rodar `coletar` (com rede), `consolidar`, `validar` e `publicar --ensaio` sobre todas as fichas verificadas, exceto as séries gigantes do INEP (`educacenso`, `censup`), que dependem da etapa 3.2. Toda falha de integração (regra que dispara no conjunto, conflito entre indicadores, pendência inesperada, erro sem tratamento) é corrigida no código com teste, ou registrada com motivo se for característica da fonte. Critério de saída: ensaio real sem erro bloqueante, com a lista de avisos explicada.

### 3.2 Coleta enxuta das séries grandes do INEP

**Atualização:** este trabalho foi iniciado pelo usuário em outra sessão e está na branch `claude/lucid-newton-fa3yjm` (commits 156bbcc "pacote de partes reduzido, download em blocos e retomada" e 94460ad "coleta de rede do educacenso exercitada de ponta a ponta"). A etapa passa a ser: revisão independente daquela branch contra os requisitos abaixo e, se aprovada, merge na branch da base (sem reescrever o histórico dela). Só se a branch for reprovada ou estiver incompleta o trabalho é refeito ou completado aqui.

Requisitos:

Para partes que declaram `arquivo_no_zip`, o coletor grava no pacote combinado só o membro necessário (a planilha), não o zip inteiro, e registra no manifesto o sha256 do zip original baixado. O download vai em fluxo para um arquivo temporário em disco, sem carregar o zip inteiro na memória. O pacote continua determinístico (sem compressão, sistema e data fixos) e com um sha256 por série. A regra "série só é registrada quando todas as partes chegaram" continua valendo. Meta: pacote das séries grandes em dezenas de MB e `coletar`/`consolidar` abaixo de ~1 GB de memória; README e `observacoes` das fichas atualizados com os custos medidos.

### 3.3 Lacunas viáveis

Cada item tem tempo limitado. O que não fechar fica registrado no dicionário com o motivo.

| Item | O que fazer | Se não der |
|---|---|---|
| Pobreza e extrema pobreza | Identificar a linha de pobreza usada pelas tabelas (5877 e 5817) ou achar a tabela da Síntese de Indicadores Sociais com linha declarada; registrar a linha na ficha; não misturar critérios. **Decisão do usuário (2026-11-01):** a linha identificada pela metadata do Ipeadata (US$ 8,30 e US$ 3,00/dia, PPC 2021; 195/195 valores iguais ao SIDRA) vale como confirmação, com nota de origem e registro como divergência | Seguem `verificado: false` e fora do site |
| Matrículas 2022–2025 | Ler os layouts novos das Sinopses | Pendência registrada por ano |
| Matrículas 2000–2002 | Ler as abas com numeração própria | Idem |
| Ensino superior 2020–2024 | Possível após 3.2 | Idem |
| PIB per capita 2007 | Acrescentar a Contagem da População 2007 (SIDRA 793) à ficha `populacao` com verificação real e conferir o per capita calculado contra valor publicado (≤ 0,5%) | 2007 segue sem valor |
| PNAD antiga 2001–2011 para renda e pobreza | Nova busca no Ipeadata e no SIDRA | Registrado como inexistente |
| PIB de 2024 | Se as Contas Regionais 2024 saírem durante o trabalho: ampliar `fim` das fichas do PIB e o mapeamento de população do per capita, com verificação e conferência | Fica para a próxima atualização (README já explica) |

Impossíveis, apenas registrados: matrículas 2003–2004 e ensino superior 2000 (só PDF); IDHM do Nordeste em 2000 e 2010 (não publicado).

### 3.4 Primeira publicação real

1. `coletar` (rede, todas as fichas verificadas), `consolidar`, `publicar --ensaio`.
2. Resumo para o usuário: indicadores e séries que vão ao ar, cobertura efetiva, avisos A01–A03 e seus motivos, os números das métricas principais (razão NE/referência no último ano de cada indicador) e uma amostra de 10 valores conferíveis com link da fonte.
3. Aprovação explícita do usuário.
4. `publicar`. Os arquivos de `dados/base/` e `dados/relatorios/` entram no repositório (versionados, como a spec da base prevê); `dados/brutos/` e `dados/trabalho/` continuam fora do Git.

### 3.5 Revisão final

Revisão da branch inteira desde o último fechamento, com uma rodada única de correções, e decisão do usuário sobre o destino da branch.

## 4. Fora do escopo

Segunda leva de indicadores; site; atualização automática no GitHub (vem com o site).

## 5. Riscos

| Risco | Mitigação |
|---|---|
| Ensaio real revela conflito estrutural entre indicadores | Etapa 3.1 vem antes de tudo e corrige com teste |
| Linha de pobreza não identificável | Pobreza segue fora; nada é publicado com critério desconhecido |
| Layouts novos do INEP exigem recurso que o padronizador não tem | Parar e decidir; não forçar leitura |
| Memória do ambiente na coleta do INEP | Etapa 3.2 antes das lacunas do INEP |
| IBGE publica 2024 no meio do trabalho | Item condicional na 3.3 |
