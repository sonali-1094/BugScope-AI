# Phase 4.1 — MongoDB schema and entity-mapping proposal

**Status:** design only. No application code, Mongoose model, index, database connection, or API was changed for this proposal.

## 1. Proposed architecture

Keep the Python FastAPI service as the GitHub collection and normalization owner, and keep the existing Node.js/Express service as the sole MongoDB/Mongoose owner. After collection and Phase 3 normalization, Python should send the normalized document to a new authenticated Node-to-Node internal ingestion API. Node validates the schema version and repository-scoped identities, then performs Mongoose bulk upserts through its existing `mongoose` connection.

The ingestion API must accept already-collected normalized data. It must not call GitHub or invoke `/api/collect`; that endpoint performs a separate GitHub collection with different filtering and reference semantics. The public `POST /api/repositories/analyze` response remains unchanged. Normalized records are an internal service-to-service payload, not a dashboard response.

This reuses one database owner and avoids duplicating the Mongoose schema in Python. Direct Mongo access from Python is not recommended: it would add a second client/pool and a second schema/index implementation that can drift. A shared file or new queue would introduce infrastructure the project does not currently have.

### Internal endpoint security

The current Express app enables unrestricted CORS and has no route authentication. CORS is a browser policy, not access control. A future ingestion route should therefore:

- Require a dedicated high-entropy `BUGSCOPE_INGEST_TOKEN` configured for both services; compare credentials in constant time and never log the token or payload.
- Be reachable only over loopback/private service networking, with HTTPS or equivalent transport protection outside a single host. Apply host/network restrictions in addition to the token where deployment allows.
- Reject unauthorized calls before parsing or writing large payloads; validate the normalized schema version, record counts, repository scope, and maximum batch/body sizes.
- Remain separate from public collector/read routes. Do not rely on CORS, an obscure URL, or the GitHub token to authorize database writes.

`MONGO_URI` remains configured only for the Node service. Python does not gain a Mongo URI, driver, or MongoDB connection.

### Configuration names (values are intentionally not documented)

| Variable | Current owner/use | Requirement |
|---|---|---|
| `MONGO_URI` | Node `config/db.js` Mongoose connection | Required by Node startup. |
| `PORT` | Node Express listen port | Optional; code defaults to 5000. |
| `GITHUB_TOKEN` | Node Octokit collector and Python GitHub client | Optional for public GitHub access; authenticated access is preferred for rate limits. |
| `BUGSCOPE_MAX_REPOSITORY_COMMITS` | Python repository commit bound | Optional; current default is 20. |
| `BUGSCOPE_MAX_RELATIONSHIP_PRS` | Python PR relationship bound | Optional; current default is 10. |
| `BUGSCOPE_CORS_ORIGINS` | Python FastAPI browser origins | Optional; code supplies local frontend defaults. |
| `VITE_API_BASE_URL` | React dashboard API URL | Frontend setting; must point to the Python API. |
| `BUGSCOPE_INGEST_TOKEN` | Proposed Node internal-ingestion auth and Python client | New secret required by both services if this design is approved; it is not currently implemented/configured. |

## 2. Existing MongoDB model inventory

Mongoose collection names below were confirmed from the loaded model definitions. Mongoose also creates the standard `_id` index.

| Model / collection | Current required and optional fields | Current indexes and references |
|---|---|---|
| `Bug` / `bugs` | Required: `repo`, `number`, `title`, `state`, `createdAt`. Optional/defaulted: `body`, `labels`, `closedAt`, `url`, `embedding`, `componentIds`, `fixCommitShas`, `familyId`, `similarBugIds`, `fixEffectivenessScore`; Mongoose timestamps provide `createdAt`/`updatedAt`. | Indexed `repo`; unique `{ repo: 1, number: 1 }`. `componentIds` refs `Component`; `familyId` refs `BugFamily`; `similarBugIds` and `BugFamily.bugIds` ref `Bug`. |
| `Commit` / `commits` | Required: `repo`, `sha`, `message`. Optional: `author`, `date`, `url`, `filesChanged`, `referencedIssueNumbers`; timestamps. | Indexed `repo`; unique `{ repo: 1, sha: 1 }`. No Mongoose refs. |
| `Component` / `components` | Required: `repo`, `path`. Optional/defaulted: `bugCount`, `lastTouchedAt`; timestamps. | Indexed `repo`; unique `{ repo: 1, path: 1 }`. |
| `BugFamily` / `bugfamilies` | Required: `repo`, `name`. Optional/defaulted: `bugIds`, `evolutionSummary`, `averageFixEffectiveness`; timestamps. | Indexed `repo`; no unique business key. `bugIds` refs `Bug`. |

