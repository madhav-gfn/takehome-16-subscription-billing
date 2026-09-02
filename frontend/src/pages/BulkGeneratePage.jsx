import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAction } from '../hooks/useApi'
import { invoicesApi } from '../api/resources'
import { download } from '../api/client'
import { notifyInvoicesChanged } from '../hooks/useAlertCount'
import { ErrorBanner, Modal, Money } from '../components/common'
import { formatPeriod } from '../lib/dates'

const OUTCOME_STYLE = {
  generated: { background: 'var(--paid-bg)', color: 'var(--paid)' },
  skipped: { background: 'var(--draft-bg)', color: 'var(--draft)' },
  failed: { background: 'var(--overdue-bg)', color: 'var(--overdue)' },
}

export default function BulkGeneratePage() {
  const { run, pending, error, clearError } = useAction()
  const [report, setReport] = useState(null)
  const [confirming, setConfirming] = useState(false)

  function generate() {
    setConfirming(false)
    run(() => invoicesApi.bulkGenerate())
      .then((r) => { setReport(r); notifyInvoicesChanged() })
      .catch(() => {})
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Bulk generate</h1>
          <p className="subtle">
            Creates the current period's invoice for every active subscription
            that does not already have one. Archived subscriptions are skipped.
          </p>
        </div>
        <div className="row">
          <button
            onClick={() => download(
              '/api/exports/receivables.csv',
              `receivables-${new Date().toISOString().slice(0, 10)}.csv`,
            )}
          >Download receivables CSV</button>
          <button className="primary" onClick={() => setConfirming(true)} disabled={pending}>
            {pending ? 'Generating…' : 'Generate current period'}
          </button>
        </div>
      </div>

      <ErrorBanner error={error} onDismiss={clearError} />

      {!report && !pending && (
        <div className="card">
          <p className="subtle" style={{ margin: 0 }}>
            Run it to see a per-subscription report. Running twice is safe — the
            second run reports everything as already invoiced.
          </p>
        </div>
      )}

      {report && (
        <>
          <div className="banner banner-info">
            <span>
              <strong>{report.summary.generated} generated</strong> ·{' '}
              {report.summary.skipped} skipped · {report.summary.failed} failed
              {' '}(of {report.summary.total} active subscriptions, as of {report.as_of})
            </span>
          </div>

          <div className="card" style={{ padding: 0 }}>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Customer</th><th>Outcome</th><th>Period</th>
                    <th data-align="right">Amount</th><th>Detail</th><th />
                  </tr>
                </thead>
                <tbody>
                  {report.results.map((r) => (
                    <tr key={r.subscription_id}>
                      <td>
                        <Link to={`/subscriptions/${r.subscription_id}`}>{r.customer_name}</Link>
                      </td>
                      <td>
                        <span className="pill" style={OUTCOME_STYLE[r.outcome]}>{r.outcome}</span>
                      </td>
                      <td>
                        {r.period_start ? formatPeriod(r.period_start, r.period_end)
                          : <span className="subtle">—</span>}
                      </td>
                      <td data-align="right">
                        {r.amount ? <Money value={r.amount} /> : <span className="subtle">—</span>}
                      </td>
                      <td className="subtle" style={{ whiteSpace: 'normal' }}>{r.reason ?? ''}</td>
                      <td data-align="right">
                        {r.invoice_id && <Link to={`/invoices/${r.invoice_id}`}>View</Link>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {confirming && (
        <Modal
          title="Generate this period's invoices?" onClose={() => setConfirming(false)}
          actions={
            <>
              <button onClick={() => setConfirming(false)}>Cancel</button>
              <button className="primary" onClick={generate}>Generate</button>
            </>
          }
        >
          <p>
            Every active subscription will be checked. Where an invoice already
            exists for the current period it is skipped, so running this twice
            is safe.
          </p>
        </Modal>
      )}
    </>
  )
}
