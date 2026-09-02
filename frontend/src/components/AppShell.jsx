import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { useAlertCount } from '../hooks/useAlertCount'
import { canBulkGenerate } from '../lib/permissions'

export default function AppShell() {
  const { user, logout } = useAuth()
  const alertCount = useAlertCount()

  return (
    <>
      <nav className="nav">
        <span className="brand">Billing</span>
        <NavLink to="/" end>Dashboard</NavLink>
        <NavLink to="/subscriptions">Subscriptions</NavLink>
        <NavLink to="/invoices">Invoices</NavLink>
        <NavLink to="/alerts">
          Alerts{alertCount > 0 && <span className="badge">{alertCount}</span>}
        </NavLink>
        {/* Cosmetic: the endpoint is billing-admin-only regardless. */}
        {canBulkGenerate(user) && <NavLink to="/bulk-generate">Bulk</NavLink>}
        <span className="spacer" />
        <span className="subtle">
          {user?.email} · {user?.role === 'billing_admin' ? 'Billing admin' : 'Account manager'}
        </span>
        <button onClick={logout}>Sign out</button>
      </nav>
      <main className="page"><Outlet /></main>
    </>
  )
}
