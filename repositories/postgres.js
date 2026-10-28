const { getPool } = require("../config/db");

function json(value) { return JSON.stringify(value ?? null); }

async function persistNormalized(data) {
  if (!data || typeof data !== "object" || Array.isArray(data)) throw Object.assign(new Error("Normalized analysis must be an object"), { status: 400 });
  const repository = data.repository;
  const run = data.collection_run || {};
  for (const key of ["issues", "pull_requests", "commits", "changed_files", "relationships", "normalization_warnings"]) {
    if (data[key] !== undefined && !Array.isArray(data[key])) throw Object.assign(new Error(`Invalid ${key} collection`), { status: 400 });
  }
  if (!repository?.repository_key || repository.repository_key !== repository.repository_key.toLowerCase()) {
    throw Object.assign(new Error("Invalid repository identity"), { status: 400 });
  }
  const runId = run.run_id;
  if (!runId || run.repository_key !== repository.repository_key) {
    throw Object.assign(new Error("A matching collection run ID is required"), { status: 400 });
  }
  const pool = getPool();
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    await client.query(`INSERT INTO repositories(repository_key,owner,name,full_name,canonical_url,description,primary_language,visibility,is_private,default_branch,stars,forks,open_issues_count,source_system,source_endpoint,source_url)
      VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
      ON CONFLICT(repository_key) DO UPDATE SET full_name=EXCLUDED.full_name, canonical_url=COALESCE(EXCLUDED.canonical_url,repositories.canonical_url), description=COALESCE(EXCLUDED.description,repositories.description), primary_language=COALESCE(EXCLUDED.primary_language,repositories.primary_language), visibility=COALESCE(EXCLUDED.visibility,repositories.visibility), is_private=COALESCE(EXCLUDED.is_private,repositories.is_private), default_branch=COALESCE(EXCLUDED.default_branch,repositories.default_branch), stars=COALESCE(EXCLUDED.stars,repositories.stars), forks=COALESCE(EXCLUDED.forks,repositories.forks), open_issues_count=COALESCE(EXCLUDED.open_issues_count,repositories.open_issues_count), updated_at=now()`,
    [repository.repository_key, repository.owner, repository.name, repository.full_name, repository.canonical_url, repository.description, repository.primary_language, repository.visibility, repository.is_private, repository.default_branch, repository.stars, repository.forks, repository.open_issues_count, repository.source_system, repository.source_endpoint, repository.source_url]);

    for (const issue of data.issues || []) {
      if (issue.repository_key !== repository.repository_key) throw Object.assign(new Error("Issue repository mismatch"), { status: 400 });
      const { rows } = await client.query(`INSERT INTO issues(entity_id,repository_key,number,title,body,state,source_created_at,closed_at,labels,author,comments,url,source_system,source_endpoint,source_url,last_seen_run_id)
        VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
        ON CONFLICT(repository_key,number) DO UPDATE SET entity_id=EXCLUDED.entity_id,title=COALESCE(EXCLUDED.title,issues.title),body=COALESCE(EXCLUDED.body,issues.body),state=COALESCE(EXCLUDED.state,issues.state),source_created_at=COALESCE(EXCLUDED.source_created_at,issues.source_created_at),closed_at=COALESCE(EXCLUDED.closed_at,issues.closed_at),labels=CASE WHEN cardinality(EXCLUDED.labels)>0 THEN EXCLUDED.labels ELSE issues.labels END,author=COALESCE(EXCLUDED.author,issues.author),comments=COALESCE(EXCLUDED.comments,issues.comments),url=COALESCE(EXCLUDED.url,issues.url),source_endpoint=EXCLUDED.source_endpoint,source_url=COALESCE(EXCLUDED.source_url,issues.source_url),last_seen_run_id=EXCLUDED.last_seen_run_id,updated_at=now() RETURNING id`,
      [issue.entity_id, issue.repository_key, issue.number, issue.title, issue.body, issue.state, issue.created_at, issue.closed_at, issue.labels, issue.author, issue.comments, issue.source_url, issue.source_system, issue.source_endpoint, issue.source_url, runId]);
      const isBug = (issue.labels || []).some((label) => ["bug", "type: bug"].includes(label.toLowerCase()));
      if (isBug) await client.query(`INSERT INTO bugs(repository_key,number,title,body,labels,state,source_created_at,closed_at,url,issue_id)
        VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) ON CONFLICT(repository_key,number) DO UPDATE SET title=COALESCE(EXCLUDED.title,bugs.title),body=COALESCE(EXCLUDED.body,bugs.body),labels=CASE WHEN cardinality(EXCLUDED.labels)>0 THEN EXCLUDED.labels ELSE bugs.labels END,state=COALESCE(EXCLUDED.state,bugs.state),source_created_at=COALESCE(EXCLUDED.source_created_at,bugs.source_created_at),closed_at=COALESCE(EXCLUDED.closed_at,bugs.closed_at),url=COALESCE(EXCLUDED.url,bugs.url),issue_id=EXCLUDED.issue_id,updated_at=now()`,
      [issue.repository_key, issue.number, issue.title, issue.body, issue.labels, issue.state, issue.created_at, issue.closed_at, issue.source_url, rows[0].id]);
    }

    for (const pr of data.pull_requests || []) {
      if (pr.repository_key !== repository.repository_key) throw Object.assign(new Error("Pull request repository mismatch"), { status: 400 });
      await client.query(`INSERT INTO pull_requests(entity_id,repository_key,number,title,body,state,merged,merged_at,source_created_at,source_updated_at,author,commits_count,changed_files_count,source_system,source_endpoint,source_url,last_seen_run_id) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17) ON CONFLICT(repository_key,number) DO UPDATE SET entity_id=EXCLUDED.entity_id,title=COALESCE(EXCLUDED.title,pull_requests.title),body=COALESCE(EXCLUDED.body,pull_requests.body),state=COALESCE(EXCLUDED.state,pull_requests.state),merged=COALESCE(EXCLUDED.merged,pull_requests.merged),merged_at=COALESCE(EXCLUDED.merged_at,pull_requests.merged_at),source_created_at=COALESCE(EXCLUDED.source_created_at,pull_requests.source_created_at),source_updated_at=COALESCE(EXCLUDED.source_updated_at,pull_requests.source_updated_at),author=COALESCE(EXCLUDED.author,pull_requests.author),commits_count=COALESCE(EXCLUDED.commits_count,pull_requests.commits_count),changed_files_count=COALESCE(EXCLUDED.changed_files_count,pull_requests.changed_files_count),source_url=COALESCE(EXCLUDED.source_url,pull_requests.source_url),last_seen_run_id=EXCLUDED.last_seen_run_id,updated_at=now()`,
      [pr.entity_id,pr.repository_key,pr.number,pr.title,pr.body,pr.state,pr.merged,pr.merged_at,pr.created_at,pr.updated_at,pr.author,pr.commits_count,pr.changed_files_count,pr.source_system,pr.source_endpoint,pr.source_url,runId]);
    }
    for (const commit of data.commits || []) {
      if (commit.repository_key !== repository.repository_key) throw Object.assign(new Error("Commit repository mismatch"), { status: 400 });
      await client.query(`INSERT INTO commits(entity_id,repository_key,sha,message,author,authored_at,source_system,source_endpoints,source_url) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9) ON CONFLICT(repository_key,sha) DO UPDATE SET entity_id=EXCLUDED.entity_id,message=COALESCE(EXCLUDED.message,commits.message),author=COALESCE(EXCLUDED.author,commits.author),authored_at=COALESCE(EXCLUDED.authored_at,commits.authored_at),source_endpoints=(SELECT ARRAY(SELECT DISTINCT unnest(commits.source_endpoints || EXCLUDED.source_endpoints))),source_url=COALESCE(EXCLUDED.source_url,commits.source_url),updated_at=now()`,
      [commit.entity_id,commit.repository_key,commit.sha.toLowerCase(),commit.message,commit.author,commit.authored_at,commit.source_system,commit.source_endpoints,commit.source_url]);
    }
    for (const file of data.changed_files || []) {
      if (file.repository_key !== repository.repository_key) throw Object.assign(new Error("Changed file repository mismatch"), { status: 400 });
      await client.query(`INSERT INTO changed_file_observations(entity_id,repository_key,source_entity_type,source_entity_id,source_commit_entity_id,source_pull_request_entity_id,path,status,additions,deletions,source_system,source_endpoint,source_url,last_seen_run_id) VALUES($1,$2,$3,$4,CASE WHEN $3='commit' THEN $4 END,CASE WHEN $3='pull_request' THEN $4 END,$5,$6,$7,$8,$9,$10,$11,$12,$13) ON CONFLICT(repository_key,source_entity_type,source_entity_id,path) DO UPDATE SET status=COALESCE(EXCLUDED.status,changed_file_observations.status),additions=COALESCE(EXCLUDED.additions,changed_file_observations.additions),deletions=COALESCE(EXCLUDED.deletions,changed_file_observations.deletions),source_url=COALESCE(EXCLUDED.source_url,changed_file_observations.source_url),last_seen_run_id=EXCLUDED.last_seen_run_id,updated_at=now()`,
      [file.entity_id,file.repository_key,file.source_entity_type,file.source_entity_id,file.path,file.status,file.additions,file.deletions,file.source_system,file.source_endpoint,file.source_url,runId]);
    }
    for (const edge of data.relationships || []) {
      if (edge.repository_key !== repository.repository_key || !Array.isArray(edge.evidence) || edge.evidence.some((item) => !item || !["github_api","explicit_text","inference"].includes(item.kind))) throw Object.assign(new Error("Invalid relationship or evidence"), { status: 400 });
      if (edge.target_repository_key !== repository.repository_key) {
        const [owner = "", name = ""] = edge.target_repository_key.split("/");
        if (!owner || !name) throw Object.assign(new Error("Invalid relationship target repository"), { status: 400 });
        await client.query(`INSERT INTO repositories(repository_key,owner,name,full_name) VALUES($1,$2,$3,$4) ON CONFLICT(repository_key) DO NOTHING`,
          [edge.target_repository_key, owner, name, `${owner}/${name}`]);
      }
      await client.query(`INSERT INTO relationships(entity_id,repository_key,source_entity_type,source_entity_id,target_entity_type,target_entity_id,target_repository_key,relation_type,evidence,last_seen_run_id) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10) ON CONFLICT(entity_id) DO UPDATE SET evidence=(SELECT jsonb_agg(DISTINCT item) FROM jsonb_array_elements(relationships.evidence || EXCLUDED.evidence) item),last_seen_run_id=EXCLUDED.last_seen_run_id,updated_at=now()`,
      [edge.entity_id,edge.repository_key,edge.source_entity_type,edge.source_entity_id,edge.target_entity_type,edge.target_entity_id,edge.target_repository_key,edge.relation_type,json(edge.evidence),runId]);
    }

    await client.query(`INSERT INTO collection_runs(repository_key,run_id,status,counts,stages,warnings,empty_results,failed_pull_requests,skipped_pull_requests,normalization_warnings,finished_at) VALUES($1,$2,$3,$4::jsonb,$5::jsonb,$6,$7,$8::jsonb,$9,$10,now()) ON CONFLICT(repository_key,run_id) DO UPDATE SET status=EXCLUDED.status,counts=EXCLUDED.counts,stages=EXCLUDED.stages,warnings=EXCLUDED.warnings,empty_results=EXCLUDED.empty_results,failed_pull_requests=EXCLUDED.failed_pull_requests,skipped_pull_requests=EXCLUDED.skipped_pull_requests,normalization_warnings=EXCLUDED.normalization_warnings,finished_at=now(),updated_at=now()`,
    [repository.repository_key,runId,run.status,json(run.counts),json(run.stages),run.warnings,run.empty_results,json(run.failed_pull_requests),run.skipped_pull_requests,data.normalization_warnings || []]);
    await client.query("COMMIT");
    return { repository_key: repository.repository_key, run_id: runId, persisted: true };
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally { client.release(); }
}

async function listBugs(repo) {
  const values = [];
  let where = "";
  if (repo) { values.push(repo); where = "WHERE r.full_name = $1"; }
  const { rows } = await getPool().query(`SELECT b.id::text AS "_id",0 AS "__v",b.number,b.title,COALESCE(b.body,'') AS body,b.labels,b.state,b.source_created_at AS "createdAt",b.closed_at AS "closedAt",b.url,r.full_name AS repo,'{}'::double precision[] AS embedding,'{}'::text[] AS "componentIds",b.fix_commit_shas AS "fixCommitShas",NULL::text AS "familyId",'{}'::text[] AS "similarBugIds",b.fix_effectiveness_score AS "fixEffectivenessScore",b.created_at AS "recordCreatedAt",b.updated_at AS "updatedAt" FROM bugs b JOIN repositories r USING(repository_key) ${where} ORDER BY b.source_created_at DESC NULLS LAST LIMIT 50`, values);
  return rows.map(formatBug);
}

function formatBug({ recordCreatedAt, ...bug }) {
  return { ...bug, createdAt: bug.createdAt || recordCreatedAt };
}

module.exports = { persistNormalized, listBugs, formatBug };
