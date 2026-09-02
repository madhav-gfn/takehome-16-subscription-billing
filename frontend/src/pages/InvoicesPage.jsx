import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useApi } from '../hooks/useApi'
import { useQueryFilters } from '../hooks/useQueryFilters'
import { useDebounced } from '../hooks/useDebounced'
import { useAuth } from '../auth/AuthContext'
import { download } from '../api/client'
import {
  DataTable, Money, OverdueTag, Pagination, StatusPill,
} from '../components/common'
import { formatDate, formatPeriod } from '../lib/dates'

const STATUSES = ['draft', 'issued', 'paid', 'void']

export default function InvoicesPage() {
  const { isAdmin } = useAuth()
  const { filters, setFilter, clear, queryString } = useQueryFilters()
  const [search, setSearch] = useState(filters.search ?? '')
  const debounced = useDebounced(search)

  useEffect(() => {
    if ((filters.search ?? '') !== debounced) setFilter('search', debounced)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced])

  // Every filter is a URL param and the whole query string goes straight to the
  // server. Nothing is filtered in the browser.
  const { data, loading, error, slow, refetch } = useApi(`/api/invoices/${queryString}`)
  const { data: managers } = useApi('/api/auth/users/?role=account_manager')

  const selectedStatuses = Array.isArray(filters.status)
    ? filters.status : filters.status ? [filters.status] : []

  function toggleStatus(s) {
    const next = selectedStatuses.includes(s)
      ? selectedStatuses.filter((x) => x !== s)
      : [...selectedStatuses, s]
    setFilter('status', next)
  }

  function toggleSort(key) {
    const current = filters.ordering ?? '-due_date'
    setFilter('ordering', current === key ? `-${key}` : key)
  }

  const columns = [
    {
      key: 'customer_name', header: 'Customer', render: (r) => (
        <>
          <Link to={`/invoices/${r.id}`}>{r.customer_name}</Link>
          <div className="subtle">{r.billing_email}</div>
        </>
      ),
    },
    { key: 'plan_name', header: 'Plan' },
    { key: 'owner_email', header: 'Owner', render: (r) => <span className="subtle">{r.owner_email}</span> },
    { key: 'period', header: 'Period', render: (r) => formatPeriod(r.period_start, r.period_end) },
    { key: 'amount', header: 'Amount', align: 'right', sortable: true, render: (r) => <Money value={r.amount} /> },
    { key: 'due_date', header: 'Due', sortable: true, render: (r) => formatDate(r.due_date) },
    {
      key: 'status', header: 'Status', sortable: true, render: (r) => (
        <span className="row">
          <StatusPill status={r.status} />
          {/* is_overdue and days_overdue are computed in SQL and sent down —
              the client never re-derives them. */}
          <OverdueTag days={r.days_overdue} />
        </span>
      ),
    },
  ]

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Invoices</h1>
          <p className="subtle">
            {isAdmin ? 'Every invoice in the system.' : 'Invoices across your subscriptions.'}
          </p>
        </div>
        <button
          onClick={() => download(
            `/api/exports/receivables.csv${queryString}`,
            `receivables-${new Date().toISOString().slice(0, 10)}.csv`,
          )}
        >Export receivables CSV</button>
      </div>

      <div className="filter-bar">
        <input
          placeholder="Search customer name or billing email…"
          value={search} onChange={(e) => setSearch(e.target.value)}
          style={{ minWidth: 260 }}
        />
        {STATUSES.map((s) => (
          <label key={s} className="checkbox">
            <input
              type="checkbox" checked={selectedStatuses.includes(s)}
              onChange={() => toggleStatus(s)}
            />
            {s}
          </label>
        ))}
        <label className="checkbox">
          <input
            type="checkbox" checked={filters.overdue === 'true'}
            onChange={(e) => setFilter('overdue', e.target.checked ? 'true' : '')}
          />
          overdue only
        </label>
        <select value={filters.owner ?? ''} onChange={(e) => setFilter('owner', e.target.value)}>
          <option value="">Any owner</option>
          {managers?.map((m) => <option key={m.id} value={m.id}>{m.email}</option>)}
        </select>
        <select value={filters.ordering ?? '-due_date'} onChange={(e) => setFilter('ordering', e.target.value)}>
          <option value="-due_date">Due date, latest first</option>
          <option value="due_date">Due date, earliest first</option>
          <option value="-amount">Amount, high to low</option>
          <option value="amount">Amount, low to high</option>
          <option value="status">Status (lifecycle order)</option>
        </select>
        <button className="link" onClick={clear}>Clear filters</button>
      </div>

      <div className="card" style={{ padding: 0 }}>
        <DataTable
          columns={columns} rows={data?.results} loading={loading} error={error}
          slow={slow} onRetry={refetch}
          sort={filters.ordering ?? '-due_date'} onSort={toggleSort}
          empty={{
            title: 'No invoices match these filters',
            hint: 'Try clearing the search, or widening the status selection.',
          }}
        />
      </div>

      <Pagination
        count={data?.count} page={filters.page ?? 1}
        onPage={(p) => setFilter('page', p)}
      />
    </>
  )
}
