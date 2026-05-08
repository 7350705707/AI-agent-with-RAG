/** Conversations service — CRUD and message retrieval. */

import { request } from './base.js';

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
