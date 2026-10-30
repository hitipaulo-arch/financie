/* ==========================================================================
   Gestor Financeiro — frontend de referência.

   Implementa o contrato da API pós-Fase 2:
     1. GET /api/csrf-token uma vez por sessão -> token real (gerado por
        flask_wtf.generate_csrf no servidor).
     2. Header X-CSRFToken em TODA escrita (POST/PUT/PATCH/DELETE).
     3. credentials: 'include' para o cookie de sessão viajar com a chamada
        (necessário quando FRONTEND_ORIGINS aponta para outro host).
     4. URLs relativas: nada de host hardcoded (funciona em localhost e no
        Azure, atrás de proxy).

   Sem framework e sem build: é só abrir /static/index.html servido pelo Flask.
   ========================================================================== */
'use strict';

const CSRF_HEADER = 'X-CSRFToken';

const state = {
  user: null,
  csrfToken: null,
  metodos: null,
  aba: 'painel',
  paginas: { transacoes: 1, parcelas: 1, investimentos: 1 },
  filtros: { asset_type: '', status: '' },
};

/* --------------------------------------------------------------------------
   Utilidades
   -------------------------------------------------------------------------- */
const $ = (seletor, raiz = document) => raiz.querySelector(seletor);
const $$ = (seletor, raiz = document) => Array.from(raiz.querySelectorAll(seletor));

const formatBRL = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });

function dinheiro(valor) {
  const n = Number(valor);
  return Number.isFinite(n) ? formatBRL.format(n) : '—';
}

function dataBr(iso) {
  if (!iso) return '—';
  const [ano, mes, dia] = String(iso).slice(0, 10).split('-');
  return dia && mes && ano ? `${dia}/${mes}/${ano}` : iso;
}

function hojeISO() {
  return new Date().toISOString().slice(0, 10);
}

function toast(mensagem, tipo = 'ok') {
  const el = $('#toast');
  el.textContent = mensagem;
  el.className = `toast${tipo === 'erro' ? ' erro-toast' : ''}`;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add('oculto'), 3200);
}

/* Converte a resposta de erro da API em texto legível.
   Formatos possíveis:
     {"error":"bad_request","details":{"amount":["Valor inválido"]}}   (Marshmallow)
     {"error":"internal_error","details":"...","error_id":"abc123"}    (500)
     {"error":"no_active_consent","details":"..."}                     (regra de negócio) */
function mensagemDeErro(corpo, status) {
  if (!corpo || typeof corpo !== 'object') return `Erro ${status}`;

  if (corpo.error_id) {
    return `${corpo.details || 'Erro interno.'} (código para o suporte: ${corpo.error_id})`;
  }

  const d = corpo.details;
  if (d && typeof d === 'object') {
    const partes = Object.entries(d).map(
      ([campo, msgs]) => `${campo}: ${Array.isArray(msgs) ? msgs.join(', ') : msgs}`,
    );
    return partes.join(' · ');
  }
  if (typeof d === 'string' && d) return d;
  return corpo.error ? String(corpo.error).replace(/_/g, ' ') : `Erro ${status}`;
}

class ErroApi extends Error {
  constructor(status, corpo) {
    super(mensagemDeErro(corpo, status));
    this.status = status;
    this.corpo = corpo || {};
    this.detalhes = (corpo && typeof corpo.details === 'object' && corpo.details) || null;
  }
}

/* --------------------------------------------------------------------------
   Camada HTTP — o ponto central do fluxo CSRF
   -------------------------------------------------------------------------- */
async function carregarCsrfToken(forcar = false) {
  if (state.csrfToken && !forcar) return state.csrfToken;

  const resp = await fetch('/api/csrf-token', { credentials: 'include' });
  if (!resp.ok) throw new ErroApi(resp.status, await resp.json().catch(() => null));

  const corpo = await resp.json();
  // Proteção contra o bug antigo: o endpoint devolvia literalmente "N/A".
  if (!corpo.csrf_token || corpo.csrf_token === 'N/A') {
    throw new Error('O servidor não devolveu um token CSRF válido (GET /api/csrf-token).');
  }
  state.csrfToken = corpo.csrf_token;
  return state.csrfToken;
}

