const mongoose = require("mongoose");

const bugFamilySchema = new mongoose.Schema(
  {
    repo: { type: String, required: true, index: true },
    name: { type: String, required: true }, // e.g. "Payment Validation Family"
    bugIds: [{ type: mongoose.Schema.Types.ObjectId, ref: "Bug" }],
    // filled in later phases
    evolutionSummary: { type: String },
    averageFixEffectiveness: { type: Number },
  },
  { timestamps: true }
);

module.exports = mongoose.model("BugFamily", bugFamilySchema);
