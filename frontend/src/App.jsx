import { useState } from 'react'
import { analyzeRepository, validateRepositoryUrl } from './services/api.js'

const navigation = [
  { id: 'overview', label: 'Overview', glyph: '◫' },
  { id: 'issues', label: 'Issues', glyph: '◎' },
  { id: 'pulls', label: 'Pull requests', glyph: '⇄' },
  { id: 'relationships', label: 'Relationships', glyph: '⌘' },
]

function formatDate(value) {
  if (!value) return 'Date unavailable'
  const date = new Date(value)
  return Number.isNaN(date.valueOf())
    ? 'Date unavailable'
    : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(date)
}

function shortHash(value) {
  return typeof value === 'string' ? value.slice(0, 8) : 'Hash unavailable'
}

function EmptyState({ title, detail }) {
  return (
    <div className="empty-state">
      <span className="empty-mark" aria-hidden="true">—</span>
      <h3>{title}</h3>
      <p>{detail}</p>
    </div>
  )
}

function StatusBanner({ analysis }) {
  const partial = analysis.status !== 'complete'
  const warnings = analysis.warnings || []
  return (
    <>
      <div className={`status-banner ${partial ? 'is-partial' : 'is-complete'}`} role="status">
        <span className="status-indicator" aria-hidden="true" />
        <div>
          <strong>{partial ? 'Collection completed with gaps' : 'Collection complete'}</strong>
          <p>{partial ? 'Some repository data could not be collected. Review the notes below.' : 'All requested collection steps returned successfully.'}</p>
          {warnings.length > 0 && <ul>{warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>}
        </div>
      </div>
      {analysis.persistence?.status !== 'persisted' && <div className="warning-list" role="status">
        <span>Database save status: {analysis.persistence?.status || 'unknown'}. The analysis results are available, but this run is not confirmed in PostgreSQL.</span>
      </div>}
    </>
  )
}

function Metric({ label, value, note, tone }) {
  return (
    <article className={`metric metric-${tone}`}>
      <div className="metric-top"><span>{label}</span><span className="metric-dot" aria-hidden="true" /></div>
      <strong>{value ?? 0}</strong>
      <small>{note}</small>
    </article>
  )
}

function SearchFilter({ query, setQuery, state, setState, kind }) {
  return (
    <div className="list-controls">
      <label className="search-field">
        <span className="search-glyph" aria-hidden="true">⌕</span>
        <span className="sr-only">Search {kind}</span>
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={`Search ${kind.toLowerCase()}...`} />
      </label>
      <label className="filter-field">
        <span className="sr-only">Filter by state</span>
        <select value={state} onChange={(event) => setState(event.target.value)}>
          <option value="all">All states</option>
          <option value="open">Open</option>
          <option value="closed">Closed</option>
        </select>
      </label>
    </div>
  )
}

function App() {
  const [activeView, setActiveView] = useState('overview')
  const [repositoryUrl, setRepositoryUrl] = useState('')
  const [urlError, setUrlError] = useState('')
  const [requestError, setRequestError] = useState('')
  const [loading, setLoading] = useState(false)
  const [analysis, setAnalysis] = useState(null)
  const [issueQuery, setIssueQuery] = useState('')
  const [issueState, setIssueState] = useState('all')
  const [pullQuery, setPullQuery] = useState('')
  const [pullState, setPullState] = useState('all')

  async function submitAnalysis(event) {
    event.preventDefault()
    setRequestError('')
    const validationMessage = validateRepositoryUrl(repositoryUrl)
    setUrlError(validationMessage)
    if (validationMessage) return

    setLoading(true)
    try {
      const nextAnalysis = await analyzeRepository(repositoryUrl)
      setAnalysis(nextAnalysis)
      setActiveView('overview')
    } catch (error) {
      setRequestError(error.message || 'Repository collection failed.')
    } finally {
      setLoading(false)
    }
  }

  const issues = analysis?.issues || []
  const pullRequests = analysis?.pull_requests || []
  const issueRows = issues.filter((issue) => {
    const matchesState = issueState === 'all' || issue.state === issueState
    const searchText = `${issue.issue_number ?? issue.number ?? ''} ${issue.title ?? ''} ${issue.author ?? ''} ${(issue.labels || []).join(' ')}`.toLowerCase()
    return matchesState && searchText.includes(issueQuery.toLowerCase())
  })
  const pullRows = pullRequests.filter((pull) => {
    const matchesState = pullState === 'all' || pull.state === pullState
    const searchText = `${pull.number ?? ''} ${pull.title ?? ''} ${pull.author ?? ''}`.toLowerCase()
    return matchesState && searchText.includes(pullQuery.toLowerCase())
  })

  const currentLabel = navigation.find((item) => item.id === activeView)?.label || 'Overview'

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#overview" onClick={() => setActiveView('overview')} aria-label="BugScope AI overview">
          <span className="brand-mark"><span /></span>
          <span className="brand-name">bugscope<span>AI</span></span>
        </a>
        <div className="workspace-label">WORKSPACE</div>
        <nav className="side-nav" aria-label="Main navigation">
          {navigation.map((item) => (
            <button key={item.id} className={`nav-item ${activeView === item.id ? 'active' : ''}`} onClick={() => setActiveView(item.id)}>
              <span className="nav-glyph" aria-hidden="true">{item.glyph}</span>
              <span>{item.label}</span>
              {item.id === 'issues' && analysis && <span className="nav-count">{analysis.counts?.issues ?? issues.length}</span>}
              {item.id === 'pulls' && analysis && <span className="nav-count">{analysis.counts?.pull_requests ?? pullRequests.length}</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <span className="phase-mark" aria-hidden="true">01</span>
          <div><strong>Data collection</strong><small>GitHub history</small></div>
          <span className="phase-live" title="Current project phase" />
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumb"><span>BugScope</span><span className="crumb-separator">/</span><strong>{currentLabel}</strong></div>
          <div className="topbar-meta"><span className="connection-dot" /> API connected on demand</div>
        </header>

        <div className="page-content">
          <section className="page-heading">
            <div>
              <div className="eyebrow">HISTORICAL REPOSITORY INTELLIGENCE</div>
              <h1>{activeView === 'overview' ? 'Repository overview' : currentLabel}</h1>
              <p>Trace the history behind software issues, fixes, and changed files.</p>
            </div>
            {analysis && <a className="repo-pill" href={analysis.repository_url} target="_blank" rel="noreferrer"><span className="repo-pill-mark">⌂</span>{analysis.repository}<span className="external-mark">↗</span></a>}
          </section>

          <section className="analyze-panel" aria-labelledby="analyze-title">
            <div className="analyze-copy">
              <span className="step-number">01 / COLLECT</span>
              <h2 id="analyze-title">Start with a repository</h2>
              <p>Collect historical issues, pull requests, commits, and changed files from GitHub.</p>
            </div>
            <form className="analyze-form" onSubmit={submitAnalysis} noValidate>
              <label htmlFor="repository-url">GitHub repository URL</label>
              <div className={`input-action ${urlError ? 'has-error' : ''}`}>
                <span className="input-prefix" aria-hidden="true">github.com /</span>
                <input
                  id="repository-url"
                  type="url"
                  autoComplete="url"
                  placeholder="owner/repository"
                  value={repositoryUrl}
                  onChange={(event) => { setRepositoryUrl(event.target.value); setUrlError(''); setRequestError('') }}
                  aria-invalid={Boolean(urlError)}
                  aria-describedby={urlError ? 'url-error' : undefined}
                />
                <button type="submit" disabled={loading}>
                  {loading ? <><span className="button-spinner" /> Collecting</> : <>Analyze repository <span aria-hidden="true">↗</span></>}
                </button>
              </div>
              {urlError && <p id="url-error" className="field-error">{urlError}</p>}
            </form>
          </section>

          {requestError && <div className="error-banner" role="alert"><span className="error-symbol">!</span><div><strong>Could not analyze repository</strong><p>{requestError}</p></div><button onClick={() => setRequestError('')} aria-label="Dismiss error">×</button></div>}

          {loading && <div className="loading-line" role="status"><span className="loading-track"><span /></span><span>Collecting repository history from GitHub…</span></div>}

          {!analysis && !loading ? (
            <section className="welcome-state">
              <div className="welcome-graphic" aria-hidden="true"><div className="graphic-ring ring-one" /><div className="graphic-ring ring-two" /><div className="graphic-node node-one" /><div className="graphic-node node-two" /><div className="graphic-node node-three" /><div className="graphic-center">B</div><div className="graphic-connector connector-one" /><div className="graphic-connector connector-two" /></div>
              <div className="welcome-text"><span className="eyebrow">READY WHEN YOU ARE</span><h2>Make repository history<br />easier to investigate.</h2><p>Enter an accessible GitHub repository above. Collected records will appear here, with incomplete results clearly marked.</p></div>
              <div className="welcome-meta"><span>ISSUES</span><i /><span>PULL REQUESTS</span><i /><span>FILE HISTORY</span></div>
            </section>
          ) : analysis ? (
            <>
              <StatusBanner analysis={analysis} />
              {activeView === 'overview' && <Overview analysis={analysis} onNavigate={setActiveView} />}
              {activeView === 'issues' && <IssuesView issues={issueRows} query={issueQuery} setQuery={setIssueQuery} state={issueState} setState={setIssueState} total={issues.length} />}
              {activeView === 'pulls' && <PullRequestsView pulls={pullRows} query={pullQuery} setQuery={setPullQuery} state={pullState} setState={setPullState} total={pullRequests.length} />}
              {activeView === 'relationships' && <RelationshipsView analysis={analysis} />}
            </>
          ) : null}

          <footer className="page-footer"><span>BUGSCOPE AI <i>·</i> GITHUB DATA COLLECTION</span><span>Historical records, collected on request</span></footer>
        </div>
      </main>
    </div>
  )
}

function Overview({ analysis, onNavigate }) {
  const counts = analysis.counts || {}
  const failures = (counts.failed_relationships || 0) + (counts.skipped_relationships || 0)
  const details = analysis.repository_details || {}
  return (
    <div className="view-stack">
      <section className="repository-card">
        <div className="repository-card-main">
          <div className="repo-avatar" aria-hidden="true">{analysis.repository?.split('/').at(-1)?.slice(0, 1).toUpperCase() || 'R'}</div>
          <div><span className="card-kicker">REPOSITORY PROFILE</span><h2>{details.full_name || analysis.repository}</h2><p>{details.description || 'No repository description provided by GitHub.'}</p></div>
        </div>
        <div className="repository-card-side"><span className={`collection-tag ${analysis.status === 'complete' ? 'tag-complete' : 'tag-partial'}`}><i />{analysis.status === 'complete' ? 'Complete' : 'Partial'}</span><a href={analysis.repository_url} target="_blank" rel="noreferrer">Open on GitHub ↗</a></div>
      </section>

      <section className="metrics-grid" aria-label="Collection summary">
        <Metric label="Issues collected" value={counts.issues ?? analysis.issues.length} note="Historical issues" tone="green" />
        <Metric label="Pull requests" value={counts.pull_requests ?? analysis.pull_requests.length} note="Open and closed" tone="orange" />
        <Metric label="Relationships" value={counts.relationships ?? analysis.relationships.length} note="PR commit references" tone="blue" />
        <Metric label="Gaps to review" value={failures} note="Failed or skipped PRs" tone="rose" />
      </section>

      <section className="overview-lower">
        <div className="section-panel collection-panel">
          <div className="panel-heading"><div><span className="card-kicker">COLLECTION REPORT</span><h2>What was gathered</h2></div><span className="report-icon" aria-hidden="true">⌁</span></div>
          <div className="report-rows">
            <button onClick={() => onNavigate('issues')}><span className="report-index">01</span><span className="report-name">Historical issues</span><strong>{counts.issues ?? analysis.issues.length}</strong><span className="report-arrow">↗</span></button>
            <button onClick={() => onNavigate('pulls')}><span className="report-index">02</span><span className="report-name">Pull requests</span><strong>{counts.pull_requests ?? analysis.pull_requests.length}</strong><span className="report-arrow">↗</span></button>
            <button onClick={() => onNavigate('relationships')}><span className="report-index">03</span><span className="report-name">PR relationships</span><strong>{counts.relationships ?? analysis.relationships.length}</strong><span className="report-arrow">↗</span></button>
          </div>
        </div>
        <div className="section-panel notes-panel">
          <div className="panel-heading"><div><span className="card-kicker">COLLECTION NOTES</span><h2>Coverage</h2></div><span className="notes-status">{analysis.status === 'complete' ? 'ALL CLEAR' : 'ATTENTION'}</span></div>
          {analysis.warnings?.length ? <ul className="warning-list">{analysis.warnings.map((warning) => <li key={warning}><span>!</span>{warning}</li>)}</ul> : <div className="no-warnings"><span className="check-mark">✓</span><div><strong>No collection warnings</strong><small>All requested records were returned.</small></div></div>}
          <div className="coverage-footnote">Issues are GitHub issues excluding pull requests. No AI classification is applied.</div>
        </div>
      </section>
    </div>
  )
}

function IssuesView({ issues, query, setQuery, state, setState, total }) {
  return (
    <section className="section-panel data-panel">
      <div className="panel-heading data-heading"><div><span className="card-kicker">ISSUE ARCHIVE</span><h2>Historical issues <span className="heading-count">{total}</span></h2></div><SearchFilter query={query} setQuery={setQuery} state={state} setState={setState} kind="issues" /></div>
      {issues.length ? <div className="table-scroll"><table><thead><tr><th>ISSUE</th><th>STATE</th><th>AUTHOR</th><th>LABELS</th><th>CREATED</th><th /></tr></thead><tbody>
        {issues.map((issue, index) => <tr key={issue.issue_number ?? issue.number ?? index}>
          <td><div className="record-title"><span className="record-number">#{issue.issue_number ?? issue.number ?? '—'}</span>{issue.html_url ? <a href={issue.html_url} target="_blank" rel="noreferrer">{issue.title || 'Untitled issue'} <span>↗</span></a> : <strong>{issue.title || 'Untitled issue'}</strong>}</div></td>
          <td><StateBadge state={issue.state} /></td><td>{issue.author || <span className="muted">Unknown</span>}</td>
          <td><div className="labels-cell">{Array.isArray(issue.labels) && issue.labels.length ? issue.labels.slice(0, 3).map((label) => <span className="label-chip" key={label}>{label}</span>) : <span className="muted">No labels</span>}{issue.labels?.length > 3 && <span className="muted">+{issue.labels.length - 3}</span>}</div></td>
          <td className="date-cell">{formatDate(issue.created_at)}</td><td className="row-link">{issue.html_url && <a href={issue.html_url} target="_blank" rel="noreferrer" aria-label={`Open issue ${issue.issue_number ?? issue.number} on GitHub`}>↗</a>}</td>
        </tr>)}
      </tbody></table></div> : <EmptyState title={total ? 'No matching issues' : 'No issues collected'} detail={total ? 'Try a different search or state filter.' : 'This repository returned no issues for the selected collection.'} />}
      <div className="table-footnote">Showing {issues.length} of {total} collected issues</div>
    </section>
  )
}

function PullRequestsView({ pulls, query, setQuery, state, setState, total }) {
  return (
    <section className="section-panel data-panel">
      <div className="panel-heading data-heading"><div><span className="card-kicker">CHANGE HISTORY</span><h2>Pull requests <span className="heading-count">{total}</span></h2></div><SearchFilter query={query} setQuery={setQuery} state={state} setState={setState} kind="pull requests" /></div>
      {pulls.length ? <div className="table-scroll"><table><thead><tr><th>PULL REQUEST</th><th>STATE</th><th>MERGE</th><th>AUTHOR</th><th>CREATED</th><th /></tr></thead><tbody>
        {pulls.map((pull, index) => <tr key={pull.number ?? index}>
          <td><div className="record-title"><span className="record-number">#{pull.number ?? '—'}</span>{pull.html_url ? <a href={pull.html_url} target="_blank" rel="noreferrer">{pull.title || 'Untitled pull request'} <span>↗</span></a> : <strong>{pull.title || 'Untitled pull request'}</strong>}</div></td>
          <td><StateBadge state={pull.state} /></td><td>{pull.merged === true ? <span className="merge-state merged">Merged</span> : pull.merged === false ? <span className="merge-state not-merged">Not merged</span> : <span className="muted">Unknown</span>}</td>
          <td>{pull.author || <span className="muted">Unknown</span>}</td><td className="date-cell">{formatDate(pull.created_at)}</td><td className="row-link">{pull.html_url && <a href={pull.html_url} target="_blank" rel="noreferrer" aria-label={`Open pull request ${pull.number} on GitHub`}>↗</a>}</td>
        </tr>)}
      </tbody></table></div> : <EmptyState title={total ? 'No matching pull requests' : 'No pull requests collected'} detail={total ? 'Try a different search or state filter.' : 'This repository returned no pull requests for the selected collection.'} />}
      <div className="table-footnote">Showing {pulls.length} of {total} collected pull requests</div>
    </section>
  )
}

function StateBadge({ state }) {
  const normalized = typeof state === 'string' ? state.toLowerCase() : ''
  return <span className={`state-badge state-${normalized || 'unknown'}`}><i />{normalized || 'Unknown'}</span>
}

function RelationshipsView({ analysis }) {
  const relationships = analysis.relationships || []
  const failures = analysis.failed_pull_requests || []
  const skipped = analysis.skipped_pull_requests || 0
  return (
    <div className="view-stack">
      {(failures.length > 0 || skipped > 0) && <section className="relationship-alert"><div className="alert-icon">!</div><div><strong>Relationship collection is incomplete</strong><p>{failures.length ? `${failures.length} pull request(s) failed while fetching commits or changed files.` : ''}{skipped ? ` ${skipped} pull request(s) were skipped by the collection limit.` : ''}</p>{failures.length > 0 && <ul>{failures.map((failure) => <li key={failure.pull_request_number}>PR #{failure.pull_request_number}: {failure.error || 'Relationship details unavailable.'}</li>)}</ul>}</div></section>}
      <section className="relationship-section">
        <div className="panel-heading relationship-heading"><div><span className="card-kicker">CHANGE TRACE</span><h2>Pull request relationships <span className="heading-count">{relationships.length}</span></h2></div><span className="relationship-caption">Only relationships returned by GitHub are shown</span></div>
        {relationships.length ? <div className="relationship-list">{relationships.map((relationship, index) => <article className="relationship-card" key={relationship.pull_request_number ?? index}>
          <div className="relationship-card-head"><div className="pr-icon">PR</div><div className="pr-summary"><span className="card-kicker">PULL REQUEST #{relationship.pull_request_number ?? '—'}</span><h3>{relationship.pull_request_title || 'Untitled pull request'}</h3></div><StateBadge state={relationship.pull_request_state} />{relationship.merged_at && <span className="merge-state merged">Merged</span>}</div>
          <div className="relationship-grid">
            <div className="trace-column commits-column"><div className="trace-heading"><span className="trace-symbol">⌘</span><span>COMMITS</span><strong>{relationship.commits?.length || 0}</strong></div>
              {relationship.commits?.length ? <div className="trace-items">{relationship.commits.map((commit, commitIndex) => <div className="commit-item" key={commit.commit_sha || commit.sha || commitIndex}><span className="commit-line" /><div><div className="commit-message">{commit.message || 'Commit message unavailable'}</div><code>{shortHash(commit.commit_sha || commit.sha)}</code>{commit.author && <span className="commit-author">by {commit.author}</span>}</div></div>)}</div> : <div className="trace-empty">No commit references returned.</div>}
            </div>
            <div className="trace-column files-column"><div className="trace-heading"><span className="trace-symbol file-symbol">⌑</span><span>CHANGED FILES</span><strong>{relationship.changed_files_count ?? relationship.changed_files?.length ?? 0}</strong></div>
              {relationship.changed_files?.length ? <div className="file-list">{relationship.changed_files.map((file, fileIndex) => { const filename = typeof file === 'string' ? file : file?.filename; return <div className="file-row" key={filename || fileIndex}><span className="file-type">{filename?.split('.').pop()?.slice(0, 4).toUpperCase() || 'FILE'}</span><code>{filename || 'Filename unavailable'}</code>{typeof file === 'object' && file.status && <span className="file-status">{file.status}</span>}</div> })}</div> : <div className="trace-empty">No changed-file records returned.</div>}
            </div>
          </div>
        </article>)}</div> : <EmptyState title="No relationships collected" detail="Relationship records appear when GitHub returns pull-request commit and changed-file data." />}
      </section>
    </div>
  )
}

export default App
