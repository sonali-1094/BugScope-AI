const express = require("express");
const router = express.Router();

const { collectRepository } = require("../services/githubCollector");
const Bug = require("../models/Bug");
const Commit = require("../models/Commit");

// POST /api/collect  { "owner": "axios", "repo": "axios", "maxCommits": 300 }
router.post("/collect", async (req, res) => {
  const { owner, repo, maxCommits } = req.body;

  if (!owner || !repo) {
    return res.status(400).json({ error: "owner and repo are required" });
  }

  try {
    console.log(`[collector] starting collection for ${owner}/${repo}...`);
    const result = await collectRepository(owner, repo, { maxCommits });
    console.log("[collector] done:", result);
    res.json(result);
  } catch (err) {
    console.error("[collector] failed:", err);
    res.status(500).json({ error: err.message });
  }
});

// GET /api/bugs?repo=axios/axios  — quick sanity check on what's stored
router.get("/bugs", async (req, res) => {
  const { repo } = req.query;
  const filter = repo ? { repo } : {};
  const bugs = await Bug.find(filter).limit(50).sort({ createdAt: -1 });
  res.json({ count: bugs.length, bugs });
});

// GET /api/commits?repo=axios/axios
router.get("/commits", async (req, res) => {
  const { repo } = req.query;
  const filter = repo ? { repo } : {};
  const commits = await Commit.find(filter).limit(50).sort({ date: -1 });
  res.json({ count: commits.length, commits });
});

module.exports = router;
