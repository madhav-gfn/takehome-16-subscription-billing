const BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

const ACCESS = 'billing.access'
const REFRESH = 'billing.refresh'

export const tokens = {
  get access() { return localStorage.getItem(ACCESS) },
  get refresh() { return localStorage.getItem(REFRESH) },
  set({ access, refresh }) {
    if (access) localStorage.setItem(ACCESS, access)
    if (refresh) localStorage.setItem(REFRESH, refresh)
  },
  clear() {
    localStorage.removeItem(ACCESS)
    localStorage.removeItem(REFRESH)
  },
}

export class ApiError extends Error {
  constructor({ code, message, field, details, status }) {
    super(message)
    this.name = 'ApiError'
    Object.assign(this, { code, field, details, status })
  }
}

// One in-flight refresh, shared. Five parallel 401s must trigger one refresh,
// not five — with ROTATE_REFRESH_TOKENS on, the losers would invalidate the
// winner's token.
let refreshing = null

async function refreshAccess() {
  if (!refreshing) {
    refreshing = (async () => {
      const rt = tokens.refresh
      if (!rt) throw new Error('no refresh token')
      const res = await fetch(`${BASE}/api/auth/refresh/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh: rt }),
      })
      if (!res.ok) throw new Error('refresh failed')
      const data = await res.json()
      tokens.set(data)
      return data.access
    })().finally(() => { refreshing = null })
  }
  return refreshing
}

async function raw(path, { method = 'GET', body, headers = {}, retry = true } = {}) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...(tokens.access ? { Authorization: `Bearer ${tokens.access}` } : {}),
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

  if (res.status === 401 && retry && tokens.refresh) {
    try {
      await refreshAccess()
      return raw(path, { method, body, headers, retry: false })
    } catch {
      tokens.clear()
      window.dispatchEvent(new Event('billing:signed-out'))
      throw new ApiError({
        code: 'UNAUTHENTICATED',
        message: 'Your session has expired. Please sign in again.',
        status: 401,
      })
    }
  }
  return res
}

export async function api(path, opts) {
  const res = await raw(path, opts)
  if (res.status === 204) return null
  const data = await res.json().catch(() => null)
  if (!res.ok) {
    const e = data?.error ?? {}
    // The server's message is shown verbatim. The client never writes its own
    // explanation for a rule it does not own.
    throw new ApiError({
      code: e.code ?? 'ERROR',
      message: e.message ?? `Request failed (${res.status})`,
      field: e.field,
      details: e.details,
      status: res.status,
    })
  }
  return data
}

export const get = (p) => api(p)
export const post = (p, b) => api(p, { method: 'POST', body: b ?? {} })
export const patch = (p, b) => api(p, { method: 'PATCH', body: b })
export const del = (p) => api(p, { method: 'DELETE' })

// The CSV export needs the bearer header, so it cannot be a bare <a href>.
export async function download(path, filename) {
  const res = await raw(path)
  if (!res.ok) {
    throw new ApiError({ code: 'EXPORT_FAILED', message: 'Export failed.', status: res.status })
  }
  const url = URL.createObjectURL(await res.blob())
  const a = Object.assign(document.createElement('a'), { href: url, download: filename })
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