async function api(caminho, { method = 'GET', body } = {}) {
  const escrita = method !== 'GET' && method !== 'HEAD';
  const cabecalhos = { Accept: 'application/json' };
  if (body !== undefined) cabecalhos['Content-Type'] = 'application/json';
  if (escrita) cabecalhos[CSRF_HEADER] = await carregarCsrfToken();

  const resp = await fetch(caminho, {
    method,
    headers: cabecalhos,
    credentials: 'include',
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  // Token expirado/sessão trocada: renova UMA vez e tenta de novo.
  if (escrita && resp.status === 400) {
    const texto = await resp.clone().text();
    if (/csrf/i.test(texto)) {
      state.csrfToken = null;
      cabecalhos[CSRF_HEADER] = await carregarCsrfToken(true);
      const segunda = await fetch(caminho, {
        method,
        headers: cabecalhos,
        credentials: 'include',
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      return finalizar(segunda);
    }
    return finalizar(resp, texto);
  }

  return finalizar(resp);
}

async function finalizar(resp, textoBruto) {
  if (resp.status === 401) {
    mostrarLogin();
    throw new ErroApi(401, { error: 'unauthorized', details: 'Sessão expirada. Entre novamente.' });
  }

  const corpo = textoBruto !== undefined
    ? (() => { try { return JSON.parse(textoBruto); } catch { return null; } })()
    : await resp.json().catch(() => null);

  if (!resp.ok) throw new ErroApi(resp.status, corpo);
  return corpo;
}

/* --------------------------------------------------------------------------
   Sessão / telas
   -------------------------------------------------------------------------- */
/** Usuário da entrada automática — é onde ficam os dados de demonstração. */
const USUARIO_AUTOMATICO = 'dev';

/**
 * Uma tentativa por carga de página. Depois de um logout explícito a pessoa tem
 * que ver a tela de login, não ser jogada de volta para dentro.
 */
let entradaAutomaticaTentada = false;

function mostrarLogin() {
  state.user = null;
  $('#app').classList.add('oculto');
  $('#tela-login').classList.remove('oculto');
  $('#login-carregando').classList.add('oculto');
  aplicarMetodosDeLogin(state.metodos);
}

/** Tela neutra enquanto a entrada automática roda, para o login não piscar. */
function mostrarEntrando() {
  $('#app').classList.add('oculto');
  $('#tela-login').classList.remove('oculto');
  for (const id of ['btn-google', 'painel-dev-login', 'login-erro', 'login-aviso']) {
    $(`#${id}`).classList.add('oculto');
  }
  $('#login-carregando').classList.remove('oculto');
}

async function consultarMetodos() {
  try {
    const resp = await fetch('/auth/methods', { credentials: 'include' });
    if (resp.ok) return await resp.json();
  } catch {
    /* sem rede: os chamadores tratam null como "não sei" */
  }
  return null;
}

/**
 * Entrar sozinho só faz sentido quando não há escolha a fazer: o servidor
 * oferece o login de desenvolvimento e não tem Google configurado.
 *
 * Em produção `/auth/methods` responde `dev_login: false` — a Fase 1 já ignora
 * `ENABLE_DEV_LOGIN` lá —, então isto nunca dispara e a autenticação continua
 * obrigatória. Nada aqui afrouxa a API: ela segue exigindo sessão e CSRF.
 */
function entradaAutomaticaDisponivel(metodos) {
  return Boolean(metodos) && metodos.dev_login === true && metodos.google !== true;
}

/**
 * Descobre o que este servidor oferece de entrada e mostra só o que funciona.
 *
 * Sem isso a tela exibia sempre o botão do Google (que responde 500 quando
 * GOOGLE_CLIENT_ID/SECRET não existem) e escondia o login sem Google dentro de um
 * <details> — justamente o caminho que funciona em ambiente de teste.
 */
async function aplicarMetodosDeLogin(metodos) {
  const google = $('#btn-google');
  const painel = $('#painel-dev-login');
  const alvoErro = $('#login-erro');
  const alvoAviso = $('#login-aviso');

  if (!metodos) metodos = await consultarMetodos();
  state.metodos = metodos;

  if (!metodos) {
    // Não deu para consultar: mostra o caminho padrão em vez de deixar a pessoa
    // presa numa tela sem nenhuma saída.
    google.classList.remove('oculto');
    return;
  }

  google.classList.toggle('oculto', !metodos.google);
  painel.classList.toggle('oculto', !metodos.dev_login);

  if (metodos.dev_login) {
    alvoAviso.textContent = metodos.google
      ? 'Você também pode entrar com Google; o acesso sem conta usa apenas um nome de usuário.'
      : `Este servidor não tem Google configurado: a página entra sozinha como `
        + `"${USUARIO_AUTOMATICO}". Use o campo acima para entrar como outra pessoa.`;
    alvoAviso.classList.remove('oculto');
  }

  if (!metodos.google && !metodos.dev_login) {
    alvoErro.textContent =
      'Nenhuma forma de entrada está habilitada neste servidor. '
      + 'Configure GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET, '
      + 'ou ENABLE_DEV_LOGIN=true fora de produção.';
    alvoErro.classList.remove('oculto');
  }
}

/** Lê a sessão atual; devolve o usuário ou null. */
async function lerSessao() {
  try {
    const eu = await fetch('/auth/me', { credentials: 'include' });
    if (!eu.ok) return null;
    state.user = await eu.json();
    return state.user;
  } catch {
    return null;
  }
}

/**
 * Cria a sessão sem nenhuma interação e confirma que ela grudou.
 *
 * A confirmação não é frescura: com cookie de terceiro bloqueado (página dentro
 * de iframe) o POST devolve 200 e o `/auth/me` seguinte devolve 401. Sem
 * conferir, o painel abriria e cada chamada de API falharia em silêncio.
 */
async function entrarAutomaticamente() {
  try {
    const resp = await fetch('/auth/dev-login', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: USUARIO_AUTOMATICO }),
    });
    if (!resp.ok) return { ok: false, motivo: 'recusado', status: resp.status };
    if (!(await lerSessao())) return { ok: false, motivo: 'cookie' };
    return { ok: true };
  } catch {
    return { ok: false, motivo: 'rede' };
  }
}

function mostrarApp() {
  $('#tela-login').classList.add('oculto');
  $('#app').classList.remove('oculto');

  $('#usuario-nome').textContent = state.user.name || state.user.email || 'Usuário';
  $('#usuario-email').textContent = state.user.email || state.user.id || '';
  const avatar = $('#usuario-avatar');
  if (state.user.picture) {
    avatar.src = state.user.picture;
    avatar.classList.remove('oculto');
  } else {
    avatar.classList.add('oculto');
  }
}

async function iniciar() {
  if (!(await lerSessao())) {
    const metodos = await consultarMetodos();
    state.metodos = metodos;

    if (entradaAutomaticaTentada || !entradaAutomaticaDisponivel(metodos)) {
      mostrarLogin();
      return;
    }

    entradaAutomaticaTentada = true;
    mostrarEntrando();
    const entrada = await entrarAutomaticamente();
    if (!entrada.ok) {
      mostrarLogin();
      if (entrada.motivo === 'cookie') {
        const alvoErro = $('#login-erro');
        const alvoAviso = $('#login-aviso');
        alvoErro.textContent =
          'A entrada automática foi aceita pelo servidor, mas o navegador não devolveu '
          + 'o cookie de sessão — a página está dentro de um quadro (iframe) de outro '
          + 'site e os cookies de terceiros estão bloqueados.';
        alvoErro.classList.remove('oculto');
        alvoAviso.textContent =
          'Como resolver: abra esta aplicação em uma aba própria do navegador; '
          + 'lá ela entra sozinha, sem tela de login.';
        alvoAviso.classList.remove('oculto');
      }
      return;
    }
  }

  try {
    await carregarCsrfToken(true);
  } catch (erro) {
    // Sem token não há como escrever; avisa mas ainda deixa navegar/ler.
    toast(erro.message, 'erro');
  }

  mostrarApp();
  await trocarAba('painel');
}

async function trocarAba(aba) {
  state.aba = aba;
  $$('.aba').forEach((b) => b.classList.toggle('ativa', b.dataset.aba === aba));
  $$('.painel').forEach((p) => p.classList.toggle('oculto', p.dataset.painel !== aba));

  try {
    if (aba === 'painel') await Promise.all([carregarPainel(), carregarSugestoes(), carregarPortfolio()]);
    if (aba === 'transacoes') await carregarTransacoes();
    if (aba === 'parcelas') await carregarParcelas();
    if (aba === 'investimentos') await carregarInvestimentos();
    if (aba === 'openfinance') await carregarConsents();
  } catch (erro) {
    toast(erro.message, 'erro');
  }
}

const base = () => `/api/users/${encodeURIComponent(state.user.user_id || state.user.id)}`;

/* --------------------------------------------------------------------------
   Painel
   -------------------------------------------------------------------------- */
function pintarValor(id, valor, { cor = false } = {}) {
  const el = $(id);
  el.textContent = dinheiro(valor);
  el.classList.remove('positivo', 'negativo');
  if (cor) {
    const n = Number(valor);
    if (n > 0) el.classList.add('positivo');
    else if (n < 0) el.classList.add('negativo');
  }
}

async function carregarPainel() {
  const resumo = await api(`${base()}/summary`);
  pintarValor('#res-income', resumo.income);
  pintarValor('#res-avulsa', resumo.expenses_avulsa);
  pintarValor('#res-parcelas', resumo.expenses_parcelas);
  pintarValor('#res-balance', resumo.balance, { cor: true });
}

async function carregarSugestoes() {
  const alvo = $('#lista-sugestoes');
  const dados = await api(`${base()}/suggestions`);
  const lista = dados.suggestions || [];

  if (!lista.length) {
    alvo.innerHTML = '<p class="vazio">Nenhuma sugestão no período.</p>';
    return;
  }

  alvo.innerHTML = '';
  for (const s of lista) {
    const item = document.createElement('div');
    item.className = 'item-sugestao';
    item.dataset.tipo = s.type || 'info';

    const titulo = document.createElement('strong');
    titulo.textContent = `${s.icon ? `${s.icon} ` : ''}${s.title || ''}`;
    const desc = document.createElement('p');
    desc.textContent = s.description || '';
    item.append(titulo, desc);

    if (s.potential_savings) {
      const eco = document.createElement('p');
      eco.className = 'economia';
      eco.textContent = `Economia potencial: ${dinheiro(s.potential_savings)}`;
      item.append(eco);
    }
    if (typeof s.progress === 'number') {
      const prog = document.createElement('p');
      prog.className = 'economia';
      prog.textContent = `Progresso da meta: ${Math.round(s.progress)}%`;
      item.append(prog);
    }
    alvo.append(item);
  }
}

async function carregarPortfolio() {
  const alvo = $('#resumo-portfolio');
  const { portfolio: p, recommendations } = await api(`${base()}/investments/portfolio`);

  alvo.innerHTML = '';
  if (!p || !p.count) {
    alvo.innerHTML = '<p class="vazio">Nenhum investimento ativo registrado.</p>';
    return;
  }

  const linhas = [
    ['Investido', dinheiro(p.total_invested)],
    ['Valor atual', dinheiro(p.current_value)],
    ['Retorno', `${dinheiro(p.total_return)} (${Number(p.return_percentage || 0).toFixed(2)}%)`],
    ['Posições', String(p.count)],
  ];

  const tabela = document.createElement('table');
  tabela.className = 'tabela';
  for (const [rotulo, valor] of linhas) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${rotulo}</td><td class="num">${valor}</td>`;
    tabela.append(tr);
  }
  alvo.append(tabela);

  const tipos = p.by_asset_type || {};
  for (const [tipo, dados] of Object.entries(tipos)) {
    const div = document.createElement('p');
    div.className = 'dica';
    div.textContent = `${tipo}: ${dinheiro(dados.current_value)} (${dados.count} posição(ões), `
      + `${Number(dados.return_percentage || 0).toFixed(2)}%)`;
    alvo.append(div);
  }

  for (const r of recommendations || []) {
    const div = document.createElement('div');
    div.className = 'item-sugestao';
    div.dataset.tipo = r.type || 'tip';
    div.innerHTML = `<strong>${r.icon ? `${r.icon} ` : ''}${r.title}</strong><p></p>`;
    $('p', div).textContent = r.description || '';
    alvo.append(div);
  }
}

/* --------------------------------------------------------------------------
   Paginação
   -------------------------------------------------------------------------- */
function pintarPaginacao(alvo, pag, aoTrocar) {
  alvo.innerHTML = '';
  if (!pag || !pag.pages || pag.pages <= 1) {
    if (pag && pag.total) {
      const span = document.createElement('span');
      span.textContent = `${pag.total} registro(s)`;
      alvo.append(span);
    }
    return;
  }

  const anterior = document.createElement('button');
  anterior.className = 'botao botao-secundario botao-mini';
  anterior.textContent = '← Anterior';
  anterior.disabled = pag.current_page <= 1;
  anterior.onclick = () => aoTrocar(pag.current_page - 1);

  const info = document.createElement('span');
  info.textContent = `Página ${pag.current_page} de ${pag.pages} · ${pag.total} registro(s)`;

  const proxima = document.createElement('button');
  proxima.className = 'botao botao-secundario botao-mini';
  proxima.textContent = 'Próxima →';
  proxima.disabled = pag.current_page >= pag.pages;
  proxima.onclick = () => aoTrocar(pag.current_page + 1);

  alvo.append(anterior, info, proxima);
}

function linhaVazia(tabela, colunas, texto) {
  tabela.innerHTML = `<tr><td colspan="${colunas}" class="vazio">${texto}</td></tr>`;
}

/* --------------------------------------------------------------------------
   Transações
   -------------------------------------------------------------------------- */
async function carregarTransacoes() {
  const corpo = $('#corpo-transacoes');
  const pagina = state.paginas.transacoes;
  const dados = await api(`${base()}/transactions?page=${pagina}&per_page=20`);

  if (!dados.items.length) {
    linhaVazia(corpo, 5, 'Nenhuma transação. Adicione a primeira acima.');
  } else {
    corpo.innerHTML = '';
    for (const t of dados.items) {
      const tr = document.createElement('tr');

      const ehReceita = t.type === 'income';
      tr.innerHTML = `
        <td>${dataBr(t.date)}</td>
        <td class="descricao"></td>
        <td class="num ${ehReceita ? 'positivo' : 'negativo'}">${ehReceita ? '+' : '−'} ${dinheiro(t.amount)}</td>
        <td><span class="etiqueta ${ehReceita ? 'etiqueta-receita' : 'etiqueta-despesa'}">
          ${ehReceita ? 'Receita' : 'Despesa'}</span></td>
        <td class="num"></td>`;

      tr.children[1].textContent = t.description;

      const acoes = tr.children[4];
      const editar = document.createElement('button');
      editar.className = 'botao botao-secundario botao-mini';
      editar.textContent = 'Editar';
      editar.onclick = () => editarTransacao(t);

      const excluir = document.createElement('button');
      excluir.className = 'botao botao-perigo botao-mini';
      excluir.textContent = 'Excluir';
      excluir.onclick = () => excluirTransacao(t);

      acoes.append(editar, excluir);
      corpo.append(tr);
    }
  }

  pintarPaginacao($('#pag-transacoes'), dados.pagination, (p) => {
    state.paginas.transacoes = p;
    carregarTransacoes().catch((e) => toast(e.message, 'erro'));
  });
}

function editarTransacao(t) {
  const form = $('#form-transacao');
  form.id.value = t.id;
  form.description.value = t.description;
  form.amount.value = t.amount;
  form.type.value = t.type;
  form.date.value = t.date || '';
  $('#btn-transacao-salvar').textContent = 'Salvar alterações';
  $('#btn-transacao-cancelar').classList.remove('oculto');
  form.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function resetarFormTransacao() {
  const form = $('#form-transacao');
  form.reset();
  form.id.value = '';
  form.date.value = hojeISO();
  $('#btn-transacao-salvar').textContent = 'Adicionar';
  $('#btn-transacao-cancelar').classList.add('oculto');
  $('[data-erro="transacao"]').classList.add('oculto');
}

async function salvarTransacao(evento) {
  evento.preventDefault();
  const form = $('#form-transacao');
  const alvoErro = $('[data-erro="transacao"]');
  alvoErro.classList.add('oculto');

  const id = form.id.value;
  const corpo = {
    description: form.description.value.trim(),
    amount: Number(form.amount.value),
    type: form.type.value,
    date: form.date.value || hojeISO(),
  };

  const botao = $('#btn-transacao-salvar');
  botao.disabled = true;
  try {
    if (id) {
      await api(`${base()}/transactions/${id}`, { method: 'PUT', body: corpo });
      toast('Transação atualizada.');
    } else {
      await api(`${base()}/transactions`, { method: 'POST', body: corpo });
      toast('Transação adicionada.');
    }
    resetarFormTransacao();
    await Promise.all([carregarTransacoes(), carregarPainel()]);
  } catch (erro) {
    alvoErro.textContent = erro.message;
    alvoErro.classList.remove('oculto');
  } finally {
    botao.disabled = false;
  }
}

async function excluirTransacao(t) {
  if (!window.confirm(`Excluir "${t.description}" (${dinheiro(t.amount)})?`)) return;
  try {
    await api(`${base()}/transactions/${t.id}`, { method: 'DELETE' });
    toast('Transação excluída.');
    await Promise.all([carregarTransacoes(), carregarPainel()]);
  } catch (erro) {
    toast(erro.message, 'erro');
  }
}

async function importarExtrato() {
  const botao = $('#btn-importar');
  botao.disabled = true;
  try {
    const r = await api(`${base()}/import`, { method: 'POST' });
    toast(`${r.imported} transação(ões) importada(s).`);
    await Promise.all([carregarTransacoes(), carregarPainel()]);
  } catch (erro) {
    toast(erro.message, 'erro');
  } finally {
    botao.disabled = false;
  }
}

/* --------------------------------------------------------------------------
   Parcelas
   -------------------------------------------------------------------------- */
function situacaoParcela(p) {
  if (!p.date_added) return { texto: '—', classe: '' };
  const inicio = new Date(`${String(p.date_added).slice(0, 10)}T00:00:00`);
  const agora = new Date();
  const decorridos = (agora.getFullYear() - inicio.getFullYear()) * 12
    + (agora.getMonth() - inicio.getMonth()) + 1;
  const restantes = Math.max(0, Number(p.total_months) - decorridos + 1);
  return restantes > 0
    ? { texto: `${restantes} de ${p.total_months} restantes`, classe: 'etiqueta-active' }
    : { texto: 'Quitada', classe: 'etiqueta-matured' };
}

async function carregarParcelas() {
  const corpo = $('#corpo-parcelas');
  const dados = await api(
    `${base()}/installments?page=${state.paginas.parcelas}&per_page=20`,
  );

  if (!dados.items.length) {
    linhaVazia(corpo, 6, 'Nenhuma compra parcelada.');
  } else {
    corpo.innerHTML = '';
    for (const p of dados.items) {
      const situacao = situacaoParcela(p);
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${dataBr(p.date_added)}</td>
        <td class="descricao"></td>
        <td class="num">${dinheiro(p.monthly_value)}</td>
        <td class="num">${p.total_months}×</td>
        <td><span class="etiqueta ${situacao.classe}">${situacao.texto}</span></td>
        <td class="num"></td>`;
      tr.children[1].textContent = p.description;

      const editar = document.createElement('button');
      editar.className = 'botao botao-secundario botao-mini';
      editar.textContent = 'Editar';
      editar.onclick = () => editarParcela(p);

      const excluir = document.createElement('button');
      excluir.className = 'botao botao-perigo botao-mini';
      excluir.textContent = 'Excluir';
      excluir.onclick = () => excluirParcela(p);

      tr.children[5].append(editar, excluir);
      corpo.append(tr);
    }
  }

  pintarPaginacao($('#pag-parcelas'), dados.pagination, (pag) => {
    state.paginas.parcelas = pag;
    carregarParcelas().catch((e) => toast(e.message, 'erro'));
  });
}

