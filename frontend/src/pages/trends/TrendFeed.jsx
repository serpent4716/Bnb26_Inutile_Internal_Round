import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { ArrowsClockwise, Gauge, Lightning, TrendUp } from '@phosphor-icons/react'
import { EmptyState, Page, SectionTitle } from '../../components/Page'
import { badge, btn, card, errorText, field, skeleton, tile } from '../../components/ui'
import { errorMessage } from '../../api/client'
import { createRun, getConfig, getTrends, listRuns, STATE_TEXT } from '../../api/trendshort'

const REGIONS = [['ALL', 'All regions'], ['US', 'United States'], ['IN', 'India'], ['GB', 'United Kingdom'], ['CA', 'Canada'], ['AU', 'Australia']]
const CATEGORIES = ['general', 'tech', 'science', 'lifestyle', 'food', 'nature']
const SOURCE = { youtube: 'YouTube', google_trends: 'Google Trends', reddit: 'Reddit', mock: 'Demo data' }
const PLATFORM = { youtube_shorts: 'YouTube Shorts', tiktok: 'TikTok', instagram_reels: 'Reels' }

const chip = (active) =>
  `inline-flex h-9 items-center rounded-full px-4 text-sm font-semibold transition-colors focus-ring ${active ? 'bg-dark text-on-dark' : 'border border-hairline bg-card text-ink hover:bg-bone'}`

function Momentum({ value }) {
  const v = Math.round(value)
  return (
    <div className="flex items-center gap-2" title={`Momentum ${v} / 100`}>
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-stone/50" role="meter" aria-valuenow={v} aria-valuemin={0} aria-valuemax={100} aria-label="Momentum">
        <div className="h-full rounded-full bg-ink" style={{ width: `${v}%` }} />
      </div>
      <span className="font-mono text-xs text-charcoal">{v}</span>
      {v >= 80 && <span className={badge.dark}><TrendUp size={12} weight="bold" /> Rising</span>}
    </div>
  )
}

function IdeaCard({ idea, onMake, starting }) {
  return (
    <article className={`${card} flex flex-col p-6`}>
      <div className="flex flex-wrap items-center gap-2">
        {idea.sources.map((s) => <span key={s} className={badge.tag}>{SOURCE[s] || s}</span>)}
        <span className="ml-auto text-xs text-mute">{PLATFORM[idea.target_platform] || idea.target_platform} · ~{idea.estimated_length_sec}s</span>
      </div>
      <h3 className="mt-4 font-display text-xl font-semibold leading-tight tracking-tight">{idea.title}</h3>
      <p className="mt-3 font-display text-base font-medium">“{idea.hook_angle}”</p>
      <p className="mt-2 flex-1 text-sm leading-relaxed text-charcoal">{idea.why_trending}</p>
      <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
        <Momentum value={idea.momentum_score} />
        <button onClick={() => onMake(idea.id)} disabled={!!starting} className={btn.darkSm}>
          <Lightning size={14} weight="fill" /> {starting === idea.id ? 'Starting' : 'Make this Short'}
        </button>
      </div>
    </article>
  )
}

