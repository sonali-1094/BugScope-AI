const mongoose = require("mongoose");

const commitSchema = new mongoose.Schema(
  {
    repo: { type: String, required: true, index: true },
    sha: { type: String, required: true },
    message: { type: String, required: true },
    author: { type: String },
    date: { type: Date },
    url: { type: String },
    filesChanged: [{ type: String }], // component paths touched by this commit
    // issue numbers this commit's message references, e.g. "fixes #123"
    referencedIssueNumbers: [{ type: Number }],
  },
  { timestamps: true }
);

commitSchema.index({ repo: 1, sha: 1 }, { unique: true });

module.exports = mongoose.model("Commit", commitSchema);
