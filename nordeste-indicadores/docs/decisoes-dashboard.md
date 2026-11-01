# Decisões para a dashboard (subprojeto 3)

Registro das escolhas feitas no ponto de controle da etapa 1, a partir do rascunho de layout. Servem de entrada para o brainstorming do subprojeto 3; não substituem a spec dele.

## Narrativa guiada

- Ordem de cada bloco: pergunta → lide com o número → gráfico → detalhe → fonte.
- O lide traz o número principal (valor atual, valor inicial, variação da distância). O detalhe vem depois do gráfico e segue as formulações da seção 19 do plano original ("a tendência começou antes da mudança de governo"), nunca atribuição causal direta.
- Lide e detalhe são gerados a partir dos dados com modelos de texto fixos e passam por revisão humana antes de publicar.

## Faixas de governo

- Peso atual aprovado: cinza claro alternado, sem cor de partido, nome do presidente no topo.
- 2016 hachurado como transição; período interino de Temer (12/05 a 31/08/2016) registrado na tabela de governos.
- Anos ainda não publicados aparecem hachurados dentro da faixa do governo em curso.

## Fonte e nota metodológica

- Ficam coladas ao gráfico, para acompanhar o print: fonte, último ano disponível, próximo dado esperado e nota de ruptura de série.

## Estados

- Duas visualizações: mapa de calor ano a ano e uma segunda visualização a definir no subprojeto 3 (ranking por ano ou mapa geográfico).

## Celular

- Gráfico redesenhado pela largura da tela; nomes das faixas viram iniciais em telas estreitas. Aprovado.

## Brainstorming do site (pausado em 2026-11-01, a pedido do usuário, para concluir a base antes)

Decidido:
- Hospedagem: Hostinger compartilhada (hPanel), site 100% estático; o pipeline não roda na Hostinger.
- Atualização automática por GitHub Actions (coletar → consolidar → validar → publicar → gerar site → enviar); primeira publicação real com revisão humana obrigatória; política para as seguintes a definir.
- Repositório público novo, só para o projeto (nome sugerido: `nordeste-em-numeros`); criação só com confirmação do usuário.
- Primeira versão: página inicial com 5 perguntas (1 PIB per capita × Brasil fora do NE; 2 volume do PIB e participação; 3 IDEB e abandono; 4 desocupação e renda; 5 IDHM), página "Estados" (mapa de calor + ranking), "Dados e método" (downloads, fichas, governos, regras) e "Sobre". Pobreza fora até a linha ser identificada. Exploração com filtros, mapa geográfico e demais indicadores na segunda leva.
- Abordagem: o próprio pipeline gera o site (`python -m nordeste site`, Jinja2, gráficos em SVG com JavaScript simples); envio por branch `site-publicado` + Git do hPanel, sem senha da Hostinger no GitHub.
- Seção 1 do design (arquitetura: módulo `nordeste.site`, `perguntas.yaml`, site só a partir de publicação aprovada) aprovada.

Em aberto ao pausar: seção 2 (páginas e conteúdo) apresentada e não aprovada — pontos pendentes: detalhe editorial escrito pelo usuário; sem Google Analytics; imagem de compartilhamento fixa. Seções 3 a 5 (publicação/envio, erros/segurança, testes) não apresentadas. Domínio não definido.

## Retomada do brainstorming do site (2026-11-01, depois da primeira publicação real)

Decidido pelo usuário:
- Endereço: subdomínio `nordeste.dnascimento.com.br` (o usuário cogitou a pasta `/nordeste` e voltou ao subdomínio: com publicação automática, o subdomínio isola o site do Nordeste do site principal; Google trata os dois de forma equivalente; link visível no site principal compensa a busca). O dnascimento.com.br já roda na Hostinger (hPanel).
- Site estático, mas com fluidez: transições e movimentos suaves (sempre respeitando `prefers-reduced-motion`).
- Atualização totalmente automática (opção C): sem revisão humana a cada atualização; o que barra a publicação são as regras de validação do pipeline.
- Voz do autor (Júlio Diógenes), primeira pessoa, linguagem simples, sem cenas; o site responde a quem diz que "o Nordeste está do mesmo jeito".
- Visual do dnascimento.com.br: laranja #ea2e00 (texto pequeno em fundo claro #c42600), preto #080808, papel #f5f4ef; Manrope nos títulos, DM Sans no texto; cantos 24/34 px, pílulas, rótulos em caixa alta laranja.
- O painel no Claude (https://claude.ai/artifact/4Ekqm88b9JvsyzdLriFi7f) é o protótipo: perguntas no formato "frase feita × dado", fechos "No frigir dos ovos", Estados, Explorar (com comparação lado a lado e zoom de período e de escala), 17 cards de compartilhar em formato 4:5 e "Sobre os dados" com todas as fontes e fórmulas.
- OpenGraph e Twitter Card por página e dados estruturados (JSON-LD `Dataset`, com links para os CSVs).
- Imagens: uma imagem gráfica para o OpenGraph (contorno do Nordeste em laranja sobre preto, título e número) e uma foto contemporânea com licença livre e crédito para a abertura. Evitar o estereótipo da seca.
- Sem Google Analytics; imagem de compartilhamento fixa por página.

Subdomínio criado pelo usuário no hPanel (2026-11-01). Pasta do subdomínio: `/home/u411523977/domains/dnascimento.com.br/public_html/nordeste` (dentro do `public_html` do site principal). Consequências para o design: (1) o mesmo conteúdo também responderia em `dnascimento.com.br/nordeste`; o site gerado leva um `.htaccess` que redireciona (301) esse endereço para `https://nordeste.dnascimento.com.br/` e páginas com `<link rel="canonical">` no subdomínio; (2) a publicação do site principal não pode limpar arquivos não rastreados de `public_html` (se ele usar Git, `nordeste/` vai no `.gitignore` dele); (3) o Git do hPanel exige a pasta vazia na primeira implantação.

Em aberto: repositório do site; seções 3 a 5 do design (publicação/envio, erros/segurança, testes).

