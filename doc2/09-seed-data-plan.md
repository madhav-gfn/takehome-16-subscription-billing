# 09 — Seed Data Plan

The brief: *"Seeded with enough demo data to show the system doing something, not an empty shell."*

## 1. Design principle

The dataset is designed backwards from the screens. For each screen I ask: what must exist for this
to be worth looking at? Then the seed guarantees exactly that. A reviewer who logs in as any of the
three demo users should land on a dashboard with every tile non-zero and find something interesting
on every page — without hunting.

Every date is computed **relative to today** at seed time, never hardcoded. A seed with fixed 2025
dates looks broken three months later: nothing is overdue, the 8-week chart is empty, and the
dashboard reads all zeros. Relative dates mean the demo is still correct whenever the reviewer opens
it, which for a link that sits in an inbox for a week is not a small detail.

## 2. Users

Unchanged from `seed_users`, and unchanged in `SUBMISSION.md`:

| Role | Email | Password |
|---|---|---|
| billing_admin | `admin@example.com` | `admin123` |
| account_manager | `manager1@example.com` | `manager123` |
| account_manager | `manager2@example.com` | `manager123` |

A third AM, `manager3@example.com` / `manager123`, is added and **not** published in
`SUBMISSION.md`. Its purpose is to own subscriptions that manager1 and manager2 can see nothing of —
so that logging in as manager1 visibly does *not* show everything, which is the observable proof of
Goal 1. Without a third book of business, an AM's view and a BA's view look identical on a small
dataset and the whole authorization story is invisible to a reviewer clicking around.

## 3. Subscriptions — 14 total

| # | Customer | Plan | Cycle | Price | Started | Owner | Collaborators | Purpose |
|---|---|---|---|---|---|---|---|---|
| 1 | Northwind Traders | Pro | monthly | 199.00 | 8 mo ago | m1 | m2 | Long history; the "open this one" subscription |
| 2 | Contoso Ltd | Enterprise | monthly | 899.00 | 6 mo ago | m1 | m2, m3 | Multiple collaborators (Goal 5) |
| 3 | Fabrikam Inc | Starter | monthly | 49.00 | 5 mo ago | m1 | — | No collaborators |
| 4 | Adventure Works | Pro | annual | 1990.00 | 14 mo ago | m1 | — | Annual cycle, two periods |
| 5 | Tailwind Traders | Starter | monthly | 49.00 | 4 mo ago | m2 | m1 | Reciprocal collaboration |
| 6 | Woodgrove Bank | Enterprise | annual | 8990.00 | 10 mo ago | m2 | — | Largest amount — dominates receivables |
| 7 | Litware Inc | Pro | monthly | 199.00 | 3 mo ago | m2 | — | |
| 8 | Proseware | Starter | monthly | 49.00 | 7 mo ago | m2 | m1 | **Archived** 1 mo ago (Goal 2) |
| 9 | Wide World Importers | Pro | monthly | 199.00 | 9 mo ago | m1 | — | Chronic late payer — overdue source |
| 10 | Lucerne Publishing | Starter | monthly | 49.00 | 2 mo ago | m1 | m2 | |
| 11 | Alpine Ski House | Enterprise | monthly | 899.00 | 5 mo ago | m3 | — | **Invisible to m1/m2** |
| 12 | Relecloud | Pro | monthly | 199.00 | 4 mo ago | m3 | — | **Invisible to m1/m2** |
| 13 | Trey Research | Starter | monthly | 49.00 | 6 mo ago | m3 | m1 | m3-owned but m1 collaborates — the interesting case |
| 14 | Blue Yonder Airlines | Pro | monthly | 199.00 | **starts in 1 mo** | m2 | — | Future start → bulk-generate reports `skipped` (A-13) |

Three plans (Starter / Pro / Enterprise) so the Goal 8 by-plan breakdown has three meaningful bars,
not one. Both cycles present so the period arithmetic is visibly exercised on real data.

Row 13 is worth the trouble: manager1 sees it as a collaborator but does not own it, so the
subscription list, the invoice list and the dashboard all have to get the owner-vs-collaborator
distinction right for it to look correct.

## 4. Invoices — roughly 60

Generated per subscription by walking its periods from `start_date` to today, then assigning a
status by a fixed rule (not randomly — a seed that produces a different dataset each run makes bug
reports irreproducible):

