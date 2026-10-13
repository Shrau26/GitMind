import { useEffect, useState, useCallback } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { analyzeRepo, fetchRepos, deleteRepo, toggleFavorite } from '../api'
import RepoCard from '../components/RepoCard'
import FeatureSlideshow from '../components/FeatureSlideshow'

const gridVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.06 } },
}

function SkeletonCard({ delay = 0 }) {
  return (
    <motion.div
      className="repo-card repo-card-skeleton"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3, delay }}
    >
      <div className="skeleton-line skeleton-w-40" />
      <div className="skeleton-line skeleton-w-70" />
      <div className="skeleton-line skeleton-w-90" />
      <div className="skeleton-line skeleton-w-50" />
    </motion.div>
  )
}

export default function Home() {
  const [url, setUrl] = useState('')
  const [token, setToken] = useState('')
  const [showToken, setShowToken] = useState(false)
  const [repos, setRepos] = useState([])
  const [loading, setLoading] = useState(false)
  const [loadingList, setLoadingList] = useState(true)
  const [error, setError] = useState(null)
  const [cacheNotice, setCacheNotice] = useState(null)

  const loadRepos = useCallback(async () => {
    setLoadingList(true)
    try {
      const data = await fetchRepos()
      setRepos(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoadingList(false)
    }
  }, [])

  useEffect(() => {
    loadRepos()
  }, [loadRepos])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!url.trim()) {
      setError('Enter a GitHub repository URL first.')
      return
    }
    setLoading(true)
    setError(null)
    setCacheNotice(null)
    try {
      const repo = await analyzeRepo(url.trim(), token.trim())
      setRepos((prev) => {
        const withoutExisting = prev.filter((r) => r.id !== repo.id)
        return [repo, ...withoutExisting]
      })
      if (repo.from_cache) {
        setCacheNotice({ url: url.trim(), repoId: repo.id, cachedAt: repo.cached_at })
      }
      setUrl('')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleForceRefresh = async () => {
    if (!cacheNotice) return
    setLoading(true)
    setError(null)
    try {
      const repo = await analyzeRepo(cacheNotice.url, token.trim(), true)
      setRepos((prev) => {
        const withoutExisting = prev.filter((r) => r.id !== repo.id)
        return [repo, ...withoutExisting]
      })
      setCacheNotice(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (id) => {
    await deleteRepo(id)
    setRepos((prev) => prev.filter((r) => r.id !== id))
  }

  const handleToggleFavorite = async (id) => {
    const updated = await toggleFavorite(id)
    setRepos((prev) => {
      const next = prev.map((r) => (r.id === id ? updated : r))
      // Keep favorites pinned to the top, same as the backend's default ordering.
      return [...next].sort((a, b) => Number(b.is_favorite) - Number(a.is_favorite))
    })
  }

  return (
    <>
      <motion.header
        className="hero"
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      >
        <p className="eyebrow">git log --analyze</p>
        <h1 className="wordmark">
          Git<span className="wordmark-accent">Mind</span>
        </h1>
        <p className="tagline">
          Paste a repository URL. Get its vitals — stars, forks, language, open issues,
          a health score, risk flags, and a plain-English summary — pulled from the GitHub
          API and generated locally.
        </p>
      </motion.header>

      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.08, ease: [0.22, 1, 0.36, 1] }}
      >
        <FeatureSlideshow />
      </motion.div>

      <motion.form
        className="analyze-form"
        onSubmit={handleSubmit}
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.15, ease: [0.22, 1, 0.36, 1] }}
      >
        <div className="field-row">
          <input
            type="text"
            className="url-input"
            placeholder="https://github.com/owner/repository"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            disabled={loading}
            autoComplete="off"
            spellCheck="false"
          />
          <motion.button
            type="submit"
            className="analyze-button"
            disabled={loading}
            whileHover={loading ? {} : { scale: 1.02 }}
            whileTap={loading ? {} : { scale: 0.97 }}
          >
            <AnimatePresence mode="wait" initial={false}>
              <motion.span
                key={loading ? 'loading' : 'idle'}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.15 }}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}
              >
                {loading && <span className="btn-spinner" aria-hidden="true" />}
                {loading ? 'Analyzing…' : 'Analyze'}
              </motion.span>
            </AnimatePresence>
          </motion.button>
        </div>

        <div className="token-row">
          <button
            type="button"
            className="token-toggle"
            onClick={() => setShowToken((s) => !s)}
          >
            {showToken ? '– hide token field' : '+ add a GitHub token (optional)'}
          </button>
          <AnimatePresence initial={false}>
            {showToken && (
              <motion.input
                type="password"
                className="token-input"
                placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                disabled={loading}
                autoComplete="off"
                initial={{ opacity: 0, height: 0, marginTop: 0 }}
                animate={{ opacity: 1, height: 'auto', marginTop: 8 }}
                exit={{ opacity: 0, height: 0, marginTop: 0 }}
                transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
              />
            )}
          </AnimatePresence>
        </div>

        <AnimatePresence>
          {error && (
            <motion.p
              className="error-banner"
              role="alert"
              initial={{ opacity: 0, y: -6, height: 0 }}
              animate={{ opacity: 1, y: 0, height: 'auto' }}
              exit={{ opacity: 0, y: -6, height: 0 }}
              transition={{ duration: 0.2 }}
            >
              {error}
            </motion.p>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {cacheNotice && (
            <motion.p
              className="cache-notice-banner"
              initial={{ opacity: 0, y: -6, height: 0 }}
              animate={{ opacity: 1, y: 0, height: 'auto' }}
              exit={{ opacity: 0, y: -6, height: 0 }}
              transition={{ duration: 0.2 }}
            >
              Showing cached data from{' '}
              {cacheNotice.cachedAt ? new Date(cacheNotice.cachedAt.replace(' ', 'T') + 'Z').toLocaleTimeString() : 'earlier'}
              {' '}(analyzed within the last 10 minutes, so GitHub wasn't re-queried).{' '}
              <button type="button" className="cache-notice-link" onClick={handleForceRefresh} disabled={loading}>
                Force refresh
              </button>
            </motion.p>
          )}
        </AnimatePresence>
      </motion.form>

      <main className="results">
        {loadingList ? (
          <div className="repo-grid">
            <SkeletonCard delay={0} />
            <SkeletonCard delay={0.06} />
            <SkeletonCard delay={0.12} />
          </div>
        ) : repos.length === 0 ? (
          <motion.div
            className="empty-state"
            initial={{ opacity: 0, scale: 0.97 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.35 }}
          >
            <p>No repositories analyzed yet.</p>
            <p className="empty-state-sub">Drop a GitHub URL above to get started.</p>
          </motion.div>
        ) : (
          <motion.div
            className="repo-grid"
            variants={gridVariants}
            initial="hidden"
            animate="visible"
          >
            <AnimatePresence>
              {repos.map((repo) => (
                <RepoCard key={repo.id} repo={repo} onDelete={handleDelete} onToggleFavorite={handleToggleFavorite} />
              ))}
            </AnimatePresence>
          </motion.div>
        )}
      </main>
    </>
  )
}
