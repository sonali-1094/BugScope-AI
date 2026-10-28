const mongoose = require("mongoose");

const collectionRunSchema = new mongoose.Schema(
  {
    repositoryKey: {
      type: String,
      required: true,
      lowercase: true,
      match: /^[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+$/,
    },
    runId: { type: String, required: true },
    status: { type: String, enum: ["complete", "partial"], required: true },
    counts: { type: mongoose.Schema.Types.Mixed, default: {} },
    stages: { type: mongoose.Schema.Types.Mixed, default: {} },
    warnings: [{ type: String }],
    emptyResults: [{ type: String }],
    failedPullRequests: [{ type: mongoose.Schema.Types.Mixed }],
    skippedPullRequests: { type: Number, min: 0, validate: Number.isInteger, default: 0 },
    normalizationWarnings: [{ type: String }],
    persistence: { type: mongoose.Schema.Types.Mixed },
    startedAt: { type: Date },
    finishedAt: { type: Date },
    schemaVersion: { type: Number, min: 1, validate: Number.isInteger, default: 1 },
  },
  { timestamps: true, strict: "throw" }
);

collectionRunSchema.index({ repositoryKey: 1, runId: 1 }, { unique: true });

module.exports = mongoose.model("CollectionRun", collectionRunSchema);
