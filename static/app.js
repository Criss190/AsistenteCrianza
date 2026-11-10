const form = document.querySelector('#chat-form');
const input = document.querySelector('#message-input');
const sendButton = document.querySelector('#send-button');
const conversation = document.querySelector('#conversation');
const suggestions = document.querySelector('#suggestions');
const charCount = document.querySelector('#char-count');
const knowledgeStatus = document.querySelector('#knowledge-status');

const MAX_TURNOS_HISTORIAL = 8; // hasta 4 intercambios usuario/asistente
let historial = [];

function scrollToLatest() {
  window.requestAnimationFrame(() => window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' }));
}

function addUserMessage(text) {
  const article = document.createElement('article');
  article.className = 'message user-message';
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.textContent = text;
  article.append(bubble);
  conversation.append(article);
  scrollToLatest();
}

function addTypingIndicator() {
  const article = document.createElement('article');
  article.className = 'message assistant-message';
  article.id = 'typing-indicator';
  const avatar = document.createElement('div');
  avatar.className = 'assistant-avatar';
  avatar.textContent = '✳';
  avatar.setAttribute('aria-hidden', 'true');
  const column = document.createElement('div');
  column.className = 'message-column';
  const meta = document.createElement('div');
  meta.className = 'message-meta';
  const name = document.createElement('strong');
  name.textContent = 'CrianzApp';
  meta.append(name);
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.setAttribute('aria-label', 'CrianzApp está pensando');
  const dots = document.createElement('span');
  dots.className = 'typing-dots';
  for (let index = 0; index < 3; index += 1) {
    dots.append(document.createElement('span'));
  }
  bubble.append(dots);
  column.append(meta, bubble);
  article.append(avatar, column);
  conversation.append(article);
  scrollToLatest();
}

function addAssistantMessage(result) {
  const article = document.createElement('article');
  article.className = 'message assistant-message';
  const avatar = document.createElement('div');
  avatar.className = 'assistant-avatar';
  avatar.textContent = '✳';
  avatar.setAttribute('aria-hidden', 'true');

  const column = document.createElement('div');
  column.className = 'message-column';
  const meta = document.createElement('div');
  meta.className = 'message-meta';
  const name = document.createElement('strong');
  name.textContent = 'CrianzApp';
  const subtitle = document.createElement('span');
  const subtitles = {
    agent: 'respuesta del agente, con las tools que decidió usar',
    no_llm: 'el agente necesita un modelo con tool calling',
    safety: 'orientación prioritaria de seguridad',
    no_evidence: 'sin evidencia suficiente en la guía ni en la web',
  };
  subtitle.textContent = subtitles[result.mode] || 'orientación basada en fuentes';
  meta.append(name, subtitle);

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  const answer = document.createElement('p');
  answer.textContent = result.answer || 'No pude generar una respuesta. Inténtalo de nuevo.';
  bubble.append(answer);

  const toolCalls = result.tool_calls || [];
  if (Array.isArray(toolCalls) && toolCalls.length > 0) {
    const details = document.createElement('details');
    details.className = 'sources';
    const summary = document.createElement('summary');
    summary.textContent = `Herramientas usadas (${toolCalls.length})`;
    details.append(summary);
    toolCalls.forEach((llamada) => {
      const item = document.createElement('div');
      item.className = 'source-item';
      const nombre = document.createElement('strong');
      nombre.textContent = llamada.tool;
      const argumentos = document.createElement('p');
      argumentos.textContent = JSON.stringify(llamada.argumentos || {});
      item.append(nombre, argumentos);
      details.append(item);
    });
    bubble.append(details);
  }

  const sources = result.fuentes || result.sources || [];
  const fuentesBase = sources.filter((s) => (s.origen || 'base') === 'base');
  const fuentesWeb = sources.filter((s) => s.origen === 'web');
  if (fuentesBase.length > 0) {
    const details = document.createElement('details');
    details.className = 'sources';
    const summary = document.createElement('summary');
    summary.textContent = `De la guía (${fuentesBase.length})`;
    details.append(summary);
    fuentesBase.forEach((source) => {
      const item = document.createElement('div');
      item.className = 'source-item';
      const sourceName = document.createElement('strong');
      const ubicacion = source.pagina
        ? ` · página ${source.pagina}`
        : source.seccion
          ? ` · ${source.seccion}`
          : '';
      sourceName.textContent = `${source.documento || source.title || source.source || 'Guía local'}${ubicacion}`;
      const excerpt = document.createElement('p');
      excerpt.textContent = source.texto || source.excerpt || '';
      item.append(sourceName, excerpt);
      details.append(item);
    });
    bubble.append(details);
  }
  if (fuentesWeb.length > 0) {
    const details = document.createElement('details');
    details.className = 'sources';
    const summary = document.createElement('summary');
    summary.textContent = `De la web (${fuentesWeb.length})`;
    details.append(summary);
    fuentesWeb.forEach((source) => {
      const item = document.createElement('div');
      item.className = 'source-item';
      const link = document.createElement('a');
      link.href = source.url;
      link.target = '_blank';
      link.rel = 'noreferrer';
      link.textContent = source.titulo || source.url;
      const excerpt = document.createElement('p');
      excerpt.textContent = source.extracto || '';
      item.append(link, excerpt);
      details.append(item);
    });
    bubble.append(details);
  }

  column.append(meta, bubble);
  if (result.notice) {
    const notice = document.createElement('div');
    notice.className = 'notice';
    notice.textContent = result.notice;
    column.append(notice);
  }
  const mode = document.createElement('div');
  mode.className = `message-mode${result.mode === 'safety' ? ' mode-safety' : ''}`;
  const modeLabels = {
    agent: 'Respuesta del agente a partir de las tools que usó',
    no_llm: 'El agente necesita un modelo con tool calling configurado',
    safety: 'Orientación prioritaria de seguridad',
    no_evidence: 'Sin evidencia suficiente en la guía ni en la web',
  };
  mode.textContent = modeLabels[result.mode] || 'Respuesta basada en conocimiento local';
  column.append(mode);
  article.append(avatar, column);
  conversation.append(article);
  scrollToLatest();
}

async function sendMessage(text) {
  addUserMessage(text);
  if (suggestions) suggestions.hidden = true;
  sendButton.disabled = true;
  input.disabled = true;
  addTypingIndicator();

  try {
    const response = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, history: historial }),
    });
    const result = await response.json();
    document.querySelector('#typing-indicator')?.remove();
    if (!response.ok) throw new Error(result.error || 'No fue posible enviar tu consulta.');
    addAssistantMessage(result);
    historial.push({ role: 'user', content: text }, { role: 'assistant', content: result.answer || '' });
    historial = historial.slice(-MAX_TURNOS_HISTORIAL);
  } catch (error) {
    document.querySelector('#typing-indicator')?.remove();
    addAssistantMessage({ answer: error.message || 'No se pudo conectar. Comprueba tu conexión e inténtalo de nuevo.', mode: 'no_evidence', sources: [] });
  } finally {
    sendButton.disabled = false;
    input.disabled = false;
    input.focus();
  }
}

form.addEventListener('submit', (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text || sendButton.disabled) return;
  input.value = '';
  input.style.height = 'auto';
  charCount.textContent = '0 / 2000';
  sendMessage(text);
});

input.addEventListener('input', () => {
  input.style.height = 'auto';
  input.style.height = `${Math.min(input.scrollHeight, 150)}px`;
  charCount.textContent = `${input.value.length} / 2000`;
});

input.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

document.querySelector('#new-chat').addEventListener('click', () => window.location.reload());

document.querySelectorAll('.suggestion').forEach((button) => {
  button.addEventListener('click', () => {
    input.value = button.textContent.trim();
    form.requestSubmit();
  });
});

fetch('/api/health')
  .then((response) => response.json())
  .then((state) => {
    if (!state.knowledge_chunks) {
      knowledgeStatus.textContent = 'No se encontró la guía local';
      return;
    }
    knowledgeStatus.textContent = state.llm_configured
      ? `Guía conectada · ${state.model}`
      : 'Guía conectada · respuesta local';
  })
  .catch(() => { knowledgeStatus.textContent = 'Estado de la guía no disponible'; });
