import { motion } from 'framer-motion'
import { computeAchievements } from '../../lib/repoWorld'

export default function AchievementPanel({ repo }) {
  const achievements = computeAchievements(repo)
  const unlockedCount = achievements.filter((a) => a.unlocked).length

  return (
    <div className="detail-panel world-panel">
      <h2 className="panel-title">Achievements ({unlockedCount}/{achievements.length})</h2>
      <div className="world-achievement-grid">
        {achievements.map((a) => (
          <motion.div
            key={a.key}
            className={`world-achievement ${a.unlocked ? 'world-achievement-unlocked' : 'world-achievement-locked'}`}
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.35 }}
            title={a.description}
          >
            <span className="world-achievement-icon">{a.unlocked ? a.icon : '🔒'}</span>
            <span className="world-achievement-title">{a.title}</span>
            <span className="world-achievement-detail">{a.detail}</span>
          </motion.div>
        ))}
      </div>
      <p className="panel-note">
        Each badge unlocks only when the underlying GitMind metric crosses its stated threshold —
        hover a badge to see exactly which data supports (or doesn't yet support) it.
      </p>
    </div>
  )
}
