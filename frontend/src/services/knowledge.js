/** Knowledge base service — document upload, listing, management. */

import { BASE, request, authHeaders, extractErrorDetail, getToken, clearToken, clearStoredUser } from './base.js';

/**
 * Upload a knowledge document with progress reporting.
 * @param {File} file
 * @param {(pct: number) => void} [onProgress]
 * @returns {Promise<Object>}
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
        return reject(Object.assign(new Error(extractErrorDetail(body) || 'Duplicate file'), { isDuplicate: true }));
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        let body = {};
        try { body = JSON.parse(xhr.responseText); } catch { /* */ }
        return reject(new Error(extractErrorDetail(body) || `Upload failed: ${xhr.status}`));
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

export const summarizeKnowledgeDoc = (id) =>
  request(`/knowledge/documents/${id}/summarize`, { method: 'POST' });

export const searchKnowledge = (q, limit = 10) =>
  request(`/knowledge/search?q=${encodeURIComponent(q)}&limit=${limit}`);

export const getKnowledgeDocUrl = (docId) => {
  const token = getToken();
  const url = `${BASE}/knowledge/documents/${docId}/download`;
  return token ? `${url}?token=${encodeURIComponent(token)}` : url;
};
