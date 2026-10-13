import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { fetchRepos } from '../api'

function fmt(value, suffix = '') {
  if (value === null || value === undefined) return '—'
  return `${value}${suffix}`
}

function pct(value) {
  if (value === null || value === undefined) return '—'
  return `${value}%`
}

function buildRows(repo) {
  const dep = repo.dependencies
  const ci = repo.ci_cd
  const pr = repo.pr_analysis
  const issues = repo.issue_analysis
  const testing = repo.testing_analysis
  const contrib = repo.contributor_analysis
  const releases = repo.release_analysis

  return {
    'Health score': `${fmt(repo.health_score)} (${repo.health_status || '—'})`,
    'Security score': dep?.security?.available ? fmt(dep.security.security_score) : (dep?.security?.reason ? 'unavailable' : '—'),
    'Last activity': repo.last_commit_at ? new Date(repo.last_commit_at).toLocaleDateString() : '—',
    'Stars': fmt(repo.stars),
    'Forks': fmt(repo.forks),
    'Open issues': fmt(issues?.open_issues ?? repo.open_issues),
    'Open PRs': fmt(pr?.open_prs),
    'Merged PRs': fmt(pr?.merged_prs),
    'Stale PRs': fmt(pr?.stale_prs),
    'Contributors': fmt(contrib?.total_contributors ?? repo.contributor_count),
    'Contributor concentration (top 1)': contrib?.available ? pct(contrib.top1_percentage) : '—',
    'Total releases': releases?.available ? (releases.has_releases ? fmt(releases.total_releases) : '0 (none)') : '—',
    'CI/CD': ci ? (ci.has_workflows ? `${fmt(ci.ci_score)}/100` : 'no workflows') : '—',
    'Testing status': testing?.available ? testing.status : '—',
    'Test/source ratio': testing?.available ? fmt(testing.test_source_ratio) : '—',
  }
}

export default function Compare() {
  const [repos, setRepos] = useState([])
  const [loading, setLoading] = useState(true)
  const [leftId, setLeftId] = useState('')
  const [rightId, setRightId] = useState('')

  useEffect(() => {
    fetchRepos()
      .then((data) => {
        setRepos(data)
        if (data.length >= 1) setLeftId(String(data[0].id))
        if (data.length >= 2) setRightId(String(data[1].id))
      })
      .catch(() => setRepos([]))
      .finally(() => setLoading(false))
  }, [])

  const left = repos.find((r) => String(r.id) === leftId)
  const right = repos.find((r) => String(r.id) === rightId)

  return (
    <>
      <motion.header
        className="hero"
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      >
        <p className="eyebrow">git diff --repos</p>
        <h1 className="wordmark">
          Compare<span className="wordmark-accent">Repos</span>
        </h1>
        <p className="tagline">
          Pick two repos you've already analyzed and see how they stack up, side by side.
        </p>
      </motion.header>

      {loading ? (
        <p className="panel-note">Loading your saved repos…</p>
      ) : repos.length < 2 ? (
        <div className="empty-state">
          <p>Analyze at least two repositories to compare them.</p>
          <p className="empty-state-sub">Head back to Analyze to get started.</p>
        </div>
      ) : (
        <>
          <div className="compare-picker-row">
            <div className="compare-picker">
              <label htmlFor="compare-left">Repository A</label>
              <select id="compare-left" value={leftId} onChange={(e) => setLeftId(e.target.value)}>
                {repos.map((r) => (
                  <option key={r.id} value={r.id}>{r.full_name || r.name}</option>
                ))}
              </select>
            </div>
            <div className="compare-picker">
              <label htmlFor="compare-right">Repository B</label>
              <select id="compare-right" value={rightId} onChange={(e) => setRightId(e.target.value)}>
                {repos.map((r) => (
                  <option key={r.id} value={r.id}>{r.full_name || r.name}</option>
                ))}
              </select>
            </div>
          </div>

          {left && right && (() => {
            const leftRow = buildRows(left)
            const rightRow = buildRows(right)
            return (
              <motion.div
                className="detail-panel compare-table-wrap"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3 }}
              >
                <table className="compare-table">
                  <thead>
                    <tr>
                      <th>Metric</th>
                      <th>{left.full_name || left.name}</th>
                      <th>{right.full_name || right.name}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.keys(leftRow).map((label) => (
                      <tr key={label}>
                        <td className="compare-row-label">{label}</td>
                        <td>{leftRow[label]}</td>
                        <td>{rightRow[label]}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="panel-note">
                  All figures come directly from each repo's most recent analysis — nothing here is
                  recomputed or estimated for the comparison.
                </p>
              </motion.div>
            )
          })()}
        </>
      )}
    </>
  )
}
