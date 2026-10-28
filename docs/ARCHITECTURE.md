# BugScope AI architecture

## Services

- **React + Vite (`frontend/`)** provides the dashboard and sends repository
  URLs to FastAPI. `VITE_API_BASE_URL` selects the API host; it contains no
  credentials.
- **FastAPI (`backend/app/`)** owns GitHub collection and normalization. It
  calls GitHub's API using the backend-only `GITHUB_TOKEN`, reports partial
  collection and warnings, and posts versioned normalized records to Express.
- **Express (`server.js`)** owns the PostgreSQL pool and exposes the internal
  authenticated normalized-data endpoint plus read-only query routes.
- **Neon PostgreSQL** stores repositories, issues, bug-classified issues,
  pull requests, commits, changed-file observations, relationships, and
  collection runs using repository-scoped unique keys and upserts.

## Analysis request flow

1. The dashboard posts `{ repository_url }` to FastAPI's
   `POST /api/repositories/analyze`.
2. FastAPI collects records, marks stages complete/partial/failed, normalizes
   identities and provenance, and sends schema version 1 to Express at
   `POST /internal/normalized-analysis` with a bearer service token.
3. Express validates the token and payload, then persists related rows in one
   PostgreSQL transaction. The migration runner records applied SQL migration
   names in `schema_migrations` so they are not reapplied.
4. FastAPI returns collection data and a `persistence.status` field. Only
   `persisted` confirms that the internal write succeeded.

The React dashboard uses FastAPI on port 8010 by default. Express uses port
5000. Configure the same high-entropy `BUGSCOPE_INGEST_TOKEN` in root and
`backend/.env`; configure `DATABASE_URL` only in root `.env`. Never put secrets
in Vite variables because those are exposed to browser code.

## Scope and limitations

Relationship rows represent observed GitHub membership and explicit textual
references. Bug families, similarity ranking, and AI classification are not
implemented by this flow. The Express `/api/collect` endpoint returns `410`
for older clients so it cannot create a second collection/persistence path;
use FastAPI analysis instead. `services/githubCollector.js` remains in the
working tree as legacy code but is no longer mounted or called by the server.