function editarParcela(p) {
  const form = $('#form-parcela');
  form.id.value = p.id;
  form.description.value = p.description;
  form.monthly_value.value = p.monthly_value;
  form.total_months.value = p.total_months;
  form.date_added.value = p.date_added || '';
  $('#btn-parcela-salvar').textContent = 'Salvar alterações';
  $('#btn-parcela-cancelar').classList.remove('oculto');
}

function resetarFormParcela() {
  const form = $('#form-parcela');
  form.reset();
  form.id.value = '';
  form.date_added.value = hojeISO();
  $('#btn-parcela-salvar').textContent = 'Adicionar';
  $('#btn-parcela-cancelar').classList.add('oculto');
  $('[data-erro="parcela"]').classList.add('oculto');
}

async function salvarParcela(evento) {
  evento.preventDefault();
  const form = $('#form-parcela');
  const alvoErro = $('[data-erro="parcela"]');
  alvoErro.classList.add('oculto');

  const id = form.id.value;
  const corpo = {
    description: form.description.value.trim(),
    monthly_value: Number(form.monthly_value.value),
    total_months: Number(form.total_months.value),
    date_added: form.date_added.value || hojeISO(),
  };

  const botao = $('#btn-parcela-salvar');
  botao.disabled = true;
  try {
    if (id) {
      await api(`${base()}/installments/${id}`, { method: 'PUT', body: corpo });
      toast('Parcela atualizada.');
    } else {
      await api(`${base()}/installments`, { method: 'POST', body: corpo });
      toast('Parcela adicionada.');
    }
    resetarFormParcela();
    await Promise.all([carregarParcelas(), carregarPainel()]);
  } catch (erro) {
    alvoErro.textContent = erro.message;
    alvoErro.classList.remove('oculto');
  } finally {
    botao.disabled = false;
  }
}