| Period age | Status | Notes |
|---|---|---|
| Older than 3 periods | `paid` | `paid_at` set a few days after the due date |
| 2–3 periods ago | `paid` | |
| Previous period | `issued` | Some overdue by design (below) |
| Current period | `draft` or `issued` | Mixed, so both Goal 6 filters have hits |

Deliberate exceptions, each existing to make one screen show something:

| Condition | Where | Why |
|---|---|---|
| 5 **overdue** invoices (issued, due 5–40 days ago) | subs 9, 6, 2, 7, 3 | Goal 10's list and badge; the dashboard's overdue tile |
| 2 of those already **dismissed** | subs 9, 2 | Proves dismissal works, and leaves 3 visible in the badge |
| 1 dismissed invoice whose **due date was later extended and has passed again** | sub 9's older invoice | The A-10 re-arming case, visible live in the demo |
| 2 **void** invoices with reasons | subs 1, 5 | Goal 4's void path; one is "Duplicate of INV-…", one "Billed at the wrong plan tier" |
| 1 void whose period was **regenerated** | sub 5 | A-14 — shows a void plus a live invoice for the same period |
| 2 **credit notes** against paid invoices | subs 2, 6 | Goal 4's correction path; £150 "Overbilled two seats", £400 "Service credit for downtime" |
| 3 **draft** invoices | subs 3, 10, 12 | So bulk-generate has something to skip and the draft filter has hits |
| 1 subscription with **no invoices at all** | sub 14 | Empty-state rendering on the detail page |

Amounts equal the subscription price. No random variation — a demo where the same plan bills
different amounts invites a question about a bug that does not exist.

## 5. Timeline events

Every invoice gets a realistic event trail, written **through the service layer** rather than by
bulk-inserting event rows. That is slower to seed but it means the seed exercises the same code path
as the app, so a broken transition shows up at seed time rather than in the demo.

Extra flavour on a handful of invoices so the Goal 9 timeline is worth opening:
- Two notes on Northwind's most recent paid invoice: *"Customer asked for a PO number on the next
  one"* and *"Confirmed payment by BACS, ref 88213"*.
- One due-date extension on a Wide World Importers invoice: *"Extended after the customer's AP
  contact went on leave"* — as a note next to the `field_changed` event.
- A void with its reason, followed by a regenerated invoice for the same period, on Tailwind.

Northwind's latest paid invoice is the reference specimen: created → issued → due date changed →
paid → credit note → two notes. Six event types on one screen. It is the invoice to open first in a
demo, and `SUBMISSION.md`'s notes section names it by customer.

## 6. Command

```bash
python main.py seed_demo            # idempotent, skips what exists
python main.py seed_demo --flush    # wipe billing tables and users, then reseed
```

Implementation notes that matter:

1. **Wrapped in `rls_session("billing_admin", admin.id)`** (D-06). Without it, `FORCE ROW LEVEL
   SECURITY` silently rejects every insert and the command reports success having written nothing.
   This is the single most likely thing to go wrong in this file.
2. `--flush` deletes in FK order: events → credit notes → dismissals → invoices → collaborators →
   subscriptions → users. It refuses to run when `DEBUG=False` unless `--force` is passed, so a
   fat-fingered flush cannot wipe the deployed demo.
3. Deterministic: `random.seed(42)` for the small amount of jitter in `paid_at` offsets, so two runs
   produce identical data.
4. Prints a summary — counts per table, the demo credentials, and the number of currently overdue
   and currently alerting invoices — so a post-deploy run confirms the demo is in the intended state
   without opening a browser.

## 7. Post-deploy verification

Run against the live URL after seeding. If any of these is false, the demo is not ready:

- [ ] Login works for all three published credentials.
- [ ] Dashboard as admin: every headline tile non-zero; 8-week chart has at least 4 non-zero weeks.
- [ ] Dashboard as manager1: numbers are *smaller* than admin's — the visible proof of scoping.
- [ ] Subscriptions as manager1: 8 rows (own + collaborated), and Alpine Ski House / Relecloud are
      **absent**.
- [ ] Invoices as admin: >50 results, pagination visible, count correct.
- [ ] Search "north" matches Northwind; search "@contoso" matches by email.
- [ ] Alerts badge shows 3; the list has 3 rows; dismiss works and the badge drops to 2.
- [ ] Northwind's latest paid invoice shows all six event types.
- [ ] Void and Edit are disabled on that paid invoice, with explanatory tooltips.
- [ ] Bulk-generate as admin returns a mix of generated, skipped and skipped-not-started.
- [ ] Receivables CSV downloads and opens cleanly in a spreadsheet.
