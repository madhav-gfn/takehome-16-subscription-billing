/**
 * FORMATTING ONLY.
 *
 * Amounts arrive from the API as strings and are displayed as strings. Nothing
 * in this client adds, subtracts or compares two money values — every total
 * shown comes from the server. A Number(amount) outside this file is a bug.
 */
const FMT = new Intl.NumberFormat('en-GB', { style: 'currency', currency: 'GBP' })

export function formatMoney(value) {
  if (value == null || value === '') return '—'
  const n = Number(value) // display only, never written back
  return Number.isFinite(n) ? FMT.format(n) : String(value)
}
