# BugScope AI Phase 2 data handoff

This document describes the current Python dashboard API and a proposed normalized contract for Phase 3. The contract section is a recommendation; it is not implemented or persisted by this project yet.

## Which backend this describes

The React dashboard calls the Python FastAPI service at `POST /api/repositories/analyze`. The project also has a separate Node.js/Express collector on port 5000 that writes its own Bug and Commit records to MongoDB. The Node collector does not implement this dashboard response and is not the source of the Python analysis below.

The Python endpoint currently returns a JSON response in memory. It does not persist its analysis in MongoDB.

## Implemented behavior

- Collects repository issues from GitHub's Issues API. It includes all labels and does not require a `bug` label. Pull requests returned by the Issues API are excluded from `issues`.
- Collects pull requests newest first from GitHub's Pull Requests API.
- Collects recent repository commits independently of issues and pull requests. It fetches changed-file details for each returned repository commit.
- For a bounded set of pull requests, collects the commits belonging to each PR and the files returned by that PR's changed-files endpoint.
- Extracts explicit `Fixes`, `Closes`, and `Resolves` references from commit messages and PR descriptions. Bare issue-number mentions are ignored.
- Reports collection stages, counts, warnings, empty successful results, and skipped/failed relationships. A limit hit makes the overall result `partial`.
- Retains the legacy `bugs` and `total_bugs` response fields as aliases of `issues` and its count for existing clients.

## Live verification performed

A live analysis of `pallets/flask` returned:

| Field | Observed value |
|---|---:|
| `status` | `partial` |
| Issues | 144 |
| Pull requests | 500 |
| Repository commits | 20 |
| Unique changed-file paths | 38 |
| PR relationships | 10 |
| Failed relationships | 0 |
| Skipped PR relationships | 490 |

The response warned that the issue, pull-request, and repository-commit limits were reached and that 490 PR relationships were skipped. This is a partial sample, not complete repository coverage.

On the current response, all 10 relationship rows passed these consistency checks: their repository matches the analysis repository; their PR number exists in `pull_requests`; `commit_count` and `changed_file_count` match the returned records; commit identifiers are 40-character SHAs; changed-file paths are nonempty; and every reference marked `target_in_collected_issues: true` resolves in `issues`. These checks validate response consistency and the endpoint evidence; they do not turn explicit text references into proof that an issue was fixed.

I checked an actual returned relationship for `pallets/flask#6158` against GitHub's PR detail, PR-commits, and PR-files endpoints:

- The PR exists at `https://github.com/pallets/flask/pull/6158`.
- GitHub's PR detail reports one commit and one changed file; the collector returned one commit and one changed file.
- Commit SHA: `c66b591aee573a637262e55db02d2a36c261413c`.
- Changed file: `docs/deploying/index.rst` (`modified`, 1 addition, 0 deletions).
- The PR description contains the explicit text `Closes #6146`. Issue `pallets/flask#6146` exists and was present in the bounded issue collection.

The issue reference is evidence that the PR description explicitly declares a closing reference. It is not a claim that this code independently verified the issue's final state or that a particular commit fixed it.

## Current API response shape

The root response fields are:

```json
{
  "repository": "pallets/flask",
  "repository_url": "https://github.com/pallets/flask",
  "repository_details": {},
  "status": "partial",
  "warnings": [
    "Issue collection reached its page limit; more issues may exist.",
    "Pull-request collection reached its page limit; more pull requests may exist.",
    "Repository commit collection reached its configured limit (20); more commits may exist.",
    "Relationship collection was limited; 490 pull request(s) were skipped."
  ],
  "counts": {
    "issues": 144,
    "pull_requests": 500,
    "commits": 20,
    "changed_files": 38,
    "relationships": 10,
    "failed_relationships": 0,
    "skipped_relationships": 490
  },
  "collection": {
    "issues": {"status": "partial", "returned": 144, "limit_reached": true},
    "repository_metadata": {"status": "complete", "returned": 1},
    "pull_requests": {"status": "partial", "returned": 500, "limit_reached": true},
    "commits": {"status": "partial", "returned": 20, "limit_reached": true, "failed_file_details": 0},
    "relationships": {"status": "partial", "returned": 10, "failed": 0, "skipped": 490}
  },
  "empty_results": [],
  "issues": [{"issue_number": "...", "title": "..."}],
  "pull_requests": [{"repository": "pallets/flask", "number": "...", "title": "..."}],
  "commits": [{"repository": "pallets/flask", "sha": "...", "changed_files": []}],
  "relationships": [{"repository": "pallets/flask", "pull_request_number": "...", "commits": [], "changed_files": []}],
  "failed_pull_requests": [],
  "skipped_pull_requests": 490,
  "total_bugs": 144,
  "bugs": [{"issue_number": "...", "title": "..."}]
}
```

