import { useEffect, useState } from 'react'
import { fetchPredictiveRisk } from '../api'

function directionClass(direction) {
  if (direction === 'Deteriorating') return 'predictive-risk-bad'
  if (direction === 'Improving') return 'predictive-risk-good'
  return ''
}

function titleForFactor(factor) {
  return {
    contributors: 'Contributor concentration',
    pull_requests: 'Pull request backlog',
    testing: 'Testing',
    security: 'Security',
    ci_cd: 'CI/CD',
    activity: 'Activity',
    issues: 'Issues',
    documentation: 'Documentation',
    releases: 'Releases',
  }[factor] || factor.replaceAll('_', ' ')
}

export default function PredictiveRiskCard({ repo }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetchPredictiveRisk(repo.id)
      .then((value) => { if (!cancelled) setData(value) })
      .catch(() => { if (!cancelled) setData(null) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [repo.id])

  return (
    <section className="detail-panel predictive-risk-panel">
      <div className="predictive-risk-heading">
        <div>
          <h2 className="panel-title">🔮 Predictive Repository Risk</h2>
          <p className="panel-note">Repository Failure Forecast &amp; Recovery Engine — deterministic GitMind analysis, not a second health score.</p>
        </div>
        {data?.confidence && <span className={`predictive-confidence predictive-confidence-${data.confidence.toLowerCase()}`}>{data.confidence} confidence</span>}
      </div>

      {loading ? <p className="panel-note">Analyzing repository history…</p> : !data ? (
        <p className="panel-note">Predictive analysis is temporarily unavailable.</p>
      ) : !data.available ? (
        <div className="predictive-insufficient">
          <strong>Forecast requires additional repository history.</strong>
          <span>GitMind never fabricates missing historical snapshots.</span>
        </div>
      ) : (
        <>
          <div className="predictive-summary-grid">
            <div><span>Current Health</span><strong>{data.current_health ?? '—'}</strong></div>
            <div><span>Future Direction</span><strong className={directionClass(data.future_direction)}>{data.future_direction}</strong></div>
            <div><span>Risk Level</span><strong>{data.risk_level}</strong></div>
            <div><span>History</span><strong>{data.history_points} snapshots</strong></div>
          </div>

          {data.health_paradox?.detected && (
            <div className="predictive-paradox">
              <strong>⚠ HEALTH PARADOX DETECTED</strong>
              <p>
                Health improved {data.health_paradox.previous_health} → {data.health_paradox.current_health},
                but structural risk increased.
              </p>
              <div className="predictive-evidence-list">
                {data.health_paradox.worsened_factors.map((factor) => <span key={factor}>• {titleForFactor(factor)} worsened</span>)}
              </div>
            </div>
          )}

          {data.top_risk_pathways?.length > 0 && (
            <div className="predictive-section">
              <h3>Top Risk Pathways</h3>
              {data.top_risk_pathways.map((pathway) => (
                <div className="predictive-pathway" key={pathway.name}>
                  <strong>{pathway.name}</strong>
                  <div className="predictive-pathway-flow">
                    {pathway.factors.map((factor) => <span key={factor}>{titleForFactor(factor)}</span>)}
                  </div>
                  <small>{pathway.relationship}</small>
                  <div className="predictive-evidence-list">
                    {pathway.evidence.map((item) => <span key={item}>• {item}</span>)}
                  </div>
                </div>
              ))}
            </div>
          )}

          {data.recommended_intervention && (
            <div className="predictive-recommendation">
              <p className="predictive-kicker">RECOMMENDED FIRST ACTION</p>
              <h3>{data.recommended_intervention.action}</h3>
              <div className="predictive-recommendation-meta">
                <span>Expected risk reduction: <strong>{data.recommended_intervention.expected_risk_reduction}</strong></span>
                <span>Estimated effort: <strong>{data.recommended_intervention.estimated_effort}</strong></span>
                <span>Confidence: <strong>{data.recommended_intervention.confidence}</strong></span>
              </div>
              <p>{data.recommended_intervention.problem} is an observed problem in the selected risk pathway. The result is a simulated estimate using GitMind's existing health-factor weighting.</p>
              <small>SIMULATED / ESTIMATED — not a guaranteed outcome.</small>
            </div>
          )}

          {data.alternative_interventions?.length > 0 && (
            <div className="predictive-section">
              <h3>Alternative Interventions</h3>
              <div className="predictive-alternatives">
                {data.alternative_interventions.map((item) => (
                  <div className="predictive-alt" key={item.action}>
                    <strong>{item.action}</strong>
                    <span>{item.expected_risk_reduction} reduction · {item.estimated_effort} effort</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="predictive-section">
            <h3>Evidence &amp; Confidence</h3>
            <div className="predictive-evidence-list">
              {(data.evidence || []).map((item) => <span key={item}>• {item}</span>)}
              {(!data.evidence || data.evidence.length === 0) && <span>• No additional trend evidence available.</span>}
            </div>
            <p className="panel-note">Relationships are reported as associated risk pathways, not proven causal relationships.</p>
          </div>
        </>
      )}
    </section>
  )
}
