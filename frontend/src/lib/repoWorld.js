// Repository World: derived, presentation-only calculations.
//
// Every function here reads fields GitMind's backend already computed
// (health_score, health_breakdown, ci_cd, dependencies, testing_analysis,
// documentation_analysis, release_analysis, branch_analysis,
// contributor_analysis, issue_analysis, pr_analysis, risk_flags). Nothing
// is fetched or invented independently — this module only reshapes real
// data for the game-like presentation layer.

// Same weights as backend/health.py WEIGHTS — duplicated as plain data
// (not re-implementing the scoring logic) so the What-If simulator can
// recompute the *same* weighted average client-side for a hypothetical
// factor score, without a round trip. Kept numerically identical on
// purpose; if health.py's weights ever change, update here too.
export const HEALTH_WEIGHTS = {
  activity: 20,
  issues: 15,
  pull_requests: 10,
  contributors: 10,
  releases: 8,
  ci_cd: 15,
  security: 12,
  testing: 5,
  documentation: 5,
}

export const FACTOR_LABELS = {
  activity: 'Activity',
  issues: 'Issues',
  pull_requests: 'Pull requests',
  contributors: 'Contributors',
  releases: 'Releases',
  ci_cd: 'CI/CD',
  security: 'Security',
  testing: 'Testing',
  documentation: 'Documentation',
}

// --- Environment tier -----------------------------------------------------
// Reuses the exact thresholds HealthBadge already uses (80/55/30) so the
// World's tier always agrees with the health badge shown everywhere else.
export function environmentTier(healthScore) {
  if (healthScore == null) return { tier: 1, key: 'beginner', label: 'Beginner', icon: '🌱' }
  if (healthScore >= 80) return { tier: 4, key: 'excellent', label: 'Excellent', icon: '🚀' }
  if (healthScore >= 55) return { tier: 3, key: 'mature', label: 'Mature', icon: '🏢' }
  if (healthScore >= 30) return { tier: 2, key: 'growing', label: 'Growing', icon: '🌿' }
  return { tier: 1, key: 'beginner', label: 'Beginner', icon: '🌱' }
}

// --- XP & Level -------------------------------------------------------------
// XP is literally the same weighted health composite, scaled to /1000
// instead of /100 — it does not add any new weighting scheme on top of the
// Risk Engine's own health score, since that score already excludes
// unavailable factors and redistributes weight honestly.
export function computeXP(repo) {
  const health = repo?.health_score
  if (health == null) return { xp: 0, xpMax: 1000, level: 1, progressPct: 0 }
  const xp = Math.round(health * 10)
  const level = 1 + Math.floor(xp / 100) // 1..11
  const progressPct = xp % 100
  return { xp, xpMax: 1000, level, progressPct }
}

// --- Maintenance streak -----------------------------------------------------
// Counts consecutive most-recent history snapshots (each snapshot = one
// real analysis) with a non-decreasing health score. Requires at least 2
// snapshots; otherwise honestly reports insufficient data rather than
// fabricating a streak.
export function computeMaintenanceStreak(history) {
  if (!history || history.length < 2) {
    return { available: false, days: null, snapshots: 0 }
  }
  const sorted = [...history].sort(
    (a, b) => new Date(a.captured_at.replace(' ', 'T') + 'Z') - new Date(b.captured_at.replace(' ', 'T') + 'Z')
  )
  let streak = 1
  for (let i = sorted.length - 1; i > 0; i--) {
    const cur = sorted[i].health_score
    const prev = sorted[i - 1].health_score
    if (cur == null || prev == null || cur < prev) break
    streak += 1
  }
  const first = sorted[sorted.length - streak]
  const last = sorted[sorted.length - 1]
  const days = Math.max(
    0,
    Math.round(
      (new Date(last.captured_at.replace(' ', 'T') + 'Z') - new Date(first.captured_at.replace(' ', 'T') + 'Z')) /
        86400000
    )
  )
  return { available: true, days, snapshots: streak }
}

