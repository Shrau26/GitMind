import { motion } from 'framer-motion'

// Central glowing core: color + pulse intensity map directly to
// repo.health_score (0-100), the same score used everywhere else in
// GitMind. No separate "core energy" metric is invented.
export default function RepositoryCore({ healthScore, healthStatus, tierIcon, onClick }) {
  const available = healthScore != null
  const pct = available ? Math.max(4, healthScore) : 0

  return (
    <button
      type="button"
      className="world-core"
      onClick={onClick}
      title={available ? `Health score: ${healthScore}/100` : 'Health score unavailable'}
    >
      <motion.div
        className="world-core-ring"
        style={{ '--core-pct': pct }}
        animate={available ? { scale: [1, 1.03, 1] } : {}}
        transition={{ duration: 3.2, repeat: Infinity, ease: 'easeInOut' }}
      >
        <div className="world-core-inner">
          <span className="world-core-icon">{tierIcon}</span>
          <span className="world-core-score">{available ? healthScore : 'N/A'}</span>
          <span className="world-core-label">{healthStatus || 'Data unavailable'}</span>
        </div>
      </motion.div>
    </button>
  )
}
