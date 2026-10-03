import { useCallback, useEffect, useState } from 'react'
import { ArrowsClockwise, ChartLineUp, Database, Sparkle } from '@phosphor-icons/react'
import { EmptyState, Page, StatTile } from '../components/Page'
import { ChartCard, Columns, HBars, Trend, compact, percent } from '../components/Charts'
import { generateInsights, getPerformance, getProduction, latestInsights, seedAnalytics } from '../api/insights'
import { errorMessage } from '../api/client'
import { parseDate } from '../lib/format'
import { badge, btn, card, errorText, inverse, skeleton, tile } from '../components/ui'

const HOOK = { question: 'Question', contrarian: 'Contrarian', bold_claim: 'Bold claim', story: 'Story', statistic: 'Statistic' }
const PLATFORM = { shorts: 'Shorts', reels: 'Reels', tiktok: 'TikTok', youtube: 'YouTube', linkedin: 'LinkedIn', x: 'X' }
const WEEKDAY = ['', 'Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'] // Mongo $dayOfWeek: 1 = Sunday
const STAGE = { idea: 'Idea', scripting: 'Scripting', recording: 'Recording', editing: 'Editing', review: 'Review', scheduled: 'Scheduled', published: 'Published' }

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
    <section aria-labelledby="ai-heading" className="mt-20">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="ai-heading" className="display-md">What to do next</h2>
          <p className="mt-2 text-base text-charcoal">Written by AI from the numbers on this page.</p>
        </div>
        <button onClick={run} disabled={busy || !hasData} className={btn.dark}>
          {doc ? <ArrowsClockwise size={16} /> : <Sparkle size={16} />} {busy ? 'Analysing' : doc ? 'Refresh' : 'Generate insights'}
        </button>
      </div>
      {error && <p role="alert" className={`mt-4 ${errorText}`}>{error}</p>}
      {doc === undefined ? (
        <div className={`mt-6 h-32 ${skeleton}`} />
      ) : doc ? (
        <>
          <ul className="mt-6 grid gap-4 md:grid-cols-2">
            {doc.variants.map((c) => (
              <li key={c.label} className={`${card} p-6`}>
                <p className="heading-sm">{c.label}</p>
                <p className="mt-2 text-base leading-relaxed text-body">{c.text}</p>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-sm text-mute">
            Generated {parseDate(doc.created_at).toLocaleString()}.
            {doc.prompt_context !== JSON.stringify(fingerprint) && <> Your numbers have changed since then, so <strong className="font-medium text-body">refresh</strong> before acting on these.</>}
          </p>
        </>
      ) : (
        <p className={`${tile} mt-6 px-6 py-8 text-base text-charcoal`}>No insights yet. Generate them from the numbers above.</p>
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
        {error ? <p role="alert" className={errorText}>{error}</p>
          : <div className={`h-64 ${skeleton}`} />}
      </Page>
    )
  }

  const t = perf.totals
  const saved = prod.time_saved
  const sampleButton = (
    <button onClick={seed} disabled={seeding} className={btn.outlineSm}>
      <Database size={16} /> {seeding ? 'Loading' : t.posts ? 'Reload sample data' : 'Load sample analytics'}
    </button>
  )

  return (
    <Page title="Insights" description="What's working across platforms, and where production time goes.">
      {error && <p role="alert" className={`mb-6 ${errorText}`}>{error}</p>}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="display-md">Performance</h2>
        <div className="flex items-center gap-3">
          {t.mock && <span className={badge.tag}>Sample data</span>}
          {sampleButton}
        </div>
      </div>

      {t.posts ? (
        <>
          <div className={`${tile} mt-6 grid grid-cols-2 gap-8 p-8 md:grid-cols-4`}>
            <StatTile label="Posts" value={t.posts.toLocaleString()} />
            <StatTile label="Total views" value={compact(t.views)} />
            <StatTile label="Avg 3-second retention" value={percent(t.avg_retention_3s, 1)} />
            <StatTile label="Engagement rate" value={percent(t.avg_engagement, 1)} sub="likes, comments and shares per view" />
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
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

          <ChartCard title="Top posts" className="mt-4">
            <div className="-mt-1 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-sm text-charcoal">
                  <tr><th className="py-2 font-semibold">Post</th><th className="py-2 font-semibold">Platform</th><th className="py-2 font-semibold">Hook</th><th className="py-2 text-right font-semibold">Views</th><th className="py-2 text-right font-semibold">3s retention</th></tr>
                </thead>
                <tbody className="text-base">
                  {perf.top_posts.map((p, i) => (
                    <tr key={i} className="border-t border-hairline">
                      <td className="py-3 pr-3">{p.title}</td><td className="py-3 pr-3">{PLATFORM[p.platform]}</td><td className="py-3 pr-3">{HOOK[p.hook_type]}</td>
                      <td className="py-3 text-right font-mono text-sm">{p.views.toLocaleString()}</td><td className="py-3 text-right font-mono text-sm">{percent(p.retention_3s, 1)}</td>
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

      <h2 className="mt-20 display-md">Production</h2>
      <div className="mt-6 grid gap-4 lg:grid-cols-[2fr_3fr]">
        <section className={`${inverse} p-8`}>
          <p className="text-sm text-on-dark-mute">Editing time saved by AI</p>
          <p className="mt-2 font-display text-7xl leading-none font-bold tracking-tight">{saved.minutes_saved >= 60 ? `${(saved.minutes_saved / 60).toFixed(1)} h` : `${Math.round(saved.minutes_saved)} min`}</p>
          <dl className="mt-8 grid grid-cols-2 gap-x-4 gap-y-4 border-t border-divider-dark pt-6 text-base">
            <div><dt className="text-sm text-on-dark-mute">Raw footage</dt><dd className="font-mono">{saved.raw_footage_minutes.toFixed(1)} min</dd></div>
            <div><dt className="text-sm text-on-dark-mute">Clips ready</dt><dd className="font-mono">{saved.clips_ready} ({saved.final_clip_minutes.toFixed(1)} min)</dd></div>
            <div><dt className="text-sm text-on-dark-mute">By hand (estimate)</dt><dd className="font-mono">{Math.round(saved.manual_estimate_minutes)} min</dd></div>
            <div><dt className="text-sm text-on-dark-mute">AI processing</dt><dd className="font-mono">{saved.ai_processing_minutes.toFixed(1)} min</dd></div>
          </dl>
          <p className="mt-6 text-sm leading-relaxed text-on-dark-mute">
            Estimate: {saved.assumptions.manual_min_per_footage_min} min of manual work per minute of raw footage, plus {saved.assumptions.manual_min_per_clip} min to cut, caption and reframe each clip.
          </p>
        </section>
        <ChartCard title="Average time in each stage" subtitle={prod.bottleneck ? `Slowest stage: ${STAGE[prod.bottleneck]}` : 'Move projects between stages to see where time goes'}>
          {prod.time_per_stage.length ? (
            <HBars rows={prod.time_per_stage.map((r) => ({ label: STAGE[r.stage], value: r.avg_hours }))} name="Avg time" format={hours} tipWidth={72} />
          ) : (
            <p className="text-base text-charcoal">No completed stages yet.</p>
          )}
        </ChartCard>
      </div>

      {prod.jobs.length > 0 && (
        <ChartCard title="Processing jobs" className="mt-4">
          <div className="-mt-1 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-sm text-charcoal">
                <tr><th className="py-2 font-semibold">Job</th><th className="py-2 text-right font-semibold">Runs</th><th className="py-2 text-right font-semibold">Failed</th><th className="py-2 text-right font-semibold">Avg duration</th></tr>
              </thead>
              <tbody className="text-base">
                {prod.jobs.map((j) => (
                  <tr key={j.type} className="border-t border-hairline">
                    <td className="py-3 capitalize">{j.type}</td><td className="py-3 text-right font-mono text-sm">{j.runs}</td><td className="py-3 text-right font-mono text-sm">{j.failed}</td><td className="py-3 text-right font-mono text-sm">{j.avg_seconds.toFixed(1)} s</td>
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
