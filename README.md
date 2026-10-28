# BugScope AI

BugScope AI collects GitHub repository history to help developers investigate
bugs using issues, pull requests, commits, changed files, and explicit
relationships. The app has a React frontend, a Python FastAPI collection and
normalization service, a Node/Express API and PostgreSQL persistence service,
and a Neon PostgreSQL database. Bug-family detection and similarity ranking
are not implemented yet.

## Prerequisites

- Node.js and npm
- Python 3.10 or newer
- PostgreSQL/Neon credentials for persistence
- A GitHub token is optional for public repositories but recommended for higher
  API limits

## Configure environment

Copy `.env.example` to root `.env`, `backend/.env.example` to
`backend/.env`, and `frontend/.env.example` to `frontend/.env`. Use local
placeholders in the example files only. Put `DATABASE_URL` in root `.env` and
set the same high-entropy `BUGSCOPE_INGEST_TOKEN` in root and `backend/.env`.
Set `GITHUB_TOKEN` in `backend/.env`. The frontend only needs
`VITE_API_BASE_URL=http://127.0.0.1:8010`; never put credentials in frontend
environment variables.

All `.env` files are ignored by Git; example files are tracked.

## Install

From the project root in PowerShell:

```powershell
npm.cmd install
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
Set-Location frontend
npm.cmd install
Set-Location ..
```

## Migrate and start

Run the migration once (the runner tracks applied filenames):

```powershell
npm.cmd run migrate
```

Start Express in one terminal:

```powershell
npm.cmd run dev
```

Start FastAPI in another terminal from the project root:

```powershell
python -m uvicorn app.main:app --reload --app-dir backend --host 127.0.0.1 --port 8010
```

Start Vite in a third terminal:

```powershell
Set-Location frontend
npm.cmd run dev
```

The dashboard calls FastAPI `POST /api/repositories/analyze`. FastAPI collects
and normalizes GitHub data, then sends it to Express's authenticated internal
ingest endpoint. Express writes PostgreSQL records transactionally. The
analysis response includes `persistence.status`; only `persisted` confirms the
write succeeded. Express exposes `/api/bugs` and `/api/commits` read routes on
port 5000. Its old `POST /api/collect` endpoint returns `410` to avoid a
second active collection/persistence implementation.

## Tests and checks

```powershell
npm.cmd test
python -m unittest discover -s backend/tests -v
```

These automated tests use local mocks and do not need Neon credentials. Do not
run application flows against a production database as a test. To check
database setup manually, `node check-db.js` lists public table names without
printing the database URL.

## Troubleshooting

- FastAPI `/health` works but analysis returns a GitHub error: inspect
  `GITHUB_TOKEN` configuration with `GET /api/github/auth-status`; it never
  returns the token.
- `persistence.status` is `not_configured` or `failed`: ensure Express is
  running, root `DATABASE_URL` is valid, and the ingest token matches in root
  and `backend/.env`.
- PostgreSQL TLS/network errors: confirm Neon availability and the local
  connection string; never paste it into logs, issues, or chat.
- Port conflicts: change `PORT` for Express or use another Uvicorn/Vite port
  and update `VITE_API_BASE_URL` accordingly.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and
[docs/PROJECT_HANDOFF.md](docs/PROJECT_HANDOFF.md) for the data flow and
current implementation limits.
