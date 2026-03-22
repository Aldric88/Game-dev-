const BASE = import.meta.env.VITE_API_BASE_URL || '';

// Set to true while a token refresh is in-flight to avoid parallel refresh races.
let _refreshing = false;
let _refreshWaiters = [];

function _clearSession() {
  localStorage.removeItem('token');
  localStorage.removeItem('user');
  // Dispatch a custom event so AuthContext (or any listener) can react
  // without this module needing a direct dependency on React state.
  window.dispatchEvent(new CustomEvent('auth:logout'));
}

async function _attemptRefresh() {
  if (_refreshing) {
    // Another call is already refreshing — wait for it to finish.
    return new Promise((resolve, reject) => {
      _refreshWaiters.push({ resolve, reject });
    });
  }
  _refreshing = true;
  try {
    const token = localStorage.getItem('token');
    if (!token) throw new Error('No token');
    const res = await fetch(`${BASE}/api/v1/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error('Refresh failed');
    const data = await res.json();
    localStorage.setItem('token', data.access_token);
    _refreshWaiters.forEach(({ resolve }) => resolve());
    return data.access_token;
  } catch (err) {
    _refreshWaiters.forEach(({ reject }) => reject(err));
    _clearSession();
    throw err;
  } finally {
    _refreshing = false;
    _refreshWaiters = [];
  }
}

async function request(path, options = {}, _isRetry = false) {
  const token = localStorage.getItem('token');
  const headers = { 'Content-Type': 'application/json', ...options.headers };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  let res;
  try {
    res = await fetch(`${BASE}${path}`, { ...options, headers });
  } catch (err) {
    throw new Error('Network error: unable to reach the server. Is the backend running?');
  }

  if (res.status === 204) return null;

  // Try to parse JSON body (some errors may not have JSON)
  let data;
  try {
    data = await res.json();
  } catch {
    if (!res.ok) throw new Error(`Request failed (${res.status})`);
    return null;
  }

  if (res.status === 401) {
    // On first 401, attempt a token refresh then retry the original request once.
    // If the refresh itself fails (expired session), _clearSession() logs the user out.
    if (!_isRetry && path !== '/api/v1/auth/refresh') {
      try {
        await _attemptRefresh();
        return request(path, options, true);
      } catch {
        throw new Error('Session expired. Please log in again.');
      }
    }
    _clearSession();
    throw new Error(data.detail || 'Authentication required');
  }

  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}

/* ── Auth ── */
export const auth = {
  register: (body) =>
    request('/api/v1/auth/register', { method: 'POST', body: JSON.stringify(body) }),
  login: (body) =>
    request('/api/v1/auth/login', { method: 'POST', body: JSON.stringify(body) }),
  me: () => request('/api/v1/auth/me'),
  refresh: () => request('/api/v1/auth/refresh', { method: 'POST' }),
  forgotPassword: (body) =>
    request('/api/v1/auth/forgot-password', { method: 'POST', body: JSON.stringify(body) }),
  resetPassword: (body) =>
    request('/api/v1/auth/reset-password', { method: 'POST', body: JSON.stringify(body) }),
};

/* ── Projects ── */
export const projects = {
  list: () => request('/api/v1/projects'),
  get: (id) => request(`/api/v1/projects/${id}`),
  create: (body) =>
    request('/api/v1/projects', { method: 'POST', body: JSON.stringify(body) }),
  update: (id, body) =>
    request(`/api/v1/projects/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: (id) =>
    request(`/api/v1/projects/${id}`, { method: 'DELETE' }),
};

/* ── AI ── */
export const ai = {
  design: (body) =>
    request('/api/v1/ai/design', { method: 'POST', body: JSON.stringify(body) }),
  generate: (body) =>
    request('/api/v1/ai/generate', { method: 'POST', body: JSON.stringify(body) }),
  chat: (body) =>
    request('/api/v1/ai/chat', { method: 'POST', body: JSON.stringify(body) }),
  godotGenerate: (body) =>
    request('/api/v1/ai/godot/generate', { method: 'POST', body: JSON.stringify(body) }),
  importFiles: (projectId, body) =>
    request(`/api/v1/ai/import/${projectId}`, { method: 'POST', body: JSON.stringify(body) }),
  saveCode: (projectId, files) =>
    request(`/api/v1/ai/code/${projectId}`, { method: 'PATCH', body: JSON.stringify({ files }) }),
};

/* ── Download ── */
export async function downloadProjectZip(projectId) {
  const token = localStorage.getItem('token');
  const res = await fetch(`${BASE}/api/v1/ai/download/${projectId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Download failed');
  }
  return res.blob();
}

/* ── Godot Actions ── */
export const godot = {
  openFolder: (projectId) =>
    request(`/api/v1/ai/open-folder/${projectId}`, { method: 'POST' }),
  runGodot: (projectId) =>
    request(`/api/v1/ai/run-godot/${projectId}`, { method: 'POST' }),
};

/* ── Users ── */
export const users = {
  getProfile: () => request('/api/v1/users/me'),
  updateProfile: (body) => request('/api/v1/users/me', { method: 'PATCH', body: JSON.stringify(body) }),
  getUsage: () => request('/api/v1/users/me/usage'),
};

/* ── Dashboard ── */
export const dashboard = {
  summary: () => request('/api/v1/dashboard/summary'),
};

/* ── Health ── */
export const health = {
  check: () => request('/api/v1/health'),
};

/* ── Preview ── */
export function getPreviewUrl(projectId) {
  const token = localStorage.getItem('token');
  return `${BASE}/api/v1/preview/${projectId}?token=${token}`;
}
