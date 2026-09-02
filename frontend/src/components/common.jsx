import { Link } from 'react-router-dom'
import { formatMoney } from '../lib/money'
import { overdueLabel } from '../lib/dates'

export function Money({ value, className = '' }) {
  return <span className={`num ${className}`}>{formatMoney(value)}</span>
}

export function StatusPill({ status }) {
  return <span className={`pill pill-${status}`}>{status}</span>
}

export function OverdueTag({ days }) {
  if (!days) return null
  return <span className="pill pill-overdue">{overdueLabel(days)}</span>
}

export function ErrorBanner({ error, onRetry, onDismiss }) {
  if (!error) return null
  return (
    <div className="banner banner-error">
      {/* The server's message, verbatim. */}
      <span>{error.message}</span>
      <span className="row">
        {onRetry && <button onClick={onRetry}>Retry</button>}
        {onDismiss && <button onClick={onDismiss}>Dismiss</button>}
      </span>
    </div>
  )
}

export function EmptyState({ title = 'Nothing here yet', hint, action }) {
  return (
    <div className="empty">
      <p style={{ fontWeight: 600, color: 'var(--text)' }}>{title}</p>
      {hint && <p>{hint}</p>}
      {action}
    </div>
  )
}

export function Spinner({ slow }) {
  return (
    <div className="empty">
      <p>Loading…</p>
      {slow && (
        <p className="subtle">
          Waking the backend — free hosting sleeps when idle. This can take up
          to a minute on the first request.
        </p>
      )}
    </div>
  )
}

export function SkeletonRows({ cols = 5, rows = 6 }) {
  return (
    <table className="data-table">
      <tbody>
        {Array.from({ length: rows }).map((_, r) => (
          <tr key={r}>
            {Array.from({ length: cols }).map((__, c) => (
              <td key={c}><div className="skeleton" /></td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

/**
 * Handles loading, error and empty in one place, so no page can forget one —
 * these are exactly the states that get skipped under time pressure.
 */
export function DataTable({
  columns, rows, loading, error, slow, empty, onRetry,
  sort, onSort, rowKey = (r) => r.id,
}) {
  if (loading) return <SkeletonRows cols={columns.length} />
  if (error) return <ErrorBanner error={error} onRetry={onRetry} />
  if (!rows?.length) return <EmptyState {...empty} />

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} data-align={c.align}>
                {c.sortable && onSort ? (
                  <button className="th-sort" onClick={() => onSort(c.key)}>
                    {c.header}
                    {sort === c.key ? ' ▲' : sort === `-${c.key}` ? ' ▼' : ''}
                  </button>
                ) : c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={rowKey(r)}>
              {columns.map((c) => (
                <td key={c.key} data-align={c.align}>
                  {c.render ? c.render(r) : r[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Pagination({ count, page, pageSize = 25, onPage }) {
  if (!count) return null
  const pages = Math.ceil(count / pageSize)
  const current = Number(page) || 1
  const from = (current - 1) * pageSize + 1
  const to = Math.min(current * pageSize, count)

  return (
    <div className="row" style={{ justifyContent: 'space-between', marginTop: 12 }}>
      {/* Goal 6 requires the total number of matches. */}
      <span className="subtle">Showing {from}–{to} of {count}</span>
      <span className="row">
        <button disabled={current <= 1} onClick={() => onPage(current - 1)}>‹ Previous</button>
        <span className="subtle">Page {current} of {pages}</span>
        <button disabled={current >= pages} onClick={() => onPage(current + 1)}>Next ›</button>
      </span>
    </div>
  )
}

export function Modal({ title, children, onClose, actions }) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>{title}</h2>
        {children}
        <div className="modal-actions">{actions}</div>
      </div>
    </div>
  )
}

export function SubscriptionLink({ id, children }) {
  return <Link to={`/subscriptions/${id}`}>{children}</Link>
}
