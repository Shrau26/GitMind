const STAGES = ['Code', 'Build', 'Test', 'Deploy']

// Pipeline state comes directly from repo.ci_cd (latest_status, ci_score).
// No stage-by-stage data exists in GitMind, so all four stages simply
// share the same overall state — this is stated in the label rather than
// implied as more granular than it is.
export default function CICDPipeline({ ciCd, onClick }) {
  const available = Boolean(ciCd)
  const success = available && ciCd.latest_status === 'success'
  const failing = available && ciCd.latest_status === 'failure'
  const stateClass = !available ? 'world-pipeline-unknown' : success ? 'world-pipeline-success' : failing ? 'world-pipeline-failing' : 'world-pipeline-unknown'

  return (
    <button type="button" className={`world-structure world-pipeline ${stateClass}`} onClick={onClick} title="CI/CD pipeline">
      <div className="world-pipeline-row">
        {STAGES.map((stage, i) => (
          <div key={stage} className="world-pipeline-stage">
            <span className="world-pipeline-dot" style={{ animationDelay: `${i * 0.25}s` }} />
            <span className="world-pipeline-name">{stage}</span>
            {i < STAGES.length - 1 && <span className="world-pipeline-connector" style={{ animationDelay: `${i * 0.25}s` }} />}
          </div>
        ))}
      </div>
      <div className="world-structure-label">
        <strong>CI/CD Pipeline</strong>
        <span>
          {available
            ? `${ciCd.ci_score != null ? `score ${ciCd.ci_score}/100 · ` : ''}latest: ${ciCd.latest_status || 'unknown'}`
            : 'Data unavailable'}
        </span>
      </div>
    </button>
  )
}
