const BASE = import.meta.env.VITE_API_BASE_URL || '';

async function request(path, options = {}) {
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
    // Don't hard-redirect — let the calling code (AuthContext) handle 401 gracefully
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