The individual `repo` index is a prefix of each of the first three compound indexes and may be redundant for some queries; retain it until query plans justify a change. Do not remove or rename existing reference paths as part of this phase without a separate migration plan.

The Node collector’s current `Bug` model stores only issues matching its bug-label filter. The Python collector stores all non-PR issues. The Node collector also extracts bare issue-number mentions into `referencedIssueNumbers` and adds commit SHAs to `fixCommitShas`; those fields are not equivalent to the Phase 3 evidence-bearing references.

## 3. Entity mapping and selected issue/Bug design

| Phase 3 normalized entity | Existing storage | Proposal |
|---|---|---|
| `RepositoryRecord` | None | Add one `Repository` collection. |
| `IssueRecord` | `Bug` is only a partial semantic fit | Add canonical `Issue` storage in `issues`; preserve `Bug`/`bugs` as the legacy compatibility projection linked one-to-one to an Issue. Details below. |
| `PullRequestRecord` | None | Add a `PullRequest` collection. |
| `CommitRecord` | `Commit` is a partial fit | Extend the existing `Commit` schema and preserve the existing natural key; add normalized provenance. |
| `ChangedFileRecord` | `Component` is not equivalent | Add a source-scoped `ChangedFileObservation` collection. Keep `Component` as the distinct repository/path aggregate. |
| `RelationshipRecord` | None | Add a `Relationship` collection with evidence records. |
| `CollectionRunRecord` | None | Add a `CollectionRun` collection. |

### General Issue and legacy Bug compatibility decision

The code confirms that these are different populations: Python collects all non-PR issues, while the only current Bug writer (`collectBugs`) skips PRs and stores issues only when labels match its configured bug-label list. `/api/bugs` reads the `bugs` collection directly and has no label predicate; its bug-only behavior currently depends on that writer. `Bug` ObjectIds are referenced by `BugFamily.bugIds`, `Bug.familyId`, `Bug.similarBugIds`, and `Bug.componentIds` is itself a reference to Components. There is no migration code or live-data audit.

The current route accepts an optional exact `repo` filter, returns up to 50 records sorted by `createdAt` descending, and responds with `{ count, bugs }`. Since it serializes Mongoose documents directly, preserving its contract includes keeping the same membership, sort, limit, field names/types, and response envelope; simply adding `issueId` or `repositoryKey` to the schema could leak new fields.

#### Option A — separate canonical `issues` and legacy `bugs` (recommended)

Keep the existing `bugs` collection, model name, Bug ObjectIds, indexes, reference paths, and `/api/bugs` bug-only behavior. Add `issues` as the canonical store for all normalized GitHub issues, keyed by `repositoryKey + number`. A legacy Bug is a compatibility classification/enrichment record linked to its canonical Issue by `issueId`; it is not a second independently authoritative issue. Preserve Bug-only enrichment/reference data (family, components, similar Bug IDs, embeddings) on the legacy Bug document. The canonical Issue owns current GitHub fields and source provenance.

When an Issue first qualifies under the existing agreed bug-label policy, upsert one Bug projection linked to that Issue. Repeated analyses locate the same Issue by `(repositoryKey, number)` and the same Bug projection by `issueId`; do not create another one. Keep the current Bug `_id` when linking a pre-existing Bug. A unique sparse index on `Bug.issueId` enforces at most one linked projection per Issue; after canonical-key backfill/audit, add a unique Bug `{ repositoryKey, number }` index as a second guard. If the issue no longer matches a current label rule, retain the projection and its ObjectId/references; do not delete it as a side effect of a partial run. Define whether its historical Bug membership remains visible in `/api/bugs` as part of compatibility tests.

