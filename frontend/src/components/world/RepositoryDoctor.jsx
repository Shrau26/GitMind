import { buildDiagnosis } from '../../lib/repoWorld'

export default function RepositoryDoctor({ repo }) {
  const diagnosis = buildDiagnosis(repo)

  return (
    <div className="detail-panel world-panel">
      <h2 className="panel-title">🧠 Repository doctor</h2>
      {!diagnosis.hasData ? (
        <p className="panel-note" style={{ margin: 0 }}>Data unavailable — no health breakdown to diagnose.</p>
      ) : (
        <>
          <p className="world-doctor-overall">
            Overall: <span className={`health-status-pill health-status-${diagnosis.overall.toLowerCase().replace(' ', '-')}`}>{diagnosis.overall}</span>
          </p>

          <div className="world-doctor-columns">
            <div>
              <h3 className="panel-subtitle">Strengths</h3>
              {diagnosis.strengths.length === 0 ? (
                <p className="panel-note" style={{ margin: 0 }}>No factor currently scores 75+.</p>
              ) : (
                <ul className="world-doctor-list">
                  {diagnosis.strengths.map((s) => <li key={s}>✓ {s}</li>)}
                </ul>
              )}
            </div>
            <div>
              <h3 className="panel-subtitle">Weaknesses</h3>
              {diagnosis.weaknesses.length === 0 ? (
                <p className="panel-note" style={{ margin: 0 }}>No factor currently scores below 50.</p>
              ) : (
                <ul className="world-doctor-list world-doctor-list-warn">
                  {diagnosis.weaknesses.map((w) => <li key={w.factor}>⚠ {w.label} ({w.score}/100)</li>)}
                </ul>
              )}
            </div>
          </div>

          {diagnosis.priority.length > 0 && (
            <>
              <h3 className="panel-subtitle">Priority</h3>
              <ol className="world-doctor-priority">
                {diagnosis.priority.map((p) => <li key={p}>{p}</li>)}
              </ol>
            </>
          )}

          {diagnosis.riskFlags.length > 0 && (
            <div className="risk-flags risk-flags-detail" style={{ marginTop: 10 }}>
              {diagnosis.riskFlags.map((f) => <span key={f} className="risk-flag">{f}</span>)}
            </div>
          )}

          <p className="panel-note">
            Built entirely from GitMind's existing weighted Risk Engine (health_breakdown and
            risk_flags) — no separate diagnosis logic runs here.
          </p>
        </>
      )}
    </div>
  )
}
