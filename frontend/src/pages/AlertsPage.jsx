import { Link } from 'react-router-dom'
import { useApi, useAction } from '../hooks/useApi'
import { useAuth } from '../auth/AuthContext'
import { invoicesApi } from '../api/resources'
import { notifyInvoicesChanged } from '../hooks/useAlertCount'
import { DataTable, ErrorBanner, Money } from '../components/common'
import { formatDate, overdueLabel } from '../lib/dates'

export default function AlertsPage() {
  const { isAdmin } = useAuth()
  const { data, loading, error, slow, refetch } = useApi('/api/alerts/')
  const { run, pending, error: actionError, clearError } = useAction()

  function dismiss(invoiceId) {
    run(() => invoicesApi.dismissAlert(invoiceId))
      .then(() => { refetch(); notifyInvoicesChanged() })
      .catch(() => {})
  }

  const columns = [
    {
      key: 'customer_name', header: 'Customer',
      render: (r) => (
        <>
          <Link to={`/invoices/${r.invoice_id}`}>{r.customer_name}</Link>
          <div className="subtle">{r.billing_email}</div>
        </>
      ),
    },
    { key: 'owner_email', header: 'Owner', render: (r) => <span className="subtle">{r.owner_email}</span> },
    { key: 'amount', header: 'Amount', align: 'right', render: (r) => <Money value={r.amount} /> },
    { key: 'due_date', header: 'Due', render: (r) => formatDate(r.due_date) },
    {
      key: 'days_overdue', header: 'Overdue by',
      render: (r) => <span className="pill pill-overdue">{overdueLabel(r.days_overdue)}</span>,
    },
    {
      key: 'actions', header: '', align: 'right',
      render: (r) => r.dismissible
        ? <button onClick={() => dismiss(r.invoice_id)} disabled={pending}>Dismiss</button>
        : null,
    },
  ]

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Overdue alerts</h1>
          <p className="subtle">
            Issued invoices past their due date and still unpaid.
            {isAdmin
              ? ' Dismissed alerts return if the due date changes and passes again while the invoice is unpaid.'
              : ' Only a billing admin can dismiss an alert.'}
          </p>
        </div>
      </div>

      <ErrorBanner error={actionError} onDismiss={clearError} />

      <div className="card" style={{ padding: 0 }}>
        <DataTable
          columns={columns} rows={data?.results} loading={loading} error={error}
          slow={slow} onRetry={refetch}
          rowKey={(r) => r.invoice_id}
          empty={{
            title: 'Nothing overdue',
            hint: 'Every issued invoice is either within its due date or already paid.',
          }}
        />
      </div>
    </>
  )
}
