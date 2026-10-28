const mongoose = require("mongoose");

const evidenceSchema = new mongoose.Schema(
  {
    // Ingestion should derive this deterministically from canonical evidence JSON.
    evidenceKey: { type: String, required: true },
    kind: { type: String, enum: ["github_api", "explicit_text", "inference"], required: true },
    sourceEndpoint: { type: String, required: true },
    sourceUrl: { type: String },
    sourceField: { type: String },
    text: { type: String },
    sourceCommitSha: { type: String, match: /^[0-9a-fA-F]{40,64}$/ },
    targetInCollection: { type: Boolean },
    sourcePullRequestMerged: { type: Boolean },
  },
  { _id: false, strict: "throw" }
);

const relationshipSchema = new mongoose.Schema(
  {
    // Mirrors Phase 3 relationship entity_id; distinct from Mongo's _id.
    entityId: { type: String, required: true },
    repositoryKey: {
      type: String,
      required: true,
      lowercase: true,
      match: /^[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+$/,
    },
    sourceEntityType: { type: String, enum: ["pull_request", "commit"], required: true },
    sourceEntityId: { type: String, required: true },
    targetEntityType: { type: String, enum: ["commit", "changed_file", "issue"], required: true },
    targetEntityId: { type: String, required: true },
    targetRepositoryKey: {
      type: String,
      required: true,
      lowercase: true,
      match: /^[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+$/,
    },
    relationType: {
      type: String,
      enum: [
        "pull_request_contains_commit",
        "pull_request_changes_file",
        "commit_changes_file",
        "explicitly_references_issue",
        "inferred_candidate",
      ],
      required: true,
    },
    evidence: { type: [evidenceSchema], default: [] },
    lastSeenRunId: { type: String },
  },
  { timestamps: true, strict: "throw" }
);

// entityId is deterministic from repository, relation type, source and target.
relationshipSchema.index({ entityId: 1 }, { unique: true });
relationshipSchema.index({ repositoryKey: 1, sourceEntityId: 1 });
relationshipSchema.index({ targetRepositoryKey: 1, targetEntityId: 1 });

module.exports = mongoose.model("Relationship", relationshipSchema);
