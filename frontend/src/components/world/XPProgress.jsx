import { motion } from 'framer-motion'
import { computeXP } from '../../lib/repoWorld'

export default function XPProgress({ repo }) {
  const { xp, xpMax, level, progressPct } = computeXP(repo)
  const available = repo?.health_score != null

  return (
    <div className="detail-panel world-panel">
      <h2 className="panel-title">Repository level</h2>
      {!available ? (
        <p className="panel-note" style={{ margin: 0 }}>Data unavailable.</p>
      ) : (
        <>
          <div className="world-level-row">
            <span className="world-level-number">{level}</span>
            <div className="world-xp-track">
              <motion.div
                className="world-xp-fill"
                initial={{ width: 0 }}
                animate={{ width: `${progressPct}%` }}
                transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
              />
            </div>
          </div>
          <p className="panel-note" style={{ margin: '8px 0 0' }}>{xp} / {xpMax} XP</p>
          <p className="panel-note">
            XP is the repo's own weighted health score (health_score × 10) — it isn't a separate
            invented metric, just the same 0-100 score GitMind already computes, shown as a
            0-1000 bar with a level number.
          </p>
        </>
      )}
    </div>
  )
}
