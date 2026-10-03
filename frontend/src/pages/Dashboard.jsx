import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { Lightning } from '@phosphor-icons/react'
import { EmptyState, Page, StatTile } from '../components/Page'
import { listJobs } from '../api/assets'
import { getProduction } from '../api/insights'
import { listProjects } from '../api/projects'
import { errorMessage } from '../api/client'
import { parseDate } from '../lib/format'

const STAGE = { idea: 'Idea', scripting: 'Scripting', recording: 'Recording', editing: 'Editing', review: 'Review', scheduled: 'Scheduled', published: 'Published' }
const JOB = { pipeline: 'Processing project', transcription: 'Transcribing footage', render: 'Rendering', adapt: 'Adapting for platforms', tagging: 'Tagging' }
const STEP = {
  extracting_keyframes: 'Extracting keyframes', extracting_audio: 'Extracting audio', transcribing: 'Transcribing', saving: 'Saving',
  tagging: 'Describing footage', indexing: 'Indexing for search', aligning: 'Matching script', finding_clips: 'Finding clips',
  building_edls: 'Building edits', reframing: 'Tracking the speaker', writing_copy: 'Writing copy', building_variants: 'Building versions',
  rendering: 'Rendering', publishing: 'Saving',
}

function timeSaved(min) {
  return min >= 60 ? `${(min / 60).toFixed(1)} h` : `${Math.round(min)} min`
}

export default function Dashboard() {
  const [projects, setProjects] = useState(null)
  const [prod, setProd] = useState(null)
  const [jobs, setJobs] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([listProjects(), getProduction()])
      .then(([p, q]) => { setProjects(p); setProd(q) })
      .catch((e) => setError(errorMessage(e, 'Could not load the dashboard.')))
  }, [])

  // Poll running jobs; slow down when nothing is running.
  useEffect(() => {
    let alive = true
    let timer
    const tick = async () => {
      const active = await listJobs(true).catch(() => [])
      if (!alive) return
      setJobs(active)
      timer = setTimeout(tick, active.length ? 2000 : 10000)
    }
    tick()
    return () => { alive = false; clearTimeout(timer) }
  }, [])

  if (!projects || !prod) {
    return (
      <Page title="Dashboard" description="Your projects, running jobs and output at a glance.">
        {error ? <p role="alert" className="text-sm text-red-600 dark:text-red-400">{error}</p>
          : <div className="h-40 rounded-lg bg-zinc-200 motion-safe:animate-pulse dark:bg-zinc-800" />}
      </Page>
    )
  }

  const saved = prod.time_saved
  const inFlight = projects.filter((p) => p.stage !== 'published').length

  return (
    <Page title="Dashboard" description="Your projects, running jobs and output at a glance.">
      <div className="grid gap-6 rounded-lg border border-zinc-200 p-5 sm:grid-cols-[1.4fr_1fr_1fr_1fr] dark:border-zinc-800">
        <div>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">Editing time saved by AI</p>
          <p className="mt-1 text-5xl font-semibold tracking-tight">{timeSaved(saved.minutes_saved)}</p>
        </div>
        <StatTile label="Projects in progress" value={inFlight} sub={`${projects.length - inFlight} published`} />
        <StatTile label="Clips ready" value={saved.clips_ready} sub={`${saved.final_clip_minutes.toFixed(1)} min of edited video`} />
        <StatTile label="Footage processed" value={`${saved.raw_footage_minutes.toFixed(1)} min`} sub={`${saved.footage_files} files`} />
      </div>

      <div className="mt-10 grid gap-10 lg:grid-cols-[3fr_2fr]">
        <section aria-labelledby="recent-heading">
          <div className="flex items-baseline justify-between">
            <h2 id="recent-heading" className="font-medium">Recent projects</h2>
            <Link to="/projects" className="text-sm text-orange-600 hover:underline dark:text-orange-400">All projects</Link>
          </div>
          {projects.length ? (
            <ul className="mt-3 divide-y divide-zinc-200 dark:divide-zinc-800">
              {projects.slice(0, 6).map((p) => (
                <li key={p.id}>
                  <Link to={`/projects/${p.id}`} className="flex items-center justify-between gap-4 py-3 hover:text-orange-600 dark:hover:text-orange-400">
                    <span className="min-w-0">
                      <span className="block truncate font-medium">{p.title}</span>
                      <span className="text-xs text-zinc-500 dark:text-zinc-400">Updated {parseDate(p.updated_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</span>
                    </span>
                    <span className="shrink-0 rounded-full border border-zinc-300 px-2.5 py-0.5 text-xs text-zinc-600 dark:border-zinc-700 dark:text-zinc-400">{STAGE[p.stage]}</span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <div className="mt-3">
              <EmptyState icon={Lightning} title="No projects yet">
                <Link to="/projects" className="text-orange-600 hover:underline dark:text-orange-400">Create your first project</Link>, then add a script and footage.
              </EmptyState>
            </div>
          )}
        </section>

        <section aria-labelledby="jobs-heading">
          <h2 id="jobs-heading" className="font-medium">Running now</h2>
          {jobs.length ? (
            <ul className="mt-3 space-y-3" aria-live="polite">
              {jobs.map((j) => (
                <li key={j.id} className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-800">
                  <div className="flex items-baseline justify-between gap-3 text-sm">
                    <span className="font-medium">{JOB[j.type] ?? j.type}</span>
                    <span className="font-mono text-xs text-zinc-500 tabular-nums dark:text-zinc-400">{j.progress}%</span>
                  </div>
                  <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
                    {STEP[j.current_step] ?? 'Queued'}
                    {j.project_id && <> in <Link to={`/projects/${j.project_id}`} className="text-orange-600 hover:underline dark:text-orange-400">project</Link></>}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">Nothing running. Uploads, processing and exports show up here while they work.</p>
          )}
        </section>
      </div>
    </Page>
  )
}
