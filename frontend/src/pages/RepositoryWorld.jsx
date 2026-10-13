import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import RepositoryEnvironment from '../components/world/RepositoryEnvironment'
import XPProgress from '../components/world/XPProgress'
import MaintenanceLevel from '../components/world/MaintenanceLevel'
import AchievementPanel from '../components/world/AchievementPanel'
import RepositoryTimeline from '../components/world/RepositoryTimeline'
import WhatIfSimulator from '../components/world/WhatIfSimulator'
import RepositoryDoctor from '../components/world/RepositoryDoctor'
import { fetchRepo, fetchRepoHistory } from '../api'
import '../world.css'

// Maps a clicked world structure to where its real detail already lives in
// GitMind — the world never duplicates analysis, only launches into it.
const NAV_TARGETS = {
  security: (id) => `/repo/${id}/security`,
}

export default function RepositoryWorld() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [repo, setRepo] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [history, setHistory] = useState([])
  const [historyLoading, setHistoryLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetchRepo(id)
      .then((data) => { if (!cancelled) setRepo(data) })
      .catch((err) => { if (!cancelled) setError(err.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [id])

  useEffect(() => {
    let cancelled = false
    setHistoryLoading(true)
    fetchRepoHistory(id)
      .then((data) => { if (!cancelled) setHistory(data) })
      .catch(() => { if (!cancelled) setHistory([]) })
      .finally(() => { if (!cancelled) setHistoryLoading(false) })
    return () => { cancelled = true }
  }, [id])

  const handleNavigate = (key) => {
    if (NAV_TARGETS[key]) {
      navigate(NAV_TARGETS[key](id))
      return
    }
    navigate(`/repo/${id}#${key}`)
  }

  if (loading) return <p className="status-text">Loading repository world…</p>
  if (error) return <p className="error-banner" role="alert">{error}</p>
  if (!repo) return null

  return (
    <div className="repo-detail world-page">
      <Link to={`/repo/${id}`} className="back-link">← back to repo</Link>

      <header className="repo-detail-header">
        <div>
          <p className="repo-eyebrow">
            {repo.owner}
          </p>
          <h1 className="repo-detail-title">🌎 Repository World</h1>
          <p className="repo-detail-fullname">{repo.full_name}</p>
        </div>
      </header>

      <section className="detail-panel world-panel world-environment-panel">
        <h2 className="panel-title">Live environment</h2>
        <p className="panel-note" style={{ marginTop: 0 }}>
          Click any structure to open its real analysis. Every visual here reflects an actual
          GitMind metric — nothing is decorative-only or invented.
        </p>
        <RepositoryEnvironment repo={repo} onNavigate={handleNavigate} />
      </section>

      <div className="world-two-col">
        <XPProgress repo={repo} />
        <MaintenanceLevel history={history} historyLoading={historyLoading} />
      </div>

      <AchievementPanel repo={repo} />

      <RepositoryTimeline history={history} historyLoading={historyLoading} />

      <WhatIfSimulator repo={repo} />

      <RepositoryDoctor repo={repo} />
    </div>
  )
}