// --- Achievements -----------------------------------------------------------
// Each achievement carries the exact condition it checked, so the UI can
// state plainly why it is (or isn't) unlocked — no achievement is granted
// without a real, cited field backing it.
export function computeAchievements(repo) {
  const ci = repo?.ci_cd
  const pr = repo?.pr_analysis
  const testing = repo?.testing_analysis
  const doc = repo?.documentation_analysis
  const security = repo?.dependencies?.security
  const contrib = repo?.contributor_analysis
  const release = repo?.release_analysis

  return [
    {
      key: 'ci_master',
      icon: '🏆',
      title: 'CI Master',
      description: 'CI/CD score of 80+ across sampled workflow runs.',
      unlocked: Boolean(ci && ci.ci_score != null && ci.ci_score >= 80),
      detail: ci && ci.ci_score != null
        ? `CI/CD score: ${ci.ci_score}/100 (${ci.success_count}/${ci.sample_size} runs succeeded)`
        : 'No CI/CD data available.',
    },
    {
      key: 'pr_cleaner',
      icon: '🧹',
      title: 'PR Cleaner',
      description: 'Zero stale open pull requests.',
      unlocked: Boolean(pr && pr.stale_prs === 0),
      detail: pr ? `${pr.stale_prs} stale PR${pr.stale_prs === 1 ? '' : 's'} out of ${pr.open_prs} open` : 'No pull request data available.',
    },
    {
      key: 'testing_champion',
      icon: '🧪',
      title: 'Testing Champion',
      description: 'Test-to-source ratio classified "Good".',
      unlocked: Boolean(testing?.available && testing.status === 'Good'),
      detail: testing?.available
        ? `Status: ${testing.status} (${testing.total_test_files} test files / ${testing.total_source_files} source files)`
        : 'No testing data available.',
    },
    {
      key: 'documentation_hero',
      icon: '📚',
      title: 'Documentation Hero',
      description: 'Documentation score of 80+.',
      unlocked: Boolean(doc?.available && doc.documentation_score >= 80),
      detail: doc?.available ? `Documentation score: ${doc.documentation_score}/100` : 'No documentation data available.',
    },
    {
      key: 'security_guardian',
      icon: '🛡️',
      title: 'Security Guardian',
      description: 'No critical or high-severity dependency vulnerabilities.',
      unlocked: Boolean(security?.available && security.critical === 0 && security.high === 0),
      detail: security?.available
        ? `${security.critical} critical, ${security.high} high severity alerts`
        : (security?.reason || 'Security data not available.'),
    },
    {
      key: 'community_builder',
      icon: '🌱',
      title: 'Community Builder',
      description: 'Contribution activity isn\'t concentrated in a single person.',
      unlocked: Boolean(contrib?.available && !contrib.high_concentration),
      detail: contrib?.available
        ? `Top contributor accounts for ${contrib.top1_percentage}% of sampled activity`
        : 'No contributor distribution data available.',
    },
    {
      key: 'release_machine',
      icon: '🚀',
      title: 'Release Machine',
      description: 'Releases roughly every 60 days or more often.',
      unlocked: Boolean(release?.available && release.has_releases && release.release_frequency_days != null && release.release_frequency_days <= 60),
      detail: release?.available && release.has_releases
        ? (release.release_frequency_days != null ? `~every ${release.release_frequency_days} days` : 'Not enough releases yet to compute a frequency.')
        : 'No release data available.',
    },
  ]
}

// --- Repository Doctor --------------------------------------------------------
// Purely presentational: reads the Risk Engine's own health_breakdown and
// risk_flags rather than re-deriving strengths/weaknesses independently.
export function buildDiagnosis(repo) {
  const breakdown = repo?.health_breakdown || {}
  const available = Object.entries(breakdown).filter(([, v]) => v?.available)

  const strengths = available
    .filter(([, v]) => v.score >= 75)
    .sort((a, b) => b[1].score - a[1].score)
    .map(([factor, v]) => `${FACTOR_LABELS[factor] || factor} (${Math.round(v.score)}/100)`)

  const weaknesses = available
    .filter(([, v]) => v.score < 50)
    .sort((a, b) => a[1].score - b[1].score)
    .map(([factor, v]) => ({ factor, label: FACTOR_LABELS[factor] || factor, score: Math.round(v.score) }))

  const priority = weaknesses.slice(0, 3).map((w) => `Improve ${w.label.toLowerCase()} (currently ${w.score}/100)`)

  const hasRealFlags = repo?.risk_flags?.length && repo.risk_flags[0] !== 'no risk signals detected'

  let overall = 'UNKNOWN'
  if (repo?.health_score != null) {
    if (repo.health_score >= 80) overall = 'HEALTHY'
    else if (repo.health_score >= 55) overall = 'FAIR'
    else if (repo.health_score >= 30) overall = 'AT RISK'
    else overall = 'CRITICAL'
  }

  return {
    overall,
    strengths,
    weaknesses,
    priority,
    riskFlags: hasRealFlags ? repo.risk_flags : [],
    hasData: available.length > 0,
  }
}

// --- What-If simulator --------------------------------------------------------
// Recomputes the exact same weighted-average formula health.py uses, with
// one factor's score hypothetically overridden. This is a client-side
// simulation only — it never writes back to the repository record.
export function simulateWhatIf(repo, factor, hypotheticalScore) {
  const breakdown = repo?.health_breakdown || {}
  let weightedSum = 0
  let totalWeight = 0
  const contributions = []

  for (const [key, weight] of Object.entries(HEALTH_WEIGHTS)) {
    const info = breakdown[key]
    const isTarget = key === factor
    const scoreAvailable = isTarget ? true : info?.available
    if (!scoreAvailable) continue
    const score = isTarget ? hypotheticalScore : info.score
    weightedSum += score * weight
    totalWeight += weight
    contributions.push({ key, weight, score })
  }

  const simulated = totalWeight > 0 ? Math.round(weightedSum / totalWeight) : repo?.health_score ?? 0
  const current = repo?.health_score ?? 0
  return {
    current,
    simulated,
    impact: simulated - current,
  }
}

export const WHAT_IF_SCENARIOS = [
  { key: 'ci_cd', label: 'CI/CD failures increase', factor: 'ci_cd', delta: -40 },
  { key: 'pull_requests', label: 'Stale PRs increase', factor: 'pull_requests', delta: -40 },
  { key: 'activity', label: 'Contributor activity decreases', factor: 'activity', delta: -40 },
  { key: 'testing', label: 'Testing improves', factor: 'testing', delta: 30 },
  { key: 'documentation', label: 'Documentation reaches 90', factor: 'documentation', absolute: 90 },
  { key: 'security', label: 'Security risks are resolved', factor: 'security', absolute: 100 },
]
