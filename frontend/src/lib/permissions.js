/**
 * COSMETIC ONLY.
 *
 * Every rule below is enforced on the server and tested there. These exist so
 * the UI does not render controls that are guaranteed to 403. Deleting this
 * file would change nothing about what a user can actually do.
 *
 * Do not add a rule here that the server does not also enforce.
 */
export const isAdmin = (u) => u?.role === 'billing_admin'

export const canIssue = (u, i) => isAdmin(u) && i.status === 'draft'
export const canPay = (u, i) => isAdmin(u) && i.status === 'issued'
export const canVoid = (u, i) => isAdmin(u) && ['draft', 'issued'].includes(i.status)
export const canCredit = (u, i) => isAdmin(u) && i.status === 'paid'
export const canEditFields = (i) => i.status === 'draft'
export const canEditDueDate = (i) => ['draft', 'issued'].includes(i.status)
export const canArchive = isAdmin
export const canManageCollaborators = isAdmin
export const canBulkGenerate = isAdmin
export const canDismissAlert = isAdmin

/** Why a control is disabled — rendered as a title attribute. */
export function whyDisabled(user, invoice, action) {
  if (!isAdmin(user) && ['issue', 'pay', 'void', 'credit'].includes(action)) {
    return 'Only a billing admin can do this.'
  }
  if (invoice.status === 'void') return 'This invoice has been voided.'
  if (action === 'void' && invoice.status === 'paid') {
    return 'A paid invoice cannot be voided. Issue a credit note instead.'
  }
  if (action === 'credit' && invoice.status !== 'paid') {
    return 'Credit notes can only be issued against paid invoices.'
  }
  if (action === 'issue' && invoice.status !== 'draft') {
    return 'Only a draft invoice can be issued.'
  }
  if (action === 'pay' && invoice.status !== 'issued') {
    return 'An invoice must be issued before it can be marked paid.'
  }
  return ''
}
