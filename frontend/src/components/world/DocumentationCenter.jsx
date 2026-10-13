// Number of lit "floors" scales with documentation_analysis.documentation_score
// (0-100, from real README section detection) — never a made-up count.
export default function DocumentationCenter({ documentationAnalysis, onClick }) {
  const available = Boolean(documentationAnalysis?.available)
  const score = available ? documentationAnalysis.documentation_score : 0
  const floors = 5
  const litFloors = available ? Math.max(1, Math.round((score / 100) * floors)) : 0

  return (
    <button type="button" className="world-structure world-docs" onClick={onClick} title="Documentation center">
      <div className="world-docs-tower">
        {Array.from({ length: floors }).map((_, i) => (
          <span
            key={i}
            className={`world-docs-floor ${i >= floors - litFloors ? 'world-docs-floor-lit' : ''}`}
          />
        ))}
      </div>
      <div className="world-structure-label">
        <strong>Documentation Center</strong>
        <span>{available ? `Score: ${score}/100` : 'Data unavailable'}</span>
      </div>
    </button>
  )
}
