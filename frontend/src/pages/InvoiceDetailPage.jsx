import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useApi, useAction } from '../hooks/useApi'
import { useAuth } from '../auth/AuthContext'
import { invoicesApi } from '../api/resources'
import { notifyInvoicesChanged } from '../hooks/useAlertCount'
import {
  ErrorBanner, Modal, Money, OverdueTag, Spinner, StatusPill,
} from '../components/common'
import { formatDate, formatDateTime, formatPeriod } from '../lib/dates'
import {
  canCredit, canEditDueDate, canEditFields, canIssue, canPay, canVoid, whyDisabled,
} from '../lib/permissions'

export default function InvoiceDetailPage() {
  const { id } = useParams()
  const { user } = useAuth()
  const { data: inv, loading, error, slow, refetch } = useApi(`/api/invoices/${id}/`)
  const { run, pending, error: actionError, clearError } = useAction()
  const [dialog, setDialog] = useState(null) // 'void' | 'credit' | 'note' | 'edit'

  if (loading) return <Spinner slow={slow} />
  if (error) return <ErrorBanner error={error} onRetry={refetch} />
  if (!inv) return null

  const act = (fn) => run(fn)
    .then(() => { refetch(); notifyInvoicesChanged(); setDialog(null) })
    .catch(() => {})

  return (
    <>
      <div className="page-head">
        <div>
          <Link to="/invoices" className="subtle">← All invoices</Link>
          <h1 style={{ marginTop: 6 }}>
            <Link to={`/subscriptions/${inv.subscription_id}`}>{inv.customer_name}</Link>
          </h1>
          <p className="row">
            <StatusPill status={inv.status} />
            <OverdueTag days={inv.days_overdue} />
            <span className="subtle">{inv.plan_name} · {inv.billing_email}</span>
          </p>
        </div>
        <div className="stat" style={{ minWidth: 200 }}>
          <div className="label">Amount</div>
          <div className="value"><Money value={inv.amount} /></div>
          {Number(inv.credited_total) > 0 && (
            <div className="sub">
              less <Money value={inv.credited_total} /> credited ·
              net <Money value={inv.net_amount} />
            </div>
          )}
        </div>
      </div>

      <ErrorBanner error={actionError} onDismiss={clearError} />

      <div className="card">
        <div className="row" style={{ gap: 32 }}>
          <div>
            <div className="subtle">Billing period</div>
            <div>{formatPeriod(inv.period_start, inv.period_end)}</div>
          </div>
          <div>
            <div className="subtle">Due date</div>
            <div className="row">
              {formatDate(inv.due_date)}
              {canEditDueDate(inv) && (
                <button className="link" onClick={() => setDialog('edit')}>Change</button>
              )}
            </div>
          </div>
          {inv.issued_at && (
            <div><div className="subtle">Issued</div><div>{formatDateTime(inv.issued_at)}</div></div>
          )}
          {inv.paid_at && (
            <div><div className="subtle">Paid</div><div>{formatDateTime(inv.paid_at)}</div></div>
          )}
        </div>

        {inv.status === 'void' && (
          <div className="banner banner-error" style={{ marginTop: 16, marginBottom: 0 }}>
            <span><strong>Voided:</strong> {inv.void_reason}</span>
          </div>
        )}
        {inv.status === 'issued' && (
          <p className="subtle" style={{ marginTop: 12, marginBottom: 0 }}>
            This invoice is issued, so its period and amount are locked. The due
            date can still be changed until it is paid.
          </p>
        )}
        {inv.status === 'paid' && (
          <p className="subtle" style={{ marginTop: 12, marginBottom: 0 }}>
            Paid invoices are immutable. Corrections are made by issuing a
            credit note, which stands as its own record.
          </p>
        )}
      </div>

      {/* Disabled buttons carry a title explaining why. The user learns the
          rule from the UI; the server enforces it regardless. */}
      <div className="card">
        <h2>Actions</h2>
        <div className="row">
          <ActionButton
            label="Issue" primary
            enabled={canIssue(user, inv)} why={whyDisabled(user, inv, 'issue')}
            onClick={() => act(() => invoicesApi.issue(id))} pending={pending}
          />
          <ActionButton
            label="Mark paid" primary
            enabled={canPay(user, inv)} why={whyDisabled(user, inv, 'pay')}
            onClick={() => act(() => invoicesApi.pay(id))} pending={pending}
          />
          <ActionButton
            label="Void…" danger
            enabled={canVoid(user, inv)} why={whyDisabled(user, inv, 'void')}
            onClick={() => setDialog('void')} pending={pending}
          />
          <ActionButton
            label="Credit note…"
            enabled={canCredit(user, inv)} why={whyDisabled(user, inv, 'credit')}
            onClick={() => setDialog('credit')} pending={pending}
          />
          {canEditFields(inv) && (
            <button onClick={() => setDialog('edit')}>Edit invoice…</button>
          )}
        </div>
      </div>

      {inv.credit_notes?.length > 0 && (
        <div className="card">
          <h2>Credit notes</h2>
          <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            {inv.credit_notes.map((cn) => (
              <li key={cn.id} style={{ padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
                <strong><Money value={cn.amount} /></strong> — {cn.reason}
                <div className="subtle">
                  {cn.created_by?.email ?? 'unknown'} · {formatDateTime(cn.created_at)}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="card">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <h2 style={{ margin: 0 }}>Timeline</h2>
          <button onClick={() => setDialog('note')}>Add note</button>
        </div>
        <p className="subtle" style={{ marginTop: 8 }}>
          Append-only. Nothing here can be edited or deleted, including by a
          billing admin.
        </p>
        <Timeline events={inv.timeline} />
      </div>

      {dialog === 'void' && (
        <ReasonDialog
          title="Void this invoice"
          hint="A reason is required and becomes part of the permanent record."
          confirmLabel="Void invoice" pending={pending}
          onClose={() => setDialog(null)}
          onConfirm={(reason) => act(() => invoicesApi.void(id, reason))}
        />
      )}
      {dialog === 'credit' && (
        <CreditNoteDialog
          invoice={inv} pending={pending}
          onClose={() => setDialog(null)}
          onConfirm={(amount, reason) => act(() => invoicesApi.creditNote(id, amount, reason))}
        />
      )}
      {dialog === 'note' && (
        <ReasonDialog
          title="Add a note" hint="Notes are part of the timeline and cannot be edited later."
          confirmLabel="Add note" pending={pending}
          onClose={() => setDialog(null)}
          onConfirm={(text) => act(() => invoicesApi.addNote(id, text))}
        />
      )}
      {dialog === 'edit' && (
        <EditInvoiceDialog
          invoice={inv} pending={pending}
          onClose={() => setDialog(null)}
          onConfirm={(body) => act(() => invoicesApi.update(id, body))}
        />
      )}
    </>
  )
}

function ActionButton({ label, enabled, why, onClick, pending, primary, danger }) {
  return (
    <button
      className={primary ? 'primary' : danger ? 'danger' : ''}
      disabled={!enabled || pending} title={enabled ? '' : why}
      onClick={onClick}
    >{label}</button>
  )
}

const EVENT_LABEL = {
  created: 'Invoice created',
  status_changed: null, // rendered from old/new
  voided: 'Voided',
  field_changed: 'Fields changed',
  credit_note_issued: 'Credit note issued',
  note_added: 'Note',
}

function Timeline({ events }) {
  if (!events?.length) return <p className="subtle">No events yet.</p>
  return (
    <ul className="timeline">
      {events.map((e) => (
        <li key={e.id}>
          <span className="when">{formatDateTime(e.created_at)}</span>
          <span className="what">
            {e.event_type === 'status_changed' ? (
              <>
                Status <StatusPill status={e.old_status} /> →{' '}
                <StatusPill status={e.new_status} />
              </>
            ) : (
              <strong>{EVENT_LABEL[e.event_type] ?? e.event_type}</strong>
            )}
            <EventDetails event={e} />
          </span>
          <span className="who">{e.actor?.email ?? '(deleted user)'}</span>
        </li>
      ))}
    </ul>
  )
}

function EventDetails({ event }) {
  const d = event.details ?? {}
  if (event.event_type === 'note_added' && d.text) return <div>{d.text}</div>
  if (event.event_type === 'voided' && d.reason) {
    return <div className="subtle">Reason: {d.reason}</div>
  }
  if (event.event_type === 'credit_note_issued') {
    return <div className="subtle">{d.amount} — {d.reason}</div>
  }
  if (event.event_type === 'created') {
    return (
      <div className="subtle">
        {d.amount}{d.source === 'bulk' ? ' · generated in bulk' : ' · created manually'}
      </div>
    )
  }
  if (event.event_type === 'field_changed' && d.changes) {
    return (
      <div className="subtle">
        {Object.entries(d.changes).map(([field, c]) => (
          <div key={field}>{field}: {c.from} → {c.to}</div>
        ))}
      </div>
    )
  }
  return null
}

function ReasonDialog({ title, hint, confirmLabel, onClose, onConfirm, pending }) {
  const [text, setText] = useState('')
  return (
    <Modal
      title={title} onClose={onClose}
      actions={
        <>
          <button onClick={onClose}>Cancel</button>
          <button
            className="primary" disabled={!text.trim() || pending}
            onClick={() => onConfirm(text)}
          >{pending ? 'Working…' : confirmLabel}</button>
        </>
      }
    >
      <p className="subtle">{hint}</p>
      <textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} autoFocus />
    </Modal>
  )
}

function CreditNoteDialog({ invoice, onClose, onConfirm, pending }) {
  const [amount, setAmount] = useState('')
  const [reason, setReason] = useState('')
  return (
    <Modal
      title="Issue a credit note" onClose={onClose}
      actions={
        <>
          <button onClick={onClose}>Cancel</button>
          <button
            className="primary" disabled={!amount || !reason.trim() || pending}
            onClick={() => onConfirm(amount, reason)}
          >{pending ? 'Working…' : 'Issue credit note'}</button>
        </>
      }
    >
      <p className="subtle">
        The invoice itself is not altered. The credit note stands as its own
        record against it.
      </p>
      <div className="field">
        <label>Amount (invoice is <Money value={invoice.amount} />, already credited{' '}
          <Money value={invoice.credited_total} />)</label>
        <input type="number" step="0.01" min="0.01" value={amount}
          onChange={(e) => setAmount(e.target.value)} autoFocus />
      </div>
      <div className="field">
        <label>Reason</label>
        <textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} />
      </div>
    </Modal>
  )
}

function EditInvoiceDialog({ invoice, onClose, onConfirm, pending }) {
  const draft = invoice.status === 'draft'
  const [form, setForm] = useState({
    period_start: invoice.period_start,
    period_end: invoice.period_end,
    amount: invoice.amount,
    due_date: invoice.due_date,
  })
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  function submit() {
    // An issued invoice accepts only its due date. The server enforces this
    // too; sending only what is allowed just saves a round trip.
    onConfirm(draft ? form : { due_date: form.due_date })
  }

  return (
    <Modal
      title={draft ? 'Edit draft invoice' : 'Change due date'} onClose={onClose}
      actions={
        <>
          <button onClick={onClose}>Cancel</button>
          <button className="primary" disabled={pending} onClick={submit}>
            {pending ? 'Saving…' : 'Save'}
          </button>
        </>
      }
    >
      {!draft && (
        <p className="subtle">
          This invoice is issued, so its period and amount are locked. Only the
          due date can change.
        </p>
      )}
      <div className="form-grid">
        {draft && (
          <>
            <div className="field"><label>Period start</label>
              <input type="date" value={form.period_start} onChange={set('period_start')} /></div>
            <div className="field"><label>Period end</label>
              <input type="date" value={form.period_end} onChange={set('period_end')} /></div>
            <div className="field"><label>Amount</label>
              <input type="number" step="0.01" value={form.amount} onChange={set('amount')} /></div>
          </>
        )}
        <div className="field"><label>Due date</label>
          <input type="date" value={form.due_date} onChange={set('due_date')} /></div>
      </div>
    </Modal>
  )
}
