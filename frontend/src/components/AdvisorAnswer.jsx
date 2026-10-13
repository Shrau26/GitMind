import React from 'react'

const SECTION_META = {
  answer: { title: 'Advisor summary', icon: '✦', className: 'answer' },
  fact: { title: 'Verified findings', icon: '✓', className: 'fact' },
  inference: { title: 'Risk interpretation', icon: '⌁', className: 'inference' },
  recommendation: { title: 'Recommended actions', icon: '→', className: 'recommendation' },
  unknown: { title: 'Data limitations', icon: 'ⓘ', className: 'unknown' },
  evidence: { title: 'Evidence', icon: '▤', className: 'evidence' },
}

function parseSections(rawText) {
  const text = String(rawText || '').trim()
  if (!text) return []
  const labelPattern = /(?:^|\s)(FACT|INFERENCE|RECOMMENDATION|UNKNOWN|ANSWER|EVIDENCE|CONFIDENCE)\s*:\s*/gi
  const matches = [...text.matchAll(labelPattern)]
  if (!matches.length) return [{ key: 'answer', value: text }]

  const sections = []
  const first = matches[0].index
  if (first > 0) {
    const intro = text.slice(0, first).trim()
    if (intro) sections.push({ key: 'answer', value: intro })
  }
  matches.forEach((match, index) => {
    const start = match.index + match[0].length
    const end = index + 1 < matches.length ? matches[index + 1].index : text.length
    const key = match[1].toLowerCase()
    const value = text.slice(start, end).trim().replace(/^\s*[-•]\s*/, '')
    if (value) sections.push({ key, value })
  })
  return sections
}

function cleanEvidence(value) {
  // Keep evidence readable if Gemini returns serialized JSON, without hiding its content.
  const trimmed = value.trim()
  if ((trimmed.startsWith('{') && trimmed.endsWith('}')) || (trimmed.startsWith('[') && trimmed.endsWith(']'))) {
    try { return JSON.stringify(JSON.parse(trimmed), null, 2) } catch { /* retain the original evidence */ }
  }
  return trimmed
}

export default function AdvisorAnswer({ text }) {
  const sections = parseSections(text)
  if (!sections.length) return null
  const confidence = sections.find((section) => section.key === 'confidence')
  const visibleSections = sections.filter((section) => section.key !== 'confidence')

  return (
    <div className="advisor-answer">
      <div className="advisor-answer-topline">
        <span className="advisor-ai-mark" aria-hidden="true">✦</span>
        <div>
          <strong>GitMind AI Advisor</strong>
          <span className="advisor-answer-subtitle">Grounded in repository evidence</span>
        </div>
        {confidence && (
          <span className={`advisor-confidence advisor-confidence-${confidence.value.toLowerCase().includes('high') ? 'high' : confidence.value.toLowerCase().includes('low') ? 'low' : 'medium'}`}>
            {confidence.value.replace(/[.\s]+$/, '')} confidence
          </span>
        )}
      </div>
      <div className="advisor-section-grid">
        {visibleSections.map((section, index) => {
          const meta = SECTION_META[section.key] || SECTION_META.answer
          const value = section.key === 'evidence' ? cleanEvidence(section.value) : section.value
          const isEvidence = section.key === 'evidence'
          return (
            <section key={`${section.key}-${index}`} className={`advisor-section advisor-section-${meta.className}${isEvidence ? ' advisor-section-wide' : ''}`}>
              <h4><span aria-hidden="true">{meta.icon}</span>{meta.title}</h4>
              {isEvidence
                ? <pre>{value}</pre>
                : <p>{value}</p>}
            </section>
          )
        })}
      </div>
    </div>
  )
}