The excerpt uses the counts and stage statuses from the captured live response; record bodies are abbreviated to show their structure. `bugs` duplicates `issues`; consumers should use `issues` for new work.

### Issue records

Each item in `issues` has:

- `issue_number`: GitHub issue number.
- `title`, `description`, `state`.
- `created_at`, `closed_at`.
- `labels`: label names, including an empty list when no labels exist.
- `html_url`, `author`, `comments`.

The per-record issue object does not currently repeat `repository`; its repository is supplied by the root `repository` field. Treat an issue identity as `(repository, issue_number)`, not as a globally unique number.

### Pull-request records

Each item in `pull_requests` has:

- `repository`, `number`, `title`, `description`, `state`.
- `merged`, `merged_at`, `created_at`, `updated_at`.
- `author`, `html_url`.
- `commits_count`, `changed_files_count`.

The last two values come from the PR list response and may be `null`. The relationship records carry observed `commit_count` and `changed_file_count` for PRs whose relationship details were collected.

### Repository commit records

Each item in `commits` has:

- `repository`, `sha`, `message`, `author`, `date`, `html_url`.
- `changed_files`: objects with `filename`, `status`, `additions`, and `deletions`.
- `issue_references`: explicit closing-reference evidence extracted from the commit message.

Treat a repository commit identity as `(repository, sha)`. A commit SHA is not exposed as the PR number and should not be joined to a PR by number.

### PR relationship records

Each item in `relationships` has:

- `repository`, `pull_request_number`, `pull_request_title`, `pull_request_state`, `merged_at`.
- `commits`: GitHub PR-commit endpoint results with `commit_sha`, `message`, `author`, `date`, and `changed_files`.
- `commit_count`: number of commit records returned for that PR.
- `changed_files`: repo-relative filename strings, retained for the current dashboard.
- `changed_file_count`: number of unique paths returned for the PR.
- `changed_file_details`: objects with `filename`, `status`, `additions`, and `deletions`.
- `issue_references`: explicit closing-reference evidence from commit messages or the PR description.

The `repository` plus `pull_request_number` identifies the PR side. Each nested commit is identified by `(repository, commit_sha)`. File strings are scoped to the parent repository and PR; they are not global file IDs.

The PR-commits endpoint does not return changed files per commit. Therefore nested relationship commit objects currently have an empty `changed_files` list; the sibling `changed_file_details` list is supported at the PR level and must not be copied onto each nested commit. Per-commit changed-file observations are available separately under top-level repository `commits`, fetched by commit SHA.

Issue reference objects currently use:

- `repository`, `issue_number`.
- `relationship`: currently `explicit_closing_reference`.
- `source`: `commit_message` or `pull_request_description`.
- `evidence`: matched text such as `Closes #6146`.
- `source_commit_sha` when the reference came from a commit message.
- `target_in_collected_issues` when the same-repository target was checked against this response's collected issue set. `false` means it was not in that set; limits or the target being a PR can explain absence.
- `source_pull_request_merged` for same-repository references found in a PR relationship.

These are explicit references, not inferred links. No inferred candidate relationship is currently emitted. A merged PR flag and a closing-reference string alone do not prove which commit caused an issue to close.

## Collection status, counts, and limits

`status` is `complete` when the requested stages finished without warnings and `partial` when a stage failed, returned partial data, or hit a configured limit. `collection` has a per-stage status (`complete`, `partial`, `failed`, or `not_run`) and returned counts. `empty_results` lists successful stages that returned zero records; those are distinguishable from failed stages. `warnings` explains known limits and errors.

Current collection bounds:

| Stage | Current bound and behavior |
|---|---|
| Issues | 100 records/page, at most 5 pages (500 GitHub Issues API records). The Issues API also returns PR entries, which are filtered out after retrieval. |
| Pull requests | 100/page, at most 5 pages (500 PRs), sorted newest first. |
| Repository commits | 20 by default; configured with `BUGSCOPE_MAX_REPOSITORY_COMMITS`, clamped to 99. One extra list record is requested to detect truncation. File details are fetched for each selected commit. |
| PR relationships | 10 by default; configured with `BUGSCOPE_MAX_RELATIONSHIP_PRS`. Remaining PRs are counted as skipped. |
| PR commits | 100/page; fetched until GitHub returns the final page. |
| PR changed files | 100/page, at most 10 pages (1,000 file rows per PR). |

