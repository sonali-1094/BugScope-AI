const crypto = require("node:crypto");
const express = require("express");
const { persistNormalized } = require("../repositories/postgres");

const router = express.Router();
function authorized(req) {
  const expected = process.env.BUGSCOPE_INGEST_TOKEN;
  const actual = req.get("authorization")?.replace(/^Bearer\s+/i, "");
  if (!expected || !actual) return false;
  const left = Buffer.from(expected);
  const right = Buffer.from(actual);
  return left.length === right.length && crypto.timingSafeEqual(left, right);
}

router.post("/normalized-analysis", (req, res, next) => {
  if (!authorized(req)) return res.status(401).json({ error: "Unauthorized" });
  next();
}, express.json({ limit: "5mb" }), async (req, res) => {
  if (!req.body || req.body.schema_version !== 1) return res.status(400).json({ error: "Unsupported or missing schema_version" });
  try {
    const result = await persistNormalized(req.body.analysis);
    return res.status(200).json(result);
  } catch (error) {
    const status = error.status || 500;
    if (status === 500) console.error(`[ingest] normalized persistence failed (${error.code || error.name})`);
    return res.status(status).json({ error: status === 500 ? "Normalized data could not be persisted" : error.message });
  }
});

module.exports = router;
