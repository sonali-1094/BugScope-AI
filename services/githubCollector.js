const { Octokit } = require("octokit");
const { getPool } = require("../config/db");

const ISSUE_REF_REGEX = /\b(?:fix|fixes|fixed|close|closes|closed|resolve|resolves|resolved)?\s*#(\d+)\b/gi;
function extractIssueNumbers(message) {
  const numbers = new Set();
  let match;
  while ((match = ISSUE_REF_REGEX.exec(message || "")) !== null) numbers.add(Number(match[1]));
  return [...numbers];
}

async function ensureRepository(owner, name, details = {}) {
  const key = `${owner}/${name}`.toLowerCase();
  await getPool().query(`INSERT INTO repositories(repository_key,owner,name,full_name,canonical_url,source_url) VALUES($1,$2,$3,$4,$5,$5) ON CONFLICT(repository_key) DO UPDATE SET full_name=EXCLUDED.full_name,updated_at=now()`,
    [key, owner, name, `${owner}/${name}`, details.url || `https://github.com/${owner}/${name}`]);
  return key;
}

async function collectBugs(owner, repo, { bugLabels = ["bug", "Bug", "type: bug"] } = {}) {
  const octokit = new Octokit({ auth: process.env.GITHUB_TOKEN });
  const repositoryKey = await ensureRepository(owner, repo);
  let saved = 0;
  const iterator = octokit.paginate.iterator(octokit.rest.issues.listForRepo, { owner, repo, state: "all", per_page: 100 });
  for await (const { data: issues } of iterator) {
    for (const issue of issues) {
      if (issue.pull_request) continue;
      const labels = issue.labels.map((label) => typeof label === "string" ? label : label.name);
      if (!labels.some((label) => bugLabels.includes(label))) continue;
      const client = await getPool().connect();
      try {
        await client.query("BEGIN");
        const result = await client.query(`INSERT INTO issues(entity_id,repository_key,number,title,body,state,source_created_at,closed_at,labels,author,comments,url,source_url)
          VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$12) ON CONFLICT(repository_key,number) DO UPDATE SET title=EXCLUDED.title,body=EXCLUDED.body,state=EXCLUDED.state,source_created_at=EXCLUDED.source_created_at,closed_at=EXCLUDED.closed_at,labels=EXCLUDED.labels,author=EXCLUDED.author,comments=EXCLUDED.comments,url=EXCLUDED.url,updated_at=now() RETURNING id`,
        [`${repositoryKey}#issue:${issue.number}`, repositoryKey, issue.number, issue.title, issue.body, issue.state, issue.created_at, issue.closed_at, labels, issue.user?.login, issue.comments, issue.html_url]);
        await client.query(`INSERT INTO bugs(repository_key,number,title,body,labels,state,source_created_at,closed_at,url,issue_id) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
          ON CONFLICT(repository_key,number) DO UPDATE SET title=EXCLUDED.title,body=EXCLUDED.body,labels=EXCLUDED.labels,state=EXCLUDED.state,source_created_at=EXCLUDED.source_created_at,closed_at=EXCLUDED.closed_at,url=EXCLUDED.url,issue_id=EXCLUDED.issue_id,updated_at=now()`,
        [repositoryKey, issue.number, issue.title, issue.body, labels, issue.state, issue.created_at, issue.closed_at, issue.html_url, result.rows[0].id]);
        await client.query("COMMIT");
      } catch (error) { await client.query("ROLLBACK"); throw error; }
      finally { client.release(); }
      saved += 1;
    }
  }
  return saved;
}

async function collectCommits(owner, repo, { maxCommits = 300 } = {}) {
  const octokit = new Octokit({ auth: process.env.GITHUB_TOKEN });
  const repositoryKey = await ensureRepository(owner, repo);
  let saved = 0;
  const iterator = octokit.paginate.iterator(octokit.rest.repos.listCommits, { owner, repo, per_page: 100 });
  outer: for await (const { data: commits } of iterator) {
    for (const commit of commits) {
      if (saved >= maxCommits) break outer;
      const message = commit.commit.message || "";
      let filesChanged = [];
      let fileFacts = [];
      try {
        const { data } = await octokit.rest.repos.getCommit({ owner, repo, ref: commit.sha });
        fileFacts = data.files || [];
        filesChanged = fileFacts.map((file) => file.filename);
      } catch (error) {
        console.warn(`[collector] changed files unavailable (${error.status || error.name})`);
      }
      const sha = commit.sha.toLowerCase();
      await getPool().query(`INSERT INTO commits(entity_id,repository_key,sha,message,author,authored_at,source_endpoints,source_url)
        VALUES($1,$2,$3,$4,$5,$6,$7,$8) ON CONFLICT(repository_key,sha) DO UPDATE SET message=EXCLUDED.message,author=EXCLUDED.author,authored_at=EXCLUDED.authored_at,source_endpoints=(SELECT ARRAY(SELECT DISTINCT unnest(commits.source_endpoints || EXCLUDED.source_endpoints))),source_url=EXCLUDED.source_url,updated_at=now()`,
      [`${repositoryKey}#commit:${sha}`, repositoryKey, sha, message, commit.commit.author?.name, commit.commit.author?.date, ["github.repository_commits"], commit.html_url]);
      for (const file of fileFacts) {
        await getPool().query(`INSERT INTO changed_file_observations(entity_id,repository_key,source_entity_type,source_entity_id,source_commit_entity_id,path,status,additions,deletions,source_endpoint,source_url)
          VALUES($1,$2,'commit',$3,$3,$4,$5,$6,$7,'github.commit_files',$8) ON CONFLICT(repository_key,source_entity_type,source_entity_id,path) DO UPDATE SET status=COALESCE(EXCLUDED.status,changed_file_observations.status),additions=COALESCE(EXCLUDED.additions,changed_file_observations.additions),deletions=COALESCE(EXCLUDED.deletions,changed_file_observations.deletions),updated_at=now()`,
        [`${repositoryKey}#file:commit:${sha}:${file.filename}`, repositoryKey, `${repositoryKey}#commit:${sha}`, file.filename, file.status, file.additions, file.deletions, commit.html_url]);
        await getPool().query(`INSERT INTO components(repository_key,path,last_touched_at) VALUES($1,$2,$3) ON CONFLICT(repository_key,path) DO UPDATE SET last_touched_at=GREATEST(components.last_touched_at,EXCLUDED.last_touched_at),updated_at=now()`,
        [repositoryKey, file.filename, commit.commit.author?.date]);
      }
      saved += 1;
    }
  }
  return saved;
}

async function collectRepository(owner, repo, options = {}) {
  const bugsSaved = await collectBugs(owner, repo, options);
  const commitsSaved = await collectCommits(owner, repo, options);
  return { repo: `${owner}/${repo}`, bugsSaved, commitsSaved };
}

module.exports = { collectRepository, collectBugs, collectCommits, extractIssueNumbers };
