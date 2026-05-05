/** API helper - all backend calls go through here. */

const BASE = `${window.location.protocol}//${window.location.hostname}:8000/api`;

// ── Token management ──────────────────────────────────────────────────────
export const getToken = () => localStorage.getItem('token');
export const setToken = (t) => localStorage.setItem('token', t);
export const clearToken = () => localStorage.removeItem('token');

export const getStoredUser = () => {
  try { return JSON.parse(localStorage.getItem('user')); } catch { return null; }
};
export const setStoredUser = (u) => localStorage.setItem('user', JSON.stringify(u));
export const clearStoredUser = () => localStorage.removeItem('user');

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...options.headers },
    ...options,
  });
  if (res.status === 401 && getToken()) {
    // Only clear & reload if user WAS logged in (token expired)
    clearToken();
    clearStoredUser();
    window.location.reload();
    throw new Error('Session expired');
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

// ── Auth ───────────────────────────────────────────────────────────────────
export const login = async (username, password) => {
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || 'Login failed');
  }
  const data = await res.json();
  setToken(data.token);
  setStoredUser(data.user);
  return data;
};

export const fetchMe = () => request('/auth/me');

export const signup = async (username, password) => {
  const res = await fetch(`${BASE}/auth/signup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || 'Signup failed');
  }
  const data = await res.json();
  setToken(data.token);
  setStoredUser(data.user);
  return data;
};

export const logout = () => {
  clearToken();
  clearStoredUser();
  // Clear any cached conversation data so history isn't visible after logout
  localStorage.removeItem('activeConversation');
};

// ── Admin: Users ──────────────────────────────────────────────────────────
export const listUsers = () => request('/admin/users');

export const createUser = (username, password, role, agents) =>
  request('/admin/users', {
    method: 'POST',
    body: JSON.stringify({ username, password, role, agents }),
  });

export const updateUser = (id, updates) =>
  request(`/admin/users/${id}`, {
    method: 'PUT',
    body: JSON.stringify(updates),
  });

export const resetUserPassword = (id, password) =>
  request(`/admin/users/${id}/password`, {
    method: 'PUT',
    body: JSON.stringify({ password }),
  });

export const deleteUser = (id) =>
  request(`/admin/users/${id}`, { method: 'DELETE' });

// ── Conversations ──────────────────────────────────────────────────────────
export const createConversation = (agentType, title) =>
  request('/conversations', {
    method: 'POST',
    body: JSON.stringify({ agent_type: agentType, title }),
  });

export const listConversations = (agentType) =>
  request(`/conversations${agentType ? `?agent_type=${agentType}` : ''}`);

export const deleteConversation = (id) =>
  request(`/conversations/${id}`, { method: 'DELETE' });

export const renameConversation = (id, title) =>
  request(`/conversations/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ title }),
  });

export const getMessages = (convId) =>
  request(`/conversations/${convId}/messages`);

// ── Chat ───────────────────────────────────────────────────────────────────
export const sendChat = (conversationId, message) =>
  request('/chat', {
    method: 'POST',
    body: JSON.stringify({ conversation_id: conversationId, message }),
  });

/**
 * Stream chat response via SSE.
 * @param {string} conversationId
 * @param {string} message
 * @param {(data: {token: string, done: boolean, sources?: Array, error?: string}) => void} onToken
 * @returns {Promise<void>}
 */
export const sendChatStream = async (conversationId, message, onToken, signal) => {
  const res = await fetch(`${BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ conversation_id: conversationId, message }),
    signal,
  });
  if (res.status === 401 && getToken()) {
    clearToken();
    clearStoredUser();
    window.location.reload();
    throw new Error('Session expired');
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    if (signal?.aborted) { reader.cancel(); break; }
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split('\n');
    buffer = lines.pop();
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const data = JSON.parse(line.slice(6));
          onToken(data);
        } catch { /* skip malformed */ }
      }
    }
  }
  if (!signal?.aborted && buffer.startsWith('data: ')) {
    try {
      const data = JSON.parse(buffer.slice(6));
      onToken(data);
    } catch { /* skip */ }
  }
};

// ── General Chat (no RAG) ──────────────────────────────────────────────────
export const sendGeneralChatStream = async (conversationId, message, onToken, signal) => {
  const res = await fetch(`${BASE}/general-chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ conversation_id: conversationId, message }),
    signal,
  });
  if (res.status === 401 && getToken()) {
    clearToken();
    clearStoredUser();
    window.location.reload();
    throw new Error('Session expired');
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    if (signal?.aborted) { reader.cancel(); break; }
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split('\n');
    buffer = lines.pop();
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const data = JSON.parse(line.slice(6));
          onToken(data);
        } catch { /* skip malformed */ }
      }
    }
  }
  if (!signal?.aborted && buffer.startsWith('data: ')) {
    try {
      const data = JSON.parse(buffer.slice(6));
      onToken(data);
    } catch { /* skip */ }
  }
};

