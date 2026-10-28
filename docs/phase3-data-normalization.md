# Phase 3: normalized data contract

## Scope and status

The Python analysis response has a pure, validated normalization adapter in `backend/app/normalization/`. `analyze_repository()` invokes it once after GitHub collection is complete and the existing response dictionary has been assembled. The normalized Pydantic result stays in the request handler's memory; it is not persisted and is not added to the HTTP response. This avoids repeat GitHub requests and preserves the existing `POST /api/repositories/analyze` response and React dashboard contract.

If normalization fails, the endpoint logs an error with the repository and exception type only, then returns the original collected response. It does not log the exception text or response payload, avoiding accidental disclosure of credentials or collected content. On success, it logs normalized record counts. The adapter itself does not make GitHub requests or write to a database.

The root Node/Express collector has a separate MongoDB connection and Mongoose models. The Python service currently has no Mongo client or persistence layer. This phase therefore does not introduce a second database connection or modify the Node models.

## How to call the normalizer

From the `backend` directory, or from a process that has `backend` on its Python import path:

```python
from app.normalization import normalize_analysis

normalized = normalize_analysis(api_response)
document = normalized.model_dump(mode="json")
```

`normalize_analysis()` is deterministic and does not mutate the input. It raises `NormalizationError` when the response is not an object or has no valid repository identity. Individual malformed records are skipped with entries in `normalization_warnings`; malformed optional values become `None` and are also reported. All model objects reject undeclared fields.

## Normalized records

Every record is scoped by a stable lower-case `repository_key` (`owner/name`). Display casing is retained in `full_name`, `owner`, and `name`. Source records and evidence retain GitHub endpoint names and source URLs where available.

### Repository

`RepositoryRecord` fields: `repository_key`, `owner`, `name`, `full_name`, optional `canonical_url`, `description`, `primary_language`, `visibility`, `is_private`, `default_branch`, `stars`, `forks`, `open_issues_count`; plus `source_system` (`github`), `source_endpoint`, and `source_url`.

ID convention: repository key is `owner/name`, normalized with case folding for joins. Source URL/display name preserve source casing.

### Issue

`IssueRecord` fields: `entity_id`, `repository_key`, `number`, optional `title`, `body`, `state`, UTC `created_at`/`closed_at`, `labels`, `author`, `comments`; plus `source_system`, `source_endpoint`, and `source_url`.

ID convention: `{repository_key}#issue:{number}`. The existing API's root `repository` supplies repository context because individual issue items do not repeat it. Labels are retained without bug-label filtering.

### Pull request

`PullRequestRecord` fields: `entity_id`, `repository_key`, `number`, optional `title`, `body`, `state`, `merged`, UTC `merged_at`/`created_at`/`updated_at`, `author`, `commits_count`, `changed_files_count`; plus provenance fields.

ID convention: `{repository_key}#pull:{number}`. A PR found under a different repository than the analysis response is skipped with a warning.

### Commit

`CommitRecord` fields: `entity_id`, `repository_key`, validated hexadecimal `sha` (40–64 characters), optional `message`, `author`, UTC `authored_at`; plus `source_system`, `source_endpoints`, and `source_url`.

ID convention: `{repository_key}#commit:{lower-case-sha}`. The same commit found in the repository commit list and a PR's commits is one record. Provenance endpoints are combined; missing fields can be filled from another observation; conflicting non-empty values keep the first and produce a warning.

### Changed file observation

`ChangedFileRecord` fields: `entity_id`, `repository_key`, `source_entity_type` (`commit` or `pull_request`), `source_entity_id`, repository-relative `path`, optional `status`, `additions`, and `deletions`; plus provenance.

ID convention: repository + source type + source entity ID + URL-encoded path. File changes are observations tied to a particular commit or PR, not global file entities. PR file lists are not assigned to each individual PR commit because the existing API does not provide that attribution.

### Relationship and evidence

`RelationshipRecord` fields: `entity_id`, `repository_key`, `source_entity_type` (`pull_request` or `commit`), `source_entity_id`, `target_entity_type` (`commit`, `changed_file`, or `issue`), `target_entity_id`, `target_repository_key`, `relation_type`, and `evidence[]`.

Relationship IDs are deterministic from repository, relation type, source ID, and target ID. Current relation types emitted by the normalizer:

| Relation | Evidence |
|---|---|
| `pull_request_contains_commit` | GitHub PR commits endpoint (`github_api`) |
| `pull_request_changes_file` | GitHub PR files endpoint (`github_api`) |
| `commit_changes_file` | GitHub commit detail files (`github_api`) |
| `explicitly_references_issue` | Explicit closing-keyword text from a PR description or commit message (`explicit_text`) |