The Flask live result hit issue, PR, repository-commit, and relationship limits. Its `partial` status and warnings must be preserved downstream; the returned counts are observed counts, not repository totals. PR list `commits_count` and `changed_files_count` may be null. The per-relationship observed counts are available only for relationships the collector processed.

The GitHub auth diagnostic is `GET /api/github/auth-status`. It reports `authenticated`, `not_configured`, `invalid_token`, `insufficient_permissions`, `rate_limited`, or a network/API error without returning token material.

## Evidence and identifier conventions

Implemented evidence sources:

| Relationship | Evidence source |
|---|---|
| PR contains commit | GitHub `GET /repos/{owner}/{repo}/pulls/{number}/commits` |
| PR changes file | GitHub `GET /repos/{owner}/{repo}/pulls/{number}/files` |
| Repository commit changes file | GitHub `GET /repos/{owner}/{repo}/commits/{sha}` |
| Commit/PR description explicitly references an issue | Closing-keyword match (`fix`, `close`, `resolve` forms) in the source text; stored with source and evidence text |

The first three are API membership/data relationships. The last is an explicit textual reference and must not be normalized as a verified fix without additional evidence. All issue and PR numbers require repository context. File paths require repository context. The response does not yet assign stable database IDs.

## Run the Python backend and tests

From the project root in PowerShell:

```powershell
python -m pip install -r backend/requirements.txt
python -m uvicorn app.main:app --reload --app-dir backend --host 127.0.0.1 --port 8010
```

Run mocked tests in another terminal:

```powershell
python -m unittest discover -s backend/tests -v
```

Verify without printing a token:

```powershell
Invoke-RestMethod http://127.0.0.1:8010/api/github/auth-status
```

Real repository verification:

```powershell
$body = @{ repository_url = "https://github.com/pallets/flask" } | ConvertTo-Json
$result = Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8010/api/repositories/analyze" `
  -ContentType "application/json" -Body $body
$result.status
$result.counts | ConvertTo-Json
$result.collection | ConvertTo-Json -Depth 5
$result.warnings
```

## Proposed Phase 3 normalized contract (not implemented)

Keep the current response as the source payload, then normalize it into repository-scoped entities and evidence-backed edges. Proposed fields below are not present in the current API unless explicitly identified above.

```text
Repository
  repository_key          proposed stable key, e.g. normalized owner/name
  owner, name, canonical_url

Issue
  repository_key, number, title, description, state
  created_at, closed_at, labels[], author, comments, html_url

PullRequest
  repository_key, number, title, description, state
  merged, merged_at, created_at, updated_at, author, html_url

Commit
  repository_key, sha, message, author, authored_at, html_url

ChangedFileObservation
  repository_key, path, status, additions, deletions
  source_commit_sha? or source_pull_request_number?

RelationshipEdge
  repository_key, source_type, source_key, target_type, target_key
  relation_type, evidence_source, evidence_text, observed_at
  verification_state
```

Suggested edge types:

- `pull_request_contains_commit` and `pull_request_changes_file`: confirmed from GitHub's PR-specific endpoints.
- `commit_changes_file`: confirmed from GitHub's commit details endpoint.
- `explicitly_references_issue`: textual evidence only; preserve the matched text and distinguish whether the source was a commit message or PR description.
- `inferred_candidate`: reserved for future analysis and must remain separate from confirmed or explicit-reference edges.

Suggested Phase 3 sequence:

1. Agree on canonical repository keys and entity/edge fields with the Phase 2 team.
2. Normalize a copy of current API results and test that partial status and evidence survive normalization.
3. Use composite keys `(repository_key, number)` for issues/PRs and `(repository_key, sha)` for commits; model file observations with repository and source context.
4. Keep explicit references, confirmed GitHub membership, and any later inferred candidates as distinct relationship types/states.
5. Add fixture tests for duplicate records, missing optional fields, cross-repository references, capped results, and unknown targets before adding downstream AI analysis.

Embeddings, bug-family clustering, AI analysis, and persistence changes are not part of this handoff implementation.
