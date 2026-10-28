# BugScope AI frontend

React + Vite dashboard for the FastAPI GitHub analysis endpoint.

## Setup

From the project root, install root dependencies with `npm.cmd install`. Copy
`frontend/.env.example` to `frontend/.env` if the API is not at its default
address, and set `VITE_API_BASE_URL` to the FastAPI base URL. Then:

```powershell
Set-Location frontend
npm.cmd install
npm.cmd run dev
```

The default API URL is `http://127.0.0.1:8010`. The dashboard posts
`{ "repository_url": "https://github.com/owner/repository" }` to
`POST /api/repositories/analyze`. It displays partial collection warnings and
whether the response confirms PostgreSQL persistence. GitHub and database
credentials belong only in backend environment files, never in Vite variables.

Build for a static production bundle with `npm.cmd run build` from `frontend/`.
