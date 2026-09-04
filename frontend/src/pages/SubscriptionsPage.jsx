import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useApi, useAction } from '../hooks/useApi'
import { useQueryFilters } from '../hooks/useQueryFilters'
import { useDebounced } from '../hooks/useDebounced'
import { useAuth } from '../auth/AuthContext'
import { subscriptionsApi } from '../api/resources'
import {
  DataTable, ErrorBanner, Modal, Money, Pagination,
} from '../components/common'
import { formatDate } from '../lib/dates'

export default function SubscriptionsPage() {
  const { user, isAdmin } = useAuth()
  const { filters, setFilter, queryString } = useQueryFilters()
  const [search, setSearch] = useState(filters.search ?? '')
  const debounced = useDebounced(search)
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    if ((filters.search ?? '') !== debounced) setFilter('search', debounced)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced])

  const { data, loading, error, slow, refetch } = useApi(`/api/subscriptions/${queryString}`)
  const { data: managers } = useApi('/api/auth/users/?role=account_manager')

  const columns = [
    {
      key: 'customer_name', header: 'Customer', sortable: true,
      render: (r) => (
        <>
          <Link to={`/subscriptions/${r.id}`}>{r.customer_name}</Link>
          {r.is_archived && <span className="pill pill-void" style={{ marginLeft: 8 }}>archived</span>}
          <div className="subtle">{r.billing_email}</div>
        </>
      ),
    },
    { key: 'plan_name', header: 'Plan' },
    { key: 'billing_cycle', header: 'Cycle' },
    { key: 'price', header: 'Price', align: 'right', sortable: true, render: (r) => <Money value={r.price} /> },
    { key: 'start_date', header: 'Started', sortable: true, render: (r) => formatDate(r.start_date) },
    { key: 'owner', header: 'Owner', render: (r) => r.owner?.email },
    {
      key: 'collaborators', header: 'Collaborators',
      render: (r) => r.collaborators?.length
        ? <span title={r.collaborators.map((c) => c.email).join(', ')}>{r.collaborators.length}</span>
        : <span className="subtle">—</span>,
    },
    {
      key: 'invoices', header: 'Invoices',
      render: (r) => r.invoice_summary
        ? <span className="subtle">
            {r.invoice_summary.total} total · {r.invoice_summary.issued} issued
          </span>
        : null,
    },
    {
      key: 'outstanding', header: 'Outstanding', align: 'right',
      render: (r) => r.invoice_summary ? <Money value={r.invoice_summary.outstanding} /> : null,
    },
  ]

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Subscriptions</h1>
          <p className="subtle">
            {isAdmin
              ? 'Every subscription in the system.'
              : 'Subscriptions you own or collaborate on.'}
          </p>
        </div>
        <button className="primary" onClick={() => setCreating(true)}>New subscription</button>
      </div>

      <div className="filter-bar">
        <input
          placeholder="Search customer or email…"
          value={search} onChange={(e) => setSearch(e.target.value)}
        />
        <select value={filters.archived ?? 'false'} onChange={(e) => setFilter('archived', e.target.value)}>
          <option value="false">Active only</option>
          <option value="true">Archived only</option>
          <option value="all">All</option>
        </select>
        <select value={filters.owner ?? ''} onChange={(e) => setFilter('owner', e.target.value)}>
          <option value="">Any owner</option>
          {managers?.map((m) => <option key={m.id} value={m.id}>{m.email}</option>)}
        </select>
        <select value={filters.ordering ?? ''} onChange={(e) => setFilter('ordering', e.target.value)}>
          <option value="">Newest first</option>
          <option value="customer_name">Customer A–Z</option>
          <option value="-price">Price, high to low</option>
          <option value="start_date">Oldest start date</option>
        </select>
      </div>

      <div className="card" style={{ padding: 0 }}>
        <DataTable
          columns={columns} rows={data?.results} loading={loading} error={error}
          slow={slow} onRetry={refetch}
          empty={{
            title: 'No subscriptions match these filters',
            hint: 'Try clearing the search or switching the archived filter.',
          }}
        />
      </div>

      <Pagination
        count={data?.count} page={filters.page ?? 1}
        onPage={(p) => setFilter('page', p)}
      />

      {creating && (
        <SubscriptionForm
          managers={managers} user={user} isAdmin={isAdmin}
          onClose={() => setCreating(false)}
          onSaved={() => { setCreating(false); refetch() }}
        />
      )}
    </>
  )
}

function SubscriptionForm({ managers, user, isAdmin, onClose, onSaved }) {
  const { run, pending, error } = useAction()
  const [form, setForm] = useState({
    customer_name: '', billing_email: '', plan_name: '',
    billing_cycle: 'monthly', price: '', start_date: '',
    owner_id: isAdmin ? '' : user.id,
  })

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  async function save() {
    await run(async () => {
      await subscriptionsApi.create(form)
      onSaved()
    }).catch(() => {})
  }

  return (
    <Modal
      title="New subscription" onClose={onClose}
      actions={
        <>
          <button onClick={onClose}>Cancel</button>
          <button className="primary" onClick={save} disabled={pending}>
            {pending ? 'Saving…' : 'Create'}
          </button>
        </>
      }
    >
      <ErrorBanner error={error} />
      <div className="form-grid">
        <div className="field">
          <label>Customer name</label>
          <input value={form.customer_name} onChange={set('customer_name')} />
        </div>
        <div className="field">
          <label>Billing email</label>
          <input type="email" value={form.billing_email} onChange={set('billing_email')} />
        </div>
        <div className="field">
          <label>Plan name</label>
          <input value={form.plan_name} onChange={set('plan_name')} list="plan-names" />
          <datalist id="plan-names">
            <option value="Starter" /><option value="Pro" /><option value="Enterprise" />
          </datalist>
        </div>
        <div className="field">
          <label>Billing cycle</label>
          <select value={form.billing_cycle} onChange={set('billing_cycle')}>
            <option value="monthly">Monthly</option>
            <option value="annual">Annual</option>
          </select>
        </div>
        <div className="field">
          <label>Price</label>
          <input type="number" step="0.01" min="0.01" value={form.price} onChange={set('price')} />
        </div>
        <div className="field">
          <label>Start date</label>
          <input type="date" value={form.start_date} onChange={set('start_date')} />
        </div>
      </div>
      <div className="field">
        <label>Owning account manager</label>
        {isAdmin ? (
          <select value={form.owner_id} onChange={set('owner_id')}>
            <option value="">Select an account manager…</option>
            {managers?.map((m) => <option key={m.id} value={m.id}>{m.email}</option>)}
          </select>
        ) : (
          // An account manager can only create subscriptions they own.
          <input value={user.email} disabled />
        )}
      </div>
    </Modal>
  )
}
