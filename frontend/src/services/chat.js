/** Chat, exam, and file-upload service — all streaming and non-streaming calls. */

import { BASE, request, authHeaders, extractErrorDetail, getToken, clearToken, clearStoredUser } from './base.js';

// ── Shared SSE stream reader ──────────────────────────────────────────────
async function _readSSEStream(res, onData, signal) {
  if (res.status === 401 && getToken()) {
    clearToken(); clearStoredUser(); window.location.reload();
    throw new Error('Session expired');
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(extractErrorDetail(body) || `Request failed: ${res.status}`);
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
        try { onData(JSON.parse(line.slice(6))); } catch { /* skip malformed */ }
      }
    }
  }
  if (!signal?.aborted && buffer.startsWith('data: ')) {
    try { onData(JSON.parse(buffer.slice(6))); } catch { /* skip */ }
  }
}

// ── Chat (RAG) ────────────────────────────────────────────────────────────
export const sendChat = (conversationId, message) =>
  request('/chat', {
    method: 'POST',
    body: JSON.stringify({ conversation_id: conversationId, message }),
  });

export const sendChatStream = async (conversationId, message, onToken, signal) => {
  const res = await fetch(`${BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ conversation_id: conversationId, message }),
    signal,
  });
  await _readSSEStream(res, onToken, signal);
};

// ── Agentic RAG Chat (tool-calling loop) ──────────────────────────────────
export const sendAgenticChatStream = async (conversationId, message, onToken, signal, fileIds = []) => {
  const res = await fetch(`${BASE}/agentic-chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ conversation_id: conversationId, message, file_ids: fileIds }),
    signal,
  });
  await _readSSEStream(res, onToken, signal);
};

// ── Exam ──────────────────────────────────────────────────────────────────
export const sendExam = (conversationId, instructions, fileIds) =>
  request('/exam', {
    method: 'POST',
    body: JSON.stringify({ conversation_id: conversationId, instructions, file_ids: fileIds }),
  });

export const sendExamStream = async (conversationId, instructions, fileIds, onEvent, counts = {}, signal) => {
  const { mcq_count = 10, tf_count = 10, fitb_count = 10 } = counts;
  const res = await fetch(`${BASE}/exam/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ conversation_id: conversationId, instructions, file_ids: fileIds, mcq_count, tf_count, fitb_count }),
    signal,
  });
  await _readSSEStream(res, onEvent, signal);
};

// ── Exam topic extraction ─────────────────────────────────────────────────
export const fetchExamTopics = (fileIds) =>
  request('/exam/topics', {
    method: 'POST',
    body: JSON.stringify({ file_ids: fileIds }),
  });

// ── Structured questions (DB persistence) ────────────────────────────────
export const getExamQuestions = (conversationId) =>
  request(`/exam/questions/${encodeURIComponent(conversationId)}`);

export const saveExamQuestions = (conversationId, questions) =>
  request(`/exam/questions/${encodeURIComponent(conversationId)}`, {
    method: 'POST',
    body: JSON.stringify({ questions }),
  });

// ── File upload (conversation-scoped) ─────────────────────────────────────
export const uploadFile = async (file, conversationId = null) => {
  const form = new FormData();
  form.append('file', file);
  const url = conversationId
    ? `${BASE}/upload?conversation_id=${encodeURIComponent(conversationId)}`
    : `${BASE}/upload`;
  const res = await fetch(url, { method: 'POST', body: form, headers: authHeaders() });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(extractErrorDetail(body) || 'Upload failed');
  }
  return res.json();
};
