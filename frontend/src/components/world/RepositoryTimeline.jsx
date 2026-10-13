import { useEffect, useState } from 'react'
import { computeXP } from '../../lib/repoWorld'

// GitMind's repo_snapshots table only stores health_score, security_score,
// open_issues, open_pr_count, stars, and contributor_count per snapshot —
// CI/CD, testing, documentation, and release data are NOT captured
// historically. Rather than backfill or estimate those, this timeline
// shows only what a snapshot really recorded and says so plainly for the
// rest.
function fmtDate(iso) {
  return new Date(iso.replace(' ', 'T') + 'Z').toLocaleDateString()
}

export default function RepositoryTimeline({ history, historyLoading }) {
  const [index, setIndex] = useState(0)

  useEffect(() => {
    if (history?.length) setIndex(history.length - 1)
  }, [history?.length])

  if (historyLoading) {
    return (
      <div className="detail-panel world-panel">
        <h2 className="panel-title">Repository time machine</h2>
        <p className="panel-note" style={{ margin: 0 }}>Loading history…</p>
      </div>
    )
  }

  if (!history || history.length < 2) {
    return (
      <div className="detail-panel world-panel">
        <h2 className="panel-title">Repository time machine</h2>
        <p className="panel-note" style={{ margin: 0 }}>
          {history?.length === 1
            ? 'Only one snapshot on record — re-analyze this repo over time to build a timeline.'
            : 'No history yet — a snapshot is recorded each time this repo is analyzed.'}
        </p>
      </div>
    )
  }

  const snap = history[index]
  const prev = index > 0 ? history[index - 1] : null
  const level = computeXP({ health_score: snap.health_score }).level

  const rows = [
    { label: 'Health', value: snap.health_score, prevValue: prev?.health_score },
    { label: 'Repository level', value: level, prevValue: prev ? computeXP({ health_score: prev.health_score }).level : null },
    { label: 'Security score', value: snap.security_score, prevValue: prev?.security_score },
    { label: 'Contributors', value: snap.contributor_count, prevValue: prev?.contributor_count },
    { label: 'Open issues', value: snap.open_issues, prevValue: prev?.open_issues },
    { label: 'Open PRs', value: snap.open_pr_count, prevValue: prev?.open_pr_count },
    { label: 'Stars', value: snap.stars, prevValue: prev?.stars },
  ]

  return (
    <div className="detail-panel world-panel">
      <h2 className="panel-title">Repository time machine</h2>
      <div className="world-timeline-track">
        <span className="world-timeline-endpoint">{fmtDate(history[0].captured_at)}</span>
        <input
          type="range"
          min={0}
          max={history.length - 1}
          value={index}
          onChange={(e) => setIndex(Number(e.target.value))}
          className="world-timeline-slider"
        />
        <span className="world-timeline-endpoint">Now</span>
      </div>
      <p className="panel-note" style={{ margin: '4px 0 12px', textAlign: 'center' }}>
        Snapshot {index + 1} of {history.length} — {fmtDate(snap.captured_at)}
      </p>

      <div className="world-timeline-grid">
        {rows.map((r) => {
          const delta = r.value != null && r.prevValue != null ? r.value - r.prevValue : null
          return (
            <div key={r.label} className="world-timeline-cell">
              <span className="world-timeline-cell-label">{r.label}</span>
              <span className="world-timeline-cell-value">
                {r.value != null ? r.value : '—'}
                {delta != null && delta !== 0 && (
                  <span className={delta > 0 ? 'world-timeline-delta-up' : 'world-timeline-delta-down'}>
                    {delta > 0 ? ` ↑${delta}` : ` ↓${Math.abs(delta)}`}
                  </span>
                )}
              </span>
            </div>
          )
        })}
      </div>
      <p className="panel-note">
        CI/CD, testing, documentation, and release data aren't captured in historical snapshots
        (only health score, security score, issues, PRs, stars, and contributors are) — so those
        aren't shown here to avoid implying a trend GitMind hasn't actually recorded.
      </p>
    </div>
  )
}