// ── Exam ───────────────────────────────────────────────────────────────────
export const sendExam = (conversationId, instructions, fileIds) =>
  request('/exam', {
    method: 'POST',
    body: JSON.stringify({
      conversation_id: conversationId,
      instructions,
      file_ids: fileIds,
    }),
  });

/**
 * Stream exam generation via SSE.
 * @param {string} conversationId
 * @param {string} instructions
 * @param {string[]} fileIds
 * @param {(data: {step: string, label: string, content: string}) => void} onEvent
 * @returns {Promise<void>}
 */
export const sendExamStream = async (conversationId, instructions, fileIds, onEvent, counts = {}, signal) => {
  const { mcq_count = 10, tf_count = 10, fitb_count = 10 } = counts;
  const res = await fetch(`${BASE}/exam/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({
      conversation_id: conversationId,
      instructions,
      file_ids: fileIds,
      mcq_count,
      tf_count,
      fitb_count,
    }),
    signal,
  });
  if (res.status === 401 && getToken()) {
    clearToken();
    clearStoredUser();
    window.location.reload();
    throw new Error('Session expired');
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    if (signal?.aborted) { reader.cancel(); break; }
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Parse SSE lines
    const lines = buffer.split('\n');
    buffer = lines.pop(); // keep incomplete line in buffer
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const data = JSON.parse(line.slice(6));
          onEvent(data);
        } catch { /* skip malformed */ }
      }
    }
  }
  // Flush remaining buffer
  if (!signal?.aborted && buffer.startsWith('data: ')) {
    try {
      const data = JSON.parse(buffer.slice(6));
      onEvent(data);
    } catch { /* skip */ }
  }
};

// ── Upload (multipart) ────────────────────────────────────────────────────
export const uploadFile = async (file, conversationId = null) => {
  const form = new FormData();
  form.append('file', file);
  const url = conversationId
    ? `${BASE}/upload?conversation_id=${encodeURIComponent(conversationId)}`
    : `${BASE}/upload`;
  const res = await fetch(url, {
    method: 'POST',
    body: form,
    headers: authHeaders(),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || 'Upload failed');
  }
  return res.json();
};

// ── Knowledge Base ─────────────────────────────────────────────────────────
/**
 * Upload a knowledge document with progress reporting.
 * @param {File} file
 * @param {(pct: number) => void} [onProgress] - called with 0-100
 * @returns {Promise<Object>} uploaded document record
 */
export const uploadKnowledgeDoc = (file, onProgress) =>
  new Promise((resolve, reject) => {
    const form = new FormData();
    form.append('file', file);
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${BASE}/knowledge/upload`);
    const token = getToken();
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    });
    xhr.onload = () => {
      if (xhr.status === 401 && getToken()) {
        clearToken(); clearStoredUser(); window.location.reload();
        return reject(new Error('Session expired'));
      }
      if (xhr.status === 409) {
        let body = {};
        try { body = JSON.parse(xhr.responseText); } catch { /* */ }
        return reject(Object.assign(new Error(body.detail || 'Duplicate file'), { isDuplicate: true }));
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        let body = {};
        try { body = JSON.parse(xhr.responseText); } catch { /* */ }
        return reject(new Error(body.detail || `Upload failed: ${xhr.status}`));
      }
      try { resolve(JSON.parse(xhr.responseText)); } catch { reject(new Error('Invalid response')); }
    };
    xhr.onerror = () => reject(new Error('Network error during upload'));
    xhr.send(form);
  });

export const listKnowledgeDocs = () => request('/knowledge/documents');

export const deleteKnowledgeDoc = (id) =>
  request(`/knowledge/documents/${id}`, { method: 'DELETE' });

export const renameKnowledgeDoc = (id, filename) =>
  request(`/knowledge/documents/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ filename }),
  });

export const clearKnowledgeBase = () =>
  request('/knowledge/clear', { method: 'DELETE' });

export const indexKnowledgeDoc = (id) =>
  request(`/knowledge/documents/${id}/index`, { method: 'POST' });

// ── Health ─────────────────────────────────────────────────────────────────
export const healthCheck = () => request('/health');

// ── Models ─────────────────────────────────────────────────────────────────
export const listModels = () => request('/models');

export const selectModel = (model) =>
  request('/models/select', {
    method: 'POST',
    body: JSON.stringify({ model }),
  });

export const loadModel = (model) =>
  request('/models/load', {
    method: 'POST',
    body: JSON.stringify({ model }),
  });

// ── Knowledge Document Download ───────────────────────────────────────────
export const getKnowledgeDocUrl = (docId) => {
  const token = getToken();
  const url = `${BASE}/knowledge/documents/${docId}/download`;
  return token ? `${url}?token=${encodeURIComponent(token)}` : url;
};
