# FastAPI backend

FastAPI collects GitHub repository metadata, issues, pull requests, commits,
changed files, and evidence-backed relationships. It normalizes that response
and sends it to the root Express service for PostgreSQL persistence.

## Setup and run (PowerShell, from the project root)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
python -m uvicorn app.main:app --reload --app-dir backend --host 127.0.0.1 --port 8010
```

Set `GITHUB_TOKEN` and `BUGSCOPE_INGEST_TOKEN` in `backend/.env`. The ingest
token must match the root `.env`; keep credentials out of source control. The
Express process must be running for persistence. Configure the Vite client with
`VITE_API_BASE_URL=http://127.0.0.1:8010` in `frontend/.env`.

## Tests

From the project root run `python -m unittest discover -s backend/tests -v`.
The tests use mocks and do not need a GitHub token or database.

## Endpoints

- `GET /health`
- `GET /api/github/auth-status` (reports token state without returning it)
- `POST /api/repositories/analyze` with `{ "repository_url": "https://github.com/owner/repository" }`

Analysis results can still be returned when PostgreSQL persistence is not
configured or fails. Check the response's `persistence.status` before assuming
the run was saved.
