/** Shared base utilities: URL, token storage, HTTP helper. */

export const BASE = `${window.location.protocol}//${window.location.hostname}:8000/api`;

// ── Token management (localStorage — survives browser restarts intentionally)
export const getToken = () => localStorage.getItem('token');
export const setToken = (t) => localStorage.setItem('token', t);
export const clearToken = () => localStorage.removeItem('token');

// ── User object (sessionStorage — cleared when the browser tab/window closes;
//    prevents role/agent metadata from persisting on shared machines)
export const getStoredUser = () => {
  try { return JSON.parse(sessionStorage.getItem('user')); } catch { return null; }
};
export const setStoredUser = (u) => sessionStorage.setItem('user', JSON.stringify(u));
export const clearStoredUser = () => sessionStorage.removeItem('user');

export function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Convert a FastAPI error body's `detail` field to a readable string. */
export function extractErrorDetail(body) {
  if (!body || !body.detail) return null;
  if (typeof body.detail === 'string') return body.detail;
  if (Array.isArray(body.detail)) {
    return body.detail.map((e) => e.msg || JSON.stringify(e)).join('; ');
  }
  return JSON.stringify(body.detail);
}

export async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...options.headers },
    ...options,
  });
  if (res.status === 401 && getToken()) {
    clearToken();
    clearStoredUser();
    window.location.reload();
    throw new Error('Session expired');
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(extractErrorDetail(body) || `Request failed: ${res.status}`);
  }
  if (res.status === 204) return null;
  return res.json();
}
