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
