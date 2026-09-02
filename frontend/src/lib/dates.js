export function formatDate(value) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value)
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
}

export function formatDateTime(value) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value)
  return d.toLocaleString('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

export function formatPeriod(start, end) {
  return `${formatDate(start)} – ${formatDate(end)}`
}

/** days_overdue always comes from the server — this only phrases it. */
export function overdueLabel(days) {
  if (!days) return ''
  return days === 1 ? '1 day overdue' : `${days} days overdue`
}
