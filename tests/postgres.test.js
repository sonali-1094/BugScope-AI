const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

process.env.DATABASE_URL ||= "postgresql://test:test@127.0.0.1/test";
const { getPool } = require("../config/db");
const { persistNormalized, formatBug } = require("../repositories/postgres");

const pool = getPool();
function normalized(evidence = []) {
  return {
    repository: { repository_key: "owner/repo", owner: "owner", name: "repo", full_name: "owner/repo" },
    issues: [], pull_requests: [], commits: [], changed_files: [], relationships: [], normalization_warnings: [],
    collection_run: { repository_key: "owner/repo", run_id: "run-1", status: "partial", counts: {}, stages: {}, warnings: [], empty_results: [], failed_pull_requests: [], skipped_pull_requests: 0 },
    ...(evidence.length ? { relationships: [{ entity_id: "edge-1", repository_key: "owner/repo", source_entity_type: "commit", source_entity_id: "owner/repo#commit:abc", target_entity_type: "issue", target_entity_id: "owner/repo#issue:1", target_repository_key: "owner/repo", relation_type: "explicitly_references_issue", evidence }] } : {}),
  };
}

test("initial migration declares repository-scoped uniqueness and foreign keys without destructive SQL", () => {
  const sql = fs.readFileSync(path.join(__dirname, "..", "migrations", "001_initial_schema.sql"), "utf8");
  for (const table of ["repositories", "issues", "bugs", "pull_requests", "commits", "changed_file_observations", "relationships", "collection_runs", "components", "bug_families"]) {
    assert.match(sql, new RegExp(`CREATE TABLE IF NOT EXISTS ${table}\\b`));
  }
  assert.match(sql, /UNIQUE \(repository_key, number\)/);
  assert.match(sql, /UNIQUE \(repository_key, sha\)/);
  assert.match(sql, /REFERENCES issues\(repository_key, number\)/);
  assert.doesNotMatch(sql, /\bDROP\s+TABLE\b|\bDELETE\s+FROM\b/i);
});

test("normalized persistence is transactional, parameterized, and keeps partial results additive", async () => {
  const queries = [];
  const client = {
    async query(sql, values) { queries.push({ sql, values }); return { rows: [], rowCount: 1 }; },
    release() {},
  };
  const originalConnect = pool.connect;
  pool.connect = async () => client;
  try {
    const result = await persistNormalized(normalized());
    assert.equal(result.persisted, true);
    assert.equal(queries[0].sql, "BEGIN");
    assert.equal(queries.at(-1).sql, "COMMIT");
    assert.ok(queries.some(({ sql, values }) => sql.includes("ON CONFLICT(repository_key) DO UPDATE") && values.includes("owner/repo")));
    assert.ok(queries.every(({ sql }) => !/^\s*DELETE\s/i.test(sql)));
  } finally { pool.connect = originalConnect; }
});

test("invalid evidence is rejected and transaction rolled back", async () => {
  const queries = [];
  const client = { async query(sql) { queries.push(sql); return { rows: [] }; }, release() {} };
  const originalConnect = pool.connect;
  pool.connect = async () => client;
  try {
    await assert.rejects(persistNormalized(normalized([{ kind: "assumed_fix" }])), { status: 400 });
    assert.ok(queries.includes("ROLLBACK"));
    assert.ok(!queries.includes("COMMIT"));
  } finally { pool.connect = originalConnect; }
});

test("legacy bug serializer keeps the endpoint envelope fields", () => {
  const bug = formatBug({ _id: "42", __v: 0, repo: "owner/repo", number: 7, title: "Issue", body: "", labels: ["bug"], state: "closed", createdAt: null, closedAt: null, url: null, embedding: [], componentIds: [], fixCommitShas: [], familyId: null, similarBugIds: [], fixEffectivenessScore: null, recordCreatedAt: "2025-01-01T00:00:00Z", updatedAt: "2025-01-02T00:00:00Z" });
  assert.deepEqual(Object.keys(bug), ["_id", "__v", "repo", "number", "title", "body", "labels", "state", "createdAt", "closedAt", "url", "embedding", "componentIds", "fixCommitShas", "familyId", "similarBugIds", "fixEffectivenessScore", "updatedAt"]);
  assert.equal(bug.createdAt, "2025-01-01T00:00:00Z");
});
