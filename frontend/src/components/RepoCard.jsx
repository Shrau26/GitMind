import { useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import HealthBadge from './HealthBadge'

function formatNumber(n) {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}m`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

function timeAgo(isoString) {
  if (!isoString) return 'unknown'
  const then = new Date(isoString.replace(' ', 'T').endsWith('Z') ? isoString.replace(' ', 'T') : isoString.replace(' ', 'T') + 'Z')
  const seconds = Math.floor((Date.now() - then.getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}d ago`
  const months = Math.floor(days / 30)
  if (months < 12) return `${months}mo ago`
  return `${Math.floor(months / 12)}y ago`
}

export function StatBar({ stars, forks }) {
  const total = stars + forks
  const starPct = total === 0 ? 50 : Math.max(6, Math.round((stars / total) * 100))
  return (
    <div className="stat-bar" title={`${stars} stars, ${forks} forks`}>
      <motion.div
        className="stat-bar-stars"
        initial={{ width: 0 }}
        animate={{ width: `${starPct}%` }}
        transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1], delay: 0.1 }}
      />
      <motion.div
        className="stat-bar-forks"
        initial={{ width: 0 }}
        animate={{ width: `${100 - starPct}%` }}
        transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1], delay: 0.1 }}
      />
    </div>
  )
}

const cardVariants = {
  hidden: { opacity: 0, y: 18, scale: 0.97 },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { duration: 0.4, ease: [0.22, 1, 0.36, 1] },
  },
  exit: {
    opacity: 0,
    scale: 0.92,
    transition: { duration: 0.2, ease: [0.4, 0, 1, 1] },
  },
}

export default function RepoCard({ repo, onDelete, onToggleFavorite }) {
  const [deleting, setDeleting] = useState(false)
  const [togglingFavorite, setTogglingFavorite] = useState(false)

  const handleDelete = async (e) => {
    e.preventDefault()
    e.stopPropagation()
    setDeleting(true)
    try {
      await onDelete(repo.id)
    } catch {
      setDeleting(false)
    }
  }

  const handleToggleFavorite = async (e) => {
    e.preventDefault()
    e.stopPropagation()
    if (!onToggleFavorite) return
    setTogglingFavorite(true)
    try {
      await onToggleFavorite(repo.id)
    } finally {
      setTogglingFavorite(false)
    }
  }

  return (
    <motion.article
      className="repo-card"
      layout
      variants={cardVariants}
      initial="hidden"
      animate="visible"
      exit="exit"
      whileHover={{ y: -4, transition: { duration: 0.18, ease: 'easeOut' } }}
    >
      <header className="repo-card-header">
        <div>
          <p className="repo-eyebrow">
            {repo.owner}
          </p>
          <h3 className="repo-name">
            <Link to={`/repo/${repo.id}`}>{repo.name}</Link>
          </h3>
        </div>
        <div className="repo-card-header-actions">
          <HealthBadge score={repo.health_score} size="sm" />
          {onToggleFavorite && (
            <motion.button
              className={`icon-button favorite-toggle${repo.is_favorite ? ' favorite-toggle-active' : ''}`}
              onClick={handleToggleFavorite}
              disabled={togglingFavorite}
              aria-label={repo.is_favorite ? `Unpin ${repo.full_name}` : `Pin ${repo.full_name}`}
              aria-pressed={!!repo.is_favorite}
              title={repo.is_favorite ? 'Remove from favorites' : 'Add to favorites'}
              whileHover={{ scale: 1.08 }}
              whileTap={{ scale: 0.9 }}
            >
              {repo.is_favorite ? '★' : '☆'}
            </motion.button>
          )}
          <motion.button
            className="icon-button"
            onClick={handleDelete}
            disabled={deleting}
            aria-label={`Remove ${repo.full_name}`}
            title="Remove from list"
            whileHover={{ scale: 1.08 }}
            whileTap={{ scale: 0.9 }}
          >
            {deleting ? '…' : '✕'}
          </motion.button>
        </div>
      </header>

      {repo.summary ? (
        <p className="repo-description">{repo.summary}</p>
      ) : repo.description ? (
        <p className="repo-description">{repo.description}</p>
      ) : null}

      {(
        <div className="repo-stats">
          <span className="stat">
            <span className="stat-icon">★</span>
            {formatNumber(repo.stars)}
          </span>
          <span className="stat">
            <span className="stat-icon">⑂</span>
            {formatNumber(repo.forks)}
          </span>
          <span className="stat">
            <span className="stat-icon">●</span>
            {formatNumber(repo.open_issues)} issues
          </span>
          {repo.language && <span className="language-tag">{repo.language}</span>}
          {repo.predicted_category && (
            <span className="category-tag" title={`Predicted by the trained category classifier (${Math.round((repo.predicted_category_confidence || 0) * 100)}% confidence)`}>
              {repo.predicted_category}
            </span>
          )}
        </div>
      )}

      <StatBar stars={repo.stars} forks={repo.forks} />

      {repo.risk_flags && repo.risk_flags.length > 0 && repo.risk_flags[0] !== 'no risk signals detected' && (
        <div className="risk-flags">
          {repo.risk_flags.map((flag) => (
            <span key={flag} className="risk-flag">{flag}</span>
          ))}
        </div>
      )}

      <footer className="repo-card-footer">
        <span className="repo-card-footer-path">{repo.full_name}</span>
        <span>updated {timeAgo(repo.updated_at)}</span>
      </footer>
    </motion.article>
  )
}

export { formatNumber, timeAgo }
