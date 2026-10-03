import { lazy, Suspense, useEffect, useState } from 'react'
import { Link, NavLink, Route, Routes, useLocation } from 'react-router'
import { List, Plus, SignOut, X } from '@phosphor-icons/react'
import { useAuth } from './store/auth'
import { btn, skeleton } from './components/ui'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Library from './pages/Library'
import AssetDetail from './pages/AssetDetail'
import ProjectBoard from './pages/ProjectBoard'
import ProjectDetail from './pages/ProjectDetail'
import ClipEditor from './pages/ClipEditor'

const Insights = lazy(() => import('./pages/Insights')) // recharts only loads with this page

const NAV = [
  { to: '/', label: 'Dashboard' },
  { to: '/library', label: 'Library' },
  { to: '/projects', label: 'Projects' },
  { to: '/insights', label: 'Insights' },
]

export function Wordmark({ className = '', cut = 'border-l-canvas' }) {
  return (
    <span className={`inline-flex items-center gap-2 font-display text-xl font-bold tracking-tight ${className}`}>
      <span aria-hidden className="grid size-6 place-items-center rounded-[7px] bg-current">
        <span className={`ml-0.5 size-0 border-y-[5px] border-l-[8px] border-y-transparent ${cut}`} />
      </span>
      CreatorAi
    </span>
  )
}

// sub-nav-pill: white pill, ink label; the current page is the dark pill
const pill = ({ isActive }) =>
  `inline-flex h-9 items-center rounded-full px-4 text-sm font-semibold transition-colors focus-ring ${
    isActive ? 'bg-dark text-on-dark' : 'text-ink hover:bg-bone'
  }`

export default function App() {
  const { token, logout } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)
  const location = useLocation()
  useEffect(() => setMenuOpen(false), [location.pathname])
  if (!token) return <Login />

  return (
    <div className="min-h-[100dvh]">
      <header className="sticky top-0 z-20 border-b border-hairline bg-canvas/95 backdrop-blur-sm">
        <div className="mx-auto flex h-[60px] max-w-[1280px] items-center gap-6 px-4 md:px-6">
          <Link to="/" className="rounded-md focus-ring" aria-label="CreatorAi home">
            <Wordmark />
          </Link>
          <nav aria-label="Main" className="hidden flex-1 justify-center gap-1 lg:flex">
            {NAV.map(({ to, label }) => (
              <NavLink key={to} to={to} end={to === '/'} className={pill}>{label}</NavLink>
            ))}
          </nav>
          <div className="ml-auto hidden items-center gap-2 lg:flex">
            <button onClick={logout} className={btn.ghost}><SignOut size={16} /> Sign out</button>
            <Link to="/projects" state={{ create: true }} className={btn.darkSm}><Plus size={16} weight="bold" /> New project</Link>
          </div>
          <button
            onClick={() => setMenuOpen((o) => !o)}
            aria-expanded={menuOpen}
            aria-controls="mobile-nav"
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            className={`${btn.icon} ml-auto size-11 lg:hidden`}
          >
            {menuOpen ? <X size={18} /> : <List size={18} />}
          </button>
        </div>
        {menuOpen && (
          <nav id="mobile-nav" aria-label="Main" className="border-t border-hairline px-4 pt-3 pb-5 lg:hidden">
            <div className="grid gap-1">
              {NAV.map(({ to, label }) => (
                <NavLink key={to} to={to} end={to === '/'} className={(s) => `${pill(s)} h-11 justify-start`}>{label}</NavLink>
              ))}
            </div>
            <div className="mt-4 flex gap-2">
              <Link to="/projects" state={{ create: true }} className={`${btn.dark} flex-1`}><Plus size={16} weight="bold" /> New project</Link>
              <button onClick={logout} className={btn.outline}>Sign out</button>
            </div>
          </nav>
        )}
      </header>

      <main className="mx-auto max-w-[1280px] px-4 pt-10 pb-24 md:px-6 md:pt-14">
        <Suspense fallback={<div className={`h-64 ${skeleton}`} />}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/library" element={<Library />} />
            <Route path="/assets/:id" element={<AssetDetail />} />
            <Route path="/projects" element={<ProjectBoard />} />
            <Route path="/projects/:id" element={<ProjectDetail />} />
            <Route path="/clips/:id" element={<ClipEditor />} />
            <Route path="/insights" element={<Insights />} />
          </Routes>
        </Suspense>
      </main>
    </div>
  )
}
