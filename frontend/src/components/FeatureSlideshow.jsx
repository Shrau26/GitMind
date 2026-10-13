import { useEffect, useState, useCallback } from 'react'
import { AnimatePresence, motion } from 'framer-motion'

const SLIDES = [
  {
    icon: '◈',
    title: 'Health score, at a glance',
    body: 'A 0–100 heuristic score weighs open-issue ratio, commit recency, and stale pull requests into one transparent number.',
    accent: 'var(--good)',
  },
  {
    icon: '▲',
    title: 'Risk flags surfaced early',
    body: 'Slowing activity, ballooning issue counts, and aging pull requests are called out automatically — before they become a surprise.',
    accent: 'var(--risk)',
  },
  {
    icon: '✎',
    title: 'Plain-English summaries',
    body: 'A local extractive summarizer distills every README into a couple of sentences — no external API, nothing leaves your machine.',
    accent: 'var(--accent)',
  },
  {
    icon: '◆',
    title: 'Machine learning, opt-in',
    body: 'TF-IDF similarity and outlier detection work out of the box; train the health and category classifiers on your own labeled data.',
    accent: 'var(--violet)',
  },
]

// Each slide index maps to a distinct transition style so the sequence
// doesn't feel like one animation looping — it genuinely varies.
const TRANSITIONS = [
  {
    name: 'fade',
    initial: { opacity: 0 },
    animate: { opacity: 1, transition: { duration: 0.55, ease: 'easeOut' } },
    exit: { opacity: 0, transition: { duration: 0.35, ease: 'easeIn' } },
  },
  {
    name: 'slide',
    initial: { opacity: 0, x: 60 },
    animate: { opacity: 1, x: 0, transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] } },
    exit: { opacity: 0, x: -60, transition: { duration: 0.35, ease: [0.4, 0, 1, 1] } },
  },
  {
    name: 'scale',
    initial: { opacity: 0, scale: 0.85 },
    animate: { opacity: 1, scale: 1, transition: { duration: 0.5, ease: [0.34, 1.56, 0.64, 1] } },
    exit: { opacity: 0, scale: 1.08, transition: { duration: 0.3, ease: 'easeIn' } },
  },
  {
    name: 'flip',
    initial: { opacity: 0, rotateX: 60, y: 20 },
    animate: { opacity: 1, rotateX: 0, y: 0, transition: { duration: 0.55, ease: [0.22, 1, 0.36, 1] } },
    exit: { opacity: 0, rotateX: -50, y: -14, transition: { duration: 0.35, ease: 'easeIn' } },
  },
  {
    name: 'drop',
    initial: { opacity: 0, y: -40 },
    animate: { opacity: 1, y: 0, transition: { duration: 0.5, type: 'spring', stiffness: 260, damping: 22 } },
    exit: { opacity: 0, y: 30, transition: { duration: 0.3, ease: 'easeIn' } },
  },
]

const AUTO_ADVANCE_MS = 4500

export default function FeatureSlideshow() {
  const [index, setIndex] = useState(0)
  const [paused, setPaused] = useState(false)

  const advance = useCallback(() => {
    setIndex((i) => (i + 1) % SLIDES.length)
  }, [])

  useEffect(() => {
    if (paused) return undefined
    const id = setInterval(advance, AUTO_ADVANCE_MS)
    return () => clearInterval(id)
  }, [paused, advance])

  const slide = SLIDES[index]
  const transition = TRANSITIONS[index % TRANSITIONS.length]

  return (
    <div
      className="feature-slideshow"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      style={{ '--slide-accent': slide.accent }}
    >
      <div className="feature-slideshow-viewport">
        <AnimatePresence mode="wait">
          <motion.div
            key={index}
            className="feature-slide"
            initial={transition.initial}
            animate={transition.animate}
            exit={transition.exit}
          >
            <span className="feature-slide-icon" aria-hidden="true">{slide.icon}</span>
            <div>
              <h3 className="feature-slide-title">{slide.title}</h3>
              <p className="feature-slide-body">{slide.body}</p>
            </div>
          </motion.div>
        </AnimatePresence>
      </div>

      <div className="feature-slideshow-dots" role="tablist" aria-label="Feature highlights">
        {SLIDES.map((s, i) => (
          <button
            key={s.title}
            type="button"
            role="tab"
            aria-selected={i === index}
            aria-label={`Show: ${s.title}`}
            className={`feature-dot${i === index ? ' feature-dot-active' : ''}`}
            onClick={() => setIndex(i)}
          >
            {i === index && (
              <motion.span
                className="feature-dot-progress"
                key={`progress-${index}-${paused}`}
                initial={{ scaleX: 0 }}
                animate={{ scaleX: paused ? 0 : 1 }}
                transition={{ duration: paused ? 0 : AUTO_ADVANCE_MS / 1000, ease: 'linear' }}
              />
            )}
          </button>
        ))}
      </div>
    </div>
  )
}
