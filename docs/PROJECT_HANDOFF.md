# Project handoff

## Status

### Verified from source

- React calls FastAPI `POST /api/repositories/analyze`.
- FastAPI collects GitHub issues, pull requests, commits, changed-file details,
  and repository relationships, then normalizes those records.
- Express has a bearer-token protected internal ingest endpoint and a
  transaction-based PostgreSQL upsert implementation.
- Migration `001_initial_schema.sql` is guarded by `schema_migrations` and its
  DDL uses `IF NOT EXISTS` for rerun safety.
- `.env`, backend/frontend `.env` files, dependency folders, and Python caches
  are ignored by `.gitignore`.

### Implemented, not verified end to end

- The Python-to-Express-to-PostgreSQL write path is implemented. A live Neon
  connection and an actual repository analysis were not run in this session, so
  database persistence is **not verified end to end**.
- The route now reports `persistence.status`; only `persisted` is confirmation.
- The old Express `/api/collect` endpoint now returns `410` so there is one
  active collection and persistence path. `services/githubCollector.js` is
  retained but unused; review/remove it after checking outside callers.

## Incomplete capabilities

- Bug-family detection and similarity ranking are not implemented.
- Existing MongoDB/Mongoose models, dependency, and historical design documents
  remain. They were retained because the new PostgreSQL flow has not yet been
  verified against a live or isolated database.
- The collection-run UUID is generated per analysis, so a repeated analysis is
  idempotent at entity level but creates a distinct run-history row.

## Main paths and data model

- `frontend/src/services/api.js`: frontend request/response handling.
- `backend/app/api/repositories.py`: GitHub analysis orchestration.
- `backend/app/normalization/`: stable repository-scoped records.
- `routes/internal.js`: authenticated internal ingest API.
- `repositories/postgres.js`: parameterized transactional PostgreSQL upserts.
- `config/db.js`: PostgreSQL pool.
- `migrations/001_initial_schema.sql`, `scripts/migrate.js`: schema and runner.
- Tables: repositories, issues, bugs, pull_requests, commits,
  changed_file_observations, relationships, collection_runs, components,
  bug_families, bug_family_members, bug_components, similar_bugs.

## Endpoints

- FastAPI: `GET /health`, `GET /api/github/auth-status`,
  `POST /api/repositories/analyze`.
- Express: `GET /`, `POST /internal/normalized-analysis` (service-token
  protected), retired `POST /api/collect` (410), `GET /api/bugs`,
  `GET /api/commits`.

## Teammate next steps

Clone and prepare the project in PowerShell (replace the placeholder with the
repository's GitHub clone URL):

```powershell
git clone <repository-url> bugscope-ai
Set-Location bugscope-ai
npm.cmd install
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
Set-Location frontend
npm.cmd install
Set-Location ..
Copy-Item .env.example .env
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.example frontend\.env
npm.cmd run migrate
```

Set local credentials in the ignored files. Then use separate terminals:

```powershell
# Express, from the project root
npm.cmd run dev
```

```powershell
# FastAPI, from the project root
python -m uvicorn app.main:app --reload --app-dir backend --host 127.0.0.1 --port 8010
```

```powershell
# Vite, from the frontend directory
npm.cmd run dev
```

1. Start the services using the commands above and analyze a small public
   repository. Confirm the API response says `persistence.status: persisted`.
2. Query `/api/bugs` and `/api/commits`; use read-only SQL to confirm matching
   repository-scoped rows and the collection run. Never point tests at the
   production Neon URL.
3. Run the Python and Node suites. Resolve failures before removing Mongoose;
   check whether any external client still calls the retired `/api/collect`.

## Verification note

The implementation was inspected, but no credentials were read and no Neon
connection or live GitHub analysis was performed. See the handoff from the
current run for the exact commands executed and their outcomes. Latest local
verification: Python unittest suite 37/37 passed, Node suite 11/11 passed,
frontend Vite production build passed, Python compileall passed, JavaScript
syntax checks passed, and `git diff --check` passed with line-ending notices
only. PostgreSQL persistence remains unverified end to end.
