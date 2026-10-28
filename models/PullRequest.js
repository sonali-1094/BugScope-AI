const mongoose = require("mongoose");

const pullRequestSchema = new mongoose.Schema(
  {
    // Mirrors Phase 3 entity_id: {repositoryKey}#pull:{number}.
    entityId: { type: String, required: true },
    repositoryKey: {
      type: String,
      required: true,
      lowercase: true,
      match: /^[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+$/,
    },
    repo: { type: String, required: true },
    number: { type: Number, required: true, min: 1, validate: Number.isInteger },
    title: { type: String },
    body: { type: String },
    state: { type: String, enum: ["open", "closed"] },
    merged: { type: Boolean },
    mergedAt: { type: Date },
    // GitHub source times; database record timestamps are separate fields.
    createdAt: { type: Date },
    updatedAt: { type: Date },
    author: { type: String },
    commitsCount: { type: Number, min: 0, validate: Number.isInteger },
    changedFilesCount: { type: Number, min: 0, validate: Number.isInteger },
    sourceSystem: { type: String, enum: ["github"], default: "github" },
    sourceEndpoint: { type: String, default: "github.pull_requests" },
    sourceUrl: { type: String },
    lastSeenRunId: { type: String },
  },
  {
    timestamps: { createdAt: "recordCreatedAt", updatedAt: "recordUpdatedAt" },
    strict: "throw",
  }
);

pullRequestSchema.index({ repositoryKey: 1, number: 1 }, { unique: true });

module.exports = mongoose.model("PullRequest", pullRequestSchema);