For linked projections, Issue is authoritative for title/body/state/dates/labels/author/comments/URL. In the steady state, new linked Bug projections should hold the Issue link and Bug-only enrichment, not a second independently editable copy of GitHub fields. A compatibility serializer for `/api/bugs` should hydrate those fields from Issue and merge the legacy Bug fields; existing unlinked Bug documents can continue using their stored fields until linked. New linkage/provenance fields must be excluded from the endpoint response. This preserves Bug ObjectIds and endpoint behavior without creating two canonical Issue records or contradictory GitHub snapshots.

The existing Node collector can continue writing legacy Bug documents during the transition. Once ingestion is implemented, it should either link/upsert the same canonical Issue or remain explicitly a legacy-only writer; it must not create a second Bug for a casing variant. Classification must use a single agreed label rule/version. Do not make a generic issue a Bug just because it has a PR or commit reference.

#### Option B — unify the current Bug collection into canonical Issue storage

Rename or copy `bugs` to `issues`, preserve every `_id`, retain the Mongoose model alias needed by existing `ref: "Bug"` paths, add a bug-classification field, and change `/api/bugs` to filter only classified Bugs while serializing the old response shape. This yields one document per GitHub issue and is conceptually cleanest, but requires stopping writes, auditing all references, resolving normalized-key collisions, validating endpoint behavior, and rehearsing a collection migration. If IDs are not preserved, existing family/component/similar-Bug references break. If the Mongoose model points at `issues` before the migration, legacy data appears missing. If general issues enter the collection before the route filter is deployed, `/api/bugs` exposes non-bugs.

#### Recommendation

Choose Option A for Phase 4.2 because it is additive and preserves the current `bugs` collection and `Bug` ObjectIds without requiring access to or assumptions about live data. Keep Issue as the single canonical source for normalized GitHub fields; treat Bug as a keyed legacy projection that carries its established enrichment references and compatibility representation. Option B remains a possible later consolidation only after a backup, live-data audit, and approved migration rehearsal. Do not repoint the current `Bug` model to `issues` or rename collections in Phase 4.2.

The recommendation depends on verifying the one-to-one `issueId` link and Bug endpoint serializer in tests. If the project rejects even a linked compatibility projection as duplicate storage, stop before ingestion and approve Option B’s migration first; do not improvise a third schema.

## 4. Proposed document schemas and unique keys

Use the Phase 3 `repository_key` as the canonical `repositoryKey` in Mongo: lower-case/case-folded `owner/name`. Preserve a display-case `repo`/`fullName` separately for legacy output. Store normalized `entity_id` where useful for traceability, but use the natural compound keys below as the database idempotency keys. Normalize commit SHA to lower-case before persistence. UTC timestamps should be BSON dates.

Fields listed below are proposed persistence fields; they do not change the Phase 3 Pydantic or public API schema.

### Repository

`repositoryKey` (required), `owner`, `name`, `fullName`, `canonicalUrl`, `description`, `primaryLanguage`, `visibility`, `isPrivate`, `defaultBranch`, `stars`, `forks`, `openIssuesCount`, `sourceSystem`, `sourceEndpoint`, `sourceUrl`, timestamps.

Unique index: `{ repositoryKey: 1 }`. Update metadata from the latest valid GitHub repository observation; preserve useful optional values if a later partial metadata fetch omits them.

### Issue (new canonical `issues` collection)

`entityId`, `repositoryKey`, `repo` (display casing), `number`, nullable `title`, `body`, `state`, `createdAt`, `closedAt`, `labels`, `author`, `comments`, `url`, `sourceSystem`, `sourceEndpoint`, `sourceUrl`, timestamps, and optional `lastSeenRunId`.

Unique indexes: `{ repositoryKey: 1, number: 1 }` and optionally unique `entityId` (which is the normalized `{repositoryKey}#issue:{number}`). Use one authoritative uniqueness rule if both are redundant. New collection is additive; no existing Bug documents are moved into it automatically. Do not use `fixCommitShas` as a destination for every explicit issue reference.

### Legacy Bug compatibility projection (existing `bugs` collection)

