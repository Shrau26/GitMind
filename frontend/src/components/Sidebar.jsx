import { useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useTheme } from '../ThemeContext'

const NAV_ITEMS = [
  { to: '/', label: 'Analyze', icon: '⌘', end: true, hint: 'GitHub URL' },
  { to: '/dashboard', label: 'Dashboard', icon: '▤', hint: 'Portfolio view' },
  { to: '/world', label: 'Repository World', icon: '🌎', hint: 'Interactive 3D view' },
  { to: '/compare', label: 'Compare', icon: '⇄', hint: 'Side by side' },
]

export default function Sidebar() {
  const { theme, toggleTheme } = useTheme()
  const [open, setOpen] = useState(false)
  const location = useLocation()

  const isItemActive = (item) =>
    item.end ? location.pathname === item.to : location.pathname.startsWith(item.to)

  return (
    <>
      <button
        type="button"
        className="sidebar-mobile-toggle"
        onClick={() => setOpen((o) => !o)}
        aria-label={open ? 'Close navigation' : 'Open navigation'}
        aria-expanded={open}
      >
        <AnimatePresence mode="wait" initial={false}>
          <motion.span
            key={open ? 'close' : 'open'}
            initial={{ rotate: -90, opacity: 0 }}
            animate={{ rotate: 0, opacity: 1 }}
            exit={{ rotate: 90, opacity: 0 }}
            transition={{ duration: 0.18 }}
            style={{ display: 'inline-block' }}
          >
            {open ? '✕' : '☰'}
          </motion.span>
        </AnimatePresence>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            className="sidebar-scrim"
            onClick={() => setOpen(false)}
            aria-hidden="true"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
          />
        )}
      </AnimatePresence>

      <aside className={`sidebar${open ? ' sidebar-open' : ''}`}>
        <NavLink to="/" className="sidebar-brand" end onClick={() => setOpen(false)}>
          <span className="sidebar-brand-mark">◈</span>
          Git<span className="wordmark-accent">Mind</span>
        </NavLink>

        <nav className="sidebar-nav">
          {NAV_ITEMS.map((item) => {
            const active = isItemActive(item)
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                onClick={() => setOpen(false)}
                className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}
              >
                {active && (
                  <motion.span
                    layoutId="sidebar-active-pill"
                    className="sidebar-active-pill"
                    transition={{ type: 'spring', stiffness: 500, damping: 38 }}
                  />
                )}
                <span className="sidebar-link-icon" aria-hidden="true">{item.icon}</span>
                <span className="sidebar-link-text">
                  <span className="sidebar-link-label">{item.label}</span>
                  <span className="sidebar-link-hint">{item.hint}</span>
                </span>
              </NavLink>
            )
          })}
        </nav>

        <motion.button
          type="button"
          className="theme-toggle sidebar-theme-toggle"
          onClick={toggleTheme}
          aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          whileTap={{ scale: 0.94 }}
        >
          <AnimatePresence mode="wait" initial={false}>
            <motion.span
              key={theme}
              initial={{ rotate: -60, opacity: 0, scale: 0.6 }}
              animate={{ rotate: 0, opacity: 1, scale: 1 }}
              exit={{ rotate: 60, opacity: 0, scale: 0.6 }}
              transition={{ duration: 0.25 }}
              style={{ display: 'inline-block' }}
            >
              {theme === 'dark' ? '☀︎' : '☾'}
            </motion.span>
          </AnimatePresence>
          <span>{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span>
        </motion.button>

        <p className="sidebar-footnote">local-only · SQLite storage</p>
      </aside>
    </>
  )
}
