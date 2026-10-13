const STATUS_CLASS = {
  Good: 'world-lab-good',
  Fair: 'world-lab-fair',
  Weak: 'world-lab-weak',
  'Not Detected': 'world-lab-weak',
}

// Lab "activity" (flask fill level, glow) reflects testing_analysis.status,
// which is a real ratio-based classification, not a coverage percentage —
// the label says "status", never "coverage".
export default function TestingLab({ testingAnalysis, onClick }) {
  const available = Boolean(testingAnalysis?.available)
  const status = available ? testingAnalysis.status : null
  const stateClass = available ? (STATUS_CLASS[status] || 'world-lab-fair') : 'world-lab-unknown'
  const fillPct = { Good: 85, Fair: 50, Weak: 25, 'Not Detected': 8 }[status] ?? 0

  return (
    <button type="button" className={`world-structure world-lab ${stateClass}`} onClick={onClick} title="Testing lab">
      <svg viewBox="0 0 60 90" className="world-structure-svg">
        <path d="M22 8 H38 V32 L52 76 C54 82 50 86 44 86 H16 C10 86 6 82 8 76 L22 32 Z" className="world-lab-flask" />
        <clipPath id="labClip">
          <path d="M22 8 H38 V32 L52 76 C54 82 50 86 44 86 H16 C10 86 6 82 8 76 L22 32 Z" />
        </clipPath>
        {available && (
          <rect x="4" y={86 - (fillPct / 100) * 60} width="52" height={(fillPct / 100) * 60} clipPath="url(#labClip)" className="world-lab-liquid" />
        )}
      </svg>
      <div className="world-structure-label">
        <strong>Testing Lab</strong>
        <span>{available ? `Status: ${status}` : (testingAnalysis?.reason || 'Data unavailable')}</span>
      </div>
    </button>
  )
}