Retain the current `Bug` model name, `bugs` collection, unique `{ repo: 1, number: 1 }`, existing fields, ObjectIds, and refs. Add optional `issueId` (ObjectId ref to `Issue`, `select: false`) with a unique sparse index so existing unlinked Bug records remain valid and a canonical Issue can have at most one Bug projection. Leave `issueId` absent on unlinked records; do not write `null`, which would be indexed by a sparse index. Add optional canonical `repositoryKey` (`select: false`), but defer its unique index until old data is backfilled and normalized-key collisions are resolved. Relax Bug-only required core-field constraints only after the link-aware `/api/bugs` serializer hydrates linked records from Issue; legacy writers still provide their current required values. Do not change the query or serialized response before compatibility tests pass.

### PullRequest

`entityId`, `repositoryKey`, `repo`, `number`, `title`, `body`, `state`, `merged`, `mergedAt`, `createdAt` (GitHub source time), `updatedAt`, `author`, `commitsCount`, `changedFilesCount`, `sourceSystem`, `sourceEndpoint`, `sourceUrl`, timestamps.

Unique index: `{ repositoryKey: 1, number: 1 }`. Nullable GitHub counts stay nullable; do not synthesize counts from uncollected pages.

### Commit (extend existing `Commit`)

`entityId`, `repositoryKey`, `repo`, `sha`, `message`, `author`, `date` (normalized `authored_at`), `url`, existing `filesChanged`, existing `referencedIssueNumbers` for legacy behavior only, `sourceSystem`, `sourceEndpoints`, `sourceUrl`, timestamps.

Unique index: `{ repositoryKey: 1, sha: 1 }`. The current `{ repo, sha }` index may be retained during migration and dropped only after canonical-key validation. Preserve existing file path summaries for compatibility, but use `ChangedFileObservation` for full file facts and source attribution.

### ChangedFileObservation

`entityId`, `repositoryKey`, `sourceEntityType` (`commit` or `pull_request`), `sourceEntityId`, `path`, `status`, `additions`, `deletions`, `sourceSystem`, `sourceEndpoint`, `sourceUrl`, timestamps.

Unique index: `{ repositoryKey: 1, sourceEntityType: 1, sourceEntityId: 1, path: 1 }`. This corresponds to Phase 3’s source-scoped file identity. Do not put observations into `Component`: a component is an aggregate path, while an observation records a change made by one source entity.

### Relationship and evidence

Relationship document: `entityId`/`edgeKey`, `repositoryKey`, `sourceEntityType`, `sourceEntityId`, `targetEntityType`, `targetEntityId`, `targetRepositoryKey`, `relationType`, `evidence[]`, timestamps.

Unique index: `{ edgeKey: 1 }` (equal to the deterministic Phase 3 `entity_id`) or the equivalent compound key `{ repositoryKey, relationType, sourceEntityId, targetRepositoryKey, targetEntityId }`. Choose one authoritative unique key and test it against cross-repository issue targets.

Each evidence item should retain `kind` (`github_api`, `explicit_text`, or future `inference`), `sourceEndpoint`, `sourceUrl`, `sourceField`, matched `text`, `sourceCommitSha`, `targetInCollection`, and `sourcePullRequestMerged`. Add a deterministic `evidenceKey` (for example, a hash of canonical evidence JSON) if evidence is stored as an embedded array; use `$addToSet` keyed by that stable representation so retries do not duplicate evidence.

Keep these current relationship classes separate:

- `pull_request_contains_commit`, `pull_request_changes_file`, and `commit_changes_file`: observed GitHub API relationships.
- `explicitly_references_issue`: explicit closing-keyword text, not a verified fix.
- `inferred_candidate`: future inferred evidence only; do not mix it with the confirmed API edges or explicit-text edges.

Never make a `fixCommitShas` claim solely from an explicit reference or a matching number. Preserve repository context on both relationship endpoints.

### CollectionRun

`repositoryKey`, `runId`, `status` (`complete`/`partial`), `counts`, `stages`, `warnings`, `emptyResults`, `failedPullRequests`, `skippedPullRequests`, `normalizationWarnings`, `persistence` stage status/error summary, start/finish timestamps, `schemaVersion`.

Unique index: `{ repositoryKey: 1, runId: 1 }`. Phase 3 currently leaves `run_id` unset; Phase 4 must create a stable run/idempotency key at request start and carry it in the private ingest envelope. Persist the original collector status and metadata unchanged; persistence outcome is a separate field and must not turn a partial GitHub collection into a complete one.

