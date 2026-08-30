# AI prompts

The prompts you actually used, in the order you used them, grouped by what you were trying to achieve. For each significant one: what you asked, what you got back, and what you had to correct.

Include at least one prompt that produced something wrong, and what you did about it.

If you did not use AI at all, say so here, and describe your process instead.








# 1.
## <What you were trying to achieve>
I was trying to gather knowledge about similar things that exist to this and the technologies or frameworks that can be used in this

### Prompt
```
The scenario
Picture a small software company selling subscriptions to a couple hundred business customers, each on one of a handful of plans billed monthly or annually. Right now billing runs out of a spreadsheet: someone works out by hand which customers are due to be billed this period, types up an invoice in a document, and emails it out, hoping they remembered to update the row before moving to the next customer.
The result is predictable. A customer who cancelled last month gets invoiced anyway because nobody updated the spreadsheet in time. An invoice goes out with the wrong amount, someone "fixes" it by editing that same row and re-sending it, and afterward nobody can say which version the customer actually paid against. Finance cannot say how much revenue is actually outstanding right now without opening the spreadsheet and adding up unpaid rows by hand.
They want one system: billing admins keep the subscription list current and step in for anything that needs a judgment call, invoices for the current period generate themselves instead of being typed out one by one, and a paid invoice is never quietly edited after the fact — a correction leaves its own trail instead. Anyone should be able to tell what is overdue and what is still owed without opening a spreadsheet. That is the system you are building.
What it must do
Everything below is required. Several of the ten spell out exact rules — what happens on an illegal move, what a bulk action must report back, when a dismissed alert is allowed to reappear — and those specifics are the actual ask, not just the bold headline in front of them.
Accounts and roles. People sign in with an email and password, and there are at least two roles — a billing admin role and an account manager role. Billing admins create, edit and archive any subscription, and can issue, mark as paid, void or credit-note any invoice. Account managers create subscriptions and edit ones they own or collaborate on, and can create invoices for them, but cannot issue, mark an invoice as paid, void or credit-note an invoice, archive a subscription, or act on a subscription they do not own or collaborate on. The difference must be enforced on the server, not just hidden in the interface.
Subscriptions. Billing admins and account managers create subscriptions with a customer name, a billing email, a plan name, a billing cycle, a price as an exact decimal amount, a start date, and an owning account manager, and can edit them later. Subscriptions can be archived and restored. Archiving a subscription stops future invoices from being generated for it without destroying its invoice history.
Invoices. Every invoice belongs to exactly one subscription and carries a billing period's start and end date, an amount owed as an exact decimal amount, and a due date. A billing admin or the subscription's owning account manager can create an invoice for it, edit it freely while it is Draft, and change its due date until it is Paid. Opening a subscription shows all of its invoices.
An invoice lifecycle with rules. An invoice moves through Draft → Issued → Paid. Issuing an invoice locks its billing period and amount; an Issued invoice not yet Paid by its due date counts as overdue, though it stays Issued until it is actually paid or voided. An invoice can be marked Void, with a required reason, only while it is Draft or Issued — never once it is Paid. A Paid invoice is immutable: no field on it can be changed, and the only way to correct one is to issue a credit note against it, recording a reason and an exact decimal amount, which stands as its own record rather than altering the original invoice. Any other move must be rejected by the server with a message explaining why.
Collaborators. A subscription has one owning account manager, but any number of other account managers can be added to it as collaborators who can also edit it and create invoices for it, and an account manager can collaborate on any number of subscriptions. Only a billing admin can add or remove a collaborator. Every account manager can see one list of every subscription where they are the owner or a collaborator.
Finding invoices. One list shows invoices across every subscription the viewer can see, with a text search over customer name and billing email, filters for status, overdue and owning account manager, sorting by due date, amount or status, and pagination showing the total number of matches. All of this must happen on the server — do not load every invoice into the browser and filter there.
Generating invoices in bulk. A billing admin can bulk-generate the current period's invoices across every active subscription in a single action. The result is a per-subscription report: generated where no invoice exists yet for that period, skipped where one already does, or failed with a reason. Separately, export receivables — every Issued or overdue invoice with its subscription, amount and due date — as a CSV file.
A dashboard. A landing view shows headline numbers — invoices issued this month, revenue collected this month, receivables, and invoices overdue. It also breaks invoices down by status and by plan, and charts revenue collected per week over the last eight weeks.
History you cannot rewrite. Every invoice has a timeline showing when it was created, every status change with the old and new status and who made it, any credit notes issued against it with their reason and amount, and any notes left on it. Nothing in this timeline can be edited or deleted after the fact, including by billing admins.
Overdue invoice alerts. An invoice that counts as overdue appears in an alerts area, with a count badge visible in the navigation. A billing admin can dismiss the alert. If the due date later changes and then passes again while the invoice is still not Paid, the alert returns.
Stretch ideas (optional)
None of these are required, and none substitute for a goal above. If you finish all ten with time left over, pick whichever of these sounds most useful and build it:
Usage-based add-on charges on top of a plan's base price.
Proration when a subscription changes plan mid-cycle.
A customer-facing self-service billing portal.
Reminder emails for invoices approaching or past their due date.
Multi-currency billing.
Tax calculation by jurisdiction.
Automatic discounts for annual versus monthly billing.
Revenue reporting spread evenly across each invoice's billing period.
A trial period before a subscription's first invoice.


this is a breif about a project i am building can you do a deep research on the related projects that are there, the things that can be used to build it and give me a comprehensive report
```

### What you got
this file
docs\Billing System Development Research.pdf

### What you corrected
Its majorly a reference Knowledge document, so required no edits


# 2.
## <What you were trying to achieve>
I want to connect the backend to frontend, just so i have a rough idea

### Prompt
```
We have a basic frontend working and basic backend working I want to connect both of them, just show the health endpoint of backend visible on frontend 
```

### What you got
![alt text](image.png) and commit 1b8b5b079f105ffe4936a44c2d6a89dab6d07549

### What you corrected
Nothing



# 3.
## <What you were trying to achieve>
I want to setup env config

### Prompt
```
Set up env config and resolution in backend

```

### What you got
working env and commit  42c873692ddb8f715f0a3598cba1afc33c5fbf41

### What you corrected
Nothing


# 4.
## <What you were trying to achieve>
implement all the authentication and authorization 

### Prompt
```
Set up env config and resolution in backend

```

### What you got


### What you corrected
Nothing