const form = document.querySelector('#chat-form');
const input = document.querySelector('#message-input');
const sendButton = document.querySelector('#send-button');
const conversation = document.querySelector('#conversation');
const suggestions = document.querySelector('#suggestions');
const charCount = document.querySelector('#char-count');
const knowledgeStatus = document.querySelector('#knowledge-status');
const history = [];

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
  subtitle.textContent = result.mode === 'groq' ? 'orientación generada con IA' : 'orientación basada en la guía';
  meta.append(name, subtitle);

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  const answer = document.createElement('p');
  answer.textContent = result.answer || 'No pude generar una respuesta. Inténtalo de nuevo.';
  bubble.append(answer);

  const sources = result.fuentes || result.sources || [];
  if (Array.isArray(sources) && sources.length > 0) {
    const details = document.createElement('details');
    details.className = 'sources';
    const summary = document.createElement('summary');
    summary.textContent = `Fuentes consultadas (${sources.length})`;
    details.append(summary);
    sources.forEach((source) => {
      const item = document.createElement('div');
      item.className = 'source-item';
      const sourceName = document.createElement('strong');
      const location = source.page ? ` · página ${source.page}` : '';
      const section = source.section ? ` · ${source.section}` : '';
      sourceName.textContent = `${source.name || source.source || 'Guía local'}${location}${section}`;
      const excerpt = document.createElement('p');
      excerpt.textContent = source.excerpt || source.fragment || '';
      item.append(sourceName, excerpt);
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
    groq: 'Respuesta generada a partir de la guía recuperada',
    local: 'Evidencia local · sin generación externa',
    safety: 'Orientación prioritaria de seguridad',
    no_evidence: 'Sin evidencia suficiente en la guía',
  };
  mode.textContent = modeLabels[result.mode] || 'Respuesta basada en conocimiento local';
  column.append(mode);
  article.append(avatar, column);
  conversation.append(article);
  scrollToLatest();
}

async function sendMessage(text) {
  addUserMessage(text);
  history.push({ role: 'user', content: text });
  if (history.length > 8) history.splice(0, history.length - 8);
  if (suggestions) suggestions.hidden = true;
  sendButton.disabled = true;
  input.disabled = true;
  addTypingIndicator();

  try {
    const response = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, history: history.slice(0, -1) }),
    });
    const result = await response.json();
    document.querySelector('#typing-indicator')?.remove();
    if (!response.ok) throw new Error(result.error || 'No fue posible enviar tu consulta.');
    addAssistantMessage(result);
    history.push({ role: 'assistant', content: result.respuesta || result.answer });
    if (history.length > 8) history.splice(0, history.length - 8);
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
