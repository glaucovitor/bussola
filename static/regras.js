/* Editor das regras do plano metodológico.
 * O estado é o próprio JSON das regras; cada campo do formulário aponta para um
 * caminho nesse JSON (data-path). Salvar envia o JSON inteiro ao servidor, que
 * valida e cria uma nova versão. */
(function () {
  const R = JSON.parse(document.getElementById('dados-regras').textContent);
  const META = JSON.parse(document.getElementById('dados-meta').textContent);
  const ed = document.getElementById('editor');
  const estado = document.getElementById('estado');
  const caixaErros = document.getElementById('erros');
  let aba = 'entrada', sujo = false, filtroTecnicas = '', perfil = null;

  const INTENS = ['Alta', 'Média', 'Baixa'];
  const NIVEL_TXT = {1: 'mais simples', 2: 'intermediária', 3: 'mais complexa'};
  const CRIT = Object.fromEntries(META.criterios.map(c => [c.codigo, c]));

  // ---------- utilidades ----------
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const partes = p => p.split('.').map(k => /^\d+$/.test(k) ? Number(k) : k);
  function get(p) { return partes(p).reduce((o, k) => (o == null ? undefined : o[k]), R); }
  function set(p, v) { const ks = partes(p); let o = R; ks.slice(0, -1).forEach(k => o = o[k]); o[ks.at(-1)] = v; }
  function marcar() { sujo = true; estado.textContent = 'Alterações não salvas'; estado.style.color = 'var(--bad)'; }
  const etapas = () => R.etapas.map(e => [e.codigo, e.nome]);
  const nomeEtapa = c => (R.etapas.find(e => e.codigo === c) || {}).nome || c;
  const rotulo = (cod, n) => (R.criterios[cod] && R.criterios[cod].rotulos[n - 1]) || NIVEL_TXT[n];

  // ---------- componentes ----------
  function texto(rotuloCampo, p, dica = '', larg = '') {
    return `<label>${esc(rotuloCampo)}</label><input type="text" data-path="${p}" data-kind="text" value="${esc(get(p))}" ${larg}>${dica ? `<div class="ed-hint">${dica}</div>` : ''}`;
  }
  function area(rotuloCampo, p, dica = '', linhas = 3) {
    return `<label>${esc(rotuloCampo)}</label><textarea rows="${linhas}" data-path="${p}" data-kind="text">${esc(get(p))}</textarea>${dica ? `<div class="ed-hint">${dica}</div>` : ''}`;
  }
  function itens(rotuloCampo, p, dica = 'Um item por linha.') {
    const v = (get(p) || []).join('\n');
    return `<label>${esc(rotuloCampo)}</label><textarea rows="${Math.max(2, (get(p) || []).length + 1)}" data-path="${p}" data-kind="lines">${esc(v)}</textarea><div class="ed-hint">${dica}</div>`;
  }
  function selecao(rotuloCampo, p, opcoes, extra = '') {
    const v = get(p);
    return `${rotuloCampo ? `<label>${esc(rotuloCampo)}</label>` : ''}<select data-path="${p}" data-kind="select" ${extra}>${opcoes.map(([k, t]) => `<option value="${esc(k)}" ${String(k) === String(v) ? 'selected' : ''}>${esc(t)}</option>`).join('')}</select>`;
  }
  function marcaCaixa(rotuloCampo, p) {
    return `<label class="ed-check"><input type="checkbox" data-path="${p}" data-kind="bool" ${get(p) ? 'checked' : ''}> ${esc(rotuloCampo)}</label>`;
  }
  function grupo(p, opcoes, num = false) {      // conjunto de valores (níveis, respostas, critérios)
    const atual = get(p) || [];
    return `<span class="ed-set">${opcoes.map(([k, t]) => `<label class="ed-check"><input type="checkbox" data-path="${p}" data-kind="set" data-val="${esc(k)}" ${num ? 'data-num="1"' : ''} ${atual.includes(num ? Number(k) : k) ? 'checked' : ''}> ${esc(t)}</label>`).join('')}</span>`;
  }
  function botoes(lista, i, total) {
    return `<span class="ed-btns">
      <button type="button" class="ghost sm" data-acao="subir" data-lista="${lista}" data-i="${i}" ${i === 0 ? 'disabled' : ''} title="Mover para cima">↑</button>
      <button type="button" class="ghost sm" data-acao="descer" data-lista="${lista}" data-i="${i}" ${i === total - 1 ? 'disabled' : ''} title="Mover para baixo">↓</button>
      <button type="button" class="ghost sm ed-del" data-acao="remover" data-lista="${lista}" data-i="${i}">Remover</button></span>`;
  }

  // Construtor de condições
  function condicoes(base, textoModo = true) {
    const conds = get(base + '.condicoes') || [];
    const linhas = conds.map((c, j) => {
      const p = `${base}.condicoes.${j}`;
      let campos = '';
      if (c.tipo === 'criterio') {
        campos = selecao('', p + '.criterio', META.criterios.map(x => [x.codigo, x.titulo]), 'data-rerender="1"')
          + ' está em ' + grupo(p + '.niveis', [1, 2, 3].map(n => [n, rotulo(c.criterio, n)]), true);
      } else if (c.tipo === 'condicao') {
        campos = selecao('', p + '.condicao', META.condicoes.map(x => [x.codigo, x.titulo]))
          + ' respondida como ' + grupo(p + '.respostas', Object.entries(META.respostas));
      } else {
        campos = selecao('', p + '.contexto', Object.entries(META.contextos).map(([k, t]) => [k, t.charAt(0).toUpperCase() + t.slice(1)]));
      }
      return `<div class="ed-cond">
        <select data-path="${p}.tipo" data-kind="tipo" aria-label="Tipo de condição">
          <option value="criterio" ${c.tipo === 'criterio' ? 'selected' : ''}>Critério</option>
          <option value="condicao" ${c.tipo === 'condicao' ? 'selected' : ''}>Condição especial</option>
          <option value="contexto" ${c.tipo === 'contexto' ? 'selected' : ''}>Contexto</option>
        </select>
        <span class="ed-cond-campos">${campos}</span>
        <button type="button" class="ghost sm ed-del" data-acao="remover" data-lista="${base}.condicoes" data-i="${j}" title="Remover condição">✕</button>
      </div>`;
    }).join('');
    const modo = textoModo ? `<div class="ed-modo">Vale quando ${selecao('', base + '.modo', [['todas', 'todas as condições'], ['qualquer', 'qualquer uma das condições']])} for verdadeira:</div>` : '';
    return `<div class="ed-conds">${modo}${linhas || '<div class="ed-hint">Nenhuma condição ainda.</div>'}
      <button type="button" class="sec sm" data-acao="nova-condicao" data-lista="${base}.condicoes">+ condição</button></div>`;
  }

  // ---------- abas ----------
  const ABAS = {
    entrada() {
      const rs = R.ponto_entrada.regras;
      return `<h2>Ponto de entrada</h2>
        <p class="ed-intro">Depois do primeiro passo do percurso, o sistema verifica estas regras <b>de cima para baixo</b> e usa a <b>primeira verdadeira</b>. As etapas dispensáveis que vêm antes do ponto de entrada não são feitas. Use <code>{motivos}</code> no texto para inserir a descrição dos critérios que tornaram a regra verdadeira.</p>
        ${rs.map((r, i) => `<div class="ed-card"><div class="ed-card-head"><b>Regra ${i + 1}</b>${botoes('ponto_entrada.regras', i, rs.length)}</div>
          <div class="ed-g2"><div>${texto('Nome da regra', `ponto_entrada.regras.${i}.nome`)}</div>
          <div>${selecao('Vai para a etapa', `ponto_entrada.regras.${i}.etapa`, etapas())}</div></div>
          ${condicoes(`ponto_entrada.regras.${i}`)}
          ${area('Texto no plano', `ponto_entrada.regras.${i}.texto`, 'Marcador disponível: {motivos}')}
          ${area('Complemento quando o peso dobrado decidir (opcional)', `ponto_entrada.regras.${i}.texto_peso`, 'Acrescentado ao final quando um critério de peso dobrado foi o que tornou a regra verdadeira. Marcadores: {criterios}, {tem}.', 2)}
        </div>`).join('')}
        <button type="button" class="sec" data-acao="nova-regra-entrada">+ nova regra de entrada</button>
        <div class="ed-card ed-padrao"><div class="ed-card-head"><b>Regra padrão</b> <span class="ed-hint">Usada quando nenhuma regra acima se aplica.</span></div>
          <div class="ed-g2"><div>${texto('Nome', 'ponto_entrada.padrao.nome')}</div><div>${selecao('Vai para a etapa', 'ponto_entrada.padrao.etapa', etapas())}</div></div>
          ${area('Texto no plano', 'ponto_entrada.padrao.texto')}</div>`;
    },

    etapas() {
      return `<h2>Etapas</h2>
        <p class="ed-intro">A ordem abaixo é a ordem do percurso. Etapas <b>sempre presentes</b> são feitas em todo projeto; as demais só a partir do ponto de entrada. A intensidade de cada etapa é o maior nível entre os critérios marcados.</p>
        ${R.etapas.map((e, i) => `<details class="ed-card" ${i === 0 ? 'open' : ''}><summary class="ed-card-head"><b>${i + 1}. ${esc(e.nome)}</b> <span class="ed-hint">${e.sempre_presente ? 'sempre presente' : 'dispensável'}</span>${botoes('etapas', i, R.etapas.length)}</summary>
          <div class="ed-g2"><div>${texto('Nome da etapa', `etapas.${i}.nome`)}</div><div>${texto('Nome curto', `etapas.${i}.curta`)}</div></div>
          ${marcaCaixa('Sempre presente (não pode ser dispensada)', `etapas.${i}.sempre_presente`)}
          <label>Critérios que definem a intensidade</label>${grupo(`etapas.${i}.criterios_intensidade`, META.criterios.map(c => [c.codigo, c.titulo]))}
          <div class="ed-g3"><div>${itens('Entrada', `etapas.${i}.entrada`)}</div>
            <div>${itens('Entrada quando é o ponto de entrada', `etapas.${i}.entrada_direta`, 'Opcional. Usada no lugar da entrada normal.')}</div>
            <div>${itens('Entrada quando corre em paralelo', `etapas.${i}.entrada_paralela`, 'Opcional.')}</div></div>
          <div class="ed-g2"><div>${itens('Saída', `etapas.${i}.saida`)}</div><div>${area('Avança quando', `etapas.${i}.avanca_quando`, '', 2)}${itens('Técnicas de base (sempre sugeridas)', `etapas.${i}.tecnicas_base`)}</div></div>
          ${INTENS.map(n => area(`Orientação — intensidade ${n.toLowerCase()}`, `etapas.${i}.orientacao.${n}`)).join('')}
        </details>`).join('')}
        <button type="button" class="sec" data-acao="nova-etapa">+ nova etapa</button>`;
    },

    intensidade() {
      const d = R.intensidade.definicoes;
      return `<h2>Intensidade e textos de justificativa</h2>
        <p class="ed-intro">A intensidade de cada etapa ativa é o maior nível entre os seus critérios: situação mais complexa = <b>alta</b>, intermediária = <b>média</b>, mais simples = <b>baixa</b>. Aqui você define o que cada intensidade significa e a frase que justifica a intensidade no plano.</p>
        <table class="ed-table"><thead><tr><th></th><th>Profundidade</th><th>Participantes</th><th>Ciclos</th><th>Validação</th></tr></thead><tbody>
        ${INTENS.map(n => `<tr><th>${n}</th>${['profundidade', 'participantes', 'ciclos', 'validacao'].map(k => `<td><textarea rows="2" data-path="intensidade.definicoes.${n}.${k}" data-kind="text">${esc(d[n][k])}</textarea></td>`).join('')}</tr>`).join('')}
        </tbody></table>
        ${texto('Frase que justifica a intensidade', 'intensidade.texto_porque', 'Marcadores: {intensidade} (Alta, Média, Baixa) e {motivos} (frases dos critérios que definiram o nível — edite na aba Critérios).')}
        ${area('Complemento quando o peso dobrado decide', 'intensidade.texto_peso', 'Marcadores: {criterios} (nome dos critérios de peso dobrado) e {tem} (tem/têm).', 2)}
        <p class="ed-hint">As orientações de cada etapa por intensidade ficam na aba Etapas.</p>`;
    },

    excecoes() {
      const xs = R.excecoes;
      return `<h2>Exceções</h2>
        <p class="ed-intro">Uma exceção muda uma etapa quando suas condições são atendidas. Campos vazios mantêm o que vem da regra geral.</p>
        ${xs.map((x, i) => `<div class="ed-card"><div class="ed-card-head"><b>${esc(x.nome || 'Nova exceção')}</b>${botoes('excecoes', i, xs.length)}</div>
          <div class="ed-g2"><div>${texto('Nome', `excecoes.${i}.nome`)}</div><div>${selecao('Etapa afetada', `excecoes.${i}.etapa`, etapas())}</div></div>
          ${condicoes(`excecoes.${i}`)}
          <div class="ed-g3"><div>${selecao('Intensidade', `excecoes.${i}.intensidade`, [['', 'não alterar'], ...INTENS.map(n => [n, n])])}</div>
            <div>${texto('Rótulo no percurso (opcional)', `excecoes.${i}.rotulo_percurso`)}</div><div>${texto('Selo na etapa (opcional)', `excecoes.${i}.selo`)}</div></div>
          ${area('Justificativa da intensidade', `excecoes.${i}.porque`)}${area('Orientação', `excecoes.${i}.orientacao`)}
          <div class="ed-g3"><div>${itens('Entrada', `excecoes.${i}.entrada`, 'Vazio = não altera.')}</div><div>${itens('Saída', `excecoes.${i}.saida`, 'Vazio = não altera.')}</div>
            <div>${area('Avança quando', `excecoes.${i}.avanca_quando`, 'Vazio = não altera.', 2)}</div></div>
          ${itens('Técnicas de base', `excecoes.${i}.tecnicas_base`, 'Substituem as técnicas de base da etapa. Vazio = não altera.')}
          <div class="ed-g2"><div>${selecao('Técnicas dos critérios', `excecoes.${i}.tecnicas_criterios`, [['manter', 'manter todas'], ['remover', 'remover todas'], ['manter_algumas', 'manter apenas as listadas']], 'data-rerender="1"')}
            ${x.tecnicas_criterios === 'manter_algumas' ? itens('Técnicas mantidas', `excecoes.${i}.tecnicas_manter`, 'Nomes exatamente como na aba Técnicas.') : ''}</div>
            <div>${selecao('Focos', `excecoes.${i}.focos`, [['manter', 'manter todos'], ['remover', 'remover todos'], ['manter_algumas', 'manter apenas os dos critérios marcados']], 'data-rerender="1"')}
            ${x.focos === 'manter_algumas' ? grupo(`excecoes.${i}.focos_manter`, META.criterios.map(c => [c.codigo, c.titulo])) : ''}</div></div>
        </div>`).join('')}
        <button type="button" class="sec" data-acao="nova-excecao">+ nova exceção</button>`;
    },

    tecnicas() {
      const opcEtapas = etapas();
      const visiveis = R.tecnicas.map((t, i) => [t, i]).filter(([t]) => !filtroTecnicas || t.etapa === filtroTecnicas);
      return `<h2>Técnicas sugeridas</h2>
        <p class="ed-intro">Cada técnica aparece na etapa indicada quando o critério está em um dos níveis marcados. As de critérios na situação mais complexa aparecem primeiro. As técnicas de base de cada etapa ficam na aba Etapas.</p>
        <div class="row"><label style="margin:0">Mostrar etapa</label><select id="filtro-tecnicas" style="max-width:320px"><option value="">Todas</option>${opcEtapas.map(([k, t]) => `<option value="${k}" ${k === filtroTecnicas ? 'selected' : ''}>${esc(t)}</option>`).join('')}</select>
          <span class="ed-hint">${visiveis.length} de ${R.tecnicas.length} técnicas</span></div>
        <div class="table-scroll"><table class="ed-table ed-tec"><thead><tr><th>Técnica</th><th>Etapa</th><th>Critério</th><th>Sugerida quando o critério está em</th><th></th></tr></thead><tbody>
        ${visiveis.map(([t, i]) => `<tr>
          <td><input type="text" data-path="tecnicas.${i}.nome" data-kind="text" value="${esc(t.nome)}" aria-label="Nome da técnica"></td>
          <td>${selecao('', `tecnicas.${i}.etapa`, opcEtapas)}</td>
          <td>${selecao('', `tecnicas.${i}.criterio`, META.criterios.map(c => [c.codigo, c.titulo]), 'data-rerender="1"')}</td>
          <td>${grupo(`tecnicas.${i}.niveis`, [2, 3].map(n => [n, rotulo(t.criterio, n)]), true)}</td>
          <td><button type="button" class="ghost sm ed-del" data-acao="remover" data-lista="tecnicas" data-i="${i}">Remover</button></td></tr>`).join('')}
        </tbody></table></div>
        <button type="button" class="sec" data-acao="nova-tecnica">+ nova técnica</button>`;
    },

    focos() {
      return `<h2>Focos das etapas</h2>
        <p class="ed-intro">O foco é uma frase que diz o que a etapa precisa observar por causa de um critério. Aparece quando o critério está em um dos níveis marcados.</p>
        <div class="table-scroll"><table class="ed-table ed-foc"><thead><tr><th>Etapa</th><th>Critério</th><th>Aparece quando o critério está em</th><th>Texto do foco</th><th></th></tr></thead><tbody>
        ${R.focos.map((f, i) => `<tr><td>${selecao('', `focos.${i}.etapa`, etapas())}</td>
          <td>${selecao('', `focos.${i}.criterio`, META.criterios.map(c => [c.codigo, c.titulo]), 'data-rerender="1"')}</td>
          <td>${grupo(`focos.${i}.niveis`, [1, 2, 3].map(n => [n, rotulo(f.criterio, n)]), true)}</td>
          <td><textarea rows="2" data-path="focos.${i}.texto" data-kind="text">${esc(f.texto)}</textarea></td>
          <td><button type="button" class="ghost sm ed-del" data-acao="remover" data-lista="focos" data-i="${i}">Remover</button></td></tr>`).join('')}
        </tbody></table></div>
        <button type="button" class="sec" data-acao="novo-foco">+ novo foco</button>`;
    },

    criterios() {
      return `<h2>Critérios: peso, rótulos e frases</h2>
        <p class="ed-intro">O <b>rótulo</b> nomeia o nível no plano e no editor. A <b>frase</b> entra nas justificativas no lugar de {motivos}. Com <b>peso dobrado</b>, a situação intermediária conta como a mais complexa em todas as regras.</p>
        ${META.criterios.map(c => `<div class="ed-card"><div class="ed-card-head"><b>${esc(c.titulo)}</b>${marcaCaixa('Peso dobrado', `criterios.${c.codigo}.peso_dobrado`)}</div>
          <table class="ed-table"><thead><tr><th>Situação</th><th>Rótulo</th><th>Frase usada nas justificativas</th></tr></thead><tbody>
          ${[0, 1, 2].map(k => `<tr><td class="ed-hint" style="max-width:280px">${esc(c.opcoes[k])}</td>
            <td><input type="text" data-path="criterios.${c.codigo}.rotulos.${k}" data-kind="text" value="${esc(R.criterios[c.codigo].rotulos[k])}"></td>
            <td><input type="text" data-path="criterios.${c.codigo}.frases.${k}" data-kind="text" value="${esc(R.criterios[c.codigo].frases[k])}"></td></tr>`).join('')}
          </tbody></table></div>`).join('')}`;
    },

    condicoes() {
      return `<h2>Condições especiais</h2>
        <p class="ed-intro">Cada condição especial gera um ponto de atenção no plano quando o grupo dá uma das respostas marcadas.</p>
        ${META.condicoes.map(t => `<div class="ed-card"><div class="ed-card-head"><b>${esc(t.titulo)}</b></div>
          <label>Gera ponto de atenção quando a resposta for</label>${grupo(`condicoes_especiais.${t.codigo}.respostas`, Object.entries(META.respostas))}
          ${area('Ação recomendada', `condicoes_especiais.${t.codigo}.acao`, '', 2)}
          ${texto('Etapa(s) em que a ação se aplica', `condicoes_especiais.${t.codigo}.etapa`)}</div>`).join('')}
        <div class="ed-card"><div class="ed-card-head"><b>Texto que explica a resposta do grupo</b></div>
          ${Object.entries(META.respostas).filter(([k]) => k !== 'no').map(([k, t]) => texto(t, `textos_resposta.${k}`)).join('')}</div>`;
    },

    riscos() {
      const rs = R.riscos;
      return `<h2>Riscos</h2>
        <p class="ed-intro">Cada regra de risco gera um ponto de atenção quando suas condições são atendidas.</p>
        ${rs.map((r, i) => `<div class="ed-card"><div class="ed-card-head"><b>${esc(r.titulo || 'Novo risco')}</b>${botoes('riscos', i, rs.length)}</div>
          ${texto('Título', `riscos.${i}.titulo`)}${condicoes(`riscos.${i}`)}${area('Texto no plano', `riscos.${i}.texto`)}</div>`).join('')}
        <button type="button" class="sec" data-acao="novo-risco">+ novo risco</button>
        <div class="ed-card"><div class="ed-card-head"><b>Risco de grupo dividido</b></div>
          ${marcaCaixa('Gerar ponto de atenção para cada critério com divergência alta na consolidação', 'risco_divergencia.ativo')}
          ${texto('Título', 'risco_divergencia.titulo', 'Marcador: {criterio} (nome do critério).')}${area('Texto', 'risco_divergencia.texto')}</div>`;
    },

    envolvimento() {
      const rs = R.envolvimento;
      return `<h2>Envolvimento dos atores</h2>
        <p class="ed-intro">Os textos de todas as regras verdadeiras são juntados, nesta ordem, para formar o parágrafo de envolvimento dos atores.</p>
        ${rs.map((r, i) => `<div class="ed-card"><div class="ed-card-head"><b>Regra ${i + 1}</b>${botoes('envolvimento', i, rs.length)}</div>
          ${condicoes(`envolvimento.${i}`)}${area('Texto', `envolvimento.${i}.texto`, '', 2)}</div>`).join('')}
        <button type="button" class="sec" data-acao="novo-envolvimento">+ nova regra de envolvimento</button>`;
    },

    mapa() {
      const M = R.mapa;
      const eixo = (k, nome) => `<div class="ed-card"><div class="ed-card-head"><b>Eixo ${nome}</b></div>
        ${texto('Nome do eixo', `mapa.${k}.nome`)}
        <label>Peso de cada critério</label>
        <div class="ed-hint">A posição no eixo é a média ponderada dos níveis desses critérios. Peso 0 = o critério não entra no eixo.</div>
        <table class="ed-table ed-pesos"><tbody>${META.criterios.map(c => `<tr><td>${esc(c.titulo)}</td>
          <td><input type="number" min="0" max="10" step="1" data-path="mapa.${k}.pesos.${c.codigo}" data-kind="num" value="${esc(M[k].pesos[c.codigo] ?? 0)}" aria-label="Peso de ${esc(c.titulo)}"></td></tr>`).join('')}</tbody></table></div>`;
      const quad = (k, nome) => `<div><b class="small">${nome}</b>${texto('Nome', `mapa.quadrantes.${k}.nome`)}${texto('Descrição', `mapa.quadrantes.${k}.descricao`)}</div>`;
      return `<h2>Mapa do diagnóstico</h2>
        <p class="ed-intro">Plano cartesiano mostrado no plano, logo após os pontos de atenção. Cada eixo é a média ponderada dos níveis dos critérios, de 0 (situação mais simples) a 100 (mais complexa). A linha do meio fica em 50; um ponto exatamente sobre ela conta como lado alto.</p>
        ${marcaCaixa('Mostrar o mapa no plano', 'mapa.ativo')}
        ${marcaCaixa('Mostrar a posição de cada participante', 'mapa.mostrar_participantes')}
        ${texto('Título da seção', 'mapa.titulo')}
        <div class="ed-g2"><div>${texto('Rótulo da ponta inicial dos eixos', 'mapa.rotulo_menor')}</div><div>${texto('Rótulo da ponta final dos eixos', 'mapa.rotulo_maior')}</div></div>
        ${texto('Frase de leitura', 'mapa.texto', 'Marcadores: {quadrante} (nome do quadrante), {descricao} (descrição do quadrante), {x} e {y} (posição de 0 a 100).')}
        <div class="ed-g2">${eixo('eixo_x', 'horizontal')}${eixo('eixo_y', 'vertical')}</div>
        <div class="ed-card"><div class="ed-card-head"><b>Quadrantes</b></div>
          <div class="ed-g2">${quad('superior_esquerdo', 'Superior esquerdo')}${quad('superior_direito', 'Superior direito')}
          ${quad('inferior_esquerdo', 'Inferior esquerdo')}${quad('inferior_direito', 'Inferior direito')}</div></div>`;
    },

    geral() {
      return `<h2>Consenso e etapas em paralelo</h2>
        <div class="ed-card"><div class="ed-card-head"><b>Consenso na consolidação</b></div>
          <label>Percentual mínimo de participantes na mesma alternativa</label>
          <input type="number" min="50" max="100" step="1" data-path="consenso.limiar" data-kind="pct" value="${Math.round(R.consenso.limiar * 100)}" style="max-width:120px">
          <div class="ed-hint">Além disso, respostas nos dois extremos nunca contam como consenso.</div></div>
        <div class="ed-card"><div class="ed-card-head"><b>Etapas em paralelo</b></div>
          ${marcaCaixa('Quando as duas etapas estão ativas, a segunda corre junto com a primeira', 'paralelo.ativo')}
          <div class="ed-g2"><div>${selecao('Primeira etapa', 'paralelo.de', etapas())}</div><div>${selecao('Etapa que corre em paralelo', 'paralelo.para', etapas())}</div></div>
          <div class="ed-hint">A etapa em paralelo usa a sua lista “entrada quando corre em paralelo”. O contexto “em paralelo” também pode ser usado em condições.</div></div>`;
    },

    testar() {
      if (!perfil) {
        perfil = {tem_sistema: true};
        META.criterios.forEach(c => perfil[c.codigo] = 2);
        META.condicoes.forEach(t => perfil[t.codigo] = 'no');
      }
      return `<h2>Testar regras</h2>
        <p class="ed-intro">Escolha um diagnóstico e veja o plano que as regras <b>em edição</b> gerariam, antes de salvar.</p>
        <div class="ed-g2">
          <div>${META.criterios.map(c => `<label>${esc(c.titulo)}</label><select data-perfil="${c.codigo}">${[1, 2, 3].map(n => `<option value="${n}" ${perfil[c.codigo] == n ? 'selected' : ''}>${esc(rotulo(c.codigo, n))}</option>`).join('')}</select>`).join('')}</div>
          <div>${META.condicoes.map(t => `<label>${esc(t.titulo)}</label><select data-perfil="${t.codigo}">${Object.entries(META.respostas).map(([k, r]) => `<option value="${k}" ${perfil[t.codigo] === k ? 'selected' : ''}>${esc(r)}</option>`).join('')}</select>`).join('')}
            <label class="ed-check" style="margin-top:14px"><input type="checkbox" data-perfil="tem_sistema" ${perfil.tem_sistema ? 'checked' : ''}> Há sistema envolvido</label></div>
        </div>
        <div style="margin-top:14px"><button type="button" data-acao="simular">Gerar plano de teste</button></div>
        <div id="resultado-teste"></div>`;
    },
  };

  function mostrarSimulacao(p) {
    const box = document.getElementById('resultado-teste');
    const regras = rs => `<ul class="ed-trace">${rs.map(r => `<li><b>${esc(r.rotulo)}:</b> ${esc(r.texto || '')}${r.itens ? `<ul>${r.itens.map(i => `<li>${esc(i)}</li>`).join('')}</ul>` : ''}</li>`).join('')}</ul>`;
    box.innerHTML = `<div class="ed-sim">
      <h3>Ponto de entrada: ${esc(p.ponto_entrada)}</h3>
      <p>${esc(p.justificativa_entrada)}</p>
      <p class="ed-hint">Regra aplicada: ${esc(p.rastro_entrada.regra)}${p.rastro_entrada.padrao ? ' (padrão)' : ` (regra ${p.rastro_entrada.ordem})`} — ${esc(p.rastro_entrada.motivos.join('; ') || p.rastro_entrada.condicao)}</p>
      ${p.percurso.map((e, i) => `<div class="ed-sim-etapa ${e.ativa ? '' : 'off'}">
        <div><b>${i + 1}. ${esc(e.fase)}</b> · ${e.ativa ? `intensidade ${esc((e.intensidade || '').toLowerCase())}` : 'dispensada'}${e.selo ? ` · ${esc(e.selo)}` : ''}</div>
        ${e.ativa ? `<p><b>${esc(e.texto_intensidade.porque)}</b> ${esc(e.texto_intensidade.orientacao)}</p>
          <div class="ed-g3 small"><div><b>Entrada</b><br>${e.entrada_itens.map(esc).join('<br>')}</div>
            <div><b>Técnicas</b><br>${e.tecnicas.map(t => esc(t.nome)).join('<br>') || '–'}</div>
            <div><b>Saída</b><br>${e.saida_itens.map(esc).join('<br>')}<br><i>Avança quando: ${esc(e.pronta_quando)}</i></div></div>
          ${e.texto_intensidade.focos.length ? `<div class="small"><b>Focos:</b> ${e.texto_intensidade.focos.map(esc).join(' · ')}</div>` : ''}
          <details><summary class="small">Regras aplicadas</summary>${regras(e.regras_aplicadas)}</details>` : ''}
      </div>`).join('')}
      <h3>Pontos de atenção</h3>${p.atencao.length ? `<ul>${p.atencao.map(a => `<li><b>${esc(a.titulo)}</b> — ${esc(a.acao)} <span class="ed-hint">(${esc(a.motivo)})</span></li>`).join('')}</ul>` : '<p class="ed-hint">Nenhum.</p>'}
      <h3>Envolvimento</h3><p>${esc(p.envolvimento) || '<span class="ed-hint">Nenhuma regra de envolvimento se aplicou.</span>'}</p>
      <h3>Mapa do diagnóstico</h3><p>${p.mapa ? `${esc(p.mapa.texto)} <span class="ed-hint">(posição: ${Math.round(p.mapa.grupo.x)} no eixo horizontal, ${Math.round(p.mapa.grupo.y)} no vertical)</span>` : '<span class="ed-hint">Mapa desativado.</span>'}</p>
    </div>`;
    box.scrollIntoView({behavior: 'smooth', block: 'start'});
  }

  // ---------- render ----------
  function render() {
    const y = window.scrollY;
    ed.innerHTML = ABAS[aba]();
    document.querySelectorAll('#abas button').forEach(b => b.classList.toggle('on', b.dataset.aba === aba));
    window.scrollTo(0, y);
  }

  function mostrarErros(lista) {
    if (!lista || !lista.length) { caixaErros.hidden = true; return; }
    caixaErros.hidden = false;
    caixaErros.innerHTML = `<b>Corrija antes de continuar:</b><ul>${lista.map(e => `<li>${esc(e)}</li>`).join('')}</ul>`;
    caixaErros.scrollIntoView({behavior: 'smooth', block: 'start'});
  }

  // ---------- eventos ----------
  document.getElementById('abas').addEventListener('click', ev => {
    const b = ev.target.closest('button[data-aba]');
    if (!b) return;
    aba = b.dataset.aba; render(); window.scrollTo({top: document.querySelector('.ed').offsetTop - 10});
  });

  function aplicar(el) {
    const p = el.dataset.path, kind = el.dataset.kind;
    if (!p) return false;
    if (kind === 'text') set(p, el.value);
    else if (kind === 'lines') set(p, el.value.split('\n').map(s => s.trim()).filter(Boolean));
    else if (kind === 'bool') set(p, el.checked);
    else if (kind === 'pct') { const v = Number(el.value); if (!isNaN(v)) set(p, Math.round(v * 100) / 10000); }
    else if (kind === 'num') { const v = Number(el.value); if (el.value !== '' && !isNaN(v)) set(p, v); }
    else if (kind === 'select') set(p, el.value);
    else if (kind === 'set') {
      const val = el.dataset.num ? Number(el.dataset.val) : el.dataset.val;
      const atual = (get(p) || []).filter(v => v !== val);
      if (el.checked) atual.push(val);
      atual.sort((a, b) => (typeof a === 'number' ? a - b : 0));
      set(p, atual);
    } else if (kind === 'tipo') {
      const novo = {criterio: {tipo: 'criterio', criterio: 'C1', niveis: [3]},
                    condicao: {tipo: 'condicao', condicao: 'T1', respostas: ['yes']},
                    contexto: {tipo: 'contexto', contexto: 'sem_sistema'}}[el.value];
      set(p.replace(/\.tipo$/, ''), novo);
      return true;
    }
    return !!el.dataset.rerender;
  }

  ed.addEventListener('input', ev => {
    const el = ev.target;
    if (el.dataset.path && ['text', 'lines', 'pct', 'num'].includes(el.dataset.kind)) { aplicar(el); marcar(); }
  });
  ed.addEventListener('change', ev => {
    const el = ev.target;
    if (el.id === 'filtro-tecnicas') { filtroTecnicas = el.value; render(); return; }
    if (el.dataset.perfil) { perfil[el.dataset.perfil] = el.type === 'checkbox' ? el.checked : (el.dataset.perfil.startsWith('C') ? Number(el.value) : el.value); return; }
    if (!el.dataset.path || ['text', 'lines', 'pct', 'num'].includes(el.dataset.kind)) return;
    const rerender = aplicar(el);
    marcar();
    if (rerender || el.dataset.kind === 'bool' && el.dataset.path.endsWith('sempre_presente')) render();
  });

  ed.addEventListener('click', async ev => {
    const b = ev.target.closest('button[data-acao]');
    if (!b) return;
    const acao = b.dataset.acao, lista = b.dataset.lista, i = Number(b.dataset.i);
    const L = lista ? get(lista) : null;
    if (acao === 'simular') return simular();
    if (acao === 'remover') {
      if (lista === 'etapas') {
        const cod = L[i].codigo;
        const usos = R.tecnicas.filter(t => t.etapa === cod).length + R.focos.filter(f => f.etapa === cod).length
          + R.excecoes.filter(x => x.etapa === cod).length + R.ponto_entrada.regras.filter(r => r.etapa === cod).length;
        if (!confirm(`Remover a etapa “${L[i].nome}”?` + (usos ? `\n\n${usos} técnica(s), foco(s), exceção(ões) ou regra(s) de entrada usam esta etapa e também serão removidos.` : ''))) return;
        R.tecnicas = R.tecnicas.filter(t => t.etapa !== cod);
        R.focos = R.focos.filter(f => f.etapa !== cod);
        R.excecoes = R.excecoes.filter(x => x.etapa !== cod);
        R.ponto_entrada.regras = R.ponto_entrada.regras.filter(r => r.etapa !== cod);
        L.splice(i, 1);
      } else if (lista.endsWith('.condicoes') || confirm('Remover este item?')) {
        L.splice(i, 1);
      } else return;
    } else if (acao === 'subir' && i > 0) { [L[i - 1], L[i]] = [L[i], L[i - 1]]; }
    else if (acao === 'descer' && i < L.length - 1) { [L[i + 1], L[i]] = [L[i], L[i + 1]]; }
    else if (acao === 'nova-condicao') L.push({tipo: 'criterio', criterio: 'C1', niveis: [3]});
    else if (acao === 'nova-regra-entrada') R.ponto_entrada.regras.push({id: 'entrada-' + Date.now(), nome: 'Nova regra', etapa: R.etapas[0].codigo, modo: 'qualquer', condicoes: [{tipo: 'criterio', criterio: 'C1', niveis: [3]}], texto: '', texto_peso: ''});
    else if (acao === 'nova-excecao') R.excecoes.push({id: 'excecao-' + Date.now(), nome: 'Nova exceção', etapa: R.etapas[0].codigo, modo: 'todas', condicoes: [{tipo: 'criterio', criterio: 'C1', niveis: [1]}], intensidade: '', rotulo_percurso: '', selo: '', porque: '', orientacao: '', entrada: [], saida: [], avanca_quando: '', tecnicas_base: [], tecnicas_criterios: 'manter', tecnicas_manter: [], focos: 'manter', focos_manter: []});
    else if (acao === 'nova-tecnica') R.tecnicas.push({nome: '', etapa: filtroTecnicas || R.etapas[0].codigo, criterio: 'C1', niveis: [2, 3]});
    else if (acao === 'novo-foco') R.focos.push({etapa: R.etapas[0].codigo, criterio: 'C1', niveis: [2, 3], texto: ''});
    else if (acao === 'novo-risco') R.riscos.push({id: 'risco-' + Date.now(), titulo: '', modo: 'todas', condicoes: [{tipo: 'criterio', criterio: 'C1', niveis: [3]}], texto: ''});
    else if (acao === 'novo-envolvimento') R.envolvimento.push({id: 'env-' + Date.now(), modo: 'todas', condicoes: [{tipo: 'criterio', criterio: 'C5', niveis: [3]}], texto: ''});
    else if (acao === 'nova-etapa') {
      let n = R.etapas.length + 1; while (R.etapas.some(e => e.codigo === 'E' + n)) n++;
      R.etapas.push({codigo: 'E' + n, nome: 'Nova etapa', curta: 'Nova', sempre_presente: false, criterios_intensidade: [], entrada: [], entrada_direta: [], entrada_paralela: [], saida: [], avanca_quando: '', orientacao: {Alta: '', 'Média': '', Baixa: ''}, tecnicas_base: []});
    } else return;
    marcar(); render();
    if (acao.startsWith('nov')) window.scrollTo({top: document.body.scrollHeight});
  });

  async function enviar(url, corpo) {
    const r = await fetch(url, {method: 'POST', credentials: 'same-origin',
      headers: {'Content-Type': 'application/json', 'X-CSRF-Token': CSRF}, body: JSON.stringify(corpo)});
    let j = {}; try { j = await r.json(); } catch (e) {}
    if (!r.ok) throw Object.assign(new Error(j.erro || 'Falha na comunicação com o servidor.'), {erros: j.erros});
    return j;
  }

  async function simular() {
    mostrarErros([]);
    try { const j = await enviar(URL_SIMULAR, {regras: R, perfil}); mostrarSimulacao(j.plano); }
    catch (e) { mostrarErros(e.erros || [e.message]); }
  }

  document.getElementById('salvar').addEventListener('click', async () => {
    mostrarErros([]);
    const btn = document.getElementById('salvar'); btn.disabled = true; estado.textContent = 'Salvando…';
    try {
      const j = await enviar(URL_SALVAR, {regras: R, nota: document.getElementById('nota').value});
      sujo = false; estado.style.color = 'var(--ok)';
      estado.innerHTML = `Salvo como versão ${j.versao}. <a href="${URL_VER}">Ver regras</a>`;
      document.getElementById('nota').value = '';
    } catch (e) {
      estado.textContent = 'Não foi salvo.'; mostrarErros(e.erros || [e.message]);
    }
    btn.disabled = false;
  });

  window.addEventListener('beforeunload', e => { if (sujo) { e.preventDefault(); e.returnValue = ''; } });
  document.getElementById('descartar').addEventListener('click', e => { if (sujo && !confirm('Descartar as alterações não salvas?')) e.preventDefault(); else sujo = false; });
  render();
})();
