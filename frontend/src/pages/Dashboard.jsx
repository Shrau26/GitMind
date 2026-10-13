import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'
import { fetchRepos, fetchAnomalyReport } from '../api'
import HealthBadge from '../components/HealthBadge'

const BUCKETS = [
  { key: 'healthy', label: 'Healthy', min: 80, max: 100, color: '#5eead4' },
  { key: 'fair', label: 'Fair', min: 55, max: 79, color: '#f2b84b' },
  { key: 'at_risk', label: 'At risk', min: 30, max: 54, color: '#f2925b' },
  { key: 'critical', label: 'Critical', min: 0, max: 29, color: '#f26b6b' },
]

export default function Dashboard() {
  const [repos, setRepos] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [anomalyReport, setAnomalyReport] = useState(null)

  useEffect(() => {
    fetchRepos()
      .then(setRepos)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
    fetchAnomalyReport().then(setAnomalyReport).catch(() => setAnomalyReport(null))
  }, [])

  const stats = useMemo(() => {
    if (repos.length === 0) return null
    const avgHealth = Math.round(repos.reduce((sum, r) => sum + r.health_score, 0) / repos.length)
    const totalStars = repos.reduce((sum, r) => sum + (r.stars || 0), 0)
    const totalFlags = repos.reduce(
      (sum, r) => sum + (r.risk_flags?.[0] === 'no risk signals detected' ? 0 : r.risk_flags?.length || 0),
      0
    )
    const buckets = BUCKETS.map((b) => ({
      ...b,
      count: repos.filter((r) => r.health_score >= b.min && r.health_score <= b.max).length,
    }))
    const riskiest = [...repos].sort((a, b) => a.health_score - b.health_score).slice(0, 5)
    const favorites = repos.filter((r) => r.is_favorite)

    const topByStars = [...repos]
      .sort((a, b) => (b.stars || 0) - (a.stars || 0))
      .slice(0, 6)
      .map((r) => ({ name: r.name, stars: r.stars }))

    return { avgHealth, totalStars, totalFlags, buckets, riskiest, favorites, topByStars }
  }, [repos])

  if (loading) return <p className="status-text">Loading dashboard…</p>
  if (error) return <p className="error-banner" role="alert">{error}</p>

  if (!stats) {
    return (
      <div className="empty-state">
        <p>Nothing to show yet.</p>
        <p className="empty-state-sub">Analyze a repository first, then come back here.</p>
      </div>
    )
  }

  return (
    <div className="dashboard">
      <header className="hero hero-compact">
        <p className="eyebrow">portfolio view</p>
        <h1 className="wordmark wordmark-sm">Dashboard</h1>
        <p className="tagline">A rollup of every repository you've analyzed.</p>
      </header>

      <div className="summary-cards">
        <div className="summary-card">
          <p className="summary-card-label">Repositories tracked</p>
          <p className="summary-card-value">{repos.length}</p>
        </div>
        <div className="summary-card">
          <p className="summary-card-label">Average health score</p>
          <p className="summary-card-value">{stats.avgHealth}</p>
        </div>
        <div className="summary-card">
          <p className="summary-card-label">Total stars tracked</p>
          <p className="summary-card-value">{stats.totalStars.toLocaleString()}</p>
        </div>
        <div className="summary-card">
          <p className="summary-card-label">Active risk flags</p>
          <p className="summary-card-value">{stats.totalFlags}</p>
        </div>
      </div>

      <section className="detail-panel">
        <h2 className="panel-title">Health distribution</h2>
        <div style={{ width: '100%', height: 200 }}>
          <ResponsiveContainer>
            <BarChart data={stats.buckets} margin={{ top: 4, right: 16, bottom: 4, left: 4 }}>
              <XAxis dataKey="label" tick={{ fontSize: 12, fill: 'var(--text-muted)' }} />
              <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
              <Tooltip
                contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', fontSize: 12 }}
                formatter={(value) => [`${value} repo${value === 1 ? '' : 's'}`, 'Count']}
              />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {stats.buckets.map((b) => (
                  <Cell key={b.key} fill={b.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      <div className="dashboard-chart-row">
        {stats.topByStars.length > 0 && (
          <section className="detail-panel dashboard-chart-half">
            <h2 className="panel-title">Top repos by stars</h2>
            <div style={{ width: '100%', height: 220 }}>
              <ResponsiveContainer>
                <BarChart
                  data={stats.topByStars}
                  layout="vertical"
                  margin={{ top: 4, right: 16, bottom: 4, left: 4 }}
                >
                  <XAxis type="number" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
                  <YAxis type="category" dataKey="name" width={90} tick={{ fontSize: 11, fill: 'var(--text)' }} />
                  <Tooltip
                    contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', fontSize: 12 }}
                    formatter={(value) => [value.toLocaleString(), 'Stars']}
                  />
                  <Bar dataKey="stars" fill="#5eead4" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </section>
        )}
      </div>

      {stats.favorites.length > 0 && (
        <section className="detail-panel">
          <h2 className="panel-title">★ Favorites</h2>
          <ul className="risk-list">
            {stats.favorites.map((repo) => (
              <li key={repo.id} className="risk-list-item">
                <Link to={`/repo/${repo.id}`} className="risk-list-link">
                  {repo.full_name}
                </Link>
                <HealthBadge score={repo.health_score} size="sm" />
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="detail-panel">
        <h2 className="panel-title">Needs attention</h2>
        {stats.riskiest.length === 0 ? (
          <p className="panel-note">Nothing flagged.</p>
        ) : (
          <ul className="risk-list">
            {stats.riskiest.map((repo) => (
              <li key={repo.id} className="risk-list-item">
                <Link to={`/repo/${repo.id}`} className="risk-list-link">
                  {repo.full_name}
                </Link>
                <HealthBadge score={repo.health_score} size="sm" />
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="detail-panel">
        <h2 className="panel-title">Outliers</h2>
        {!anomalyReport ? (
          <p className="panel-note">Loading…</p>
        ) : !anomalyReport.available ? (
          <p className="panel-note">
            Need at least {anomalyReport.min_repos_required} saved repos to run outlier
            detection (you have {repos.length}). Analyze a few more to unlock this.
          </p>
        ) : (
          <>
            <ul className="risk-list">
              {anomalyReport.results
                .filter((r) => r.is_anomaly)
                .map((r) => (
                  <li key={r.id} className="risk-list-item">
                    <Link to={`/repo/${r.id}`} className="risk-list-link">{r.full_name}</Link>
                    <span className="anomaly-score">unusual</span>
                  </li>
                ))}
              {anomalyReport.results.every((r) => !r.is_anomaly) && (
                <li className="panel-note">No statistical outliers among your saved repos.</li>
              )}
            </ul>
            <p className="panel-note">
              Trained fresh from your saved repos with an Isolation Forest (stars, forks,
              open issues, issue ratio, commit recency, stale PRs) — unsupervised, no labels
              required.
            </p>
          </>
        )}
      </section>

    </div>
  )
}
