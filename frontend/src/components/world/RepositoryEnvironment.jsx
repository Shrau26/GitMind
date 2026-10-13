import RepositoryCore from './RepositoryCore'
import ContributorNetwork from './ContributorNetwork'
import CICDPipeline from './CICDPipeline'
import SecurityShield from './SecurityShield'
import TestingLab from './TestingLab'
import DocumentationCenter from './DocumentationCenter'
import ReleaseSystem from './ReleaseSystem'
import BranchTree from './BranchTree'
import { environmentTier } from '../../lib/repoWorld'

// Issues render as small bug markers (capped visually at 8 so a repo with
// 400 open issues doesn't render 400 DOM nodes) — the real count is always
// shown in the label. PRs render as bridge segments: solid/green for
// merged-heavy repos, amber for a stale-PR-heavy repo.
function IssueBugs({ issueAnalysis, onClick }) {
  const available = Boolean(issueAnalysis?.available)
  const stale = available ? issueAnalysis.stale_issues : 0
  const open = available ? issueAnalysis.open_issues : 0
  const bugCount = Math.min(8, Math.max(open ? 1 : 0, stale))

  return (
    <button type="button" className="world-structure world-issues" onClick={onClick} title="Issue analysis">
      <div className="world-issues-row">
        {available && bugCount === 0 && <span className="world-issues-empty">✓</span>}
        {Array.from({ length: bugCount }).map((_, i) => (
          <span key={i} className="world-bug" style={{ animationDelay: `${i * 0.15}s` }}>🐞</span>
        ))}
        {!available && <span className="world-structure-empty">No data</span>}
      </div>
      <div className="world-structure-label">
        <strong>Issues</strong>
        <span>{available ? `${open} open · ${stale} stale` : 'Data unavailable'}</span>
      </div>
    </button>
  )
}

function PRBridge({ prAnalysis, onClick }) {
  const available = Boolean(prAnalysis)
  const stale = available ? prAnalysis.stale_prs : 0
  const merged = available ? prAnalysis.merged_prs : null
  const warning = available && stale > 0
  return (
    <button type="button" className={`world-structure world-bridge ${warning ? 'world-bridge-warning' : 'world-bridge-ok'}`} onClick={onClick} title="Pull request analysis">
      <svg viewBox="0 0 120 40" className="world-structure-svg">
        <path d="M6 34 Q60 4 114 34" className="world-bridge-path" />
        {available && Array.from({ length: Math.min(5, prAnalysis.open_prs || 0) }).map((_, i) => (
          <circle key={i} cx={16 + i * 22} cy={34 - Math.sin((i / 4) * Math.PI) * 24} r="3" className="world-bridge-node" />
        ))}
      </svg>
      <div className="world-structure-label">
        <strong>Pull Requests</strong>
        <span>{available ? `${merged ?? '—'} merged · ${stale} stale` : 'Data unavailable'}</span>
      </div>
    </button>
  )
}

export default function RepositoryEnvironment({ repo, onNavigate }) {
  const tier = environmentTier(repo?.health_score)

  return (
    <div className={`world-environment world-tier-${tier.key}`}>
      <div className="world-ambient" aria-hidden="true">
        <span className="world-particle world-particle-1" />
        <span className="world-particle world-particle-2" />
        <span className="world-particle world-particle-3" />
      </div>

      <div className="world-core-slot">
        <RepositoryCore
          healthScore={repo?.health_score}
          healthStatus={repo?.health_status}
          tierIcon={tier.icon}
          onClick={() => onNavigate('health')}
        />
        <p className="world-tier-caption">{tier.icon} {tier.label} repository</p>
      </div>

      <div className="world-grid">
        <CICDPipeline ciCd={repo?.ci_cd} onClick={() => onNavigate('cicd')} />
        <SecurityShield security={repo?.dependencies?.security} onClick={() => onNavigate('security')} />
        <TestingLab testingAnalysis={repo?.testing_analysis} onClick={() => onNavigate('testing')} />
        <DocumentationCenter documentationAnalysis={repo?.documentation_analysis} onClick={() => onNavigate('documentation')} />
        <ContributorNetwork contributorAnalysis={repo?.contributor_analysis} contributors={repo?.contributors} onClick={() => onNavigate('contributors')} />
        <ReleaseSystem releaseAnalysis={repo?.release_analysis} onClick={() => onNavigate('releases')} />
        <BranchTree branchAnalysis={repo?.branch_analysis} onClick={() => onNavigate('branches')} />
        <IssueBugs issueAnalysis={repo?.issue_analysis} onClick={() => onNavigate('issues')} />
        <PRBridge prAnalysis={repo?.pr_analysis} onClick={() => onNavigate('prs')} />
      </div>
    </div>
  )
}
