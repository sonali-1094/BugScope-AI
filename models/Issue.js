const mongoose = require("mongoose");

const issueSchema = new mongoose.Schema(
  {
    // Mirrors Phase 3 entity_id: {repositoryKey}#issue:{number}.
    entityId: { type: String, required: true },
    repositoryKey: {
      type: String,
      required: true,
      lowercase: true,
      match: /^[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+$/,
    },
    repo: { type: String, required: true }, // display-cased owner/name
    number: { type: Number, required: true, min: 1, validate: Number.isInteger },
    title: { type: String },
    body: { type: String },
    state: { type: String, enum: ["open", "closed"] },
    // GitHub source time. Record timestamps use separate field names below.
    createdAt: { type: Date },
    closedAt: { type: Date },
    labels: [{ type: String }],
    author: { type: String },
    comments: { type: Number, min: 0, validate: Number.isInteger },
    url: { type: String },
    sourceSystem: { type: String, enum: ["github"], default: "github" },
    sourceEndpoint: { type: String, default: "github.repository_issues" },
    sourceUrl: { type: String },
    lastSeenRunId: { type: String },
  },
  {
    timestamps: { createdAt: "recordCreatedAt", updatedAt: "recordUpdatedAt" },
    strict: "throw",
  }
);

// Phase 3 stable identity is repository-scoped; Mongo ObjectId remains the
// storage identity and can be referenced by Bug.issueId.
issueSchema.index({ repositoryKey: 1, number: 1 }, { unique: true });

module.exports = mongoose.model("Issue", issueSchema);
