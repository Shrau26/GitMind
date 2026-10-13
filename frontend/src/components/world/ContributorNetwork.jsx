// Contributor network: one node per top contributor, connected to a
// central hub, labeled with the contributor's real name — the same names
// GitMind already shows in the Contributors chart and Contributor
// Analysis panel elsewhere in the app, so this isn't new exposure, just a
// different view of the same data. Node count and pulse are driven by
// contributor_analysis, which is real, GitHub-derived data.
export default function ContributorNetwork({ contributorAnalysis, contributors, onClick }) {
  const available = Boolean(contributorAnalysis?.available) || Boolean(contributors?.length)
  const topContributors = (contributorAnalysis?.top_contributors || contributors || []).slice(0, 6)
  const total = contributorAnalysis?.total_contributors ?? contributorAnalysis?.sampled_contributor_count ?? contributors?.length ?? null

  const nodeCount = Math.max(1, topContributors.length || 1)
  const radius = 34

  return (
    <button type="button" className="world-structure world-network" onClick={onClick} title="Contributor network">
      <svg viewBox="0 0 120 100" className="world-structure-svg">
        <circle cx="60" cy="55" r="8" className="world-network-hub" />
        {available && topContributors.map((c, i) => {
          const angle = (i / nodeCount) * Math.PI * 2 - Math.PI / 2
          const x = 60 + radius * Math.cos(angle)
          const y = 55 + radius * 0.7 * Math.sin(angle)
          const initial = (c.name || '?').trim().charAt(0).toUpperCase()
          return (
            <g key={c.name || i}>
              <title>{c.name || 'Unknown contributor'}</title>
              <line x1="60" y1="55" x2={x} y2={y} className="world-network-edge" />
              <circle cx={x} cy={y} r="9" className="world-network-node" />
              <text x={x} y={y + 3} textAnchor="middle" className="world-network-initial">{initial}</text>
            </g>
          )
        })}
        {!available && (
          <text x="60" y="58" textAnchor="middle" className="world-structure-empty">No data</text>
        )}
      </svg>
      {available && topContributors.length > 0 && (
        <div className="world-network-names">
          {topContributors.map((c) => (
            <span key={c.name} className="world-network-chip">{c.name}</span>
          ))}
        </div>
      )}
      <div className="world-structure-label">
        <strong>Contributors</strong>
        <span>{available ? `${total ?? topContributors.length} tracked` : 'Data unavailable'}</span>
      </div>
    </button>
  )
}