async function excluirParcela(p) {
  if (!window.confirm(`Excluir a compra parcelada "${p.description}"?`)) return;
  try {
    await api(`${base()}/installments/${p.id}`, { method: 'DELETE' });
    toast('Parcela excluída.');
    await Promise.all([carregarParcelas(), carregarPainel()]);
  } catch (erro) {
    toast(erro.message, 'erro');
  }
}

/* --------------------------------------------------------------------------
   Investimentos
   -------------------------------------------------------------------------- */
async function carregarInvestimentos() {
  const corpo = $('#corpo-investimentos');
  const params = new URLSearchParams({
    page: String(state.paginas.investimentos),
    per_page: '20',
  });
  if (state.filtros.asset_type) params.set('asset_type', state.filtros.asset_type);
  if (state.filtros.status) params.set('status', state.filtros.status);

  const dados = await api(`${base()}/investments?${params.toString()}`);

  if (!dados.items.length) {
    linhaVazia(corpo, 8, 'Nenhum investimento com esses filtros.');
  } else {
    corpo.innerHTML = '';
    for (const i of dados.items) {
      const investido = Number(i.amount) * Number(i.purchase_price);
      const atual = Number(i.amount) * Number(i.current_price ?? i.purchase_price);
      const retorno = investido > 0 ? ((atual - investido) / investido) * 100 : 0;

      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${dataBr(i.purchase_date)}</td>
        <td class="descricao"></td>
        <td>${i.asset_type}</td>
        <td class="num">${Number(i.amount).toLocaleString('pt-BR')}</td>
        <td class="num">${dinheiro(i.purchase_price)}</td>
        <td class="num">${dinheiro(i.current_price)}</td>
        <td class="num ${retorno >= 0 ? 'positivo' : 'negativo'}">${retorno.toFixed(2)}%</td>
        <td class="num"></td>`;
      tr.children[1].textContent = i.name;

      const etiqueta = document.createElement('span');
      etiqueta.className = `etiqueta etiqueta-${i.status}`;
      etiqueta.textContent = i.status;
      tr.children[1].append(document.createElement('br'), etiqueta);

      const editar = document.createElement('button');
      editar.className = 'botao botao-secundario botao-mini';
      editar.textContent = 'Editar';
      editar.onclick = () => editarInvestimento(i);

      const excluir = document.createElement('button');
      excluir.className = 'botao botao-perigo botao-mini';
      excluir.textContent = 'Excluir';
      excluir.onclick = () => excluirInvestimento(i);

      tr.children[7].append(editar, excluir);
      corpo.append(tr);
    }
  }

  pintarPaginacao($('#pag-investimentos'), dados.pagination, (pag) => {
    state.paginas.investimentos = pag;
    carregarInvestimentos().catch((e) => toast(e.message, 'erro'));
  });
}

function editarInvestimento(i) {
  const form = $('#form-investimento');
  form.id.value = i.id;
  form.name.value = i.name;
  form.asset_type.value = i.asset_type;
  form.amount.value = i.amount;
  form.purchase_price.value = i.purchase_price;
  form.current_price.value = i.current_price ?? '';
  form.purchase_date.value = i.purchase_date || '';
  form.target_return.value = i.target_return ?? '';
  form.status.value = i.status || 'active';
  form.notes.value = i.notes || '';
  $('#btn-investimento-salvar').textContent = 'Salvar alterações';
  $('#btn-investimento-cancelar').classList.remove('oculto');
}

function resetarFormInvestimento() {
  const form = $('#form-investimento');
  form.reset();
  form.id.value = '';
  form.purchase_date.value = hojeISO();
  $('#btn-investimento-salvar').textContent = 'Adicionar';
  $('#btn-investimento-cancelar').classList.add('oculto');
  $('[data-erro="investimento"]').classList.add('oculto');
}

async function salvarInvestimento(evento) {
  evento.preventDefault();
  const form = $('#form-investimento');
  const alvoErro = $('[data-erro="investimento"]');
  alvoErro.classList.add('oculto');

  const id = form.id.value;
  const vazio = (v) => v === '' || v === null || v === undefined;
  const corpo = {
    name: form.name.value.trim(),
    asset_type: form.asset_type.value,
    amount: Number(form.amount.value),
    purchase_price: Number(form.purchase_price.value),
    purchase_date: form.purchase_date.value || hojeISO(),
    status: form.status.value,
    current_price: vazio(form.current_price.value) ? null : Number(form.current_price.value),
    target_return: vazio(form.target_return.value) ? null : Number(form.target_return.value),
    notes: vazio(form.notes.value) ? null : form.notes.value,
  };

  const botao = $('#btn-investimento-salvar');
  botao.disabled = true;
  try {
    if (id) {
      await api(`${base()}/investments/${id}`, { method: 'PUT', body: corpo });
      toast('Investimento atualizado.');
    } else {
      await api(`${base()}/investments`, { method: 'POST', body: corpo });
      toast('Investimento adicionado.');
    }
    resetarFormInvestimento();
    await Promise.all([carregarInvestimentos(), carregarPortfolio()]);
  } catch (erro) {
    alvoErro.textContent = erro.message;
    alvoErro.classList.remove('oculto');
  } finally {
    botao.disabled = false;
  }
}

async function excluirInvestimento(i) {
  if (!window.confirm(`Excluir o investimento "${i.name}"?`)) return;
  try {
    await api(`${base()}/investments/${i.id}`, { method: 'DELETE' });
    toast('Investimento excluído.');
    await Promise.all([carregarInvestimentos(), carregarPortfolio()]);
  } catch (erro) {
    toast(erro.message, 'erro');
  }
}

/* --------------------------------------------------------------------------
   Open Finance
   -------------------------------------------------------------------------- */
async function carregarConsents() {
  const corpo = $('#corpo-consents');
  const dados = await api(`${base()}/openfinance/consents?page=1&per_page=20`);

  if (!dados.items.length) {
    linhaVazia(corpo, 5, 'Nenhum consentimento. Crie um para poder sincronizar.');
    return;
  }

  corpo.innerHTML = '';
  for (const c of dados.items) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${c.created_at ? new Date(c.created_at).toLocaleString('pt-BR') : '—'}</td>
      <td><code>${c.consent_id}</code></td>
      <td>${c.provider}</td>
      <td>${c.scopes}</td>
      <td><span class="etiqueta etiqueta-${c.status}">${c.status}</span></td>`;
    corpo.append(tr);
  }
}

function mensagemOpenFinance(texto, tipo) {
  const erro = $('[data-erro="openfinance"]');
  const ok = $('[data-sucesso="openfinance"]');
  erro.classList.add('oculto');
  ok.classList.add('oculto');
  if (!texto) return;
  const alvo = tipo === 'erro' ? erro : ok;
  alvo.textContent = texto;
  alvo.classList.remove('oculto');
}

async function criarConsent() {
  mensagemOpenFinance(null);
  try {
    const c = await api(`${base()}/openfinance/consents`, { method: 'POST', body: {} });
    mensagemOpenFinance(`Consentimento ${c.consent_id} criado com status "${c.status}".`, 'ok');
    await carregarConsents();
  } catch (erro) {
    mensagemOpenFinance(erro.message, 'erro');
  }
}

async function sincronizar() {
  mensagemOpenFinance(null);
  const botao = $('#btn-sync');
  botao.disabled = true;
  try {
    const r = await api(`${base()}/openfinance/sync`, { method: 'POST' });
    mensagemOpenFinance(
      `${r.imported} importada(s), ${r.skipped_duplicates} duplicada(s) ignorada(s) · origem: ${r.source}`,
      'ok',
    );
    await Promise.all([carregarPainel(), carregarConsents()]);
  } catch (erro) {
    mensagemOpenFinance(erro.message, 'erro');
  } finally {
    botao.disabled = false;
  }
}

/* --------------------------------------------------------------------------
   Logout / dev-login
   -------------------------------------------------------------------------- */
async function logout() {
  try {
    await api('/auth/logout');
  } catch {
    /* mesmo se falhar, volta para a tela de login */
  }
  state.csrfToken = null;
  mostrarLogin();
}

async function devLogin() {
  const alvoErro = $('#login-erro');
  const alvoAviso = $('#login-aviso');
  alvoErro.classList.add('oculto');
  const botao = $('#btn-dev-login');
  botao.disabled = true;
  try {
    // dev-login é isento de CSRF por projeto (o chamador ainda não tem sessão),
    // mas em produção responde 403 dev_login_disabled.
    const resp = await fetch('/auth/dev-login', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: $('#dev-user').value.trim() || 'dev' }),
    });
    const corpo = await resp.json().catch(() => null);

    if (resp.status === 429) {
      // O servidor devolve details "5 per minute", que não diz nada para quem
      // só clicou duas vezes no botão.
      alvoErro.textContent =
        'Muitas tentativas seguidas: aguarde 1 minuto e clique de novo. '
        + 'Se você já entrou antes nesta aba, a sessão pode estar ativa — recarregue a página.';
      alvoErro.classList.remove('oculto');
      return;
    }
    if (!resp.ok) throw new ErroApi(resp.status, corpo);

    // O servidor aceitou (200) e mandou o cookie. Falta saber se o navegador vai
    // devolvê-lo: quando a página roda dentro de um iframe de outro domínio e
    // cookies de terceiros estão bloqueados, o login "funciona" e a tela volta
    // para cá sem explicação. Confere antes de trocar de tela e diz o que fazer.
    const confere = await fetch('/auth/me', { credentials: 'include' });
    if (!confere.ok) {
      alvoErro.textContent =
        'O servidor aceitou o login, mas o navegador não devolveu o cookie de sessão. '
        + 'Isso acontece quando a página está aberta dentro de um quadro (iframe) de outro site '
        + 'e o navegador bloqueia cookies de terceiros.';
      alvoAviso.textContent =
        'Como resolver: abra esta aplicação em uma aba própria do navegador '
        + '(botão direito no preview → "abrir em nova aba") e entre por lá.';
      alvoAviso.classList.remove('oculto');
      return;
    }

    alvoAviso.classList.add('oculto');
    await iniciar();
  } catch (erro) {
    alvoErro.textContent = erro.message;
    alvoErro.classList.remove('oculto');
  } finally {
    botao.disabled = false;
  }
}

