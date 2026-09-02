import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useApi, useAction } from '../hooks/useApi'
import { useAuth } from '../auth/AuthContext'
import { invoicesApi, subscriptionsApi } from '../api/resources'
import { notifyInvoicesChanged } from '../hooks/useAlertCount'
import {
  DataTable, ErrorBanner, Modal, Money, OverdueTag, Spinner, StatusPill,
} from '../components/common'
import { formatDate, formatPeriod } from '../lib/dates'
import { canArchive, canManageCollaborators } from '../lib/permissions'

export default function SubscriptionDetailPage() {
  const { id } = useParams()
  const { user, isAdmin } = useAuth()
  const { data: sub, loading, error, slow, refetch } = useApi(`/api/subscriptions/${id}/`)
  const { data: managers } = useApi('/api/auth/users/?role=account_manager')
  const { run, pending, error: actionError, clearError } = useAction()
  const [editing, setEditing] = useState(false)
  const [invoicing, setInvoicing] = useState(false)

  if (loading) return <Spinner slow={slow} />
  if (error) return <ErrorBanner error={error} onRetry={refetch} />
  if (!sub) return null

  const act = (fn) => run(fn).then(refetch).catch(() => {})

  const invoiceColumns = [
    {
      key: 'period', header: 'Period',
      render: (r) => <Link to={`/invoices/${r.id}`}>{formatPeriod(r.period_start, r.period_end)}</Link>,
    },
    { key: 'amount', header: 'Amount', align: 'right', render: (r) => <Money value={r.amount} /> },
    { key: 'due_date', header: 'Due', render: (r) => formatDate(r.due_date) },
    {
      key: 'status', header: 'Status',
      render: (r) => (
        <span className="row">
          <StatusPill status={r.status} />
          <OverdueTag days={r.days_overdue} />
        </span>
      ),
    },
    {
      key: 'credited', header: 'Credited', align: 'right',
      render: (r) => Number(r.credited_total) > 0
        ? <Money value={r.credited_total} /> : <span className="subtle">—</span>,
    },
  ]

  return (
    <>
      <div className="page-head">
        <div>
          <Link to="/subscriptions" className="subtle">← All subscriptions</Link>
          <h1 style={{ marginTop: 6 }}>
            {sub.customer_name}
            {sub.is_archived && <span className="pill pill-void" style={{ marginLeft: 10 }}>archived</span>}
          </h1>
          <p className="subtle">{sub.billing_email}</p>
        </div>
        <div className="row">
          {!sub.is_archived && <button onClick={() => setEditing(true)}>Edit</button>}
          {canArchive(user) && (
            sub.is_archived
              ? <button onClick={() => act(() => subscriptionsApi.restore(id))} disabled={pending}>Restore</button>
              : <button className="danger" onClick={() => act(() => subscriptionsApi.archive(id))} disabled={pending}>Archive</button>
          )}
        </div>
      </div>

      <ErrorBanner error={actionError} onDismiss={clearError} />

      {sub.is_archived && (
        <div className="banner banner-info">
          <span>
            Archived subscriptions generate no new invoices. Existing invoices
            stay visible and can still be paid. Restore it to make changes.
          </span>
        </div>
      )}

      <div className="two-col">
        <div className="card">
          <h2>Details</h2>
          <dl style={{ margin: 0, display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '8px 16px' }}>
            <dt className="subtle">Plan</dt><dd style={{ margin: 0 }}>{sub.plan_name}</dd>
            <dt className="subtle">Cycle</dt><dd style={{ margin: 0 }}>{sub.billing_cycle}</dd>
            <dt className="subtle">Price</dt><dd style={{ margin: 0 }}><Money value={sub.price} /></dd>
            <dt className="subtle">Started</dt><dd style={{ margin: 0 }}>{formatDate(sub.start_date)}</dd>
            <dt className="subtle">Owner</dt><dd style={{ margin: 0 }}>{sub.owner?.email}</dd>
          </dl>
        </div>

        <div className="card">
          <h2>Collaborators</h2>
          {sub.collaborators?.length ? (
            <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
              {sub.collaborators.map((c) => (
                <li key={c.id} className="row" style={{ justifyContent: 'space-between', padding: '4px 0' }}>
                  <span>{c.email}</span>
                  {canManageCollaborators(user) && (
                    <button
                      className="link"
                      onClick={() => act(() => subscriptionsApi.removeCollaborator(id, c.id))}
                    >Remove</button>
                  )}
                </li>
              ))}
            </ul>
          ) : <p className="subtle">No collaborators.</p>}

          {canManageCollaborators(user) ? (
            <AddCollaborator
              managers={managers} subscription={sub}
              onAdd={(userId) => act(() => subscriptionsApi.addCollaborator(id, userId))}
            />
          ) : (
            <p className="subtle" style={{ marginTop: 12 }}>
              Only a billing admin can add or remove collaborators.
            </p>
          )}
        </div>
      </div>

      <div className="card" style={{ padding: 0 }}>
        <div className="row" style={{ justifyContent: 'space-between', padding: 16 }}>
          <h2 style={{ margin: 0 }}>Invoices</h2>
          {!sub.is_archived && (
            <button className="primary" onClick={() => setInvoicing(true)}>New invoice</button>
          )}
        </div>
        <DataTable
          columns={invoiceColumns} rows={sub.invoices}
          empty={{
            title: 'No invoices yet',
            hint: sub.is_archived
              ? 'This subscription was archived before any invoice was raised.'
              : 'Create one manually, or run bulk generation for the current period.',
          }}
        />
      </div>

      {editing && (
        <EditSubscription
          subscription={sub} managers={managers} isAdmin={isAdmin}
          onClose={() => setEditing(false)}
          onSaved={() => { setEditing(false); refetch() }}
        />
      )}
      {invoicing && (
        <NewInvoice
          subscription={sub}
          onClose={() => setInvoicing(false)}
          onSaved={() => { setInvoicing(false); refetch(); notifyInvoicesChanged() }}
        />
      )}
    </>
  )
}

