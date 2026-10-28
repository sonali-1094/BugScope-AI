const assert = require("node:assert/strict");
const test = require("node:test");

const Bug = require("../models/Bug");
const Commit = require("../models/Commit");
const Component = require("../models/Component");
const BugFamily = require("../models/BugFamily");
const Repository = require("../models/Repository");
const Issue = require("../models/Issue");
const PullRequest = require("../models/PullRequest");
const ChangedFileObservation = require("../models/ChangedFileObservation");
const Relationship = require("../models/Relationship");
const CollectionRun = require("../models/CollectionRun");

const SHA = "a".repeat(40);

function hasIndex(Model, keys, predicate = () => true) {
  return Model.schema.indexes().some(([indexKeys, options]) =>
    JSON.stringify(indexKeys) === JSON.stringify(keys) && predicate(options)
  );
}

test("models map to expected collections without connecting to MongoDB", () => {
  assert.equal(Repository.collection.name, "repositories");
  assert.equal(Issue.collection.name, "issues");
  assert.equal(Bug.collection.name, "bugs");
  assert.equal(PullRequest.collection.name, "pullrequests");
  assert.equal(Commit.collection.name, "commits");
  assert.equal(ChangedFileObservation.collection.name, "changedfileobservations");
  assert.equal(Relationship.collection.name, "relationships");
  assert.equal(CollectionRun.collection.name, "collectionruns");
  assert.equal(Component.collection.name, "components");
  assert.equal(BugFamily.collection.name, "bugfamilies");
});

test("new records enforce required identity fields while GitHub optional fields may be absent", () => {
  assert.ok(new Repository({}).validateSync().errors.repositoryKey);
  assert.ok(new Issue({}).validateSync().errors.repositoryKey);
  assert.ok(new PullRequest({}).validateSync().errors.repositoryKey);
  assert.ok(new ChangedFileObservation({}).validateSync().errors.entityId);
  assert.ok(new Relationship({}).validateSync().errors.entityId);
  assert.ok(new CollectionRun({}).validateSync().errors.runId);

  const issue = new Issue({
    entityId: "owner/repo#issue:5",
    repositoryKey: "Owner/Repo",
    repo: "Owner/Repo",
    number: 5,
  });
  assert.equal(issue.validateSync(), undefined);
  assert.equal(issue.repositoryKey, "owner/repo");
  assert.equal(issue.title, undefined);
  assert.equal(issue.createdAt, undefined);

  const pullRequest = new PullRequest({
    entityId: "owner/repo#pull:8",
    repositoryKey: "owner/repo",
    repo: "owner/repo",
    number: 8,
  });
  assert.equal(pullRequest.validateSync(), undefined);
  assert.equal(pullRequest.commitsCount, undefined);

  const commit = new Commit({ repo: "owner/repo", sha: SHA });
  assert.equal(commit.validateSync(), undefined);
  assert.equal(commit.message, undefined);
});

test("repository-scoped unique indexes align with normalized identities", () => {
  assert.ok(hasIndex(Repository, { repositoryKey: 1 }, (options) => options.unique === true));
  assert.ok(hasIndex(Issue, { repositoryKey: 1, number: 1 }, (options) => options.unique === true));
  assert.ok(hasIndex(PullRequest, { repositoryKey: 1, number: 1 }, (options) => options.unique === true));
  assert.ok(hasIndex(
    ChangedFileObservation,
    { repositoryKey: 1, sourceEntityType: 1, sourceEntityId: 1, path: 1 },
    (options) => options.unique === true
  ));
  assert.ok(hasIndex(CollectionRun, { repositoryKey: 1, runId: 1 }, (options) => options.unique === true));
  assert.ok(hasIndex(Bug, { repo: 1, number: 1 }, (options) => options.unique === true));
  assert.ok(hasIndex(Bug, { issueId: 1 }, (options) => options.unique === true && options.sparse === true));

  // Preserve the established business key and scope the added normalized-key
  // index to records that have been explicitly backfilled with repositoryKey.
  assert.ok(hasIndex(Commit, { repo: 1, sha: 1 }, (options) => options.unique === true));
  assert.ok(hasIndex(Commit, { repositoryKey: 1, sha: 1 }, (options) =>
    options.unique === true && options.partialFilterExpression.repositoryKey.$type === "string"
  ));
});

test("Bug compatibility reference and existing Mongoose refs remain intact", () => {
  assert.equal(Bug.schema.path("issueId").options.ref, "Issue");
  assert.equal(Bug.schema.path("issueId").options.select, false);
  assert.equal(Bug.schema.path("familyId").options.ref, "BugFamily");
  assert.equal(Bug.schema.path("componentIds").caster.options.ref, "Component");
  assert.equal(Bug.schema.path("similarBugIds").caster.options.ref, "Bug");
  assert.equal(BugFamily.schema.path("bugIds").caster.options.ref, "Bug");
});

test("relationship evidence preserves distinct API, explicit-text, and inference categories", () => {
  const base = {
    entityId: "owner/repo#edge:explicitly_references_issue:source->target",
    repositoryKey: "owner/repo",
    sourceEntityType: "pull_request",
    sourceEntityId: "owner/repo#pull:8",
    targetEntityType: "issue",
    targetEntityId: "owner/repo#issue:5",
    targetRepositoryKey: "owner/repo",
    relationType: "explicitly_references_issue",
    evidence: [{
      evidenceKey: "evidence-1",
      kind: "explicit_text",
      sourceEndpoint: "github.pull_request_description",
      text: "Closes #5",
    }],
  };
  const relationship = new Relationship(base);
  assert.equal(relationship.validateSync(), undefined);
  assert.equal(relationship.evidence[0].kind, "explicit_text");
  assert.equal(relationship.evidence[0]._id, undefined);

  const apiEvidence = new Relationship({
    ...base,
    entityId: "owner/repo#edge:pull_request_contains_commit:source->target",
    relationType: "pull_request_contains_commit",
    evidence: [{ evidenceKey: "api-1", kind: "github_api", sourceEndpoint: "github.pull_request_commits" }],
  });
  assert.equal(apiEvidence.validateSync(), undefined);
  assert.equal(apiEvidence.evidence[0].kind, "github_api");

  const unsupportedFixClaim = new Relationship({ ...base, relationType: "fixes_issue" });
  assert.ok(unsupportedFixClaim.validateSync().errors.relationType);
  const unsupportedEvidenceKind = new Relationship({
    ...base,
    evidence: [{ ...base.evidence[0], kind: "assumed_fix" }],
  });
  assert.ok(unsupportedEvidenceKind.validateSync().errors["evidence.0.kind"]);
});

test("commit normalized provenance is optional and legacy fields remain", () => {
  const commit = new Commit({
    repo: "owner/repo",
    sha: SHA,
    repositoryKey: "Owner/Repo",
    entityId: `owner/repo#commit:${SHA}`,
    sourceEndpoints: ["github.repository_commits", "github.pull_request_commits"],
    sourceUrl: `https://github.com/owner/repo/commit/${SHA}`,
  });
  assert.equal(commit.validateSync(), undefined);
  assert.equal(commit.repositoryKey, "owner/repo");
  assert.deepEqual(commit.sourceEndpoints, ["github.repository_commits", "github.pull_request_commits"]);
  assert.ok(Commit.schema.path("filesChanged"));
  assert.ok(Commit.schema.path("referencedIssueNumbers"));
});