/* --------------------------------------------------------------------------
   Ligações
   -------------------------------------------------------------------------- */
function ligarEventos() {
  $$('.aba').forEach((b) => b.addEventListener('click', () => trocarAba(b.dataset.aba)));
  $('#btn-logout').addEventListener('click', logout);
  $('#btn-dev-login').addEventListener('click', devLogin);
  // Enter no campo de usuário também entra. Ligado uma única vez aqui: antes
  // ficava dentro de aplicarMetodosDeLogin() e acumulava um listener por chamada.
  $('#dev-user').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); devLogin(); }
  });

  $('#form-transacao').addEventListener('submit', salvarTransacao);
  $('#btn-transacao-cancelar').addEventListener('click', resetarFormTransacao);
  $('#btn-importar').addEventListener('click', importarExtrato);

  $('#form-parcela').addEventListener('submit', salvarParcela);
  $('#btn-parcela-cancelar').addEventListener('click', resetarFormParcela);

  $('#form-investimento').addEventListener('submit', salvarInvestimento);
  $('#btn-investimento-cancelar').addEventListener('click', resetarFormInvestimento);

  $('#filtro-asset-type').addEventListener('change', (e) => {
    state.filtros.asset_type = e.target.value;
    state.paginas.investimentos = 1;
    carregarInvestimentos().catch((erro) => toast(erro.message, 'erro'));
  });
  $('#filtro-status').addEventListener('change', (e) => {
    state.filtros.status = e.target.value;
    state.paginas.investimentos = 1;
    carregarInvestimentos().catch((erro) => toast(erro.message, 'erro'));
  });

  $('#btn-novo-consent').addEventListener('click', criarConsent);
  $('#btn-sync').addEventListener('click', sincronizar);
}

document.addEventListener('DOMContentLoaded', () => {
  ligarEventos();
  $('#form-transacao').date.value = hojeISO();
  $('#form-parcela').date_added.value = hojeISO();
  $('#form-investimento').purchase_date.value = hojeISO();
  iniciar();
});
