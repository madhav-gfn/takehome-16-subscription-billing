import { Navigate, Route, Routes } from 'react-router-dom'
import AppShell from './components/AppShell'
import { Spinner } from './components/common'
import { useAuth } from './auth/AuthContext'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import SubscriptionsPage from './pages/SubscriptionsPage'
import SubscriptionDetailPage from './pages/SubscriptionDetailPage'
import InvoicesPage from './pages/InvoicesPage'
import InvoiceDetailPage from './pages/InvoiceDetailPage'
import AlertsPage from './pages/AlertsPage'
import BulkGeneratePage from './pages/BulkGeneratePage'

function RequireAuth({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <Spinner />
  return user ? children : <Navigate to="/login" replace />
}

function RequireAdmin({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <Spinner />
  if (!user) return <Navigate to="/login" replace />
  // Cosmetic guard: it stops an account manager who types the URL from seeing
  // a broken page. The endpoint enforces the same rule.
  return user.role === 'billing_admin' ? children : <Navigate to="/" replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth><AppShell /></RequireAuth>}>
        <Route index element={<DashboardPage />} />
        <Route path="subscriptions" element={<SubscriptionsPage />} />
        <Route path="subscriptions/:id" element={<SubscriptionDetailPage />} />
        <Route path="invoices" element={<InvoicesPage />} />
        <Route path="invoices/:id" element={<InvoiceDetailPage />} />
        <Route path="alerts" element={<AlertsPage />} />
        <Route
          path="bulk-generate"
          element={<RequireAdmin><BulkGeneratePage /></RequireAdmin>}
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
