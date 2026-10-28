const express = require("express");
const router = express.Router();

const { listBugs } = require("../repositories/postgres");
const { getPool } = require("../config/db");

// Keep a clear response for older clients without maintaining a second writer.
router.post("/collect", (_req, res) => {
  res.status(410).json({
    error: "This collector endpoint is retired. Use FastAPI POST /api/repositories/analyze.",
  });
});

// GET /api/bugs?repo=axios/axios  — quick sanity check on what's stored
router.get("/bugs", async (req, res) => {
  try {
    const bugs = await listBugs(req.query.repo);
    res.json({ count: bugs.length, bugs });
  } catch (error) {
    console.error(`[api] bug query failed (${error.code || error.name})`);
    res.status(503).json({ error: "Bug records are temporarily unavailable" });
  }
});

// GET /api/commits?repo=axios/axios
router.get("/commits", async (req, res) => {
  try {
    const values = req.query.repo ? [req.query.repo] : [];
    const where = req.query.repo ? "WHERE r.full_name = $1" : "";
    const { rows } = await getPool().query(`SELECT c.sha,c.message,c.author,c.authored_at AS date,c.source_url AS url,r.full_name AS repo,c.created_at AS "createdAt",c.updated_at AS "updatedAt" FROM commits c JOIN repositories r USING(repository_key) ${where} ORDER BY c.authored_at DESC NULLS LAST LIMIT 50`, values);
    res.json({ count: rows.length, commits: rows });
  } catch (error) {
    console.error(`[api] commit query failed (${error.code || error.name})`);
    res.status(503).json({ error: "Commit records are temporarily unavailable" });
  }
});

module.exports = router;
