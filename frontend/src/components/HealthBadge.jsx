import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'

const LABELS = [
  { min: 80, label: 'healthy', className: 'health-good' },
  { min: 55, label: 'fair', className: 'health-fair' },
  { min: 30, label: 'at risk', className: 'health-risk' },
  { min: 0, label: 'critical', className: 'health-critical' },
]

function labelFor(score) {
  return LABELS.find((l) => score >= l.min) ?? LABELS[LABELS.length - 1]
}

function useCountUp(target, duration = 700) {
  const [value, setValue] = useState(0)
  const frame = useRef(null)

  useEffect(() => {
    const start = performance.now()
    const from = 0
    const to = Number.isFinite(target) ? target : 0

    function tick(now) {
      const elapsed = now - start
      const progress = Math.min(1, elapsed / duration)
      const eased = 1 - Math.pow(1 - progress, 3)
      setValue(Math.round(from + (to - from) * eased))
      if (progress < 1) frame.current = requestAnimationFrame(tick)
    }

    frame.current = requestAnimationFrame(tick)
    return () => frame.current && cancelAnimationFrame(frame.current)
  }, [target, duration])

  return value
}

export default function HealthBadge({ score, size = 'md' }) {
  const { label, className } = labelFor(score)
  const animatedScore = useCountUp(score)

  return (
    <motion.span
      className={`health-badge health-badge-${size} ${className}`}
      title={`Health score: ${score}/100`}
      initial={{ opacity: 0, scale: 0.6 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ type: 'spring', stiffness: 400, damping: 22 }}
    >
      <span className="health-score">{animatedScore}</span>
      <span className="health-label">{label}</span>
    </motion.span>
  )
}
