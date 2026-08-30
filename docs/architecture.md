# Architecture

## Current project shape

The project is currently structured as a Django backend under the `backend/` folder. The entry point is the Django management script in [backend/main.py](../backend/main.py), which loads settings from [backend/src/settings.py](../backend/src/settings.py) and routes HTTP requests through [backend/src/urls.py](../backend/src/urls.py). The application is still in its early scaffolding stage, but the basic backend shell is in place and is verified to run through Django's system check.

## Moving pieces

- Django app runtime: handles request routing, view logic, auth, and app configuration.
- Project configuration: settings, URL routing, and WSGI setup live in the `src` package.
- Database: SQLite is currently used for local development and validation. This is enough to prototype and test the app structure before moving to a production database later.
- Future app modules: the system will eventually grow into separate billing-focused modules for accounts, subscriptions, invoices, audit history, and reports.

## Where each piece runs

- Local development runs on the machine where the developer starts the Django server.
- The database is a local SQLite file in the backend folder while the system is still being built.
- The final app will likely move to a hosted PostgreSQL database and a deployment environment, but that is future work.

## Representative request path

A representative request today would work like this:

1. A developer runs `python main.py runserver` from the backend folder.
2. Django loads settings from `src.settings`.
3. The request hits `src.urls` and resolves to the app-level route definitions.
4. The view returns a JSON response or later a real billing response.
5. The app reads or writes data through Django models and the configured database backend.

At this point, the app is not yet implementing the full billing workflow, but the request flow is consistent with the eventual architecture.

## What we decided not to build yet

- We did not keep the separate Flask service. Django alone is simpler and more consistent for this project.
- We did not build the full subscription/invoice domain yet; that is the next phase after the project shell is stable.
- We did not add a frontend or deployment configuration yet because the backend foundation is the current priority.
