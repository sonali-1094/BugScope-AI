const mongoose = require("mongoose");

const bugSchema = new mongoose.Schema(
  {
    repo: { type: String, required: true, index: true }, // e.g. "axios/axios"
    number: { type: Number, required: true }, // GitHub issue number
    // Optional link to the canonical general Issue; hidden from legacy API output.
    // Existing Bug ObjectIds and all current refs remain unchanged.
    issueId: { type: mongoose.Schema.Types.ObjectId, ref: "Issue", select: false },
    // Canonical case-folded owner/name key; backfill/index rollout is deferred.
    repositoryKey: { type: String, select: false },
    title: { type: String, required: true },
    body: { type: String, default: "" },
    labels: [{ type: String }],
    state: { type: String, enum: ["open", "closed"], required: true },
    createdAt: { type: Date, required: true },
    closedAt: { type: Date },
    url: { type: String },

    // populated in Phase 2 (Bug Family Intelligence)
    embedding: { type: [Number], default: undefined },

    // populated once we link commits (Phase 1b) and components
    componentIds: [{ type: mongoose.Schema.Types.ObjectId, ref: "Component" }],
    fixCommitShas: [{ type: String }], // commit(s) believed to fix this bug

    // populated in Phase 2/3 (grouping + knowledge graph)
    familyId: { type: mongoose.Schema.Types.ObjectId, ref: "BugFamily" },
    similarBugIds: [{ type: mongoose.Schema.Types.ObjectId, ref: "Bug" }],

    // populated in Phase 5 (Fix Effectiveness Engine)
    fixEffectivenessScore: { type: Number, min: 0, max: 100 },
  },
  { timestamps: true }
);

bugSchema.index({ repo: 1, number: 1 }, { unique: true });
// Sparse so existing Bug documents without an Issue link do not conflict.
// Preflight this index against any manually-added issueId values before deployment.
bugSchema.index({ issueId: 1 }, { unique: true, sparse: true });

module.exports = mongoose.model("Bug", bugSchema);
