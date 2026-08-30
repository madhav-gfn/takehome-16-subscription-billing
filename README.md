# Assignment 16 — Subscription Billing

## The scenario

Picture a small software company selling subscriptions to a couple hundred business customers, each
on one of a handful of plans billed monthly or annually. Right now billing runs out of a spreadsheet:
someone works out by hand which customers are due to be billed this period, types up an invoice in a
document, and emails it out, hoping they remembered to update the row before moving to the next
customer.

The result is predictable. A customer who cancelled last month gets invoiced anyway because nobody
updated the spreadsheet in time. An invoice goes out with the wrong amount, someone "fixes" it by
editing that same row and re-sending it, and afterward nobody can say which version the customer
actually paid against. Finance cannot say how much revenue is actually outstanding right now without
opening the spreadsheet and adding up unpaid rows by hand.

They want one system: billing admins keep the subscription list current and step in for anything
that needs a judgment call, invoices for the current period generate themselves instead of being
typed out one by one, and a paid invoice is never quietly edited after the fact — a correction leaves
its own trail instead. Anyone should be able to tell what is overdue and what is still owed without
opening a spreadsheet. That is the system you are building.

## What it must do

Everything below is required. Several of the ten spell out exact rules — what happens on an illegal
move, what a bulk action must report back, when a dismissed alert is allowed to reappear — and those
specifics are the actual ask, not just the bold headline in front of them.

1. **Accounts and roles.** People sign in with an email and password, and there are at least two
roles — a billing admin role and an account manager role. Billing admins create, edit and archive any
subscription, and can issue, mark as paid, void or credit-note any invoice. Account managers create
subscriptions and edit ones they own or collaborate on, and can create invoices for them, but cannot
issue, mark an invoice as paid, void or credit-note an invoice, archive a subscription, or act on a
subscription they do not own or collaborate on. The difference must be enforced on the server, not
just hidden in the interface.

2. **Subscriptions.** Billing admins and account managers create subscriptions with a customer name,
a billing email, a plan name, a billing cycle, a price as an exact decimal amount, a start date, and
an owning account manager, and can edit them later. Subscriptions can be archived and restored.
Archiving a subscription stops future invoices from being generated for it without destroying its
invoice history.

3. **Invoices.** Every invoice belongs to exactly one subscription and carries a billing period's
start and end date, an amount owed as an exact decimal amount, and a due date. A billing admin or the
subscription's owning account manager can create an invoice for it, edit it freely while it is
*Draft*, and change its due date until it is *Paid*. Opening a subscription shows all of its invoices.

4. **An invoice lifecycle with rules.** An invoice moves through *Draft → Issued → Paid*. Issuing an
invoice locks its billing period and amount; an Issued invoice not yet Paid by its due date counts as
overdue, though it stays Issued until it is actually paid or voided. An invoice can be marked *Void*,
with a required reason, only while it is Draft or Issued — never once it is Paid. A Paid invoice is
immutable: no field on it can be changed, and the only way to correct one is to issue a credit note
against it, recording a reason and an exact decimal amount, which stands as its own record rather
than altering the original invoice. Any other move must be rejected by the server with a message
explaining why.

5. **Collaborators.** A subscription has one owning account manager, but any number of other account
managers can be added to it as collaborators who can also edit it and create invoices for it, and an
account manager can collaborate on any number of subscriptions. Only a billing admin can add or
remove a collaborator. Every account manager can see one list of every subscription where they are
the owner or a collaborator.

6. **Finding invoices.** One list shows invoices across every subscription the viewer can see, with a
text search over customer name and billing email, filters for status, overdue and owning account
manager, sorting by due date, amount or status, and pagination showing the total number of matches.
All of this must happen on the server — do not load every invoice into the browser and filter there.

7. **Generating invoices in bulk.** A billing admin can bulk-generate the current period's invoices
across every active subscription in a single action. The result is a per-subscription report:
generated where no invoice exists yet for that period, skipped where one already does, or failed
with a reason. Separately, export receivables — every Issued or overdue invoice with its
subscription, amount and due date — as a CSV file.

8. **A dashboard.** A landing view shows headline numbers — invoices issued this month, revenue
collected this month, receivables, and invoices overdue. It also breaks invoices down by status and
by plan, and charts revenue collected per week over the last eight weeks.

9. **History you cannot rewrite.** Every invoice has a timeline showing when it was created, every
status change with the old and new status and who made it, any credit notes issued against it with
their reason and amount, and any notes left on it. Nothing in this timeline can be edited or deleted
after the fact, including by billing admins.

10. **Overdue invoice alerts.** An invoice that counts as overdue appears in an alerts area, with a
count badge visible in the navigation. A billing admin can dismiss the alert. If the due date later
changes and then passes again while the invoice is still not Paid, the alert returns.

## Stretch ideas (optional)

None of these are required, and none substitute for a goal above. If you finish all ten with time
left over, pick whichever of these sounds most useful and build it:

- Usage-based add-on charges on top of a plan's base price.
- Proration when a subscription changes plan mid-cycle.
- A customer-facing self-service billing portal.
- Reminder emails for invoices approaching or past their due date.
- Multi-currency billing.
- Tax calculation by jurisdiction.
- Automatic discounts for annual versus monthly billing.
- Revenue reporting spread evenly across each invoice's billing period.
- A trial period before a subscription's first invoice.


