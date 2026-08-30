# Schema

## Current state

The project has not yet implemented the full billing schema, so this is a working design note rather than a final data model. The backend is currently ready for the next step: defining the real billing entities and migrations.

## Planned core tables

### Users

- `id` — primary key
- `email` — unique email address
- `password_hash` — hashed password
- `role` — billing admin or account manager
- `created_at` — timestamp
- `updated_at` — timestamp

### Subscriptions

- `id` — primary key
- `customer_name` — text
- `billing_email` — email
- `plan_name` — text
- `billing_cycle` — monthly or annual
- `price` — decimal amount
- `start_date` — date
- `owner_id` — foreign key to user
- `is_archived` — boolean
- `created_at` — timestamp
- `updated_at` — timestamp

### Subscription collaborators

- `id` — primary key
- `subscription_id` — foreign key to subscription
- `user_id` — foreign key to user
- `created_at` — timestamp

### Invoices

- `id` — primary key
- `subscription_id` — foreign key to subscription
- `billing_period_start` — date
- `billing_period_end` — date
- `amount` — decimal amount
- `due_date` — date
- `status` — draft, issued, paid, void
- `void_reason` — optional text
- `created_at` — timestamp
- `updated_at` — timestamp

### Credit notes

- `id` — primary key
- `invoice_id` — foreign key to invoice
- `reason` — text
- `amount` — decimal amount
- `created_at` — timestamp

### Invoice audit events

- `id` — primary key
- `invoice_id` — foreign key to invoice
- `event_type` — status change, note, credit note, creation, etc.
- `old_status` — nullable status
- `new_status` — nullable status
- `actor_id` — foreign key to user
- `details` — JSON/text for metadata
- `created_at` — timestamp

## Relationship plan

- One user can own many subscriptions.
- One user can collaborate on many subscriptions.
- One subscription can have many invoices.
- One invoice can have many credit notes.
- One invoice can have many audit events.
- The subscription-to-user relationship is intentionally modeled as a separate collaborator table rather than a many-to-many field to keep access control explicit and auditable.

## Database vs application constraints

Database constraints should enforce basic integrity:
- unique email addresses for users
- foreign keys between subscriptions, invoices, and collaborators
- not-null rules on required invoice fields
- status checks for known state values

Application logic should enforce deeper business rules:
- only billing admins may manage collaborators
- only the owner or authorized manager may create invoices
- invoice immutability once paid
- overdue status rules
- audit trail restrictions

The boundary is where the rules are operationally important and where simple DB validation would be too blunt.

## Denormalization decisions

We are not yet denormalizing aggressively. The system should favor normalized tables and explicit audit rows because billing rules and compliance history are sensitive. If denormalization is needed later, it should only be for read-heavy reporting endpoints such as dashboard totals, not for the source-of-truth invoice state.

## Scaling risk at 100x volume

The first things that would become expensive are:
- invoice search/filter queries across large sets
- dashboard aggregate queries
- large audit event history for every invoice
- status-based overdue alerts that are recalculated often

The likely first optimization would be indexes on subscription owner, invoice status, due date, and invoice subscription references, followed by reporting tables or materialized summaries if needed.
