import { useCallback, useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { alertsApi } from '../api/resources'
import { useAuth } from '../auth/AuthContext'

/** Fired after any action that could change the overdue set. */
export function notifyInvoicesChanged() {
  window.dispatchEvent(new Event('billing:invoices-changed'))
}

export function useAlertCount() {
  const { user } = useAuth()
  const { pathname } = useLocation()
  const [count, setCount] = useState(0)

  const refresh = useCallback(() => {
    if (!user) return
    alertsApi.count().then((d) => setCount(d.count)).catch(() => {})
  }, [user])

  // On mount, on navigation, and on demand. No polling timer: every state
  // change that affects this count is something this client initiated.
  useEffect(() => { refresh() }, [refresh, pathname])
  useEffect(() => {
    const handler = () => refresh()
    window.addEventListener('billing:invoices-changed', handler)
    return () => window.removeEventListener('billing:invoices-changed', handler)
  }, [refresh])

  return count
}
