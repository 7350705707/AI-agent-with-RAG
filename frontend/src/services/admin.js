/** Admin service — user management (admin only). */

import { request } from './base.js';

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