function YourShorts({ runs }) {
  if (!runs?.length) return null
  return (
    <section aria-labelledby="your-shorts" className="mb-14">
      <SectionTitle id="your-shorts" sub="Pick up where you left off. Saved Shorts also appear in Projects.">Your Shorts</SectionTitle>
      <ul className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {runs.slice(0, 6).map((r) => (
          <li key={r.id}>
            <Link to={`/trends/runs/${r.id}`} className={`${tile} flex h-full flex-col gap-2 px-5 py-4 hover:bg-stone/30 focus-ring`}>
              <span className="line-clamp-2 font-semibold">{r.idea.title}</span>
              <span className="mt-auto flex flex-wrap items-center gap-2 text-xs">
                <span className={r.state === 'failed' ? badge.danger : r.state === 'ready_for_review' || r.state === 'published' ? badge.success : badge.tag}>
                  {r.awaiting_approval && !r.busy ? 'Waiting for you' : STATE_TEXT[r.state] || r.state}
                </span>
                {r.project_id && <span className={badge.tag}>Saved to Projects</span>}
                <span className="ml-auto text-mute">{new Date(r.created_at).toLocaleDateString()}</span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}

export default function TrendFeed() {
  const navigate = useNavigate()
  const [region, setRegion] = useState('ALL')
  const [category, setCategory] = useState('general')
  const [data, setData] = useState(null)
  const [runs, setRuns] = useState(null)
  const [cfg, setCfg] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [review, setReview] = useState(true)
  const [starting, setStarting] = useState(null)

  const load = useCallback((refresh = false) => {
    setLoading(true)
    setError('')
    getTrends(region, category === 'general' ? '' : category, refresh)
      .then(setData)
      .catch((e) => setError(errorMessage(e, 'Could not load trends.')))
      .finally(() => setLoading(false))
  }, [region, category])
  useEffect(() => load(), [load])
  useEffect(() => {
    listRuns().then(setRuns).catch(() => setRuns([]))
    getConfig().then(setCfg).catch(() => {})
  }, [])

  const make = async (id) => {
    setStarting(id)
    setError('')
    try {
      const run = await createRun(id, review ? 'review' : 'auto')
      navigate(`/trends/runs/${run.id}`)
    } catch (e) {
      setError(errorMessage(e, 'Could not start the Short.'))
      setStarting(null)
    }
  }

  return (
    <Page
      title="Trend to Short"
      description="Pick a trending idea and get a finished 9:16 Short: script, voiceover, footage and captions. Check and edit every step, then save it to your projects."
      actions={
        <>
          {cfg?.mock_mode && <span className={badge.dark}>Mock mode: no API calls</span>}
          <Link to="/trends/providers" className={btn.outlineSm}><Gauge size={16} /> Providers</Link>
        </>
      }
    >
      <YourShorts runs={runs} />

      <section aria-labelledby="ideas">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <SectionTitle id="ideas" sub="Trending topics, grouped and turned into Short ideas.">Trending now</SectionTitle>
          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <input type="checkbox" checked={review} onChange={(e) => setReview(e.target.checked)} className="size-4 accent-ink" />
            Stop after each step so I can review
          </label>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-2">
          <label htmlFor="region" className="sr-only">Region</label>
          <select id="region" value={region} onChange={(e) => setRegion(e.target.value)} className={`${field} h-9 w-auto px-4 text-sm`}>
            {REGIONS.map(([v, n]) => <option key={v} value={v}>{n}</option>)}
          </select>
          {CATEGORIES.map((c) => (
            <button key={c} onClick={() => setCategory(c)} aria-pressed={category === c} className={chip(category === c)}>
              {c === 'general' ? 'Everything' : c[0].toUpperCase() + c.slice(1)}
            </button>
          ))}
          <button onClick={() => load(true)} disabled={loading} className={`${btn.ghost} ml-auto`}>
            <ArrowsClockwise size={16} /> {loading ? 'Loading' : 'Refresh'}
          </button>
        </div>

        {data && (
          <p className="mt-4 text-xs text-mute">
            Sources: {Object.entries(data.providers).map(([k, v]) => `${SOURCE[k] || k} ${v}`).join(', ')}
            {data.cluster_provider && ` · ideas written by ${data.cluster_provider}`}
            {data.cached && ' · cached'}
          </p>
        )}
        {error && <p role="alert" className={`mt-4 ${errorText}`}>{error}</p>}
        {data?.message && <p className={`${tile} mt-4 px-5 py-3 text-sm`}>{data.message}</p>}

        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {loading && !data && Array.from({ length: 6 }, (_, i) => <div key={i} className={`h-64 ${skeleton}`} />)}
          {(data?.ideas || []).map((t) => <IdeaCard key={t.id} idea={t} onMake={make} starting={starting} />)}
        </div>
        {!loading && data && data.ideas.length === 0 && !data.message && (
          <div className="mt-6">
            <EmptyState icon={TrendUp} title="No trends match">Try another region or category, or refresh.</EmptyState>
          </div>
        )}
      </section>
    </Page>
  )
}
