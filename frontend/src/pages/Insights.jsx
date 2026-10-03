import { useCallback, useEffect, useState } from 'react'
import { ArrowsClockwise, ChartLineUp, Database, Sparkle } from '@phosphor-icons/react'
import { EmptyState, Page, StatTile } from '../components/Page'
import { ChartCard, Columns, HBars, Trend, compact, percent } from '../components/Charts'
import { generateInsights, getPerformance, getProduction, latestInsights, seedAnalytics } from '../api/insights'
import { errorMessage } from '../api/client'
import { parseDate } from '../lib/format'

const HOOK = { question: 'Question', contrarian: 'Contrarian', bold_claim: 'Bold claim', story: 'Story', statistic: 'Statistic' }
const PLATFORM = { shorts: 'Shorts', reels: 'Reels', tiktok: 'TikTok', youtube: 'YouTube', linkedin: 'LinkedIn', x: 'X' }
const WEEKDAY = ['', 'Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'] // Mongo $dayOfWeek: 1 = Sunday
const STAGE = { idea: 'Idea', scripting: 'Scripting', recording: 'Recording', editing: 'Editing', review: 'Review', scheduled: 'Scheduled', published: 'Published' }
const button =
  'inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-500 active:scale-[0.98] disabled:opacity-50'

function hours(h) {
  if (h < 1) return `${Math.round(h * 60)} min`
  if (h < 48) return `${h.toFixed(1)} h`
  return `${(h / 24).toFixed(1)} days`
}

