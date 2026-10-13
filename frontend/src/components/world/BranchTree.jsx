// Each branch beyond the default is drawn as a path off the trunk; active
// branches are solid, stale ones are faded — both states read directly
// from branch_analysis.stale_branch_list / active/stale counts.
export default function BranchTree({ branchAnalysis, onClick }) {
  const available = Boolean(branchAnalysis?.available)
  const total = available ? branchAnalysis.total_branches : 0
  const stale = available ? branchAnalysis.stale_branches : 0
  const active = available ? branchAnalysis.active_branches : 0
  const shown = Math.min(6, Math.max(1, total || 1))

  return (
    <button type="button" className="world-structure world-branches" onClick={onClick} title="Branch tree">
      <svg viewBox="0 0 100 90" className="world-structure-svg">
        <line x1="50" y1="86" x2="50" y2="30" className="world-branch-trunk" />
        {available && Array.from({ length: shown }).map((_, i) => {
          const isStale = i < stale && i < shown
          const side = i % 2 === 0 ? 1 : -1
          const y = 30 + (i % 3) * 14
          const x2 = 50 + side * (18 + (i % 3) * 6)
          return (
            <line
              key={i}
              x1="50" y1={y + 20} x2={x2} y2={y}
              className={isStale ? 'world-branch-stale' : 'world-branch-active'}
            />
          )
        })}
        <circle cx="50" cy="26" r="5" className="world-branch-tip" />
      </svg>
      <div className="world-structure-label">
        <strong>Branches</strong>
        <span>{available ? `${active} active · ${stale} stale` : 'Data unavailable'}</span>
      </div>
    </button>
  )
}
