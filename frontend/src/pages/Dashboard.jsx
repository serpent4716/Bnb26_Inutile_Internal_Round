import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { Lightning } from '@phosphor-icons/react'
import { EmptyState, Page, SectionTitle, StatTile } from '../components/Page'
import { badge, card, inverse, link, skeleton, tile } from '../components/ui'
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
        {error ? <p role="alert" className="text-sm text-danger">{error}</p>
          : <div className={`h-40 ${skeleton}`} />}
      </Page>
    )
  }

  const saved = prod.time_saved
  const inFlight = projects.filter((p) => p.stage !== 'published').length

  return (
    <Page title="Dashboard" description="Your projects, running jobs and output at a glance.">
      <div className="grid gap-4 lg:grid-cols-[1fr_2fr]">
        <section className={`${inverse} p-8`}>
          <StatTile inverse label="Editing time saved by AI" value={<span className="text-6xl md:text-7xl">{timeSaved(saved.minutes_saved)}</span>} sub={`${saved.raw_footage_minutes.toFixed(1)} min of footage turned into ${saved.clips_ready} clips`} />
        </section>
        <section className={`${tile} grid gap-8 p-8 sm:grid-cols-3`}>
          <StatTile label="Projects in progress" value={inFlight} sub={`${projects.length - inFlight} published`} />
          <StatTile label="Clips ready" value={saved.clips_ready} sub={`${saved.final_clip_minutes.toFixed(1)} min of edited video`} />
          <StatTile label="Footage processed" value={`${saved.raw_footage_minutes.toFixed(1)} min`} sub={`${saved.footage_files} files`} />
        </section>
      </div>

      <div className="mt-16 grid gap-12 lg:grid-cols-[3fr_2fr]">
        <section aria-labelledby="recent-heading">
          <div className="flex items-baseline justify-between gap-4">
            <SectionTitle id="recent-heading">Recent projects</SectionTitle>
            <Link to="/projects" className={link}>All projects</Link>
          </div>
          {projects.length ? (
            <ul className={`${card} mt-5 divide-y divide-hairline`}>
              {projects.slice(0, 6).map((p) => (
                <li key={p.id}>
                  <Link to={`/projects/${p.id}`} className="group flex items-center justify-between gap-4 rounded-md px-5 py-4 focus-ring">
                    <span className="min-w-0">
                      <span className="block truncate font-semibold group-hover:underline group-hover:underline-offset-4">{p.title}</span>
                      <span className="text-sm text-mute">Updated {parseDate(p.updated_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</span>
                    </span>
                    <span className={p.stage === 'published' ? badge.success : badge.tag}>{STAGE[p.stage]}</span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <div className="mt-5">
              <EmptyState icon={Lightning} title="No projects yet">
                <Link to="/projects" state={{ create: true }} className={link}>Create your first project</Link>, then add a script and footage.
              </EmptyState>
            </div>
          )}
        </section>

        <section aria-labelledby="jobs-heading">
          <SectionTitle id="jobs-heading">Running now</SectionTitle>
          {jobs.length ? (
            <ul className="mt-5 space-y-3" aria-live="polite">
              {jobs.map((j) => (
                <li key={j.id} className={`${card} p-5`}>
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="font-semibold">{JOB[j.type] ?? j.type}</span>
                    <span className="font-mono text-sm text-charcoal tabular-nums">{j.progress}%</span>
                  </div>
                  <div className="mt-3 h-1 overflow-hidden rounded-full bg-bone" role="progressbar" aria-valuenow={j.progress} aria-valuemin={0} aria-valuemax={100}>
                    <div className="h-full rounded-full bg-ink transition-[width] duration-500" style={{ width: `${j.progress}%` }} />
                  </div>
                  <p className="mt-2 text-sm text-mute">
                    {STEP[j.current_step] ?? 'Queued'}
                    {j.project_id && <> in <Link to={`/projects/${j.project_id}`} className={link}>project</Link></>}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <p className={`${tile} mt-5 px-5 py-6 text-base text-charcoal`}>Nothing running. Uploads, processing and exports show up here while they work.</p>
          )}
        </section>
      </div>
    </Page>
  )
}
