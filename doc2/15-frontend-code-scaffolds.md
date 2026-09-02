# 15 — Frontend Code Scaffolds

Doc 07 settles the screens and the principles. This is the code for the shared machinery — the
parts every page depends on, and the parts that are easy to get subtly wrong.

Individual page components are not scaffolded here: once the client, the auth context, the filter
hook and `DataTable` exist, each page is a `useApi` call plus a table, and the layouts in
[07](07-frontend-build-plan.md) §5 are the spec.

---

## 1. `api/client.js`

```js
const BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

const ACCESS = 'billing.access'
const REFRESH = 'billing.refresh'

export const tokens = {
  get access()  { return localStorage.getItem(ACCESS) },
  get refresh() { return localStorage.getItem(REFRESH) },
  set({ access, refresh }) {
    if (access)  localStorage.setItem(ACCESS, access)
    if (refresh) localStorage.setItem(REFRESH, refresh)
  },
  clear() { localStorage.removeItem(ACCESS); localStorage.removeItem(REFRESH) },
}

export class ApiError extends Error {
  constructor({ code, message, field, details, status }) {
    super(message)
    Object.assign(this, { code, field, details, status })
  }
}

// One in-flight refresh, shared. Five parallel 401s must trigger one refresh,
// not five — otherwise rotation invalidates the tokens of the losers.
let refreshing = null

async function refreshAccess() {
  if (!refreshing) {
    refreshing = (async () => {
      const rt = tokens.refresh
      if (!rt) throw new ApiError({ code: 'NO_REFRESH', message: 'Signed out.', status: 401 })
      const res = await fetch(`${BASE}/api/auth/refresh/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh: rt }),
      })
      if (!res.ok) throw new ApiError({ code: 'REFRESH_FAILED', message: 'Session expired. Please sign in again.', status: 401 })
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
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...(tokens.access ? { Authorization: `Bearer ${tokens.access}` } : {}),
      ...headers,
    },
    body: body ? JSON.stringify(body) : undefined,
  })

  if (res.status === 401 && retry && tokens.refresh) {
    try {
      await refreshAccess()
      return raw(path, { method, body, headers, retry: false })
    } catch {
      tokens.clear()
      window.dispatchEvent(new Event('billing:signed-out'))
      throw new ApiError({ code: 'UNAUTHENTICATED', message: 'Session expired. Please sign in again.', status: 401 })
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
    // The server's message is shown verbatim — the client never writes its own
    // explanation for a rule it does not own. See doc 07 §1.
    throw new ApiError({
      code: e.code ?? 'ERROR',
      message: e.message ?? `Request failed (${res.status})`,
      field: e.field, details: e.details, status: res.status,
    })
  }
  return data
}

export const get   = (p)    => api(p)
export const post  = (p, b) => api(p, { method: 'POST', body: b ?? {} })
export const patch = (p, b) => api(p, { method: 'PATCH', body: b })
export const del   = (p)    => api(p, { method: 'DELETE' })

// The CSV export needs the bearer header, so it cannot be a bare <a href>.
export async function download(path, filename) {
  const res = await raw(path)
  if (!res.ok) throw new ApiError({ code: 'EXPORT_FAILED', message: 'Export failed.', status: res.status })
  const url = URL.createObjectURL(await res.blob())
  const a = Object.assign(document.createElement('a'), { href: url, download: filename })
  document.body.appendChild(a); a.click(); a.remove()
  URL.revokeObjectURL(url)
}
```

`billing:signed-out` is a window event rather than a direct redirect so `client.js` stays free of
router imports; `AuthContext` listens for it and navigates.

---

## 2. `auth/AuthContext.jsx`

```jsx
import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { get, post, tokens } from '../api/client'

