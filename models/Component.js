const mongoose = require("mongoose");

// A "component" is a file or module path touched by commits/bugs.
// This is what the Risk Engine later scores for hotspots.
const componentSchema = new mongoose.Schema(
  {
    repo: { type: String, required: true, index: true }, // e.g. "axios/axios"
    path: { type: String, required: true }, // e.g. "lib/adapters/http.js"
    bugCount: { type: Number, default: 0 },
    lastTouchedAt: { type: Date },
  },
  { timestamps: true }
);

componentSchema.index({ repo: 1, path: 1 }, { unique: true });

module.exports = mongoose.model("Component", componentSchema);
