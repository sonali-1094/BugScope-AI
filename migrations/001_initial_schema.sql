CREATE TABLE IF NOT EXISTS repositories (
  repository_key text PRIMARY KEY CHECK (repository_key = lower(repository_key)),
  owner text NOT NULL,
  name text NOT NULL,
  full_name text NOT NULL,
  canonical_url text,
  description text,
  primary_language text,
  visibility text,
  is_private boolean,
  default_branch text,
  stars integer CHECK (stars IS NULL OR stars >= 0),
  forks integer CHECK (forks IS NULL OR forks >= 0),
  open_issues_count integer CHECK (open_issues_count IS NULL OR open_issues_count >= 0),
  source_system text NOT NULL DEFAULT 'github',
  source_endpoint text NOT NULL DEFAULT 'github.repository',
  source_url text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS issues (
  id bigserial PRIMARY KEY,
  entity_id text NOT NULL UNIQUE,
  repository_key text NOT NULL REFERENCES repositories(repository_key) ON UPDATE CASCADE,
  number integer NOT NULL CHECK (number > 0),
  title text,
  body text,
  state text CHECK (state IS NULL OR state IN ('open', 'closed')),
  source_created_at timestamptz,
  closed_at timestamptz,
  labels text[] NOT NULL DEFAULT '{}',
  author text,
  comments integer CHECK (comments IS NULL OR comments >= 0),
  url text,
  source_system text NOT NULL DEFAULT 'github',
  source_endpoint text NOT NULL DEFAULT 'github.repository_issues',
  source_url text,
  last_seen_run_id text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (repository_key, number),
  UNIQUE (repository_key, entity_id),
  UNIQUE (repository_key, id)
);
CREATE INDEX IF NOT EXISTS issues_repository_created_idx ON issues(repository_key, source_created_at DESC);

CREATE TABLE IF NOT EXISTS bugs (
  id bigserial PRIMARY KEY,
  repository_key text NOT NULL,
  number integer NOT NULL CHECK (number > 0),
  title text,
  body text,
  labels text[] NOT NULL DEFAULT '{}',
  state text CHECK (state IS NULL OR state IN ('open', 'closed')),
  source_created_at timestamptz,
  closed_at timestamptz,
  url text,
  issue_id bigint,
  embedding double precision[],
  fix_commit_shas text[] NOT NULL DEFAULT '{}',
  fix_effectiveness_score numeric CHECK (fix_effectiveness_score IS NULL OR (fix_effectiveness_score >= 0 AND fix_effectiveness_score <= 100)),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (repository_key, number) REFERENCES issues(repository_key, number) ON UPDATE CASCADE,
  FOREIGN KEY (repository_key, issue_id) REFERENCES issues(repository_key, id),
  UNIQUE (repository_key, number),
  UNIQUE (repository_key, id),
  UNIQUE (issue_id)
);
CREATE INDEX IF NOT EXISTS bugs_repository_created_idx ON bugs(repository_key, source_created_at DESC);

CREATE TABLE IF NOT EXISTS pull_requests (
  id bigserial PRIMARY KEY,
  entity_id text NOT NULL UNIQUE,
  repository_key text NOT NULL REFERENCES repositories(repository_key) ON UPDATE CASCADE,
  number integer NOT NULL CHECK (number > 0),
  title text,
  body text,
  state text CHECK (state IS NULL OR state IN ('open', 'closed')),
  merged boolean,
  merged_at timestamptz,
  source_created_at timestamptz,
  source_updated_at timestamptz,
  author text,
  commits_count integer CHECK (commits_count IS NULL OR commits_count >= 0),
  changed_files_count integer CHECK (changed_files_count IS NULL OR changed_files_count >= 0),
  source_system text NOT NULL DEFAULT 'github',
  source_endpoint text NOT NULL DEFAULT 'github.pull_requests',
  source_url text,
  last_seen_run_id text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (repository_key, number),
  UNIQUE (repository_key, entity_id)
);

CREATE TABLE IF NOT EXISTS commits (
  id bigserial PRIMARY KEY,
  entity_id text NOT NULL UNIQUE,
  repository_key text NOT NULL REFERENCES repositories(repository_key) ON UPDATE CASCADE,
  sha text NOT NULL CHECK (sha ~ '^[0-9a-f]{40,64}$'),
  message text,
  author text,
  authored_at timestamptz,
  source_system text NOT NULL DEFAULT 'github',
  source_endpoints text[] NOT NULL DEFAULT '{}',
  source_url text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (repository_key, sha),
  UNIQUE (repository_key, entity_id)
);
CREATE INDEX IF NOT EXISTS commits_repository_date_idx ON commits(repository_key, authored_at DESC);

CREATE TABLE IF NOT EXISTS changed_file_observations (
  id bigserial PRIMARY KEY,
  entity_id text NOT NULL UNIQUE,
  repository_key text NOT NULL REFERENCES repositories(repository_key) ON UPDATE CASCADE,
  source_entity_type text NOT NULL CHECK (source_entity_type IN ('commit', 'pull_request')),
  source_entity_id text NOT NULL,
  source_commit_entity_id text,
  source_pull_request_entity_id text,
  path text NOT NULL CHECK (length(trim(path)) > 0),
  status text,
  additions integer CHECK (additions IS NULL OR additions >= 0),
  deletions integer CHECK (deletions IS NULL OR deletions >= 0),
  source_system text NOT NULL DEFAULT 'github',
  source_endpoint text NOT NULL,
  source_url text,
  last_seen_run_id text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (repository_key, source_entity_type, source_entity_id, path),
  UNIQUE (repository_key, entity_id),
  CHECK ((source_entity_type = 'commit' AND source_commit_entity_id = source_entity_id AND source_pull_request_entity_id IS NULL)
      OR (source_entity_type = 'pull_request' AND source_pull_request_entity_id = source_entity_id AND source_commit_entity_id IS NULL)),
  FOREIGN KEY (repository_key, source_commit_entity_id)
    REFERENCES commits(repository_key, entity_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (repository_key, source_pull_request_entity_id)
    REFERENCES pull_requests(repository_key, entity_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS relationships (
  id bigserial PRIMARY KEY,
  entity_id text NOT NULL UNIQUE,
  repository_key text NOT NULL REFERENCES repositories(repository_key) ON UPDATE CASCADE,
  source_entity_type text NOT NULL CHECK (source_entity_type IN ('pull_request', 'commit')),
  source_entity_id text NOT NULL,
  target_entity_type text NOT NULL CHECK (target_entity_type IN ('commit', 'changed_file', 'issue')),
  target_entity_id text NOT NULL,
  target_repository_key text NOT NULL REFERENCES repositories(repository_key) ON UPDATE CASCADE,
  relation_type text NOT NULL CHECK (relation_type IN ('pull_request_contains_commit', 'pull_request_changes_file', 'commit_changes_file', 'explicitly_references_issue', 'inferred_candidate')),
  evidence jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(evidence) = 'array'),
  last_seen_run_id text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (repository_key, entity_id)
);
CREATE INDEX IF NOT EXISTS relationships_source_idx ON relationships(repository_key, source_entity_id);
CREATE INDEX IF NOT EXISTS relationships_target_idx ON relationships(target_repository_key, target_entity_id);

CREATE TABLE IF NOT EXISTS collection_runs (
  id bigserial PRIMARY KEY,
  repository_key text NOT NULL REFERENCES repositories(repository_key) ON UPDATE CASCADE,
  run_id text NOT NULL,
  status text CHECK (status IS NULL OR status IN ('complete', 'partial')),
  counts jsonb NOT NULL DEFAULT '{}'::jsonb,
  stages jsonb NOT NULL DEFAULT '{}'::jsonb,
  warnings text[] NOT NULL DEFAULT '{}',
  empty_results text[] NOT NULL DEFAULT '{}',
  failed_pull_requests jsonb NOT NULL DEFAULT '[]'::jsonb,
  skipped_pull_requests integer NOT NULL DEFAULT 0 CHECK (skipped_pull_requests >= 0),
  normalization_warnings text[] NOT NULL DEFAULT '{}',
  persistence jsonb,
  started_at timestamptz,
  finished_at timestamptz,
  schema_version integer NOT NULL DEFAULT 1 CHECK (schema_version > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (repository_key, run_id)
);

CREATE TABLE IF NOT EXISTS components (
  id bigserial PRIMARY KEY,
  repository_key text NOT NULL REFERENCES repositories(repository_key) ON UPDATE CASCADE,
  path text NOT NULL,
  bug_count integer NOT NULL DEFAULT 0 CHECK (bug_count >= 0),
  last_touched_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (repository_key, path),
  UNIQUE (repository_key, id)
);

CREATE TABLE IF NOT EXISTS bug_families (
  id bigserial PRIMARY KEY,
  repository_key text NOT NULL REFERENCES repositories(repository_key) ON UPDATE CASCADE,
  name text NOT NULL,
  evolution_summary text,
  average_fix_effectiveness numeric,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (repository_key, id)
);

CREATE TABLE IF NOT EXISTS bug_family_members (
  bug_family_id bigint NOT NULL,
  bug_id bigint NOT NULL,
  repository_key text NOT NULL,
  PRIMARY KEY (bug_family_id, bug_id),
  FOREIGN KEY (repository_key, bug_family_id) REFERENCES bug_families(repository_key, id) ON DELETE CASCADE,
  FOREIGN KEY (repository_key, bug_id) REFERENCES bugs(repository_key, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS bug_components (
  bug_id bigint NOT NULL,
  component_id bigint NOT NULL,
  repository_key text NOT NULL,
  PRIMARY KEY (bug_id, component_id),
  FOREIGN KEY (repository_key, bug_id) REFERENCES bugs(repository_key, id) ON DELETE CASCADE,
  FOREIGN KEY (repository_key, component_id) REFERENCES components(repository_key, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS similar_bugs (
  bug_id bigint NOT NULL,
  similar_bug_id bigint NOT NULL,
  repository_key text NOT NULL,
  PRIMARY KEY (bug_id, similar_bug_id),
  CHECK (bug_id <> similar_bug_id),
  FOREIGN KEY (repository_key, bug_id) REFERENCES bugs(repository_key, id) ON DELETE CASCADE,
  FOREIGN KEY (repository_key, similar_bug_id) REFERENCES bugs(repository_key, id) ON DELETE CASCADE
);

\n