const AuthContext = createContext(null)
export const useAuth = () => useContext(AuthContext)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!tokens.access) { setLoading(false); return }
    get('/api/auth/me/').then(setUser).catch(() => tokens.clear()).finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    const onSignedOut = () => setUser(null)
    window.addEventListener('billing:signed-out', onSignedOut)
    return () => window.removeEventListener('billing:signed-out', onSignedOut)
  }, [])

  const login = useCallback(async (email, password) => {
    tokens.set(await post('/api/auth/login/', { email, password }))
    setUser(await get('/api/auth/me/'))
  }, [])

  const logout = useCallback(() => { tokens.clear(); setUser(null) }, [])

  const value = {
    user, loading, login, logout,
    isAdmin: user?.role === 'billing_admin',
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
```

`loading` matters: without it, a page refresh renders `RequireAuth` before `/me/` resolves and
bounces a signed-in user to the login screen.

---

## 3. `lib/permissions.js` — cosmetic only

```js
/**
 * COSMETIC ONLY. Every rule below is enforced on the server and tested there.
 * These exist so the UI does not render controls that are guaranteed to 403.
 * Deleting this file would change nothing about what a user can actually do.
 *
 * Do not add rules here that the server does not also enforce.
 */
export const canIssue  = (u, i) => u?.role === 'billing_admin' && i.status === 'draft'
export const canPay    = (u, i) => u?.role === 'billing_admin' && i.status === 'issued'
export const canVoid   = (u, i) => u?.role === 'billing_admin' && ['draft', 'issued'].includes(i.status)
export const canCredit = (u, i) => u?.role === 'billing_admin' && i.status === 'paid'
export const canEditFields = (i) => i.status === 'draft'
export const canEditDueDate = (i) => ['draft', 'issued'].includes(i.status)
export const canArchive = (u) => u?.role === 'billing_admin'
export const canManageCollaborators = (u) => u?.role === 'billing_admin'
export const canBulkGenerate = (u) => u?.role === 'billing_admin'
export const canDismissAlert = (u) => u?.role === 'billing_admin'

/** Why a control is disabled — shown as a title attribute. */
export function whyDisabled(u, i, action) {
  if (u?.role !== 'billing_admin' && ['issue','pay','void','credit'].includes(action))
    return 'Only a billing admin can do this.'
  if (action === 'void' && i.status === 'paid')
    return 'A paid invoice cannot be voided. Issue a credit note instead.'
  if (action === 'credit' && i.status !== 'paid')
    return 'Credit notes can only be issued against paid invoices.'
  if (i.status === 'void') return 'This invoice has been voided.'
  return ''
}
```

The header comment is load-bearing. It is the file most likely to be mistaken for the authorization
logic, and the brief cares specifically about that distinction.

---

## 4. `hooks/useApi.js`

```jsx
import { useCallback, useEffect, useRef, useState } from 'react'
import { get } from '../api/client'

export function useApi(path, { skip = false } = {}) {
  const [state, setState] = useState({ data: null, loading: !skip, error: null })
  const [slow, setSlow] = useState(false)          // free-tier cold start
  const latest = useRef(0)

  const refetch = useCallback(() => {
    if (skip || !path) return
    const id = ++latest.current
    setState(s => ({ ...s, loading: true, error: null }))
    const timer = setTimeout(() => setSlow(true), 5000)

    get(path)
      .then(data => { if (id === latest.current) setState({ data, loading: false, error: null }) })
      .catch(err => { if (id === latest.current) setState({ data: null, loading: false, error: err }) })
      .finally(() => { clearTimeout(timer); if (id === latest.current) setSlow(false) })
  }, [path, skip])

  useEffect(() => { refetch() }, [refetch])
  return { ...state, slow, refetch }
}
```

`latest` guards against out-of-order responses: typing in the debounced search box fires several
requests, and without the guard a slow earlier response can overwrite a fast later one, leaving the
table showing results for a query the user has already changed.

`slow` drives the "waking the backend" message required by [10](10-deployment-plan.md) §4.

---

## 5. `hooks/useQueryFilters.js` (Goal 6)

```jsx
import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

/**
 * Filter state lives in the URL, not in component state. Three reasons:
 * a filtered view is shareable, the back button works, and it is visible
 * proof that filtering is server-side — the URL changes and a request goes
 * out. See doc 07 §5.
 */
export function useQueryFilters(defaults = {}) {
  const [params, setParams] = useSearchParams()

  const filters = useMemo(() => {
    const out = { ...defaults }
    for (const [k, v] of params.entries()) {
      out[k] = k === 'status' ? params.getAll('status') : v   // status repeats
    }
    return out
  }, [params])                                     // eslint-disable-line

  const setFilter = useCallback((key, value) => {
    const next = new URLSearchParams(params)
    next.delete(key)
    if (Array.isArray(value)) value.forEach(v => next.append(key, v))
    else if (value !== '' && value != null && value !== false) next.set(key, value)
    // Any filter change resets to page 1 — otherwise a user lands on page 7
    // of a 2-page result and sees an empty table.
    if (key !== 'page') next.delete('page')
    setParams(next, { replace: true })
  }, [params, setParams])

  const clear = useCallback(() => setParams(new URLSearchParams()), [setParams])

  const queryString = useMemo(() => {
    const qs = params.toString()
    return qs ? `?${qs}` : ''
  }, [params])

  return { filters, setFilter, clear, queryString }
}
```

A page then reads:
```jsx
const { filters, setFilter, queryString } = useQueryFilters({ page: '1' })
const { data, loading, error } = useApi(`/api/invoices/${queryString}`)
```
The page passes the query string straight through. It never inspects or reshapes the filters, which
is what keeps filtering honestly server-side.

---

## 6. `hooks/useAlertCount.js` (Goal 10)

```jsx
import { useCallback, useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { get } from '../api/client'
import { useAuth } from '../auth/AuthContext'

export function useAlertCount() {
  const { user } = useAuth()
  const { pathname } = useLocation()
  const [count, setCount] = useState(0)

  const refresh = useCallback(() => {
    if (!user) return
    get('/api/alerts/count/').then(d => setCount(d.count)).catch(() => {})
  }, [user])

  // On mount, on navigation, and on demand after an action that could change
  // it. No polling timer: every state change that affects the count is
  // something this client initiated. See doc 07 §6.
  useEffect(() => { refresh() }, [refresh, pathname])
  useEffect(() => {
    const h = () => refresh()
    window.addEventListener('billing:invoices-changed', h)
    return () => window.removeEventListener('billing:invoices-changed', h)
  }, [refresh])

  return count
}

// Fired after issue / pay / void / due-date change / dismiss.
export const notifyInvoicesChanged = () =>
  window.dispatchEvent(new Event('billing:invoices-changed'))
```

---

## 7. `lib/money.js`

```js
/**
 * FORMATTING ONLY. Amounts arrive from the API as strings and are displayed
 * as strings. Nothing in this client adds, subtracts or compares two money
 * values — every total shown comes from the server.
 *
 * A Number(amount) anywhere in this codebase is a bug. See doc 07 §3.
 */
const FMT = new Intl.NumberFormat('en-GB', { style: 'currency', currency: 'GBP' })

export function formatMoney(value) {
  if (value == null) return '—'
  const n = Number(value)                 // display only, never stored back
  return Number.isFinite(n) ? FMT.format(n) : String(value)
}
```

The one `Number()` in the codebase, confined to the formatter, with the reason next to it.

---

## 8. `App.jsx` — the route table

```jsx
import { Navigate, Route, Routes } from 'react-router-dom'
import AppShell from './components/AppShell'
import { useAuth } from './auth/AuthContext'
/* pages … */

function RequireAuth({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <FullPageSpinner />
  return user ? children : <Navigate to="/login" replace />
}

function RequireAdmin({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <FullPageSpinner />
  if (!user) return <Navigate to="/login" replace />
  return user.role === 'billing_admin' ? children : <Navigate to="/" replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth><AppShell /></RequireAuth>}>
        <Route index                        element={<DashboardPage />} />
        <Route path="subscriptions"         element={<SubscriptionsPage />} />
        <Route path="subscriptions/:id"     element={<SubscriptionDetailPage />} />
        <Route path="invoices"              element={<InvoicesPage />} />
        <Route path="invoices/:id"          element={<InvoiceDetailPage />} />
        <Route path="alerts"                element={<AlertsPage />} />
        <Route path="bulk-generate"
               element={<RequireAdmin><BulkGeneratePage /></RequireAdmin>} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
```

`RequireAdmin` on `bulk-generate` is again cosmetic — the endpoint is `IsBillingAdmin` regardless.
It exists so a manager who types the URL gets redirected instead of a broken page.

---

## 9. `components/DataTable.jsx` — the shared shape

```jsx
/**
 * columns: [{ key, header, render?, sortable?, align? }]
 * Handles the four states every list must handle (doc 07 §7) in one place,
 * so no page can forget one.
 */
export default function DataTable({
  columns, rows, loading, error, empty, onRetry, sort, onSort, rowKey = r => r.id,
}) {
  if (loading) return <SkeletonRows cols={columns.length} />
  if (error)   return <ErrorBanner error={error} onRetry={onRetry} />
  if (!rows?.length) return <EmptyState {...empty} />

  return (
    <table className="data-table">
      <thead><tr>{columns.map(c => (
        <th key={c.key} data-align={c.align}>
          {c.sortable
            ? <button className="th-sort" onClick={() => onSort(c.key)}>
                {c.header}{sort === c.key ? ' ▲' : sort === `-${c.key}` ? ' ▼' : ''}
              </button>
            : c.header}
        </th>))}
      </tr></thead>
      <tbody>{rows.map(r => (
        <tr key={rowKey(r)}>{columns.map(c => (
          <td key={c.key} data-align={c.align}>{c.render ? c.render(r) : r[c.key]}</td>
        ))}</tr>))}
      </tbody>
    </table>
  )
}
```

Loading, error and empty are handled *inside* `DataTable` rather than by each page. Doc 07 §7 lists
those states as the thing that gets skipped under time pressure; putting them in the shared
component means they cannot be.

---

## 10. `theme.css` — the tokens

```css
:root {
  --bg: #f7f8fa;  --surface: #fff;  --border: #e3e6ea;
  --text: #1a1d21; --muted: #6b7280;
  --accent: #2f5fd0; --accent-weak: #eaf0fd;

  --draft:  #6b7280;  --draft-bg:  #f3f4f6;
  --issued: #1f6feb;  --issued-bg: #e8f0fe;
  --paid:   #167a3c;  --paid-bg:   #e6f4ec;
  --void:   #9ca3af;  --void-bg:   #f3f4f6;
  --overdue:#b42318;  --overdue-bg:#fdecea;

  --space-1: 4px; --space-2: 8px; --space-3: 16px; --space-4: 24px; --space-5: 40px;
  --radius: 8px;
  --font: system-ui, -apple-system, 'Segoe UI', sans-serif;
  --mono: ui-monospace, 'SF Mono', Menlo, monospace;
}
body { margin: 0; background: var(--bg); color: var(--text); font-family: var(--font); }
/* Money and dates in tabular figures so columns line up. */
.num { font-variant-numeric: tabular-nums; text-align: right; }
```

One status colour per lifecycle state, used by `StatusPill` and by the dashboard's by-status
breakdown, so the same status is the same colour everywhere in the app.
