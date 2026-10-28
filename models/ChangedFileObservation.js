const mongoose = require("mongoose");

const changedFileObservationSchema = new mongoose.Schema(
  {
    // Mirrors Phase 3 entity_id and scopes the same path to its source entity.
    entityId: { type: String, required: true },
    repositoryKey: {
      type: String,
      required: true,
      lowercase: true,
      match: /^[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+$/,
    },
    sourceEntityType: { type: String, enum: ["commit", "pull_request"], required: true },
    sourceEntityId: { type: String, required: true },
    path: { type: String, required: true, trim: true, minlength: 1 },
    status: { type: String },
    additions: { type: Number, min: 0, validate: Number.isInteger },
    deletions: { type: Number, min: 0, validate: Number.isInteger },
    sourceSystem: { type: String, enum: ["github"], default: "github" },
    sourceEndpoint: { type: String, required: true },
    sourceUrl: { type: String },
    lastSeenRunId: { type: String },
  },
  { timestamps: true, strict: "throw" }
);

changedFileObservationSchema.index(
  { repositoryKey: 1, sourceEntityType: 1, sourceEntityId: 1, path: 1 },
  { unique: true }
);

module.exports = mongoose.model("ChangedFileObservation", changedFileObservationSchema);
