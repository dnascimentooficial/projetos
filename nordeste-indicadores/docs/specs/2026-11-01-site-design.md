# Site Nordeste em Números — Design

**Subprojeto 3** · Data: 2026-11-01 · Status: aprovado pelo usuário em 2026-11-01

## 1. Objetivo e público

Um site público, em `https://nordeste.dnascimento.com.br`, que responde com dados oficiais a quem diz que "o Nordeste está do mesmo jeito". O autor é Júlio Diógenes; a voz é a dele.

Público: geral, lendo no celular, muitas vezes a partir de um link ou print recebido no WhatsApp.

Critério de sucesso: quem abre entende a resposta em 10 segundos, consegue conferir cada número na fonte oficial e consegue compartilhar um card legível.

Base: a base histórica publicada (`dados/base/`, primeira publicação real em 2026-11-01) e o protótipo aprovado no painel do Claude (https://claude.ai/artifact/4Ekqm88b9JvsyzdLriFi7f). Decisões anteriores em `docs/decisoes-dashboard.md`.

## 2. Decisões do usuário

| Tema | Decisão |
|---|---|
| Endereço | Subdomínio `nordeste.dnascimento.com.br` (criado; SSL ativo). Pasta no servidor: `/home/u411523977/domains/dnascimento.com.br/public_html/nordeste` |
| Hospedagem | Hostinger compartilhada (hPanel), site 100% estático; o pipeline não roda na Hostinger |
| Publicação | Totalmente automática; o que barra é a validação (seção 7) |
| Repositório | Novo, público: `nordeste-em-numeros`, com o histórico do projeto |
| Voz | Primeira pessoa, linguagem simples, sem cenas; perguntas no formato "frase feita × dado"; fechos "No frigir dos ovos" |
| Visual | O de dnascimento.com.br (seção 5) |
| Movimento | Site estático com transições e movimentos suaves |
| Conteúdo | O do painel: perguntas, Estados, Explorar, 17 cards, Sobre os dados |
| Compartilhamento | OpenGraph e Twitter Card por página; dados estruturados JSON-LD `Dataset` |
| Imagens | Imagem gráfica para o OpenGraph (contorno do Nordeste) e foto com licença livre na abertura; nada de estereótipo da seca |
| Privacidade | Sem Google Analytics, sem cookies, sem recursos de terceiros |

## 3. Páginas da primeira versão

| Página | Endereço | Conteúdo |
|---|---|---|
| Início | `/` | Abertura (título e texto em primeira pessoa), faixa de números logo abaixo (três números grandes e os parágrafos de números e de fontes), as 6 perguntas com lide, gráfico, fecho e fonte; cada gráfico tem o botão "Ampliar", que abre o gráfico grande num modal |
| Estados | `/estados/` | Mapa de calor ano a ano e ranking do último ano, com escolha entre 7 indicadores |
| Explorar | `/explorar/` | 18 indicadores × 16 territórios, comparação lado a lado, zoom de período e de escala |
| Cards | `/cards/` e `/cards/<id>/` | Os 17 cards; cada um com página própria, imagem PNG para baixar e OpenGraph próprio |
| Sobre os dados | `/sobre/` | Por que o site existe, como ler, todas as fontes (uma linha por série), fórmulas, o que falta, arquivos para baixar |
| Dados | `/dados/` | Os CSVs publicados (`base_nordeste.csv`, `derivados.csv`), com sha256 e data |

**Faixa de números (Início).** Os parágrafos de números e de fontes saem da abertura e vão para uma faixa em fundo papel logo abaixo dela: três números grandes lado a lado (riqueza por pessoa do Nordeste como % do resto do país, pobreza no Nordeste, pobreza no Brasil), cada um com rótulo curto e o ano, seguidos do texto completo. Os números vêm de marcadores preenchidos pela base. Os números e o parágrafo de números obedecem à condição do parágrafo (`abertura_numeros`): se ela falha ou um destaque some da base, saem juntos e o id vai para o relatório; a nota de fontes e de faixas de governo, que não tem número, fica sempre. No celular os três números empilham.

**Modal "Ampliar" (Início).** Cada gráfico das perguntas tem um botão "Ampliar" (e o próprio gráfico, com o mouse, é clicável) que abre um `<dialog>` com o gráfico grande, pronto do Python (terceira largura, 1100×520, guardado num `<template>` por gráfico: cerca de 100 KB a mais na página, abaixo do orçamento de 500 KB). O modal mostra o título da pergunta, o título e o subtítulo do gráfico, a legenda, a fonte, "Atualizado em" e "Próximo dado esperado" dos indicadores do gráfico, as notas de quebra de série e o alerta da pergunta, e liga a mesma dica de valor dos gráficos da página. Fecha pelo botão, por Esc e por clique fora; o foco volta ao botão que abriu. No celular (até 560 px) ocupa a tela toda e, em retrato, pede para girar o aparelho. No toque, tocar no gráfico mostra o valor e só o botão abre o modal. Sem JavaScript os botões ficam escondidos e o gráfico da página segue completo.

Fora da primeira versão: segunda leva de indicadores, PNAD antiga (próximo ciclo de dados), mapa geográfico interativo, busca, versão em inglês, newsletter.

## 4. Arquitetura

**Gerador dentro do pipeline.** Novo módulo `nordeste.site` e comando `python -m nordeste site --saida <pasta>`. Ele lê só a base publicada (`dados/base/`, `dados/relatorios/`) e os metadados; nunca a base de trabalho. Mesma base, mesmo site, byte a byte.

**Entradas editoriais em arquivos versionados:**
- `metadados/site/perguntas.yaml`: cada pergunta com frase feita, lide (modelo com marcadores de número), gráficos, fecho e a **condição** que sustenta o fecho (seção 8).
- `metadados/site/cards.yaml`: os 17 cards, com frase feita, números, frase de contexto, fecho, condição e fonte.
- `metadados/site/textos.yaml`: abertura, "Por que eu fiz", "Como ler", "O que falta".

**Saída:** HTML gerado com Jinja2 (dependência nova, registrada como desvio), CSS próprio, JavaScript sem bibliotecas externas, fontes e imagens locais.

**Gráficos prontos no HTML.** Linhas, faixas de governo, quebras de série e rótulos saem do Python como SVG dentro da página. O JavaScript só acrescenta interação: valor ao passar o dedo ou o mouse, zoom, comparação e transições. Os dados do Explorar vão em arquivos JSON por indicador; a página já vem com a primeira vista desenhada.

**Imagens geradas no build:** OpenGraph de cada página (1200×630) e PNG de cada card (1080×1350), renderizados por um Chromium sem tela a partir de modelos HTML.

## 5. Identidade visual e movimento

- Cores: laranja `#ea2e00`; laranja para texto pequeno em fundo claro `#c42600`; preto `#080808`; papel `#f5f4ef`; branco.
- Fontes: Manrope (títulos, 700–800, espaçamento negativo) e DM Sans (texto), em arquivos `woff2` servidos pelo próprio site.
- Formas: cantos de 24 e 34 px, botões e abas em pílula, rótulos em caixa alta laranja.
- Abertura e cards em preto com círculos finos de contorno; o restante em papel e branco. Quando houver foto (`foto` em `textos.yaml`), ela é o fundo da abertura por CSS, sob uma camada preta de 88% (o texto branco mantém contraste acima de 4,5:1 mesmo com a foto toda branca por baixo); sem foto, a abertura segue preta. A faixa de números logo abaixo da abertura é em papel nos dois temas.
- Laranja só no que importa: a linha do Nordeste, o destaque do título, a aba ativa, o número novo nos cards.
- Movimento: transições entre páginas (View Transitions do navegador), entrada suave das seções ao rolar, linha do gráfico desenhada ao aparecer, números contando até o valor na abertura. Tudo desligado com `prefers-reduced-motion`. Nenhum conteúdo depende da animação para aparecer.

## 6. Imagens e dados estruturados

- **OpenGraph:** imagem gráfica com o contorno do Nordeste em laranja sobre preto, o título da página e um número. O contorno vem da malha oficial de estados do IBGE, simplificada. Cada card tem a própria imagem.
- **Foto da abertura:** contemporânea e urbana ou de pessoas, com licença livre (Wikimedia Commons ou Unsplash) e crédito do autor no rodapé e em "Sobre". Na implementação, três candidatas são apresentadas ao usuário para escolha.
- **JSON-LD `Dataset`:** nome, descrição, autor (Júlio Diógenes), cobertura temporal e espacial, data de atualização, links para os CSVs em `/dados/` e licença.
- **Licença da compilação:** CC BY 4.0 (aprovada com a spec). Os dados de origem são públicos (IBGE, INEP, Ipea, Atlas Brasil).

## 7. Publicação automática

**Agenda:** GitHub Actions toda segunda-feira de madrugada e sob demanda. Séries rápidas toda semana; séries do INEP na primeira execução de cada mês.

**Arquivos brutos entre execuções:** guardados como anexos de uma release fixa (`brutos`) do repositório. Cada execução baixa os anexos, coleta o que é da vez e devolve os atualizados. Se a release faltar, a execução faz a coleta completa.

**Fluxo:**
1. `coletar`, `consolidar`, `validar`, `publicar --ensaio`.
2. Se a validação barrar: nada é publicado; abre issue com o relatório.
3. Se passar e a base mudou: `publicar`, commit de `dados/base/` e `dados/relatorios/` na `main` pelo robô.
4. `python -m nordeste site`; se o site mudou, commit do resultado na branch `site-publicado` (só o site, sem código).
5. O hPanel puxa a `site-publicado` para a pasta do subdomínio pela implantação automática do Git, acionada por webhook. Nenhuma senha da Hostinger fica no GitHub.
6. Teste de fumaça (seção 9) e avisos.

**Freios e avisos:**

| Situação | Resultado |
|---|---|
| Regra de validação falha | Nada publicado; issue com o relatório |
| Fonte fora do ar ou formato novo | A série fica com os dados anteriores; as outras seguem; falha no relatório |
| Condição de um fecho ou card deixa de valer | Publica sem aquele fecho; issue "o fecho de X deixou de valer" |
| Ano novo em algum indicador | Publica; issue com a tabela das maiores mudanças, para releitura dos textos |
| Execução quebra no meio | Nada publicado; e-mail do GitHub |

**Pasta dentro do site principal:** o site gerado inclui um `.htaccess` que redireciona `dnascimento.com.br/nordeste/...` para `https://nordeste.dnascimento.com.br/...` (301), e cada página traz `<link rel="canonical">` do subdomínio. A publicação do site principal não pode apagar a pasta `nordeste/` (se usar Git, ela vai no `.gitignore` dele). A primeira implantação do Git do hPanel exige a pasta vazia.

## 8. Conteúdo, voz e fechos com condição

- Textos fixos em primeira pessoa, sem travessão, sem intensificador, com definição curta de cada termo técnico na primeira aparição.
- Todo número de frase vem da base por um modelo de texto; nenhum número é digitado.
- Cada fecho "No frigir dos ovos" e cada card declaram a condição que os sustenta, em linguagem simples de comparação (ex.: `ultimo < primeiro`, `ne < br`, `razao_ultimo > razao_primeiro`). Fecho cuja condição falha não é publicado.
- Faixas de governo só como referência de tempo; nenhuma frase atribui resultado a governo.
- Séries de pesquisas diferentes nunca são emendadas; ano sem dado fica em branco.

## 9. Erros, segurança e testes

**Erros:** site funciona sem JavaScript (números e gráficos no HTML); cada indicador mostra "atualizado em" e "próximo dado esperado"; rodapé com a data e o sha256 da base publicada; voltar uma versão é reverter um commit da `site-publicado`.

**Segurança:** sem servidor, formulário, login, cookies ou terceiros; `.htaccess` com Content-Security-Policy restrita ao próprio site, `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options` e HTTPS obrigatório; ações do GitHub fixadas por versão exata; o único segredo (webhook do hPanel) fica nas configurações do repositório.

**Testes:**
1. Gerador (sem rede, base de teste): todas as páginas geradas; nenhum `NaN`, `undefined` ou vazio; todo número de frase confere com a base; OpenGraph, Twitter Card, canonical e JSON-LD válidos; `.htaccess` com o redirecionamento; site idêntico para a mesma base; condições de fechos avaliadas corretamente, inclusive a supressão.
2. Navegador (Chromium): acessibilidade com axe sem violação grave; 390 px e 1280 px sem estouro de largura; JavaScript desligado mantém números e gráficos; `prefers-reduced-motion` desliga o movimento; página inicial abaixo de ~500 KB sem a foto.
3. Depois de publicar: o robô abre o site e confere o sha256 do rodapé; se não bater em alguns minutos, abre issue. Uma vez por mês, conferência dos links das fontes (só aviso).
4. A suíte atual do pipeline continua rodando a cada mudança.

## 10. Migração para o repositório novo

Criar `nordeste-em-numeros` (público) com o conteúdo de `nordeste-indicadores/` na raiz e o histórico preservado. O `projetos` ganha um aviso apontando para o repositório novo. Os links do painel do Claude apontam para um commit fixo do `projetos` e continuam válidos.

## 11. Riscos

| Risco | Mitigação |
|---|---|
| Número errado que passa em todas as regras | Regras de validação, condição dos fechos, issue de ano novo com as maiores mudanças |
| Coleta do INEP longa no GitHub (mais de 2 h) | INEP mensal; brutos guardados na release |
| Publicação do site principal apagar `nordeste/` | Registro do cuidado; `.gitignore` no site principal se usar Git |
| Conteúdo duplicado em `dnascimento.com.br/nordeste` | Redirecionamento 301 e canonical |
| Foto com licença mal atribuída | Só Commons ou Unsplash, crédito no site, escolha pelo usuário |
| Fonte de governo fora do ar | Série mantém o último dado bom e mostra "atualizado em" |

## 12. Pendências para o usuário

- Escolher a foto da abertura entre três candidatas (na implementação).
- Pôr um link para o site no dnascimento.com.br (menu, rodapé ou conteúdos).
- Configurar, no fim, o Git do hPanel (guiado) e esvaziar a pasta `nordeste` antes da primeira implantação.
