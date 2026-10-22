function formatError(value) {
  if (typeof value === 'string') return value
  if (Array.isArray(value)) {
    return value.map(item => {
      if (typeof item === 'string') return item
      if (!item || typeof item !== 'object') return String(item)
      const message = item.msg || item.message || item.detail
      const location = Array.isArray(item.loc) ? item.loc.filter(part => part !== 'body').join('.') : ''
      return location && message ? `${location}: ${message}` : formatError(message || item)
    }).filter(Boolean).join('；')
  }
  if (value && typeof value === 'object') {
    if (value.detail !== undefined) return formatError(value.detail)
    if (value.error !== undefined) return formatError(value.error)
    if (value.message !== undefined) return formatError(value.message)
    const fields = Object.entries(value).map(([key, item]) => `${key}: ${formatError(item)}`).filter(Boolean)
    return fields.join('；')
  }
  return value == null ? '' : String(value)
}

async function request(path, options = {}) {
  const response = await fetch(path, { credentials: 'same-origin', ...options })
  if (response.status === 401) throw new Error('UNAUTHORIZED')
  const type = response.headers.get('content-type') || ''
  const body = type.includes('json') ? await response.json() : await response.text()
  if (!response.ok) throw new Error(formatError(body?.detail ?? body?.error ?? body) || '请求失败')
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
  billing: () => request('/api/billing/me'),
  plans: () => request('/api/billing/plans'),
  billingOrders: () => request('/api/billing/orders'),
  requestPlan: (plan_code) => request('/api/billing/orders', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ plan_code }),
  }),
  cancelBillingOrder: (id) => request(`/api/billing/orders/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  apiKeys: () => request('/api/account/api-keys'),
  createApiKey: (name) => request('/api/account/api-keys', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) }),
  revokeApiKey: (id) => request(`/api/account/api-keys/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  adminPlans: () => request('/api/admin/plans'),
  adminBillingOrders: () => request('/api/admin/billing/orders'),
  fulfillBillingOrder: (id) => request(`/api/admin/billing/orders/${encodeURIComponent(id)}/fulfill`, { method: 'POST' }),
  savePlan: (code, plan) => request(`/api/admin/plans/${encodeURIComponent(code)}`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(plan),
  }),
  assignPlan: (userId, plan_code, days = 30) => request(`/api/admin/users/${userId}/plan`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ plan_code, days }),
  }),
  createUser: (username, password) => request('/api/admin/users', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, password }),
  }),
  deleteUser: (id) => request('/api/admin/users/' + id, { method: 'DELETE' }),
  saveProviderSettings: (settings) => request('/api/settings/providers', {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(settings),
  }),
  douyinCookieStatus: () => request('/api/settings/douyin-cookies'),
  uploadDouyinCookies: (file) => {
    const form = new FormData()
    form.append('cookies', file)
    return request('/api/settings/douyin-cookies', { method: 'POST', body: form })
  },
  task: (id) => request(`/api/tasks/${id}`),
  refreshPlayback: (id) => request(`/api/tasks/${id}/refresh-playback`, { method: 'POST' }),
  preparePlaybackVideo: (id) => request(`/api/tasks/${id}/prepare-playback-video`, { method: 'POST' }),
  retryTask: (id) => request(`/api/tasks/${id}/retry`, { method: 'POST' }),
  upload: (file, language = 'auto') => {
    const form = new FormData()
    form.append('video', file)
    form.append('language', language)
    return request('/api/tasks/upload', { method: 'POST', body: form })
  },
  url: (url) => request('/api/tasks/url', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url }),
  }),
  batch: (urls) => request('/api/tasks/batch', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ urls }),
  }),
  download: (url) => request('/api/tasks/download', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url }),
  }),
  saveTranscript: (id, segments) => request(`/api/tasks/${id}/transcript`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ segments }),
  }),
  highlights: (id) => request(`/api/tasks/${id}/highlights`, { method: 'POST' }),
  summarize: (id) => request(`/api/tasks/${id}/summary`, { method: 'POST' }),
  translate: (id, language) => request(`/api/tasks/${id}/translate`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ language }),
  }),
  visualAnalysis: (id) => request(`/api/tasks/${id}/visual-analysis`, { method: 'POST' }),
  refreshPlayback: (id) => request(`/api/tasks/${id}/refresh-playback`, { method: 'POST' }),
  rewrite: (id, direction) => request(`/api/tasks/${id}/rewrite`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ direction }),
  }),
  deleteSource: (id) => request(`/api/tasks/${id}/source`, { method: 'DELETE' }),
  deleteTask: (id) => request(`/api/tasks/${id}`, { method: 'DELETE' }),
}
