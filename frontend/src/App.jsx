import { useRef } from 'react'
import { Routes, Route, useLocation } from 'react-router-dom'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import Sidebar from './components/Sidebar'
import Home from './pages/Home'
import RepoDetail from './pages/RepoDetail'
import SecurityDashboard from './pages/SecurityDashboard'
import RepositoryWorld from './pages/RepositoryWorld'
import WorldHub from './pages/WorldHub'
import Dashboard from './pages/Dashboard'
import Compare from './pages/Compare'
import './App.css'

const pageVariants = {
  initial: { opacity: 0, y: 14, filter: 'blur(4px)' },
  animate: {
    opacity: 1,
    y: 0,
    filter: 'blur(0px)',
    transition: { duration: 0.45, ease: [0.22, 1, 0.36, 1] },
  },
  exit: {
    opacity: 0,
    y: -10,
    filter: 'blur(4px)',
    transition: { duration: 0.25, ease: [0.4, 0, 1, 1] },
  },
}

const reducedVariants = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: { duration: 0.2 } },
  exit: { opacity: 0, transition: { duration: 0.15 } },
}

function AnimatedBackground() {
  return (
    <div className="ambient-layer" aria-hidden="true">
      <span className="bg-orb bg-orb-1" />
      <span className="bg-orb bg-orb-2" />
      <span className="bg-orb bg-orb-3" />
    </div>
  )
}

export default function App() {
  const location = useLocation()
  const prefersReducedMotion = useReducedMotion()
  const variants = prefersReducedMotion ? reducedVariants : pageVariants
  const scrollRef = useRef(null)

  return (
    <div className="app-shell">
      <div className="grid-overlay" aria-hidden="true" />
      <AnimatedBackground />
      <Sidebar />
      <div className="app-main">
        <div className="page-content" ref={scrollRef}>
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={location.pathname}
              variants={variants}
              initial="initial"
              animate="animate"
              exit="exit"
              className="route-transition"
            >
              <Routes location={location}>
                <Route path="/" element={<Home />} />
                <Route path="/repo/:id" element={<RepoDetail />} />
                <Route path="/repo/:id/security" element={<SecurityDashboard />} />
                <Route path="/repo/:id/world" element={<RepositoryWorld />} />
                <Route path="/world" element={<WorldHub />} />
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/compare" element={<Compare />} />
              </Routes>
            </motion.div>
          </AnimatePresence>
        </div>
        <footer className="app-footer">
          <span>GitMind · local-only · SQLite storage</span>
        </footer>
      </div>
    </div>
  )
}