Evidence fields: `kind`, `source_endpoint`, optional `source_url`, `source_field`, matched `text`, `source_commit_sha`, `target_in_collection`, and `source_pull_request_merged`. Explicit references remain textual evidence; they do not mean that a commit fixed an issue. Cross-repository issue references carry their actual target `repository_key`. The `inferred_candidate` enum exists as a reserved representation, but the normalizer does not emit inferred edges.

### Collection run

`CollectionRunRecord` has optional `run_id`, `repository_key`, nullable `status` (`complete`/`partial`), `counts`, per-stage `stages`, collector `warnings`, `empty_results`, `failed_pull_requests`, and `skipped_pull_requests`.

The current API does not assign a collection run ID or timestamps, so these remain unset. Counts, stage statuses, warnings, failed/skipped PR details, and `partial` status are copied from the response rather than recalculated from normalized records. A bounded result remains partial; it must not be treated as complete repository coverage. `normalization_warnings` and `duplicate_records_merged` are separate adapter diagnostics and do not overwrite collector status.

## Timestamp and missing-data rules

- ISO timestamps with an explicit offset are parsed and converted to UTC.
- Missing, malformed, or timezone-naive timestamps normalize to `null`; invalid values add a warning. No timezone is guessed.
- Optional numeric fields must be non-negative integers; booleans are not accepted as integers.
- Optional booleans must be actual booleans.
- Missing optional strings remain `null`; absent list fields become empty lists.
- Invalid required repository/entity identifiers prevent that entity from being represented. Invalid root repository identity raises `NormalizationError`. A supplied repository identity on a PR, commit, or relationship must match the root repository after case folding; malformed or mismatched records and their derived edges are skipped with warnings. Relationships whose source PR is not in the normalized PR collection are skipped with a warning.
- Non-string issue/PR states and collection statuses are rejected with warnings and normalized to `null`; they are never coerced into allowed values.
- Duplicate entity IDs are merged; non-empty conflicts are retained from the first observation and warned. Lists are unioned while preserving order.

## Phase 4 persistence interface (proposed, not implemented)

Phase 4 can consume the normalized object through a storage adapter:

```python
normalized = normalize_analysis(api_response)
records = normalized.model_dump(mode="json")
# Proposed future adapter: repository_store.upsert_analysis(records)
```

The stable `entity_id` values are suitable idempotency keys, while `repository_key` supports scoped indexes. Proposed persistence work includes a collection-run identifier and timestamps assigned by the service, unique indexes on `entity_id`, and transactional/upsert behavior. Those fields/indexes and the `upsert_analysis` interface are recommendations only; no DB schema or writes are implemented. Before Phase 4, decide whether Python should persist to the existing MongoDB or whether the Node service should own persistence and receive normalized payloads through an explicit interface. Do not silently create a second Mongo store.

## Run and verify

From the project root in PowerShell:

```powershell
python -m pip install -r backend/requirements.txt
python -m uvicorn app.main:app --reload --app-dir backend --host 127.0.0.1 --port 8010
```

In a second terminal, run all mocked tests:

```powershell
python -m unittest discover -s backend/tests -v
```

The current automated run after endpoint integration passed **35 tests** (the prior 32-test suite plus three integration tests). These cover one-time invocation using the collected payload, partial metadata and explicit evidence retention, unchanged response fields/types, safe handling of normalization failure, and single invocation of each collector dependency.

### Live repository validation

A bounded request to `https://github.com/pallets/flask` was made through the running local API and the returned JSON was passed to `normalize_analysis()`. The API returned HTTP 200 with `status: partial`; raw counts were 144 issues, 500 pull requests, 20 commits, 38 unique changed-file paths, 10 PR relationship records, and 490 skipped PR relationships. Normalization completed with zero normalization warnings and preserved `partial` plus the skipped count. It produced 144 issues, 500 PRs, 29 deduplicated commits, 112 source-scoped changed-file observations, and 128 normalized relationship edges. Normalized file/edge counts differ from the API summary because file observations are scoped to their source commit or PR and relationship edges include commit/file/issue links; the original API counts remain available unchanged in `collection_run.counts`.

For a live collection check, configure `GITHUB_TOKEN` in the existing supported env file without printing it, then:

```powershell
$body = @{ repository_url = "https://github.com/pallets/flask" } | ConvertTo-Json
$result = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8010/api/repositories/analyze" `
  -ContentType "application/json" -Body $body
$result.status
$result.counts | ConvertTo-Json
$result.warnings
```

The normalizer can be exercised against a captured response object with `normalize_analysis($response)` in Python. Do not treat a successful HTTP status as complete collection: check `status`, per-stage `collection`, `warnings`, `empty_results`, and failed/skipped counts. The Phase 2 `pallets/flask` sample hit collection limits and therefore remains partial.
