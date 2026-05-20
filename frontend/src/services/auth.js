/** Authentication service — login, signup, logout, current user. */

import { BASE, request, extractErrorDetail, setToken, setStoredUser, clearToken, clearStoredUser } from './base.js';

export const login = async (username, password) => {
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(extractErrorDetail(body) || 'Login failed');
  }
  const data = await res.json();
  setToken(data.token);
  setStoredUser(data.user);
  return data;
};

export const signup = async (username, password) => {
  const res = await fetch(`${BASE}/auth/signup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(extractErrorDetail(body) || 'Signup failed');
  }
  const data = await res.json();
  // If the server returned pending_approval, don't store token — user needs admin approval
  if (data.token) {
    setToken(data.token);
    setStoredUser(data.user);
  }
  return data;
};

export const fetchMe = () => request('/auth/me');

export const changePassword = (current_password, new_password) =>
  request('/auth/me/password', { method: 'PUT', body: JSON.stringify({ current_password, new_password }) });

export const logout = () => {
  clearToken();
  clearStoredUser();
  localStorage.removeItem('activeConversation');
};
