# Plan

## Work split

I planned the work in a straightforward sequence based on the assignment requirements:

1. Set up the backend foundation.
2. Validate the project structure and Django startup.
3. Define the domain model for users, subscriptions, and invoices.
4. Build auth and role enforcement.
5. Implement subscription and invoice operations.
6. Add server-side filtering, bulk generation, and reporting.
7. Add audit history and overdue alert logic.
8. Write the documentation and submission artifacts.

This order matters because the business rules depend on the data model and role structure. It is better to stabilize the backend shell before adding billing logic.

## What we built so far

- Django backend initialized under `backend/`
- project configuration and URL routing created
- Django system check passes successfully
- project structure cleaned up and aligned with the current folder layout

## What is next

- create the core billing app models
- implement user roles and server-side permission checks
- add subscriptions and invoices with invoice lifecycle rules
- create invoice search/filter/query logic
- add reporting endpoints and alerts
- document decisions and final architecture once the logic exists

## Time estimate vs reality

The backend scaffolding took far less time than the full billing logic will take. The foundation was roughly a few hours, which was accurate for setup. The full domain implementation and business rule enforcement will be more involved and likely exceed the initial estimate if done properly.

## What we cut or deferred

- A frontend was intentionally deferred.
- Deployment work was deferred until the backend logic is stable.
- Complex stretch features were deferred. The priority is correctness for the required billing rules, not extra features.
- A stronger production database and deployment environment will come after the core business model is working and tested.
