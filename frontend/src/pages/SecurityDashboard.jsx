import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { fetchRepo } from '../api'

// Same four-level taxonomy used in GitMind's dependency risk scoring
// (dependencies.py per_dependency_risk) — kept identical here on purpose so
// "Critical" always means the same thing across the app.
const SEVERITY_LEVELS = ['Critical', 'High', 'Medium', 'Low']

const SEVERITY_STATUS_CLASS = {
  Critical: 'health-status-critical',
  High: 'health-status-at-risk',
  Medium: 'health-status-fair',
  Low: 'health-status-healthy',
}

const SEVERITY_DOT_CLASS = {
  Critical: 'sev-dot-critical',
  High: 'sev-dot-high',
  Medium: 'sev-dot-medium',
  Low: 'sev-dot-low',
}

function SeverityPill({ level }) {
  if (!level) return null
  return <span className={`health-status-pill ${SEVERITY_STATUS_CLASS[level] || 'health-status-fair'}`}>{level}</span>
}

export default function SecurityDashboard() {
  const { id } = useParams()
  const [repo, setRepo] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetchRepo(id)
      .then((data) => { if (!cancelled) setRepo(data) })
      .catch((err) => { if (!cancelled) setError(err.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [id])

  if (loading) return <p className="status-text">Loading security data…</p>
  if (error) return <p className="error-banner" role="alert">{error}</p>
  if (!repo) return null

  const deps = repo.dependencies || null
  const security = deps?.security || { available: false, reason: 'No dependency manifest was found for this repo.' }
  const perDepRisk = deps?.per_dependency_risk || { available: false, dependencies: [] }
  const flaggedDeps = perDepRisk.available ? (perDepRisk.dependencies || []) : []

  // Prefer the real Dependabot-derived security score; fall back to the
  // blended dependency-health score (which is explicitly noted/capped when
  // vulnerability data itself isn't accessible) rather than inventing one.
  const scoreAvailable = security.available && security.security_score != null
  const displayScore = scoreAvailable ? security.security_score : deps?.dependency_health_score ?? null
  const scoreLabel = scoreAvailable ? 'Security score' : 'Dependency health score (fallback)'

  const nothingAvailable = !security.available && !perDepRisk.available && displayScore == null

  // Highest severity actually observed across the flagged dependencies —
  // never invented, purely a max() over what's already computed elsewhere.
  const overallSeverity = SEVERITY_LEVELS.find((level) =>
    flaggedDeps.some((d) => d.risk_level === level)
  ) || (security.available ? 'Low' : null)

  // Recommendations are assembled only from remediation text and notes that
  // already exist on real records — nothing here is guessed.
  const recommendations = []
  flaggedDeps.forEach((d) => {
    if (d.remediation) recommendations.push({ key: `dep-${d.name}`, text: d.remediation, severity: d.risk_level })
  })
  if (deps?.transitive && !deps.transitive.lock_files_found?.length && deps?.manifest_files_found?.length) {
    recommendations.push({
      key: 'lockfile',
      text: 'Add a lock file (package-lock.json, poetry.lock, etc.) to pin the full resolved dependency tree and make future audits reproducible.',
      severity: null,
    })
  }
  if (!security.available) {
    recommendations.push({
      key: 'token-scope',
      text: 'Dependabot vulnerability data isn\'t accessible for this repo — analyze it with a token that has security-events read access (and admin rights on the repo) to see real alert data instead of this gap.',
      severity: null,
    })
  }

  return (
    <div className="repo-detail">
      <Link to={`/repo/${id}`} className="back-link">← back to repo</Link>

      <header className="repo-detail-header">
        <div>
          <p className="repo-eyebrow">
            {repo.owner}
          </p>
          <h1 className="repo-detail-title">🛡 Security Dashboard</h1>
          <p className="repo-detail-fullname">{repo.full_name}</p>
        </div>
        {overallSeverity && <SeverityPill level={overallSeverity} />}
      </header>

      {nothingAvailable ? (
        <section className="detail-panel">
          <h2 className="panel-title">Security overview</h2>
          <p className="panel-note" style={{ fontSize: 14, marginTop: 0 }}>Security data not available.</p>
          <p className="panel-note">
            No dependency manifest was detected, no Dependabot alert data could be read, and file-level
            risk scanning isn't available for this repo. Nothing below is inferred to fill the gap.
          </p>
        </section>
      ) : (
        <section className="detail-panel">
          <h2 className="panel-title">Security overview</h2>
          <div className="score-row">
            <div className="score-circle" style={{ '--score': displayScore ?? 0 }}>
              <span>{displayScore != null ? displayScore : 'N/A'}</span>
            </div>
            <div>
              <p className="panel-note" style={{ margin: 0, fontSize: 13, color: 'var(--text)' }}>{scoreLabel}{deps?.dependency_health_level && !scoreAvailable ? ` — ${deps.dependency_health_level}` : ''}</p>
              {!scoreAvailable && deps?.dependency_health_note && (
                <p className="panel-note">{deps.dependency_health_note}</p>
              )}
            </div>
          </div>

          <div className="severity-grid">
            {SEVERITY_LEVELS.map((level) => (
              <div key={level} className="severity-card">
                <span className={`severity-dot ${SEVERITY_DOT_CLASS[level]}`} aria-hidden="true" />
                <span className="severity-card-count">
                  {security.available ? security[level.toLowerCase()] : '—'}
                </span>
                <span className="severity-card-label">{level}</span>
              </div>
            ))}
          </div>
          <p className="panel-note">
            {security.available
              ? `${security.total} known vulnerability alert${security.total === 1 ? '' : 's'} from GitHub Dependabot, classified by severity.`
              : (security.reason || 'Security data not available.')}
          </p>
        </section>
      )}

      <section className="detail-panel">
        <h2 className="panel-title">Dependency vulnerabilities</h2>
        {!perDepRisk.available ? (
          <p className="panel-note" style={{ margin: 0 }}>{perDepRisk.reason || 'Security data not available.'}</p>
        ) : flaggedDeps.length === 0 ? (
          <p className="panel-note" style={{ margin: 0 }}>No known vulnerabilities were found in this repo's dependencies.</p>
        ) : (
          <ul className="risk-list">
            {flaggedDeps.map((d) => (
              <li key={d.name} className="finding-card">
                <div className="finding-card-head">
                  <span className="finding-card-name">{d.name}</span>
                  <SeverityPill level={d.risk_level} />
                </div>
                <p className="panel-note" style={{ margin: '4px 0 0' }}>
                  {d.ecosystem ? `${d.ecosystem} · ` : ''}
                  {d.manifest_path || 'manifest path unknown'} · {d.open_alert_count} open alert{d.open_alert_count === 1 ? '' : 's'}
                  {d.advisory_ids?.length ? ` · ${d.advisory_ids.join(', ')}` : ''}
                </p>
                {d.remediation && <p className="panel-note finding-recommendation">→ {d.remediation}</p>}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="detail-panel">
        <h2 className="panel-title">Recommendations</h2>
        {recommendations.length === 0 ? (
          <p className="panel-note" style={{ margin: 0 }}>
            {nothingAvailable
              ? 'Security data not available.'
              : 'No specific actions surfaced — nothing here crossed a risk threshold.'}
          </p>
        ) : (
          <ul className="risk-list">
            {recommendations.map((r) => (
              <li key={r.key} className="risk-list-item" style={{ alignItems: 'flex-start' }}>
                <span style={{ fontSize: 13, lineHeight: 1.5 }}>{r.text}</span>
                {r.severity && <SeverityPill level={r.severity} />}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