function InsightCards({ hasData, fingerprint }) {
  const [doc, setDoc] = useState(undefined) // undefined = loading, null = none yet
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { latestInsights().then(setDoc).catch(() => setDoc(null)) }, [])
  const run = async () => {
    setBusy(true)
    setError('')
    try {
      setDoc(await generateInsights())
    } catch (e) {
      setError(errorMessage(e, 'Could not generate insights.'))
    } finally {
      setBusy(false)
    }
  }
  return (
    <section aria-labelledby="ai-heading" className="mt-10">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="ai-heading" className="font-medium">What to do next</h2>
          <p className="mt-0.5 text-sm text-zinc-600 dark:text-zinc-400">Written by AI from the numbers on this page.</p>
        </div>
        <button onClick={run} disabled={busy || !hasData} className={`${button} border border-zinc-300 hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800`}>
          {doc ? <ArrowsClockwise size={16} /> : <Sparkle size={16} />} {busy ? 'Analysing' : doc ? 'Refresh' : 'Generate insights'}
        </button>
      </div>
      {error && <p role="alert" className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>}
      {doc === undefined ? (
        <div className="mt-4 h-24 rounded-lg bg-zinc-200 motion-safe:animate-pulse dark:bg-zinc-800" />
      ) : doc ? (
        <>
          <ul className="mt-4 grid gap-3 md:grid-cols-2">
            {doc.variants.map((c) => (
              <li key={c.label} className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
                <p className="font-medium">{c.label}</p>
                <p className="mt-1.5 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">{c.text}</p>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
            Generated {parseDate(doc.created_at).toLocaleString()}.
            {doc.prompt_context !== JSON.stringify(fingerprint) && <> Your numbers have changed since then, so <strong className="font-medium text-zinc-700 dark:text-zinc-300">refresh</strong> before acting on these.</>}
          </p>
        </>
      ) : (
        <p className="mt-4 text-sm text-zinc-500 dark:text-zinc-400">No insights yet.</p>
      )}
    </section>
  )
}

export default function Insights() {
  const [perf, setPerf] = useState(null)
  const [prod, setProd] = useState(null)
  const [error, setError] = useState('')
  const [seeding, setSeeding] = useState(false)

  const load = useCallback(() => {
    Promise.all([getPerformance(), getProduction()])
      .then(([p, q]) => { setPerf(p); setProd(q) })
      .catch((e) => setError(errorMessage(e, 'Could not load insights.')))
  }, [])
  useEffect(load, [load])

  const seed = async () => {
    setSeeding(true)
    try {
      await seedAnalytics()
      load()
    } catch (e) {
      setError(errorMessage(e, 'Could not load sample data.'))
    } finally {
      setSeeding(false)
    }
  }

  if (!perf || !prod) {
    return (
      <Page title="Insights" description="What's working across platforms, and where production time goes.">
        {error ? <p role="alert" className="text-sm text-red-600 dark:text-red-400">{error}</p>
          : <div className="h-64 rounded-lg bg-zinc-200 motion-safe:animate-pulse dark:bg-zinc-800" />}
      </Page>
    )
  }

  const t = perf.totals
  const saved = prod.time_saved
  const sampleButton = (
    <button onClick={seed} disabled={seeding} className={`${button} border border-zinc-300 hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800`}>
      <Database size={16} /> {seeding ? 'Loading' : t.posts ? 'Reload sample data' : 'Load sample analytics'}
    </button>
  )

  return (
    <Page title="Insights" description="What's working across platforms, and where production time goes.">
      {error && <p role="alert" className="mb-4 text-sm text-red-600 dark:text-red-400">{error}</p>}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-medium">Performance</h2>
        <div className="flex items-center gap-3">
          {t.mock && <span className="rounded-full border border-zinc-300 px-2.5 py-0.5 text-xs text-zinc-600 dark:border-zinc-700 dark:text-zinc-400">Sample data</span>}
          {sampleButton}
        </div>
      </div>

      {t.posts ? (
        <>
          <div className="mt-4 grid grid-cols-2 gap-6 rounded-lg border border-zinc-200 p-5 md:grid-cols-4 dark:border-zinc-800">
            <StatTile label="Posts" value={t.posts.toLocaleString()} />
            <StatTile label="Total views" value={compact(t.views)} />
            <StatTile label="Avg 3-second retention" value={percent(t.avg_retention_3s, 1)} />
            <StatTile label="Engagement rate" value={percent(t.avg_engagement, 1)} sub="likes, comments and shares per view" />
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-2">
            <ChartCard title="3-second retention by hook type" subtitle="Share of viewers still watching at 3 seconds">
              <HBars rows={perf.by_hook.map((r) => ({ label: HOOK[r.hook_type] ?? r.hook_type, value: r.avg_retention_3s }))} name="Retention" format={(v) => percent(v, 1)} />
            </ChartCard>
            <ChartCard title="Average views by platform">
              <HBars rows={perf.by_platform.map((r) => ({ label: PLATFORM[r.platform] ?? r.platform, value: r.avg_views }))} name="Avg views" />
            </ChartCard>
            <ChartCard title="Views per week">
              <Trend rows={perf.weekly.map((r) => ({ label: parseDate(r.week).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }), value: r.views }))} name="Views" />
            </ChartCard>
            <ChartCard title="Average views by posting day">
              <Columns rows={perf.by_weekday.map((r) => ({ label: WEEKDAY[r.weekday], value: r.avg_views }))} name="Avg views" />
            </ChartCard>
          </div>

          <ChartCard title="Top posts" className="mt-6">
            <div className="-mt-1 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs text-zinc-500 dark:text-zinc-400">
                  <tr><th className="py-2 font-medium">Post</th><th className="py-2 font-medium">Platform</th><th className="py-2 font-medium">Hook</th><th className="py-2 text-right font-medium">Views</th><th className="py-2 text-right font-medium">3s retention</th></tr>
                </thead>
                <tbody className="tabular-nums">
                  {perf.top_posts.map((p, i) => (
                    <tr key={i} className="border-t border-zinc-200 dark:border-zinc-800">
                      <td className="py-2 pr-3">{p.title}</td><td className="py-2 pr-3">{PLATFORM[p.platform]}</td><td className="py-2 pr-3">{HOOK[p.hook_type]}</td>
                      <td className="py-2 text-right">{p.views.toLocaleString()}</td><td className="py-2 text-right">{percent(p.retention_3s, 1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </ChartCard>
        </>
      ) : (
        <div className="mt-4">
          <EmptyState icon={ChartLineUp} title="No performance data yet">
            Publish a project, or load sample analytics to see how the dashboard reads.
          </EmptyState>
        </div>
      )}

      <h2 className="mt-12 font-medium">Production</h2>
      <div className="mt-4 grid gap-6 lg:grid-cols-[2fr_3fr]">
        <section className="rounded-lg border border-zinc-200 p-5 dark:border-zinc-800">
          <p className="text-xs text-zinc-500 dark:text-zinc-400">Editing time saved by AI</p>
          <p className="mt-1 text-5xl font-semibold tracking-tight">{saved.minutes_saved >= 60 ? `${(saved.minutes_saved / 60).toFixed(1)} h` : `${Math.round(saved.minutes_saved)} min`}</p>
          <dl className="mt-5 grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
            <div><dt className="text-xs text-zinc-500 dark:text-zinc-400">Raw footage</dt><dd className="tabular-nums">{saved.raw_footage_minutes.toFixed(1)} min</dd></div>
            <div><dt className="text-xs text-zinc-500 dark:text-zinc-400">Clips ready</dt><dd className="tabular-nums">{saved.clips_ready} ({saved.final_clip_minutes.toFixed(1)} min)</dd></div>
            <div><dt className="text-xs text-zinc-500 dark:text-zinc-400">By hand (estimate)</dt><dd className="tabular-nums">{Math.round(saved.manual_estimate_minutes)} min</dd></div>
            <div><dt className="text-xs text-zinc-500 dark:text-zinc-400">AI processing</dt><dd className="tabular-nums">{saved.ai_processing_minutes.toFixed(1)} min</dd></div>
          </dl>
          <p className="mt-4 text-xs leading-relaxed text-zinc-500 dark:text-zinc-400">
            Estimate: {saved.assumptions.manual_min_per_footage_min} min of manual work per minute of raw footage, plus {saved.assumptions.manual_min_per_clip} min to cut, caption and reframe each clip.
          </p>
        </section>
        <ChartCard title="Average time in each stage" subtitle={prod.bottleneck ? `Slowest stage: ${STAGE[prod.bottleneck]}` : 'Move projects between stages to see where time goes'}>
          {prod.time_per_stage.length ? (
            <HBars rows={prod.time_per_stage.map((r) => ({ label: STAGE[r.stage], value: r.avg_hours }))} name="Avg time" format={hours} tipWidth={72} />
          ) : (
            <p className="text-sm text-zinc-500 dark:text-zinc-400">No completed stages yet.</p>
          )}
        </ChartCard>
      </div>

      {prod.jobs.length > 0 && (
        <ChartCard title="Processing jobs" className="mt-6">
          <div className="-mt-1 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-zinc-500 dark:text-zinc-400">
                <tr><th className="py-2 font-medium">Job</th><th className="py-2 text-right font-medium">Runs</th><th className="py-2 text-right font-medium">Failed</th><th className="py-2 text-right font-medium">Avg duration</th></tr>
              </thead>
              <tbody className="tabular-nums">
                {prod.jobs.map((j) => (
                  <tr key={j.type} className="border-t border-zinc-200 dark:border-zinc-800">
                    <td className="py-2 capitalize">{j.type}</td><td className="py-2 text-right">{j.runs}</td><td className="py-2 text-right">{j.failed}</td><td className="py-2 text-right">{j.avg_seconds.toFixed(1)} s</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </ChartCard>
      )}

      <InsightCards hasData={t.posts > 0 || prod.time_per_stage.length > 0} fingerprint={{ posts: t.posts, views: t.views, stages: prod.time_per_stage.length }} />
    </Page>
  )
}
