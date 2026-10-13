import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchRepos } from '../api'
import HealthBadge from '../components/HealthBadge'
import '../world.css'

export default function WorldHub() {
  const [repos, setRepos] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetchRepos()
      .then(setRepos)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <p className="status-text">Loading your repositories…</p>
  if (error) return <p className="error-banner" role="alert">{error}</p>

  return (
    <div className="repo-detail">
      <h1 className="repo-detail-title">🌎 Repository World</h1>
      <p className="panel-note" style={{ marginTop: 4, marginBottom: 24 }}>
        Pick a repository to enter its live world — a visual, game-like reflection of the same
        real analysis GitMind already computes for it.
      </p>

      {repos.length === 0 ? (
        <section className="detail-panel">
          <p className="panel-note" style={{ margin: 0 }}>
            No repositories analyzed yet. <Link to="/" className="risk-list-link">Analyze one first →</Link>
          </p>
        </section>
      ) : (
        <div className="repo-grid">
          {repos.map((repo) => (
            <Link key={repo.id} to={`/repo/${repo.id}/world`} className="world-hub-card">
              <div className="world-hub-card-head">
                <span>{repo.is_favorite ? '★ ' : ''}{repo.name}</span>
                <HealthBadge score={repo.health_score} size="sm" />
              </div>
              <span className="panel-note" style={{ margin: 0 }}>
                {repo.full_name}
              </span>
              <span className="risk-list-link" style={{ marginTop: 8, display: 'inline-block' }}>Enter world →</span>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