function AddCollaborator({ managers, subscription, onAdd }) {
  const [selected, setSelected] = useState('')
  const taken = new Set([
    subscription.owner?.id,
    ...(subscription.collaborators ?? []).map((c) => c.id),
  ])
  const available = (managers ?? []).filter((m) => !taken.has(m.id))

  return (
    <div className="row" style={{ marginTop: 12 }}>
      <select value={selected} onChange={(e) => setSelected(e.target.value)}>
        <option value="">Add an account manager…</option>
        {available.map((m) => <option key={m.id} value={m.id}>{m.email}</option>)}
      </select>
      <button
        disabled={!selected}
        onClick={() => { onAdd(selected); setSelected('') }}
      >Add</button>
    </div>
  )
}

function EditSubscription({ subscription, managers, isAdmin, onClose, onSaved }) {
  const { run, pending, error } = useAction()
  const [form, setForm] = useState({
    customer_name: subscription.customer_name,
    billing_email: subscription.billing_email,
    plan_name: subscription.plan_name,
    billing_cycle: subscription.billing_cycle,
    price: subscription.price,
    start_date: subscription.start_date,
    owner_id: subscription.owner?.id ?? '',
  })
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  return (
    <Modal
      title="Edit subscription" onClose={onClose}
      actions={
        <>
          <button onClick={onClose}>Cancel</button>
          <button
            className="primary" disabled={pending}
            onClick={() => run(async () => {
              await subscriptionsApi.update(subscription.id, form)
              onSaved()
            }).catch(() => {})}
          >{pending ? 'Saving…' : 'Save'}</button>
        </>
      }
    >
      <ErrorBanner error={error} />
      <div className="form-grid">
        <div className="field"><label>Customer name</label>
          <input value={form.customer_name} onChange={set('customer_name')} /></div>
        <div className="field"><label>Billing email</label>
          <input type="email" value={form.billing_email} onChange={set('billing_email')} /></div>
        <div className="field"><label>Plan name</label>
          <input value={form.plan_name} onChange={set('plan_name')} /></div>
        <div className="field"><label>Billing cycle</label>
          <select value={form.billing_cycle} onChange={set('billing_cycle')}>
            <option value="monthly">Monthly</option><option value="annual">Annual</option>
          </select></div>
        <div className="field"><label>Price</label>
          <input type="number" step="0.01" value={form.price} onChange={set('price')} /></div>
        <div className="field"><label>Start date</label>
          <input type="date" value={form.start_date} onChange={set('start_date')} /></div>
      </div>
      <div className="field">
        <label>Owning account manager</label>
        <select value={form.owner_id} onChange={set('owner_id')} disabled={!isAdmin}>
          {managers?.map((m) => <option key={m.id} value={m.id}>{m.email}</option>)}
        </select>
        {!isAdmin && <p className="subtle">Only a billing admin can change the owner.</p>}
      </div>
      <p className="subtle">
        Changing the start date or cycle does not re-base existing invoices —
        they keep the periods they were raised for.
      </p>
    </Modal>
  )
}

function NewInvoice({ subscription, onClose, onSaved }) {
  const { run, pending, error } = useAction()
  const [form, setForm] = useState({
    period_start: '', period_end: '', amount: subscription.price, due_date: '',
  })
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  return (
    <Modal
      title={`New invoice — ${subscription.customer_name}`} onClose={onClose}
      actions={
        <>
          <button onClick={onClose}>Cancel</button>
          <button
            className="primary" disabled={pending}
            onClick={() => run(async () => {
              await invoicesApi.create({ subscription_id: subscription.id, ...form })
              onSaved()
            }).catch(() => {})}
          >{pending ? 'Creating…' : 'Create draft'}</button>
        </>
      }
    >
      <ErrorBanner error={error} />
      <div className="form-grid">
        <div className="field"><label>Period start</label>
          <input type="date" value={form.period_start} onChange={set('period_start')} /></div>
        <div className="field"><label>Period end</label>
          <input type="date" value={form.period_end} onChange={set('period_end')} /></div>
        <div className="field"><label>Amount</label>
          <input type="number" step="0.01" value={form.amount} onChange={set('amount')} /></div>
        <div className="field"><label>Due date</label>
          <input type="date" value={form.due_date} onChange={set('due_date')} /></div>
      </div>
      <p className="subtle">Invoices are always created as drafts.</p>
    </Modal>
  )
}
