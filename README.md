# BugScope AI — Phase 1 (Repository Data Collector)

This is the first working slice of BugScope AI: it connects to MongoDB, pulls
bug-labeled issues and recent commits from a GitHub repo via the GitHub API,
and links commits back to the bugs they mention fixing (e.g. "fixes #123").

## What this phase does

- `services/githubCollector.js` — talks to GitHub, saves Bugs/Commits/Components
- `models/` — Mongoose schemas: `Bug`, `Commit`, `Component`, `BugFamily` (the
  last one is empty until Phase 2 — it's here so relationships have somewhere
  to point)
- `routes/collector.js` — HTTP endpoints to trigger a collection run and
  inspect what got saved

## Setup

1. Install dependencies (already done if you got this scaffold from Claude):
   ```bash
   npm install
   ```
2. Copy the env template and fill in real values:
   ```bash
   cp .env.example .env
   ```
   - `MONGO_URI` — a local MongoDB (`mongodb://127.0.0.1:27017/bugscope`) or
     an Atlas connection string
   - `GITHUB_TOKEN` — a GitHub personal access token (classic). Without one
     you're capped at 60 API requests/hour, which will not get you through
     a real repo. Create one at https://github.com/settings/tokens (no
     special scopes needed for public repos).
3. Start MongoDB (`mongod` locally, or use Atlas — no local setup needed then).
4. Run the server:
   ```bash
   npm run dev
   ```
   You should see:
   ```
   [db] connected to MongoDB (bugscope)
   [server] BugScope AI backend listening on port 5000
   ```

## Try it

Trigger a collection run against axios (start small — this hits the GitHub
API once per commit to read changed files, so `maxCommits` keeps it sane):

```bash
curl -X POST http://localhost:5000/api/collect \
  -H "Content-Type: application/json" \
  -d '{"owner": "axios", "repo": "axios", "maxCommits": 150}'
```

This can take a few minutes on the first run (issues aren't rate-limited,
but each commit needs its own API call). Watch the server logs.

Then check what got stored:

```bash
curl "http://localhost:5000/api/bugs?repo=axios/axios"
curl "http://localhost:5000/api/commits?repo=axios/axios"
```

## Known limitations (by design, for now)

- Only issues carrying a `bug`-like label are saved — adjust `bugLabels` in
  `collectBugs()` if a repo uses different label names (check the repo's
  Issues page/labels first).
- `fixCommitShas` is populated from **commit message text**, not GitHub's
  own issue-timeline API. It catches "fixes #123" style messages, which
  covers most real-world cases, but isn't 100% authoritative.
- No embeddings yet, no Bug Family grouping yet, no dashboard yet — that's
  Phases 2 onward.

## Next (Phase 2 — Bug Family Intelligence)

Once you've got real Bug + Commit + Component data sitting in MongoDB, the
next step is generating embeddings for each bug's title+body (via
`transformers.js` — no Python needed) and clustering similar bugs into
`BugFamily` documents. Come back when you're ready for that or if anything
above breaks on you.
