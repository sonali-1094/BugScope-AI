const mongoose = require("mongoose");

const repositorySchema = new mongoose.Schema(
  {
    repositoryKey: {
      type: String,
      required: true,
      lowercase: true,
      match: /^[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+$/,
    },
    owner: { type: String, required: true },
    name: { type: String, required: true },
    fullName: { type: String, required: true },
    canonicalUrl: { type: String },
    description: { type: String },
    primaryLanguage: { type: String },
    visibility: { type: String },
    isPrivate: { type: Boolean },
    defaultBranch: { type: String },
    stars: { type: Number, min: 0, validate: Number.isInteger },
    forks: { type: Number, min: 0, validate: Number.isInteger },
    openIssuesCount: { type: Number, min: 0, validate: Number.isInteger },
    sourceSystem: { type: String, enum: ["github"], default: "github" },
    sourceEndpoint: { type: String, default: "github.repository" },
    sourceUrl: { type: String },
  },
  { timestamps: true, strict: "throw" }
);

repositorySchema.index({ repositoryKey: 1 }, { unique: true });

module.exports = mongoose.model("Repository", repositorySchema);