## 5. Idempotent upsert and partial-run semantics

- Upsert each entity by its repository-scoped unique key. Repeating an analysis must not create duplicate issues, PRs, commits, file observations, or relationship edges.
- For source snapshot fields, update only from fields actually supplied by the current normalized source. Define explicit clearing semantics for nullable values such as a PR becoming unmerged/open; do not replace a known value with `null` merely because a bounded/partial payload omitted it.
- Merge provenance endpoints and relationship evidence additively with deterministic deduplication. Do not replace an existing evidence list with the most recent run’s smaller list.
- Write each `CollectionRun` even when entity writes partially fail. Record per-collection attempted/succeeded/failed counts and a sanitized error category; do not record credentials or raw request bodies in logs.
- A partial run is an observation of returned data, not an authoritative repository snapshot. Upsert returned entities, mark them last-seen for that run, retain old entities absent from the response, and never issue a repository-wide delete based on missing records. Only a separately designed, demonstrably complete reconciliation could support deletion.
- Make retries idempotent using the same run key. If a batch fails after earlier batches committed, retrying must safely upsert prior records and finish remaining batches.
- Use Mongo transactions only if the deployed topology supports them and the project chooses to require that topology. The documented local Mongo URI may be standalone; do not assume multi-document transactions. Batch writes should otherwise report partial persistence explicitly in the run record and support retry.

## 6. Payload sizing and batching

Express currently installs `express.json()` with its default body limit (100 KB). A normalized analysis with hundreds of issue and PR descriptions can exceed that limit. Do not raise it without measurement or accept an unbounded request.

Prefer a run-oriented bounded ingestion protocol: initialize/authorize a run, send typed batches (for example, repository, issues, PRs, commits, changed files, relationships), then finalize with original collection metadata. Set both a maximum document count and maximum serialized byte size per batch, and reject oversized individual records with a recorded error. Choose numeric limits after measuring representative payloads, including large issue bodies. Keep the same idempotency key across all batches and retries.

## 7. Migration and compatibility risks

1. **Option A duplicates a compatibility projection by design:** Issue is canonical; a linked Bug projection exists only for bug classification and legacy enrichment/response compatibility. Enforce one Bug per Issue with unique sparse `issueId` and maintain copied fields from Issue. Do not treat the two documents as separately editable authorities.
2. **Existing unique keys:** current `repo` values may differ only by case. Canonicalizing to `repositoryKey` may reveal duplicates the current `{ repo, number }` index permits. Audit and resolve before building the new unique indexes; do not auto-merge conflicting documents or ObjectId references.
3. **Backfill ordering:** do not create a unique `{ repositoryKey, number }` index on existing Bug data before every legacy document has a canonical key and duplicate audit has passed. Missing repository keys can collide under a unique compound index.
4. **Required versus optional values:** Phase 3 permits null issue title/date and commit message, while current Bug/Commit schemas require some corresponding fields. New Issue fields must allow missing GitHub values; extend Commit validation or define an explicit reject/quarantine policy. Relax Bug core-field requirements only together with a serializer that hydrates linked projections. Never fabricate values.
5. **Legacy endpoint output:** current `/api/bugs` returns Mongoose documents directly. New `issueId`, `repositoryKey`, and provenance fields must be hidden, and the later link-aware serializer must preserve all legacy fields/types/order/count and bug-only membership.
6. **ObjectId references:** preserve all current Bug `_id` values. `BugFamily.bugIds`, Bug `familyId`, `similarBugIds`, and `componentIds` must continue resolving. Do not use a collection rename/copy or delete that leaves these references dangling.
7. **Semantic references:** do not populate `fixCommitShas` from generic textual references. Audit the Node collector’s bare-number extraction separately before representing those entries as verified relations.
8. **Component semantics:** do not reuse `Component` as the source-specific changed-file store or change `bugCount` meaning.
9. **Index deployment:** model declarations do not prove production indexes exist or can be built. Check actual index definitions and duplicate data before deployment.
10. **Partial writes and size:** bounded collection can produce large incomplete batches; Mongo write errors can occur after earlier batches commit. Run metadata, bounded batching, per-batch results, idempotent retry, and persistence status are required.
11. **Internal route exposure:** current Express CORS is permissive and routes lack authentication. A write endpoint without independent service authentication and network restriction would expose database writes.

