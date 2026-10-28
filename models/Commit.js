const mongoose = require("mongoose");

const commitSchema = new mongoose.Schema(
  {
    repo: { type: String, required: true, index: true },
    // Normalized, case-folded owner/name key. Existing rows may not have it;
    // retain the established repo + sha key during the staged backfill.
    repositoryKey: {
      type: String,
      lowercase: true,
      match: /^[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+$/,
    },
    // Phase 3 stable identifier; optional on legacy records.
    entityId: { type: String },
    sha: { type: String, required: true, match: /^[0-9a-fA-F]{40,64}$/ },
    // GitHub may omit commit text; legacy collector continues to provide it.
    message: { type: String },
    author: { type: String },
    date: { type: Date },
    url: { type: String },
    filesChanged: [{ type: String }], // component paths touched by this commit
    // issue numbers this commit's message references, e.g. "fixes #123"
    referencedIssueNumbers: [{ type: Number }],
    sourceSystem: { type: String, enum: ["github"], default: "github" },
    sourceEndpoints: [{ type: String }],
    sourceUrl: { type: String },
  },
  { timestamps: true }
);

commitSchema.index({ repo: 1, sha: 1 }, { unique: true });
// Applies only after a canonical repository key is populated. Existing legacy
// documents without repositoryKey remain governed by { repo, sha }.
// Audit keyed records for duplicates before allowing MongoDB to build this index.
commitSchema.index(
  { repositoryKey: 1, sha: 1 },
  {
    unique: true,
    partialFilterExpression: { repositoryKey: { $type: "string" } },
  }
);

module.exports = mongoose.model("Commit", commitSchema);
