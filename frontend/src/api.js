async function request(path, options = {}) {
  const response = await fetch(path, { credentials: 'same-origin', ...options })
  if (response.status === 401) throw new Error('UNAUTHORIZED')
  const type = response.headers.get('content-type') || ''
  const body = type.includes('json') ? await response.json() : await response.text()
  if (!response.ok) throw new Error(body?.detail || body?.error || body || '请求失败')
  return body
}

export const api = {
  me: () => request('/api/auth/me'),
  login: (username, password) => request('/api/auth/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  }),
  logout: () => request('/api/auth/logout', { method: 'POST' }),
  changePassword: (current_password, new_password) => request('/api/auth/change-password', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ current_password, new_password }),
  }),
  health: () => request('/api/health'),
  tasks: () => request('/api/tasks'),
  providerSettings: () => request('/api/settings/providers'),
  adminUsers: () => request('/api/admin/users'),
  createUser: (username, password) => request('/api/admin/users', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, password }),
  }),
  saveProviderSettings: (settings) => request('/api/settings/providers', {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(settings),
  }),
  task: (id) => request(`/api/tasks/${id}`),
  upload: (file, language = 'auto') => {
    const form = new FormData()
    form.append('video', file)
    form.append('language', language)
    return request('/api/tasks/upload', { method: 'POST', body: form })
  },
  url: (url) => request('/api/tasks/url', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url }),
  }),
  saveTranscript: (id, segments) => request(`/api/tasks/${id}/transcript`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ segments }),
  }),
  highlights: (id) => request(`/api/tasks/${id}/highlights`, { method: 'POST' }),
  rewrite: (id, direction) => request(`/api/tasks/${id}/rewrite`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ direction }),
  }),
  deleteSource: (id) => request(`/api/tasks/${id}/source`, { method: 'DELETE' }),
  deleteTask: (id) => request(`/api/tasks/${id}`, { method: 'DELETE' }),
}