### Live database checks — NOT VERIFIED

This design review did not connect to MongoDB. The following facts are therefore **NOT VERIFIED** against the live database: actual collection counts and names; actual deployed indexes; whether the model-declared unique indexes exist; normalized `(repositoryKey, number)` duplicate groups including case variants; malformed `repo` values; dangling or cross-repository `BugFamily`, `familyId`, `similarBugIds`, and `componentIds` ObjectId references; Node writers outside this checkout; MongoDB version/replica-set topology; and whether a backup can be restored. No live data or credentials were read.

Before any index build or migration, run a read-only audit on a restored staging copy. Normalize each `repo` value to case-folded `owner/name`, group by that key plus issue number, and report groups with count greater than one. Independently validate every referenced ObjectId against its target collection and verify that each Bug's repository context agrees with related family/component records. Resolve each duplicate/reference conflict explicitly; never choose a survivor by recency alone.

### Backup, verification, and staged rollback

Before any future live migration, take a consistent full database backup (including collection metadata and indexes) using the approved MongoDB backup tooling; store it encrypted and access-controlled. Restore that archive into an isolated staging database, then compare per-collection counts, index definitions, and all relevant ObjectId-reference checks with the source audit. A backup is not verified until the isolated restore and checks succeed. Do not put a credential-bearing URI in command history, logs, or this document.

For recommended additive Option A, deploy schema/index changes in stages: first create the new `issues` collection/indexes; then backfill optional `repositoryKey` and `issueId` links in bounded, idempotent batches; verify counts, uniqueness, and references; finally enable ingestion behind a feature flag. Keep `bugs` and its old unique index intact. If any validation fails, disable ingestion and roll back code/config; leave additive Issue documents in place for inspection rather than deleting them. If Bug documents were linked/updated, restore from the verified backup or apply an audited reversal keyed by the recorded migration/run ID. Never drop `bugs` or rebuild Bug ObjectIds as rollback.

Option B requires a separate maintenance window: stop all writers, take and restore-verify the backup, audit conflicts/references, rehearse the rename/copy preserving `_id`, deploy model alias and `/api/bugs` serializer together, verify exact contract and reference counts, then resume writes. Rollback requires stopping writers and restoring the original `bugs` collection/indexes from the verified backup while preserving any post-cutover writes in a separately reconciled delta. Do not attempt Option B until this plan and the live audit are approved.

## 8. Recommended implementation sequence

1. Approve Option A (canonical `issues` plus linked Bug compatibility projection) or explicitly approve the more invasive Option B migration. Confirm the bug-label rule and whether Bug membership is permanent once observed; Option A is recommended.
2. Back up MongoDB and verify an isolated restore. Audit live collection counts/indexes, case-folded duplicate `(repo, number)` groups, and all ObjectId references. These checks are currently **NOT VERIFIED**.
3. Finalize exact `Issue`, Bug projection link, repository-key backfill, nullable-field behavior, schema version, natural keys, evidence fingerprinting, run-key generation, and maximum batch bytes/documents.
4. Under Option A, add the `Issue` model/collection and indexes, then add only optional hidden `issueId` linkage and its sparse unique index to Bug. Preserve all existing Bug ObjectIds, current Bug index, Mongoose references, and `/api/bugs` behavior. Backfill/link only after the duplicate audit; create the Bug repositoryKey unique index only after every old record is keyed and collision-free.
5. Extend Commit and add PullRequest, ChangedFileObservation, Relationship, and CollectionRun models/indexes. Keep `Component` as an aggregate. Add model tests for schema validation, optional fields, natural IDs, refs, and index declarations.
6. Add a private authenticated Node ingestion API with validation, bounded typed batches, idempotent bulk upserts, per-stage write outcomes, and run persistence. It must accept normalized data and make no GitHub requests.
7. Add Python transport after normalization, using the stable run/idempotency key and safe failure logging. Keep `POST /api/repositories/analyze` response fields/types unchanged; persistence status belongs in internal run diagnostics.
8. Test repeated analyses, later bug classification of the same Issue, partial runs, evidence merging, migration/link retries, malformed input, authorization, oversized batches, write failures, and exact legacy `/api/bugs` response semantics.
9. Run a bounded end-to-end staging analysis. Verify one Mongo owner, stable keys, retained partial metadata, no deletion for absent records, correct one-to-one Issue/Bug links, preserved ObjectId references, unchanged API output, and safe retry before enabling production writes.

