/* Nordeste em Números: valor ao passar o mouse ou o dedo nos gráficos, seletores de Estados, Explorar (redesenho no
   navegador, comparação, zoom de período e de escala), menu e movimento.

   Sem bibliotecas. Nada de estilo inline (a Content-Security-Policy é style-src 'self'): a aparência vem só de classes
   do estilo.css e de atributos SVG. O desenho do gráfico repete o de graficos.py, para a vista redesenhada ficar igual
   à que vem pronta no HTML. Todo movimento depende de prefers-reduced-motion: no-preference, e nenhum conteúdo depende
   dele para aparecer: o número final já está no HTML. */
(function () {
  'use strict';

  /* Constantes de graficos.py (o teste confere que são as mesmas). */
  const ANO_INICIAL = 2000;
  const ANO_FINAL = 2027; /* fim do eixo, exclusivo */
  const LARGURA_CARACTERE = 6.6;
  const AFASTAMENTO_ROTULOS = 14;
  const LARGURA_ESTREITA = 520;
  const TOPO = 26;
  const BASE = 24;
  const LARGO = { largura: 720, altura: 300 };
  const ESTREITO = { largura: 360, altura: 240 };
  const SVG = 'http://www.w3.org/2000/svg';

  /* --- números no padrão brasileiro, arredondados como no Python --------------------------------------------- */

  /* Dígitos de |valor| com `casas` decimais. Como o round do Python: pelo valor exato do double, e o empate exato
     vai para o par (toFixed sozinho manda o empate para cima). */
  function arredondar(valor, casas) {
    const absoluto = Math.abs(valor);
    let fixo = absoluto.toFixed(casas);
    const exato = absoluto.toFixed(Math.min(100, casas + 60));
    const resto = exato.slice(exato.indexOf('.') + 1 + casas);
    if (/^50*$/.test(resto)) {
      let inteiro = BigInt(fixo.replace('.', ''));
      if (inteiro % 2n === 1n) inteiro -= 1n;
      const digitos = inteiro.toString().padStart(casas + 1, '0');
      fixo = casas ? digitos.slice(0, -casas) + '.' + digitos.slice(-casas) : digitos;
    }
    return fixo;
  }

  /* 1234.5, 1 -> "1.234,5"; nunca "-0,0" (formatacao.numero). */
  function numero(valor, casas) {
    const fixo = arredondar(valor, casas);
    const [inteiro, decimais] = fixo.split('.');
    const negativo = valor < 0 && /[1-9]/.test(fixo);
    return (negativo ? '-' : '') + inteiro.replace(/\B(?=(\d{3})+(?!\d))/g, '.') + (decimais ? ',' + decimais : '');
  }

  /* Coordenada com no máximo uma casa, sem ".0" e sem "-0" (graficos._c). */
  function coord(valor) {
    let texto = arredondar(valor, 1);
    if (valor < 0 && /[1-9]/.test(texto)) texto = '-' + texto;
    return texto.endsWith('.0') ? texto.slice(0, -2) : texto;
  }

  /* --- eixo y: os mesmos ticks "bonitos" do Python ------------------------------------------------------------- */

  function arredondar9(valor) {
    return Math.round(valor * 1e9) / 1e9;
  }

  function unidade(inicio, fim, quantidade) {
    const bruto = (fim - inicio) / quantidade;
    const potencia = Math.floor(Math.log10(bruto));
    const erro = bruto / 10 ** potencia;
    const fator = erro >= Math.sqrt(50) ? 10 : erro >= Math.sqrt(10) ? 5 : erro >= Math.sqrt(2) ? 2 : 1;
    return potencia >= 0 ? [fator * 10 ** potencia, false] : [10 ** -potencia / fator, true];
  }

  function ticks(inicio, fim, quantidade) {
    const [passo, fracionario] = unidade(inicio, fim, quantidade);
    const fator = fracionario ? passo : 1 / passo;
    const lista = [];
    for (let i = Math.ceil(arredondar9(inicio * fator)); i <= Math.floor(arredondar9(fim * fator)); i++) {
      lista.push(fracionario ? i / passo : i * passo);
    }
    return lista;
  }

  function dominioBonito(inicio, fim, quantidade) {
    let anterior = null;
    for (let volta = 0; volta < 10; volta++) {
      const [passo, fracionario] = unidade(inicio, fim, quantidade);
      if (anterior && anterior[0] === passo && anterior[1] === fracionario) break;
      if (fracionario) {
        inicio = Math.floor(arredondar9(inicio * passo)) / passo;
        fim = Math.ceil(arredondar9(fim * passo)) / passo;
      } else {
        inicio = Math.floor(arredondar9(inicio / passo)) * passo;
        fim = Math.ceil(arredondar9(fim / passo)) * passo;
      }
      anterior = [passo, fracionario];
    }
    return [inicio, fim];
  }

  /* --- desenho do gráfico de linhas (graficos.grafico_linhas) ------------------------------------------------- */

  function escala(d0, d1, i0, i1) {
    return (v) => i0 + (v - d0) * (i1 - i0) / (d1 - d0);
  }

  function largura(texto) {
    return [...texto].length * LARGURA_CARACTERE;
  }

  function no(nome, atributos, texto) {
    const elemento = document.createElementNS(SVG, nome);
    Object.entries(atributos || {}).forEach(([chave, valor]) => elemento.setAttribute(chave, valor));
    if (texto !== undefined) elemento.textContent = texto;
    return elemento;
  }

  /* Linhas só com os pontos ([ano, valor, serie]) dentro do eixo; linha sem ponto no eixo sai. */
  function visiveis(linhas, a0, a1) {
    return linhas
      .map((l) => Object.assign({}, l, { pontos: l.pontos.filter((p) => p[0] >= a0 && p[0] < a1) }))
      .filter((l) => l.pontos.length);
  }

  /* Quebra a linha na troca de série e no ano faltante: nunca emenda dois trechos. */
  function trechos(pontos) {
    const lista = [];
    pontos.forEach((p) => {
      const ultimo = lista.length ? lista[lista.length - 1] : null;
      const anterior = ultimo ? ultimo[ultimo.length - 1] : null;
      if (anterior && p[0] === anterior[0] + 1 && p[2] === anterior[2]) ultimo.push(p);
      else lista.push([p]);
    });
    return lista;
  }

  function yDosRotulos(alvos, topo, eixo) {
    const ordem = alvos.map((_, i) => i).sort((a, b) => alvos[a] - alvos[b]);
    const ys = alvos.slice();
    if (ordem.length) ys[ordem[0]] = Math.max(topo + 10, ys[ordem[0]]);
    for (let k = 1; k < ordem.length; k++) ys[ordem[k]] = Math.max(ys[ordem[k]], ys[ordem[k - 1]] + AFASTAMENTO_ROTULOS);
    let teto = eixo - 2;
    for (let k = ordem.length - 1; k >= 0; k--) {
      ys[ordem[k]] = Math.min(ys[ordem[k]], teto);
      teto = ys[ordem[k]] - AFASTAMENTO_ROTULOS;
    }
    return ys;
  }

  function descricao(linhas, cfg) {
    const partes = linhas.map((l) => {
      const primeiro = l.pontos[0];
      const ultimo = l.pontos[l.pontos.length - 1];
      return `${l.rotulo}: ${numero(primeiro[1], cfg.casas)}${cfg.sufixo} em ${primeiro[0]} ` +
        `e ${numero(ultimo[1], cfg.casas)}${cfg.sufixo} em ${ultimo[0]}`;
    });
    return `Gráfico de linhas, ${cfg.titulo}. ${partes.join('; ')}. A tabela com todos os valores está logo abaixo.`;
  }

  let contadorDeIds = 0;

  /* O <svg> de `linhas` ({rotulo, rotulo_curto, destaque, comparar, pontos}) no período [a0, a1); null quando nenhuma
     linha tem ponto nele. Sem `ampliar`, a escala vertical é a do período completo, como no HTML. */
  function grafico(linhas, cfg, faixas, tamanho, periodo) {
    const a0 = periodo.a0;
    const a1 = periodo.a1;
    const vis = visiveis(linhas, a0, a1);
    if (!vis.length) return null;
    const W = tamanho.largura;
    const H = tamanho.altura;
    const estreito = W < LARGURA_ESTREITA;

    const daEscala = periodo.ampliar ? vis : visiveis(linhas, ANO_INICIAL, ANO_FINAL);
    const valores = daEscala.flatMap((l) => l.pontos.map((p) => p[1]));
    let baixo = Math.min(...valores);
    let alto = Math.max(...valores);
    if (baixo === alto) { baixo -= 1; alto += 1; }
    const dominio = dominioBonito(baixo, alto, 4);
    const marcas = ticks(dominio[0], dominio[1], 4);
    const amplitude = dominio[1] - dominio[0];
    const casasEixo = amplitude < 1 ? 2 : amplitude < 10 ? 1 : 0;
    const rotulosY = marcas.map((t) => numero(t, casasEixo) + cfg.sufixo);
    const rotulosFim = vis.map((l) => `${l.rotulo_curto} ${numero(l.pontos[l.pontos.length - 1][1], cfg.casas)}${cfg.sufixo}`);

    const esquerda = Math.ceil(rotulosY.length ? Math.max(...rotulosY.map(largura)) : 30) + 10;
    const direita = Math.ceil(Math.max(...rotulosFim.map(largura))) + 12;
    const x = escala(a0, a1, esquerda, W - direita);
    const y = escala(dominio[0], dominio[1], H - BASE, TOPO);
    const xp = (p) => x(p[0] + 0.5);
    const eixo = H - BASE;
    const altoQuadro = H - TOPO - BASE;

    contadorDeIds += 1;
    const id = `nnc${contadorDeIds}`;
    const svg = no('svg', {
      role: 'img', 'aria-labelledby': `${id}-t ${id}-d`, width: '100%', viewBox: `0 0 ${W} ${H}`, 'font-size': '11',
      'data-pontos': JSON.stringify(linhas.map((l) => ({
        rotulo: l.rotulo, rotulo_curto: l.rotulo_curto, destaque: l.destaque, pontos: l.pontos,
      }))),
      'data-casas': String(cfg.casas), 'data-sufixo': cfg.sufixo, 'data-eixo': `${a0} ${a1}`,
    });
    svg.append(no('title', { id: `${id}-t` }, cfg.titulo), no('desc', { id: `${id}-d` }, descricao(vis, cfg)));
    const padrao = no('pattern', {
      id: `${id}-h`, width: '6', height: '6', patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)',
    });
    padrao.append(no('line', { x1: '0', y1: '0', x2: '0', y2: '6', class: 'nn-hachura', 'stroke-width': '2.5' }));
    const defs = no('defs');
    defs.append(padrao);
    svg.append(defs);

    faixas.forEach(([nome, inicio, fim, interino], i) => {
      const a = Math.max(a0, inicio);
      const b = Math.min(a1, fim);
      if (b <= a) return;
      const xa = x(a);
      const xb = x(b);
      const quadro = { x: coord(xa), y: String(TOPO), width: coord(xb - xa), height: coord(altoQuadro) };
      if (interino) {
        svg.append(no('rect', Object.assign(quadro, { fill: `url(#${id}-h)` })));
        return;
      }
      svg.append(no('rect', Object.assign({ class: i % 2 ? 'nn-faixa-b' : 'nn-faixa-a' }, quadro)));
      if (xb - xa >= 14) {
        const texto = estreito || xb - xa < 58 ? [...nome][0] : nome;
        svg.append(no('text', {
          class: 'nn-rotulo', x: coord((xa + xb) / 2), y: String(TOPO - 8), 'text-anchor': 'middle',
        }, texto));
      }
    });

    const ultimoAno = Math.max(...vis.map((l) => l.pontos[l.pontos.length - 1][0]));
    if (ultimoAno + 1 < a1) {
      const xa = x(ultimoAno + 1);
      svg.append(no('rect', {
        x: coord(xa), y: String(TOPO), width: coord(x(a1) - xa), height: coord(altoQuadro), fill: `url(#${id}-h)`,
      }));
    }

    marcas.forEach((t, i) => {
      svg.append(no('line', {
        class: 'nn-grade', x1: String(esquerda), x2: coord(W - direita), y1: coord(y(t)), y2: coord(y(t)),
        'stroke-width': '1',
      }));
      svg.append(no('text', {
        class: 'nn-eixo', x: String(esquerda - 6), y: coord(y(t) + 4), 'text-anchor': 'end',
      }, rotulosY[i]));
    });

    const vao = a1 - a0;
    const passo = vao <= 8 ? (estreito ? 2 : 1) : vao <= 16 ? (estreito ? 4 : 2) : (estreito ? 8 : 4);
    for (let ano = Math.ceil(a0 / passo) * passo; ano < a1; ano += passo) {
      svg.append(no('text', {
        class: 'nn-eixo', x: coord(x(ano + 0.5)), y: String(H - 6), 'text-anchor': 'middle',
      }, String(ano)));
    }

    vis.forEach((l) => {
      const classe = l.comparar ? 'nn-linha-cmp' : l.destaque ? 'nn-linha-ne' : 'nn-linha-ref';
      const espessura = l.destaque || l.comparar ? '2.6' : '2';
      const grupo = no('g', { class: classe });
      trechos(l.pontos).forEach((trecho) => {
        if (trecho.length > 1) {
          const d = trecho.map((p, i) => `${i ? 'L' : 'M'}${coord(xp(p))},${coord(y(p[1]))}`).join('');
          grupo.append(no('path', {
            d, fill: 'none', 'stroke-width': espessura, 'stroke-linejoin': 'round', 'stroke-linecap': 'round',
          }));
        }
        const raio = trecho.length > 1 ? '2.2' : '3.4';
        trecho.forEach((p) => grupo.append(no('circle', { cx: coord(xp(p)), cy: coord(y(p[1])), r: raio, stroke: 'none' })));
      });
      svg.append(grupo);
    });

    const alvos = vis.map((l) => y(l.pontos[l.pontos.length - 1][1]) + 4);
    yDosRotulos(alvos, TOPO, eixo).forEach((yRotulo, i) => {
      const l = vis[i];
      svg.append(no('text', {
        class: l.destaque || l.comparar ? 'nn-rotulo-forte' : 'nn-rotulo',
        x: coord(xp(l.pontos[l.pontos.length - 1]) + 7), y: coord(yRotulo),
      }, rotulosFim[i]));
    });

    /* para o arrasto do zoom: de x (unidades do SVG) para ano, e os limites do quadro */
    svg.nnQuadro = { esquerda, direita: W - direita, topo: TOPO, eixo, ano: escala(esquerda, W - direita, a0, a1) };
    return svg;
  }

  /* --- valor ao passar o mouse ou o dedo ---------------------------------------------------------------------- */

  function pontoNoSvg(svg, evento) {
    const matriz = svg.getScreenCTM();
    if (!matriz) return null;
    return new DOMPoint(evento.clientX, evento.clientY).matrixTransform(matriz.inverse());
  }

  /* Liga a dica a um gráfico, lendo data-pontos e os círculos já desenhados (os do Python ou os do redesenho): o
     círculo dá a posição, data-pontos dá o valor. */
  function ligarDica(svg) {
    let linhas;
    try {
      linhas = JSON.parse(svg.getAttribute('data-pontos') || '[]');
    } catch (erro) {
      return;
    }
    const [a0, a1] = (svg.getAttribute('data-eixo') || `${ANO_INICIAL} ${ANO_FINAL}`).split(' ').map(Number);
    const casas = Number(svg.getAttribute('data-casas') || 0);
    const sufixo = svg.getAttribute('data-sufixo') || '';
    const vis = visiveis(linhas, a0, a1);
    const grupos = svg.querySelectorAll('g.nn-linha-ne, g.nn-linha-ref, g.nn-linha-cmp');
    if (grupos.length !== vis.length) return;
    const porAno = new Map();
    for (let i = 0; i < vis.length; i++) {
      const circulos = grupos[i].querySelectorAll('circle');
      if (circulos.length !== vis[i].pontos.length) return;
      const doAno = new Map();
      vis[i].pontos.forEach((p) => doAno.set(p[0], (doAno.get(p[0]) || 0) + 1));
      vis[i].pontos.forEach((p, k) => {
        const ano = p[0];
        if (!porAno.has(ano)) porAno.set(ano, { x: Number(circulos[k].getAttribute('cx')), itens: [] });
        const serie = doAno.get(ano) > 1 ? ` (${p[2]})` : '';
        porAno.get(ano).itens.push({
          forte: vis[i].destaque, texto: `${vis[i].rotulo}: ${numero(p[1], casas)}${sufixo}${serie}`,
        });
      });
    }
    const anos = [...porAno.keys()].sort((a, b) => porAno.get(a).x - porAno.get(b).x);
    if (!anos.length) return;
    const largo = svg.viewBox.baseVal.width;
    const eixo = svg.viewBox.baseVal.height - BASE;
    const pxPorAno = anos.length > 1
      ? Math.abs(porAno.get(anos[anos.length - 1]).x - porAno.get(anos[0]).x) / Math.abs(anos[anos.length - 1] - anos[0])
      : 24;

    function esconder() {
      svg.querySelectorAll('.nn-dica, .nn-regua').forEach((e) => e.remove());
    }

    function mostrar(evento) {
      if (svg.classList.contains('nn-arrastando')) return;
      const ponto = pontoNoSvg(svg, evento);
      if (!ponto) return;
      let melhor = null;
      anos.forEach((ano) => {
        const distancia = Math.abs(porAno.get(ano).x - ponto.x);
        if (melhor === null || distancia < melhor.distancia) melhor = { ano, distancia };
      });
      esconder();
      if (!melhor || melhor.distancia > Math.max(pxPorAno * 0.75, 12)) return;
      const { x, itens } = porAno.get(melhor.ano);
      const ordenados = itens.filter((i) => i.forte).concat(itens.filter((i) => !i.forte));
      svg.append(no('line', { class: 'nn-regua', x1: coord(x), x2: coord(x), y1: String(TOPO), y2: String(eixo) }));
      const dica = no('g', { class: 'nn-dica', 'aria-hidden': 'true' });
      const fundo = no('rect', { class: 'nn-dica-fundo', rx: '8', x: '0', y: '0' });
      dica.append(fundo);
      const textos = [no('text', { class: 'nn-dica-ano', x: '10', y: '19' }, String(melhor.ano))];
      ordenados.forEach((item, k) => textos.push(no('text', { class: 'nn-dica-valor', x: '10', y: String(36 + k * 16) }, item.texto)));
      dica.append(...textos);
      svg.append(dica);
      const larguraDica = Math.ceil(Math.max(...textos.map((t) => t.getComputedTextLength()))) + 20;
      const alturaDica = 28 + ordenados.length * 16;
      fundo.setAttribute('width', String(larguraDica));
      fundo.setAttribute('height', String(alturaDica));
      let esquerdaDica = x + 10;
      if (esquerdaDica + larguraDica > largo - 2) esquerdaDica = Math.max(2, x - 10 - larguraDica);
      dica.setAttribute('transform', `translate(${coord(esquerdaDica)} ${TOPO})`);
    }

    svg.addEventListener('pointermove', mostrar);
    svg.addEventListener('pointerdown', mostrar);
    svg.addEventListener('pointerleave', esconder);
    svg.addEventListener('pointercancel', esconder);
  }

  /* Arrastar sobre o gráfico do Explorar escolhe um período (de ano inteiro em ano inteiro). */
  function ligarArrasto(svg, escolher) {
    const quadro = svg.nnQuadro;
    let inicio = null;
    let selecao = null;
    const limitar = (v) => Math.min(quadro.direita, Math.max(quadro.esquerda, v));

    function soltar() {
      if (selecao) selecao.remove();
      selecao = null;
      inicio = null;
      svg.classList.remove('nn-arrastando');
    }

    svg.addEventListener('pointerdown', (evento) => {
      if (evento.button !== 0) return;
      const ponto = pontoNoSvg(svg, evento);
      if (ponto) inicio = limitar(ponto.x);
    });
    svg.addEventListener('pointermove', (evento) => {
      if (inicio === null) return;
      const ponto = pontoNoSvg(svg, evento);
      if (!ponto) return;
      const atual = limitar(ponto.x);
      if (!selecao && Math.abs(atual - inicio) < 8) return;
      if (!selecao) {
        svg.classList.add('nn-arrastando');
        if (svg.setPointerCapture) svg.setPointerCapture(evento.pointerId);
        svg.querySelectorAll('.nn-dica, .nn-regua').forEach((e) => e.remove());
        selecao = no('rect', { class: 'nn-selecao', y: String(quadro.topo), height: String(quadro.eixo - quadro.topo) });
        svg.append(selecao);
      }
      selecao.setAttribute('x', coord(Math.min(inicio, atual)));
      selecao.setAttribute('width', coord(Math.abs(atual - inicio)));
    });
    svg.addEventListener('pointerup', () => {
      if (selecao) {
        const xa = Number(selecao.getAttribute('x'));
        const xb = xa + Number(selecao.getAttribute('width'));
        const de = Math.max(ANO_INICIAL, Math.round(quadro.ano(xa)));
        const ate = Math.min(ANO_FINAL - 1, Math.round(quadro.ano(xb)) - 1);
        soltar();
        if (ate - de >= 1) escolher(de, ate);
        return;
      }
      soltar();
    });
    svg.addEventListener('pointercancel', soltar);
  }

  /* --- endereço com a escolha da página (para compartilhar e voltar) ------------------------------------------ */

  function lerEndereco() {
    return new URLSearchParams(window.location.search);
  }

  function gravarEndereco(valores) {
    const params = new URLSearchParams();
    Object.entries(valores).forEach(([chave, valor]) => {
      if (valor !== null && valor !== '' && valor !== false) params.set(chave, valor === true ? '1' : String(valor));
    });
    const busca = params.toString();
    window.history.replaceState(null, '', window.location.pathname + (busca ? `?${busca}` : ''));
  }

  function temOpcao(select, valor) {
    return [...select.options].some((o) => o.value === valor);
  }

  /* --- Estados: o seletor só mostra e esconde as vistas que já estão no HTML ---------------------------------- */

  function ligarEstados() {
    const seletor = document.getElementById('sel-estado-ind');
    if (!seletor) return;
    const vistas = document.querySelectorAll('.nn-vista[data-vista]');
    const mostrar = () => vistas.forEach((v) => { v.hidden = v.getAttribute('data-vista') !== seletor.value; });
    const pedido = lerEndereco().get('indicador');
    if (pedido && temOpcao(seletor, pedido)) seletor.value = pedido;
    mostrar();
    seletor.addEventListener('change', () => {
      mostrar();
      const padrao = [...seletor.options].find((o) => o.defaultSelected);
      gravarEndereco({ indicador: padrao && padrao.value === seletor.value ? null : seletor.value });
    });
  }

  /* --- Explorar ----------------------------------------------------------------------------------------------- */

  /* Referências claras do território (explorar.referencias); com comparação, só o Brasil, se ele não for um dos dois. */
  function territoriosDoGrafico(territorio, comparado) {
    if (comparado) return [...([territorio, comparado].includes('BR') ? [] : ['BR']), comparado, territorio];
    if (territorio === 'NE') return ['BR', territorio];
    if (territorio === 'BR' || territorio === 'BR_FORA_NE') return ['NE', territorio];
    return ['NE', 'BR', territorio];
  }

  function celula(texto, classe) {
    const td = document.createElement('td');
    td.textContent = texto;
    if (classe) td.className = classe;
    return td;
  }

  /* Os controles do zoom só fazem sentido com o redesenho, então nascem aqui; os textos vêm do HTML (data-*). */
  function montarZoom(painel) {
    const texto = (nome) => painel.getAttribute(`data-${nome}`);
    const seletorDeAno = (id, rotulo, vazio) => {
      const label = document.createElement('label');
      label.htmlFor = id;
      label.append(rotulo);
      const select = document.createElement('select');
      select.id = id;
      select.append(new Option(vazio, ''));
      for (let ano = ANO_INICIAL; ano < ANO_FINAL; ano++) select.append(new Option(String(ano), String(ano)));
      label.append(select);
      return [label, select];
    };
    const botao = (classe, rotulo) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = `nn-botao ${classe}`;
      b.textContent = rotulo;
      return b;
    };
    const [rotuloDe, zoomDe] = seletorDeAno('zoom-de', texto('de'), texto('inicio'));
    const [rotuloAte, zoomAte] = seletorDeAno('zoom-ate', texto('ate'), texto('fim'));
    const botaoAmpliar = botao('nn-zoom-y', texto('ampliar'));
    botaoAmpliar.setAttribute('aria-pressed', 'false');
    const botaoTodo = botao('nn-zoom-todo', texto('todo'));
    painel.prepend(rotuloDe, rotuloAte, botaoAmpliar, botaoTodo);
    return { zoomDe, zoomAte, botaoAmpliar, botaoTodo };
  }

  function ligarExplorar() {
    const cartao = document.getElementById('explorar-grafico');
    if (!cartao) return;
    const selIndicador = document.getElementById('sel-expl-ind');
    const selTerritorio = document.getElementById('sel-expl-terr');
    const selComparado = document.getElementById('sel-expl-terr2');
    const painel = document.getElementById('explorar-zoom');
    const { zoomDe, zoomAte, botaoAmpliar, botaoTodo } = montarZoom(painel);
    const vista = document.getElementById('explorar-vista');
    const titulo = document.getElementById('explorar-titulo');
    const faixas = JSON.parse(cartao.getAttribute('data-governos'));
    const nomes = {};
    const etiquetas = {};
    [...selTerritorio.options].forEach((o) => {
      nomes[o.value] = o.textContent;
      etiquetas[o.value] = o.getAttribute('data-etiqueta');
    });
    const inicial = {
      indicador: [...selIndicador.options].find((o) => o.defaultSelected).value,
      territorio: [...selTerritorio.options].find((o) => o.defaultSelected).value,
    };
    const cache = {};
    let pedido = 0;

    const params = lerEndereco();
    const estado = {
      indicador: temOpcao(selIndicador, params.get('indicador')) ? params.get('indicador') : selIndicador.value,
      territorio: temOpcao(selTerritorio, params.get('territorio')) ? params.get('territorio') : selTerritorio.value,
      comparado: temOpcao(selComparado, params.get('comparar')) ? params.get('comparar') : selComparado.value,
      de: temOpcao(zoomDe, params.get('de')) ? params.get('de') : '',
      ate: temOpcao(zoomAte, params.get('ate')) ? params.get('ate') : '',
      ampliar: params.get('ampliar') === '1',
    };
    if (estado.de && estado.ate && Number(estado.de) >= Number(estado.ate)) estado.ate = '';

    function configuracao() {
      const opcao = selIndicador.selectedOptions[0];
      return {
        nome: opcao.getAttribute('data-nome'), unidade: opcao.getAttribute('data-unidade'),
        casas: Number(opcao.getAttribute('data-casas')), sufixo: opcao.getAttribute('data-sufixo') || '',
      };
    }

    function comparadoValido() {
      return estado.comparado && estado.comparado !== estado.territorio ? estado.comparado : '';
    }

    function sincronizar() {
      selIndicador.value = estado.indicador;
      selTerritorio.value = estado.territorio;
      selComparado.value = estado.comparado;
      zoomDe.value = estado.de;
      zoomAte.value = estado.ate;
      const comZoom = Boolean(estado.de || estado.ate);
      if (!comZoom) estado.ampliar = false;
      botaoAmpliar.disabled = !comZoom;
      botaoAmpliar.setAttribute('aria-pressed', estado.ampliar ? 'true' : 'false');
      gravarEndereco({
        indicador: estado.indicador === inicial.indicador ? null : estado.indicador,
        territorio: estado.territorio === inicial.territorio ? null : estado.territorio,
        comparar: comparadoValido() || null, de: estado.de || null, ate: estado.ate || null, ampliar: estado.ampliar,
      });
    }

    function aviso(texto) {
      const p = document.createElement('p');
      p.className = 'nn-muted nn-sem-dados';
      p.textContent = texto;
      return p;
    }

    function tabela(linhas) {
      const doTerritorio = linhas.filter((l) => l.destaque || l.comparar);
      const linhasDaTabela = [];
      doTerritorio.forEach((l, ordem) => l.pontos.forEach((p) => linhasDaTabela.push({ p, l, ordem })));
      if (doTerritorio.length > 1) {
        /* com comparação: por ano, o território escolhido primeiro (ele é o último da lista), depois a série */
        linhasDaTabela.sort((a, b) => a.p[0] - b.p[0] || (b.l.destaque - a.l.destaque) || (a.p[2] < b.p[2] ? -1 : a.p[2] > b.p[2] ? 1 : 0));
      }
      const cfg = configuracao();
      const detalhes = document.createElement('details');
      const resumo = document.createElement('summary');
      resumo.textContent = cartao.getAttribute('data-tabela');
      const caixa = document.createElement('div');
      caixa.className = 'nn-tabela';
      const tab = document.createElement('table');
      const cabeca = document.createElement('thead');
      const linhaCabeca = document.createElement('tr');
      [['Ano', ''], ['Território', ''], ['Valor', 'nn-num'], ['Série da fonte', '']].forEach(([texto, classe]) => {
        const th = document.createElement('th');
        th.scope = 'col';
        th.textContent = texto;
        if (classe) th.className = classe;
        linhaCabeca.append(th);
      });
      cabeca.append(linhaCabeca);
      const corpo = document.createElement('tbody');
      linhasDaTabela.forEach(({ p, l }) => {
        const tr = document.createElement('tr');
        tr.append(celula(String(p[0])), celula(l.rotulo), celula(numero(p[1], cfg.casas) + cfg.sufixo, 'nn-num'), celula(p[2]));
        corpo.append(tr);
      });
      tab.append(cabeca, corpo);
      caixa.append(tab);
      detalhes.append(resumo, caixa);
      return detalhes;
    }

    function escolherPeriodo(de, ate) {
      estado.de = String(de);
      estado.ate = String(ate);
      sincronizar();
      desenhar();
    }

    /* Desenha a vista com as linhas dadas, ou com as do JSON do indicador já carregado. */
    function desenhar(linhasProntas) {
      const cfg = configuracao();
      const comparado = comparadoValido();
      titulo.textContent = `${cfg.nome}: ${nomes[estado.territorio]}${comparado ? ` × ${nomes[comparado]}` : ''} (${cfg.unidade})`;
      const linhas = linhasProntas || territoriosDoGrafico(estado.territorio, comparado).map((t) => ({
        rotulo: nomes[t], rotulo_curto: etiquetas[t], destaque: t === estado.territorio, comparar: t === comparado,
        pontos: cache[estado.indicador][t] || [],
      }));
      const principal = linhas.find((l) => l.destaque);
      const aberta = Boolean(vista.querySelector('details[open]'));
      if (!principal || !principal.pontos.length) {
        vista.replaceChildren(aviso(cartao.getAttribute('data-sem-dados')));
        return;
      }
      const periodo = {
        a0: estado.de ? Number(estado.de) : ANO_INICIAL,
        a1: estado.ate ? Number(estado.ate) + 1 : ANO_FINAL,
        ampliar: estado.ampliar,
      };
      const nomeDoGrafico = `${cfg.nome}, ${nomes[estado.territorio]}${comparado ? ` e ${nomes[comparado]}` : ''}`;
      const config = { titulo: nomeDoGrafico, casas: cfg.casas, sufixo: cfg.sufixo };
      const noPeriodo = visiveis([principal], periodo.a0, periodo.a1).length;
      const largo = noPeriodo ? grafico(linhas, config, faixas, LARGO, periodo) : null;
      const detalhes = tabela(linhas);
      detalhes.open = aberta;
      if (!largo) {
        vista.replaceChildren(aviso(cartao.getAttribute('data-sem-periodo')), detalhes);
        return;
      }
      const estreito = grafico(linhas, config, faixas, ESTREITO, periodo);
      const caixa = document.createElement('div');
      caixa.className = 'nn-graf';
      caixa.id = 'g-explorar';
      [['nn-graf-largo', largo], ['nn-graf-estreito', estreito]].forEach(([classe, svg]) => {
        const div = document.createElement('div');
        div.className = classe;
        div.append(svg);
        caixa.append(div);
      });
      vista.replaceChildren(caixa, detalhes);
      [largo, estreito].forEach((svg) => {
        ligarDica(svg);
        ligarArrasto(svg, escolherPeriodo);
      });
    }

    function carregarEDesenhar() {
      sincronizar();
      const indicador = estado.indicador;
      if (cache[indicador]) {
        desenhar();
        return;
      }
      pedido += 1;
      const este = pedido;
      vista.setAttribute('aria-busy', 'true');
      fetch(`${cartao.getAttribute('data-dados')}${indicador}.json`)
        .then((resposta) => {
          if (!resposta.ok) throw new Error(String(resposta.status));
          return resposta.json();
        })
        .then((dados) => {
          cache[indicador] = dados;
          if (este === pedido && estado.indicador === indicador) desenhar();
        })
        .catch(() => {
          if (este === pedido) vista.replaceChildren(aviso(cartao.getAttribute('data-erro')));
        })
        .finally(() => {
          if (este === pedido) vista.removeAttribute('aria-busy');
        });
    }

    selIndicador.addEventListener('change', () => { estado.indicador = selIndicador.value; carregarEDesenhar(); });
    selTerritorio.addEventListener('change', () => { estado.territorio = selTerritorio.value; carregarEDesenhar(); });
    selComparado.addEventListener('change', () => { estado.comparado = selComparado.value; carregarEDesenhar(); });
    zoomDe.addEventListener('change', () => {
      estado.de = zoomDe.value;
      if (estado.de && estado.ate && Number(estado.de) >= Number(estado.ate)) estado.ate = '';
      carregarEDesenhar();
    });
    zoomAte.addEventListener('change', () => {
      estado.ate = zoomAte.value;
      if (estado.de && estado.ate && Number(estado.ate) <= Number(estado.de)) estado.de = '';
      carregarEDesenhar();
    });
    botaoAmpliar.addEventListener('click', () => { estado.ampliar = !estado.ampliar; carregarEDesenhar(); });
    botaoTodo.addEventListener('click', () => {
      estado.de = '';
      estado.ate = '';
      estado.ampliar = false;
      carregarEDesenhar();
    });

    painel.hidden = false;
    const svgInicial = vista.querySelector('.nn-graf-largo svg');
    const comoNoHtml = estado.indicador === inicial.indicador && estado.territorio === inicial.territorio &&
      !comparadoValido() && !estado.de && !estado.ate;
    if (comoNoHtml && svgInicial) {
      /* a vista inicial já está no HTML: redesenha com os mesmos pontos (data-pontos) só para ligar o zoom */
      sincronizar();
      const linhas = JSON.parse(svgInicial.getAttribute('data-pontos')).map((l) => Object.assign(l, { comparar: false }));
      desenhar(linhas);
    } else {
      carregarEDesenhar();
    }
  }

  /* --- menu em abas: no celular, a aba da página aberta fica à vista ------------------------------------------ */

  function centralizarAba() {
    const menu = document.querySelector('.nn-menu');
    const atual = menu && menu.querySelector('[aria-current="page"]');
    if (!atual || menu.scrollWidth <= menu.clientWidth) return;
    menu.scrollLeft = atual.offsetLeft - (menu.clientWidth - atual.offsetWidth) / 2;
  }

  /* --- movimento ---------------------------------------------------------------------------------------------- */

  function abaixoDaDobra(elemento) {
    const caixa = elemento.getBoundingClientRect();
    return caixa.height > 0 && caixa.top > window.innerHeight;
  }

  /* Seções que entram ao rolar e linhas que se desenham ao aparecer. Só o que está fora da tela ao abrir a página
     ganha o estado inicial, para nada piscar; o estado inicial só existe no CSS de prefers-reduced-motion:
     no-preference. */
  function animarAoRolar() {
    const observador = new IntersectionObserver((entradas) => {
      entradas.forEach((entrada) => {
        if (!entrada.isIntersecting) return;
        entrada.target.classList.add('nn-visivel');
        observador.unobserve(entrada.target);
      });
    }, { rootMargin: '0px 0px -10% 0px' });
    document.querySelectorAll('main .nn-card, main .nn-cartao-link, main .nn-legenda').forEach((elemento) => {
      if (!abaixoDaDobra(elemento)) return;
      elemento.classList.add('nn-entra');
      observador.observe(elemento);
    });
    document.querySelectorAll('#resumo .nn-graf').forEach((caixa) => {
      if (!abaixoDaDobra(caixa)) return;
      caixa.querySelectorAll('.nn-linha-ne path, .nn-linha-ref path').forEach((p) => p.setAttribute('pathLength', '1'));
      caixa.classList.add('nn-desenha');
      observador.observe(caixa);
    });
  }

  /* Números da abertura contando até o valor que já está escrito no HTML. */
  function contarNumeros() {
    const alvos = [];
    document.querySelectorAll('.nn-hero-intro').forEach((paragrafo) => {
      const caminhante = document.createTreeWalker(paragrafo, NodeFilter.SHOW_TEXT);
      const textos = [];
      while (caminhante.nextNode()) textos.push(caminhante.currentNode);
      textos.forEach((texto) => {
        const partes = texto.data.split(/(\d{1,3}(?:\.\d{3})*,\d+%?)/);
        if (partes.length < 2) return;
        const pedaco = document.createDocumentFragment();
        partes.forEach((parte, i) => {
          if (i % 2) {
            const span = document.createElement('span');
            span.className = 'nn-conta';
            span.textContent = parte;
            pedaco.append(span);
            alvos.push(span);
          } else if (parte) {
            pedaco.append(parte);
          }
        });
        texto.replaceWith(pedaco);
      });
    });
    if (!alvos.length) return;
    const duracao = 1200;
    const contar = (span) => {
      const final = span.textContent;
      const sufixo = final.endsWith('%') ? '%' : '';
      const corpo = final.slice(0, final.length - sufixo.length);
      const casas = corpo.split(',')[1].length;
      const valor = Number(corpo.replace(/\./g, '').replace(',', '.'));
      const comeco = performance.now();
      const passo = (agora) => {
        const t = Math.min(1, (agora - comeco) / duracao);
        if (t >= 1) {
          span.textContent = final;
          return;
        }
        span.textContent = numero(valor * (1 - (1 - t) ** 3), casas) + sufixo;
        window.requestAnimationFrame(passo);
      };
      window.requestAnimationFrame(passo);
    };
    const observador = new IntersectionObserver((entradas) => {
      entradas.forEach((entrada) => {
        if (!entrada.isIntersecting) return;
        observador.unobserve(entrada.target);
        entrada.target.querySelectorAll('.nn-conta').forEach(contar);
      });
    });
    document.querySelectorAll('.nn-hero-intro').forEach((p) => observador.observe(p));
  }

  /* --- início ------------------------------------------------------------------------------------------------- */

  /* no Node (teste da formatação), só exporta; no navegador, liga a página */
  if (typeof module === 'object' && module.exports) module.exports = { numero };
  if (typeof document === 'undefined') return;

  function iniciar() {
    centralizarAba();
    document.querySelectorAll('.nn-graf svg[data-pontos]').forEach(ligarDica);
    ligarEstados();
    ligarExplorar();
    const movimento = window.matchMedia('(prefers-reduced-motion: no-preference)').matches;
    if (movimento && 'IntersectionObserver' in window) {
      animarAoRolar();
      contarNumeros();
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
}());
