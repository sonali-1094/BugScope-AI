const { Octokit } = require("octokit");
const Bug = require("../models/Bug");
const Commit = require("../models/Commit");
const Component = require("../models/Component");

const octokit = new Octokit({ auth: process.env.GITHUB_TOKEN });

// Matches "fixes #123", "closes #45", "resolves #7", or a bare "#123"
const ISSUE_REF_REGEX = /\b(?:fix|fixes|fixed|close|closes|closed|resolve|resolves|resolved)?\s*#(\d+)\b/gi;

function extractIssueNumbers(message) {
  const numbers = new Set();
  let match;
  while ((match = ISSUE_REF_REGEX.exec(message)) !== null) {
    numbers.add(Number(match[1]));
  }
  return [...numbers];
}

/**
 * Pulls issues labeled as bugs for a repo and upserts them into MongoDB.
 * We only keep genuine issues (GitHub's API returns PRs as issues too,
 * so we filter those out) that carry a bug-like label.
 */
async function collectBugs(owner, repo, { bugLabels = ["bug", "Bug", "type: bug"] } = {}) {
  const repoFullName = `${owner}/${repo}`;
  let saved = 0;

  const iterator = octokit.paginate.iterator(octokit.rest.issues.listForRepo, {
    owner,
    repo,
    state: "all",
    per_page: 100,
  });

  for await (const { data: issues } of iterator) {
    for (const issue of issues) {
      if (issue.pull_request) continue; // skip PRs

      const labels = issue.labels.map((l) => (typeof l === "string" ? l : l.name));
      const isBug = labels.some((l) => bugLabels.includes(l));
      if (!isBug) continue;

      await Bug.findOneAndUpdate(
        { repo: repoFullName, number: issue.number },
        {
          repo: repoFullName,
          number: issue.number,
          title: issue.title,
          body: issue.body || "",
          labels,
          state: issue.state,
          createdAt: issue.created_at,
          closedAt: issue.closed_at || undefined,
          url: issue.html_url,
        },
        { upsert: true, new: true }
      );
      saved += 1;
    }
  }

  return saved;
}

/**
 * Pulls recent commits for a repo, records which issues they reference
 * (so we can later link bugs to their fixing commits), and tracks which
 * file paths ("components") each commit touches.
 *
 * maxCommits caps API usage — each commit needs a separate getCommit call
 * to read its changed files, so keep this modest for large repos.
 */
async function collectCommits(owner, repo, { maxCommits = 300 } = {}) {
  const repoFullName = `${owner}/${repo}`;
  let saved = 0;
  let seen = 0;

  const iterator = octokit.paginate.iterator(octokit.rest.repos.listCommits, {
    owner,
    repo,
    per_page: 100,
  });

  outer: for await (const { data: commits } of iterator) {
    for (const commit of commits) {
      if (seen >= maxCommits) break outer;
      seen += 1;

      const message = commit.commit.message || "";
      const referencedIssueNumbers = extractIssueNumbers(message);

      // Fetch file list for this commit (needed for component/hotspot tracking)
      let filesChanged = [];
      try {
        const { data: full } = await octokit.rest.repos.getCommit({
          owner,
          repo,
          ref: commit.sha,
        });
        filesChanged = (full.files || []).map((f) => f.filename);
      } catch (err) {
        console.warn(`[collector] could not fetch files for ${commit.sha}: ${err.message}`);
      }

      await Commit.findOneAndUpdate(
        { repo: repoFullName, sha: commit.sha },
        {
          repo: repoFullName,
          sha: commit.sha,
          message,
          author: commit.commit.author?.name,
          date: commit.commit.author?.date,
          url: commit.html_url,
          filesChanged,
          referencedIssueNumbers,
        },
        { upsert: true, new: true }
      );
      saved += 1;

      // Register/refresh components touched by this commit
      for (const path of filesChanged) {
        await Component.findOneAndUpdate(
          { repo: repoFullName, path },
          { $inc: { bugCount: 0 }, lastTouchedAt: commit.commit.author?.date },
          { upsert: true }
        );
      }

      // Link this commit back to any bug it references as a fix
      if (referencedIssueNumbers.length) {
        await Bug.updateMany(
          { repo: repoFullName, number: { $in: referencedIssueNumbers } },
          {
            $addToSet: { fixCommitShas: commit.sha },
          }
        );
      }
    }
  }

  return saved;
}

/**
 * Full Phase 1 run: bugs first (so commit linking has something to attach to),
 * then commits.
 */
async function collectRepository(owner, repo, options = {}) {
  const bugsSaved = await collectBugs(owner, repo, options);
  const commitsSaved = await collectCommits(owner, repo, options);
  return { repo: `${owner}/${repo}`, bugsSaved, commitsSaved };
}

module.exports = { collectRepository, collectBugs, collectCommits };
