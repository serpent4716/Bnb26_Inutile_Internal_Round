import { lazy, Suspense } from 'react'
import { NavLink, Route, Routes } from 'react-router'
import { ChartLineUp, FilmSlate, Kanban, SignOut, SquaresFour, VideoCamera } from '@phosphor-icons/react'
import { useAuth } from './store/auth'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Library from './pages/Library'
import AssetDetail from './pages/AssetDetail'
import ProjectBoard from './pages/ProjectBoard'
import ProjectDetail from './pages/ProjectDetail'
import ClipEditor from './pages/ClipEditor'

const Insights = lazy(() => import('./pages/Insights')) // recharts only loads with this page

const NAV = [
  { to: '/', label: 'Dashboard', icon: SquaresFour },
  { to: '/library', label: 'Library', icon: FilmSlate },
  { to: '/projects', label: 'Projects', icon: Kanban },
  { to: '/insights', label: 'Insights', icon: ChartLineUp },
]

export default function App() {
  const { token, logout } = useAuth()
  if (!token) return <Login />

  return (
    <div className="flex min-h-[100dvh] flex-col md:flex-row">
      <aside className="flex flex-col border-b border-zinc-200 md:sticky md:top-0 md:h-[100dvh] md:w-60 md:shrink-0 md:border-r md:border-b-0 dark:border-zinc-800">
        <div className="flex h-14 items-center gap-2 px-4 md:h-16 md:px-5">
          <VideoCamera size={22} weight="fill" className="text-orange-500" />
          <span className="text-base font-semibold tracking-tight">CreatorAi</span>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-2 pb-2 md:flex-col md:px-3 md:pb-0">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex shrink-0 items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors focus-visible:outline-2 focus-visible:outline-orange-500 ${
                  isActive
                    ? 'bg-zinc-200/70 font-medium text-zinc-900 dark:bg-zinc-800 dark:text-zinc-50'
                    : 'text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-900 dark:hover:text-zinc-100'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <Icon size={18} weight={isActive ? 'fill' : 'regular'} className={isActive ? 'text-orange-500' : ''} />
                  {label}
                </>
              )}
            </NavLink>
          ))}
        </nav>
        <button
          onClick={logout}
          className="mt-auto flex items-center gap-3 px-6 py-3 text-sm text-zinc-500 hover:text-zinc-900 focus-visible:outline-2 focus-visible:outline-orange-500 md:py-4 dark:text-zinc-400 dark:hover:text-zinc-100"
        >
          <SignOut size={18} /> Sign out
        </button>
      </aside>

      <main className="flex-1 px-4 py-6 md:px-10 md:py-10">
        <Suspense fallback={<div className="mx-auto h-64 max-w-6xl rounded-lg bg-zinc-200 motion-safe:animate-pulse dark:bg-zinc-800" />}>
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
