import { useState } from 'react'
import { simulateWhatIf, WHAT_IF_SCENARIOS, FACTOR_LABELS } from '../../lib/repoWorld'

export default function WhatIfSimulator({ repo }) {
  const breakdown = repo?.health_breakdown || {}
  const [scenarioKey, setScenarioKey] = useState(WHAT_IF_SCENARIOS[0].key)
  const scenario = WHAT_IF_SCENARIOS.find((s) => s.key === scenarioKey)

  const factorInfo = breakdown[scenario.factor]
  const factorAvailable = Boolean(factorInfo?.available)
  const baseline = factorAvailable ? factorInfo.score : 50
  const hypothetical = scenario.absolute != null
    ? scenario.absolute
    : Math.max(0, Math.min(100, baseline + scenario.delta))

  const result = repo?.health_score != null ? simulateWhatIf(repo, scenario.factor, hypothetical) : null

  return (
    <div className="detail-panel world-panel">
      <h2 className="panel-title">Repository what-if simulator</h2>
      {!repo?.health_score || Object.keys(breakdown).length === 0 ? (
        <p className="panel-note" style={{ margin: 0 }}>Data unavailable — no health breakdown to simulate against.</p>
      ) : (
        <>
          <div className="world-whatif-picker">
            {WHAT_IF_SCENARIOS.map((s) => (
              <button
                key={s.key}
                type="button"
                className={`world-whatif-chip ${s.key === scenarioKey ? 'world-whatif-chip-active' : ''}`}
                onClick={() => setScenarioKey(s.key)}
              >
                {s.label}
              </button>
            ))}
          </div>

          {!factorAvailable && (
            <p className="panel-note">
              {FACTOR_LABELS[scenario.factor]} data isn't available for this repo, so the simulation assumes a
              neutral baseline score of 50 for it.
            </p>
          )}

          <div className="world-whatif-result">
            <div className="world-whatif-score">
              <span className="world-whatif-score-label">Current health</span>
              <span className="world-whatif-score-value">{result.current}</span>
            </div>
            <span className="world-whatif-arrow">→</span>
            <div className="world-whatif-score">
              <span className="world-whatif-score-label">Simulated health</span>
              <span className={`world-whatif-score-value ${result.impact < 0 ? 'world-whatif-down' : result.impact > 0 ? 'world-whatif-up' : ''}`}>
                {result.simulated} {result.impact !== 0 && (result.impact > 0 ? `↑` : `↓`)}
              </span>
            </div>
          </div>
          <p className="panel-note" style={{ textAlign: 'center' }}>
            Impact: {result.impact > 0 ? '+' : ''}{result.impact} — {FACTOR_LABELS[scenario.factor]} hypothetically set to {hypothetical}/100
          </p>
          <p className="panel-note world-whatif-disclaimer">
            <strong>Simulated result — does not modify repository data.</strong> This recomputes GitMind's own
            weighted health formula with one factor score hypothetically changed; it is not a real GitHub metric.
          </p>
        </>
      )}
    </div>
  )
}
