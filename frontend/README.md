# BugScope AI frontend

React + Vite client for the existing FastAPI GitHub collection endpoint.

## Run locally

1. Copy `.env.example` to `.env` and set `VITE_API_BASE_URL` if the backend is not at `http://localhost:8000`.
2. Install dependencies with `npm install`.
3. Start the backend from `../backend` with `uvicorn app.main:app --reload`.
4. Start the frontend with `npm run dev` and open the URL printed by Vite.

The client sends `POST /api/repositories/analyze` with `{ "repository_url": "https://github.com/owner/repository" }`. GitHub credentials remain backend-only.