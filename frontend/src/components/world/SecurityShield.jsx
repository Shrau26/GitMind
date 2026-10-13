// Shield strength maps to dependencies.security.security_score (real
// Dependabot data) when available; cracks appear proportional to the
// actual critical+high alert count, never invented.
export default function SecurityShield({ security, onClick }) {
  const available = Boolean(security?.available)
  const score = available ? security.security_score : null
  const severeCount = available ? (security.critical + security.high) : 0
  const cracked = available && severeCount > 0
  const strengthClass = !available ? 'world-shield-unknown' : cracked ? 'world-shield-cracked' : 'world-shield-strong'

  return (
    <button type="button" className={`world-structure world-shield ${strengthClass}`} onClick={onClick} title="Security shield">
      <svg viewBox="0 0 80 90" className="world-structure-svg">
        <path
          d="M40 4 L74 16 V44 C74 66 58 80 40 88 C22 80 6 66 6 44 V16 Z"
          className="world-shield-path"
        />
        {cracked && (
          <>
            <path d="M40 20 L34 44 L44 44 L36 68" className="world-shield-crack" />
          </>
        )}
        <text x="40" y="50" textAnchor="middle" className="world-shield-score">
          {available ? score : '—'}
        </text>
      </svg>
      <div className="world-structure-label">
        <strong>Security Shield</strong>
        <span>{available ? `${severeCount} critical/high alert${severeCount === 1 ? '' : 's'}` : (security?.reason || 'Data unavailable')}</span>
      </div>
    </button>
  )
}