---

## What we are assessing

A working application is table stakes. Almost every serious candidate will produce something that runs, has a login, and roughly does what was asked. That's the floor, not the differentiator.

What actually separates submissions is the record of thinking behind the app: the decisions you made and why, the trade-offs you weighed, what you built first and what you deliberately left out, and whether you can explain any part of your own system when asked. We are hiring for judgement. The app is the evidence for that judgement, not the deliverable in itself.

We also read the code itself for structure and readability, which counts for a small share of the overall score.

## Time budget

Budget about 12 hours total, spent roughly 2 hours a day across a week.

This is not a race. We are not timing you against other candidates, and submitting early scores nothing extra. Twelve hours is a size guide so you know how much to attempt — pace yourself, stop when you're tired, and spend some of that time thinking and documenting, not only typing code.

## Pick any stack you like

Use any language, any framework, any UI library, any ORM, and any database access approach you want. We have no house stack, and no stack scores better than another — this round is not a test of whether you know particular tools.

Use whatever you are fastest and most confident in. Time spent learning something new to impress us is time not spent on the ten goals above, and it will show.

## Using AI is allowed and encouraged

Use AI tools however you want — to scaffold code, debug a stuck problem, write tests, draft documentation, or anything else that helps you move faster. A few things to know about how we treat it:

- We do not penalise AI use, and we make no attempt to detect it.
- We care about whether you understood, directed and verified the output — not about who or what produced the first draft of it.
- `docs/ai-prompts.md` must contain the prompts you actually used, including the ones that produced bad output and what you changed afterwards. If you used no AI at all, say so here and describe how you worked instead — that is assessed the same way.
- Submitting generated code you cannot explain is the single most common way candidates fail this round.

You are accountable for everything in your submission. If a reviewer points at a piece of code and asks why it's there, or why it works the way it does, "the AI wrote it" is not an answer.

## Use git properly

Publish to a public GitHub repository, and commit incrementally as the work actually happens — after each meaningful step, not in one pass at the end.

A repository whose entire history is a single "initial commit" containing a finished app scores zero on git history, and it colours how we read everything else in your submission, however good the app itself is. Your history is how we see the order you built in, where you got stuck, and how the design changed along the way. If it isn't there, we can't assess it, and we won't assume the best.

## What you must commit

Alongside your code, commit these five files under `docs/`. Your zip includes a stub for each with the questions it needs to answer — fill them in as you go, not from memory at the end.

| File | What it must answer |
|------|----------------------|
| `docs/architecture.md` | What the moving pieces are, how they talk to each other, where each one runs, the request path for one representative user action end to end, and what you decided not to build. |
| `docs/schema.md` | Every table's columns and types, which relationships are one-to-many versus many-to-many, which constraints live in the database versus the application, what you deliberately denormalised, and what would break first at 100x the data. |
| `docs/plan.md` | How you split the work into sessions, what order you built in and why, what you estimated versus what it actually took, and what you cut when you ran short. |
| `docs/decisions.md` | At least five real decisions — what you chose, what you rejected, and why — including at least one you later reversed. |
| `docs/ai-prompts.md` | The prompts you actually used, in order, grouped by what you were trying to do, including at least one that produced something wrong and what you did about it. |

## Host it for free

Deploy the whole thing somewhere reachable by URL, using free tiers only.

One combination that works, if you would rather not decide:

- **Database** — a managed service such as Supabase.
- **Server-side code** — Render.
- **Browser-side code** — Vercel.

Deploy in that order: create the database first, give the server its connection details as environment variables, then point the browser-side part at the server's public URL.

This is one option, not a requirement. Any free host is equally acceptable — everything on a single provider, one virtual machine, a container platform, a static host with serverless functions. The choice earns and loses nothing.

Requirements:

- A working live URL.
- Seeded with enough demo data to show the system doing something, not an empty shell.
- Demo credentials for every role recorded in `SUBMISSION.md`.
- Connection strings, keys and passwords kept in environment variables, never in the repository.
- Free tiers often sleep when idle and can take a minute or more to wake. Note it in `SUBMISSION.md` if yours does, so a slow first load is not read as a broken deployment.
- If you cannot get it hosted, submit anyway and record in `SUBMISSION.md` what you tried and where it broke.

## How to submit

Send us:

- The URL of your public GitHub repository.
- The URL of your live, deployed application.
- Your completed `SUBMISSION.md`, committed to the repository.

That's the whole submission. Nothing else to prepare, no separate form.

## What happens next

If your submission clears the bar, we'll set up a short call. We will ask about specific decisions we can see in your repository and its history — why you modelled something a particular way, what a certain commit was fixing, what you'd change if you kept going.

We're telling you this now because it should change how carefully you document as you go. Write `docs/decisions.md` for a version of yourself who has to explain it three weeks from now.

## Scope

The 10 goals stated in this brief are the cutoff. Meet all 10, solidly, and you have a complete submission.

Stretch ideas are optional. They exist for candidates who finish the 10 with time left and want to keep building — they are never required, and they do not make up for a goal you didn't hit. Doing 8 goals well beats doing 10 goals badly. If time is short, finish fewer goals properly rather than leaving all ten half-done.
