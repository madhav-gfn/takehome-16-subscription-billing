import { Link } from 'react-router-dom'
import {
  Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { useApi } from '../hooks/useApi'
import { useAuth } from '../auth/AuthContext'
import { ErrorBanner, Money, Spinner, StatusPill } from '../components/common'
import { formatMoney } from '../lib/money'
import { formatDate } from '../lib/dates'

export default function DashboardPage() {
  const { isAdmin } = useAuth()
  const { data, loading, error, slow, refetch } = useApi('/api/dashboard/')

  if (loading) return <Spinner slow={slow} />
  if (error) return <ErrorBanner error={error} onRetry={refetch} />
  if (!data) return null

  const h = data.headline

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Dashboard</h1>
          <p className="subtle">
            {isAdmin
              ? 'Across every subscription.'
              : 'Across the subscriptions you own or collaborate on.'}
          </p>
        </div>
      </div>

      {/* Every tile links somewhere — a dashboard whose numbers are not
          clickable makes the reader retype what they just read. */}
      <div className="stat-grid">
        <Link to="/invoices?status=issued" className="stat" style={{ color: 'inherit' }}>
          <div className="label">Issued this month</div>
          <div className="value">{h.invoices_issued_this_month}</div>
        </Link>
        <div className="stat">
          <div className="label">Collected this month</div>
          <div className="value">{formatMoney(h.revenue_collected_this_month)}</div>
          {/* Credits are shown beside revenue, never netted into it. */}
          <div className="sub">{formatMoney(h.credits_issued_this_month)} credited</div>
        </div>
        <Link to="/invoices?status=issued" className="stat" style={{ color: 'inherit' }}>
          <div className="label">Receivables</div>
          <div className="value">{formatMoney(h.receivables)}</div>
          <div className="sub">every issued invoice, overdue included</div>
        </Link>
        <Link to="/alerts" className="stat" style={{ color: 'inherit' }}>
          <div className="label">Overdue</div>
          <div className="value" style={{ color: 'var(--overdue)' }}>{h.invoices_overdue}</div>
          <div className="sub">{formatMoney(h.overdue_amount)} outstanding</div>
        </Link>
      </div>

      <div className="two-col">
        <div className="card">
          <h2>By status</h2>
          <table className="data-table">
            <tbody>
              {data.by_status.map((row) => (
                <tr key={row.status}>
                  <td>
                    <Link to={`/invoices?status=${row.status}`}>
                      <StatusPill status={row.status} />
                    </Link>
                  </td>
                  <td data-align="right">{row.count}</td>
                  <td data-align="right"><Money value={row.amount} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="card">
          <h2>By plan</h2>
          {data.by_plan.length ? (
            <table className="data-table">
              <tbody>
                {data.by_plan.map((row) => (
                  <tr key={row.plan_name}>
                    <td>
                      <Link to={`/subscriptions?plan=${encodeURIComponent(row.plan_name)}`}>
                        {row.plan_name}
                      </Link>
                    </td>
                    <td data-align="right">{row.count}</td>
                    <td data-align="right"><Money value={row.amount} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <p className="subtle">No invoices yet.</p>}
        </div>
      </div>

      <div className="card">
        <h2>Revenue collected, last 8 weeks</h2>
        <div style={{ width: '100%', height: 260 }}>
          <ResponsiveContainer>
            {/* The backend emits all 8 buckets including zeros, so the chart
                cannot silently rescale its own axis and mislead. */}
            <BarChart data={data.revenue_by_week.map((w) => ({
              week: formatDate(w.week_start).slice(0, 6),
              amount: Number(w.amount),
            }))}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis dataKey="week" tick={{ fontSize: 12, fill: 'var(--muted)' }} />
              <YAxis
                tick={{ fontSize: 12, fill: 'var(--muted)' }}
                tickFormatter={(v) => formatMoney(v).replace(/\.00$/, '')}
                width={70}
              />
              <Tooltip formatter={(v) => formatMoney(v)} />
              <Bar dataKey="amount" fill="var(--accent)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </>
  )
}
