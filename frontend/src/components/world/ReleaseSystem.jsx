import { motion } from 'framer-motion'

// The rocket only "launches" (animates) when a release actually happened
// recently (days_since <= 14) — otherwise it sits idle on the pad. Recency
// and frequency both come straight from release_analysis.
export default function ReleaseSystem({ releaseAnalysis, onClick }) {
  const available = Boolean(releaseAnalysis?.available && releaseAnalysis.has_releases)
  const recentlyLaunched = available && releaseAnalysis.latest_release?.days_since != null && releaseAnalysis.latest_release.days_since <= 14

  return (
    <button type="button" className="world-structure world-release" onClick={onClick} title="Release launch system">
      <svg viewBox="0 0 60 90" className="world-structure-svg">
        <motion.g
          animate={recentlyLaunched ? { y: [0, -6, 0] } : {}}
          transition={{ duration: 1.6, repeat: recentlyLaunched ? Infinity : 0, ease: 'easeInOut' }}
        >
          <path d="M30 6 L40 40 H20 Z" className="world-release-nose" />
          <rect x="20" y="40" width="20" height="30" className="world-release-body" />
          <path d="M20 70 L10 84 H20 Z" className="world-release-fin" />
          <path d="M40 70 L50 84 H40 Z" className="world-release-fin" />
        </motion.g>
        {recentlyLaunched && (
          <motion.path
            d="M30 70 L30 90"
            className="world-release-flame"
            animate={{ opacity: [0.3, 1, 0.3], pathLength: [0.3, 1, 0.3] }}
            transition={{ duration: 0.5, repeat: Infinity }}
          />
        )}
      </svg>
      <div className="world-structure-label">
        <strong>Release System</strong>
        <span>
          {available
            ? `Latest: ${releaseAnalysis.latest_release.name} (${releaseAnalysis.latest_release.days_since}d ago)`
            : (releaseAnalysis?.message || 'Data unavailable')}
        </span>
      </div>
    </button>
  )
}
