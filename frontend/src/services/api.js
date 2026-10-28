const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8010')
  .replace(/\/$/, '')

function isRecord(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function normalizeAnalysis(data) {
  if (!isRecord(data) || typeof data.repository !== 'string') {
    throw new Error('The backend returned an unexpected analysis response.')
  }

  const issues = Array.isArray(data.issues) ? data.issues : Array.isArray(data.bugs) ? data.bugs : null
  const pullRequests = Array.isArray(data.pull_requests) ? data.pull_requests : null
  const relationships = Array.isArray(data.relationships) ? data.relationships : null
  if (!issues || !pullRequests || !relationships) {
    throw new Error('The backend response is missing issue, pull-request, or relationship data.')
  }

  return {
    ...data,
    issues,
    pull_requests: pullRequests,
    relationships,
    warnings: Array.isArray(data.warnings) ? data.warnings : [],
    failed_pull_requests: Array.isArray(data.failed_pull_requests) ? data.failed_pull_requests : [],
    skipped_pull_requests: Number.isInteger(data.skipped_pull_requests) ? data.skipped_pull_requests : 0,
    counts: isRecord(data.counts) ? data.counts : {
      issues: issues.length,
      pull_requests: pullRequests.length,
      relationships: relationships.length,
      failed_relationships: Array.isArray(data.failed_pull_requests) ? data.failed_pull_requests.length : 0,
      skipped_relationships: Number.isInteger(data.skipped_pull_requests) ? data.skipped_pull_requests : 0,
    },
  }
}

function describeFailure(status, detail) {
  if (status === 400 || status === 422) return detail || 'Enter a valid GitHub repository URL.'
  if (status === 404) return detail || 'Repository not found or not accessible.'
  if (status === 429) return detail || 'GitHub API rate limit reached. Try again later.'
  if (status === 401 || status === 403) return detail || 'GitHub denied access to this repository.'
  if (status === 503) return detail || 'Could not reach GitHub. Check the backend network connection.'
  if (status >= 500) return detail || 'The backend could not complete this collection.'
  return detail || `Request failed with status ${status}.`
}

export function validateRepositoryUrl(value) {
  let parsed
  try {
    parsed = new URL(value.trim())
  } catch {
    return 'Enter a complete GitHub repository URL.'
  }
  const parts = parsed.pathname.split('/').filter(Boolean)
  if (
    parsed.protocol !== 'https:' ||
    parsed.hostname !== 'github.com' ||
    parsed.username ||
    parsed.password ||
    parsed.search ||
    parsed.hash ||
    parts.length !== 2 ||
    !/^[A-Za-z0-9-]+$/.test(parts[0]) ||
    !/^[A-Za-z0-9._-]+$/.test(parts[1].replace(/\.git$/, ''))
  ) {
    return 'Use a repository URL in the form https://github.com/owner/repository.'
  }
  return ''
}

export async function analyzeRepository(repositoryUrl, signal) {
  let response
  try {
    response = await fetch(`${API_BASE_URL}/api/repositories/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repository_url: repositoryUrl.trim() }),
      signal,
    })
  } catch (error) {
    if (error.name === 'AbortError') throw error
    throw new Error(`Could not connect to BugScope API at ${API_BASE_URL}. Confirm the backend is running.`)
  }

  let body
  try {
    body = await response.json()
  } catch {
    throw new Error('The backend returned an unreadable response.')
  }

  if (!response.ok) {
    const detail = typeof body?.detail === 'string' ? body.detail : ''
    throw new Error(describeFailure(response.status, detail))
  }
  return normalizeAnalysis(body)
}
