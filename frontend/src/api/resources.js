import { del, get, patch, post } from './client'

export const authApi = {
  login: (email, password) => post('/api/auth/login/', { email, password }),
  me: () => get('/api/auth/me/'),
  users: (role) => get(`/api/auth/users/${role ? `?role=${role}` : ''}`),
}

export const subscriptionsApi = {
  list: (qs = '') => get(`/api/subscriptions/${qs}`),
  detail: (id) => get(`/api/subscriptions/${id}/`),
  create: (body) => post('/api/subscriptions/', body),
  update: (id, body) => patch(`/api/subscriptions/${id}/`, body),
  archive: (id) => post(`/api/subscriptions/${id}/archive/`),
  restore: (id) => post(`/api/subscriptions/${id}/restore/`),
  addCollaborator: (id, userId) =>
    post(`/api/subscriptions/${id}/collaborators/`, { user_id: userId }),
  removeCollaborator: (id, userId) =>
    del(`/api/subscriptions/${id}/collaborators/${userId}/`),
}

export const invoicesApi = {
  list: (qs = '') => get(`/api/invoices/${qs}`),
  detail: (id) => get(`/api/invoices/${id}/`),
  create: (body) => post('/api/invoices/', body),
  update: (id, body) => patch(`/api/invoices/${id}/`, body),
  issue: (id) => post(`/api/invoices/${id}/issue/`),
  pay: (id) => post(`/api/invoices/${id}/pay/`),
  void: (id, reason) => post(`/api/invoices/${id}/void/`, { reason }),
  creditNote: (id, amount, reason) =>
    post(`/api/invoices/${id}/credit-notes/`, { amount, reason }),
  addNote: (id, text) => post(`/api/invoices/${id}/notes/`, { text }),
  timeline: (id) => get(`/api/invoices/${id}/timeline/`),
  dismissAlert: (id) => post(`/api/invoices/${id}/dismiss-alert/`),
  bulkGenerate: (asOf) => post('/api/invoices/bulk-generate/', asOf ? { as_of: asOf } : {}),
}

export const dashboardApi = { get: () => get('/api/dashboard/') }
export const alertsApi = {
  list: () => get('/api/alerts/'),
  count: () => get('/api/alerts/count/'),
}