## 9. Decisions to confirm before Phase 4.2

- Approve Option A as documented or select Option B and authorize a separately planned data migration. Confirm `issueId` as the one-to-one Bug projection link and the stable bug-label/classification rule.
- Confirm the `/api/bugs` hydration behavior for linked projections. Recommended: Issue supplies GitHub fields and Bug supplies legacy enrichment, with a serializer preserving the existing response contract.
- Confirm deployment topology and whether the internal ingestion API can be restricted to private/loopback networking; select the secret provisioning method for `BUGSCOPE_INGEST_TOKEN`.
- Confirm whether the target Mongo deployment supports transactions. The design does not require them and can use idempotent batches with run-level partial-write status.
- Confirm retention policy for collection runs and relationship/file observations, which can grow with repeated analyses.
- Confirm measured maximum body/batch sizes and whether failed or malformed optional records are rejected, quarantined, or stored with null fields.
- Complete the live MongoDB audit and backup/restore verification; these remain **NOT VERIFIED** and are mandatory before adding unique indexes to populated Bug data or performing a migration.

## 10. Phase 4.2 model-preparation implementation notes

The additive Mongoose model preparation keeps Option A. `Repository`, `Issue`, `PullRequest`, `ChangedFileObservation`, `Relationship`, and `CollectionRun` are separate models. `Bug` remains mapped to `bugs` with its existing ObjectId/reference fields and `{ repo, number }` unique key. Its optional `issueId` points to the canonical Issue ObjectId; it is excluded from default queries. `Commit` retains its existing `{ repo, sha }` unique key and legacy fields, with optional normalized identity and provenance fields. No migration, ingestion route, Python-to-Node transport, or live database write is part of model preparation.

### Identifier mapping

Phase 3 `entity_id` strings are stored as `entityId` on normalized entities and relationships for traceability and idempotent matching. MongoDB `_id` remains the ObjectId storage/reference key. The Bug-to-Issue `issueId` reference therefore stores the Issue ObjectId, not the Phase 3 string. Repository-scoped natural keys are represented by `repositoryKey` (case-folded `owner/name`) plus issue/PR number, or commit SHA. Changed-file observations are keyed by repository, source type, source entity ID, and path. Relationship `entityId` is the deterministic Phase 3 relationship identity. Evidence items require a deterministic `evidenceKey` at ingestion; the normalizer's evidence model does not currently emit that persistence key.

### Declared indexes and deployment preflight

The new collections declare unique indexes on Repository `repositoryKey`; Issue and PullRequest `(repositoryKey, number)`; ChangedFileObservation `(repositoryKey, sourceEntityType, sourceEntityId, path)`; Relationship `entityId`; and CollectionRun `(repositoryKey, runId)`. These collections are new in this design, but index creation still must be coordinated with ingestion rollout.

The existing Bug `{ repo, number }` key remains unchanged. The added unique sparse Bug `issueId` index tolerates legacy documents with no link, but any manually populated `issueId` values must be checked for duplicates before MongoDB builds it. Do not store `null` for an unlinked document. Bug `repositoryKey` is optional and has no index yet; any future unique `(repositoryKey, number)` index requires a case-folded duplicate audit and full backfill first.

Commit retains unique `{ repo, sha }`. A second partial unique `{ repositoryKey, sha }` index applies only when `repositoryKey` is a string; audit any already-keyed Commit records for duplicate canonical pairs before allowing the index to build. Existing records without `repositoryKey` remain governed by the old business key. Ingestion must reconcile a normalized commit to an existing legacy record by repository and SHA rather than create a duplicate with a different display casing.

Model tests validate schema rules and declared index definitions without opening a MongoDB connection. They do not establish that a live database has these indexes, that index builds will succeed, or that existing data is duplicate-free. Those facts remain **NOT VERIFIED** until the required read-only audit is performed against a verified staging restore.

\n