import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router'
import { ArrowsClockwise, Check } from '@phosphor-icons/react'
import { DetailHeader } from '../../components/Page'
import { btn, card, errorText, link, skeleton, tile } from '../../components/ui'
import StageTracker from '../../components/trends/StageTracker'
import { AssemblyPanel, AudioPanel, ProviderNote, PublishPanel, ScriptPanel, VisualsPanel } from '../../components/trends/Panels'
import { errorMessage } from '../../api/client'
import {
  approveRun, getConfig, getRun, getRunLog, providerLabel, rerunStage, runEventsUrl, setRunMode, STAGE_NAMES, STATE_TEXT,
} from '../../api/trendshort'

function RunLog({ runId, state }) {
  const [open, setOpen] = useState(false)
  const [lines, setLines] = useState([])
  useEffect(() => {
    if (!open) return
    const load = () => getRunLog(runId).then((d) => setLines(d.lines)).catch(() => {})
    load()
    const t = setInterval(load, 2000)
    return () => clearInterval(t)
  }, [open, runId, state])
  return (
    <section className="mt-10">
      <button className={link} onClick={() => setOpen(!open)} aria-expanded={open}>
        {open ? 'Hide run log' : 'Show run log (which provider answered each step)'}
      </button>
      {open && (
        <div className="mt-3 max-h-80 overflow-auto rounded-md bg-dark p-4 font-mono text-xs text-on-dark">
          {lines.length === 0 && <p className="text-on-dark-mute">No log lines yet.</p>}
          {lines.map((l, i) => (
            <div key={i} className="flex gap-3 py-0.5">
              <span className="w-16 shrink-0 text-on-dark-mute">{l.ts?.slice(11)}</span>
              <span className="w-16 shrink-0 text-on-dark-mute">{l.stage}</span>
              <span className={l.level === 'error' ? 'text-hero-pink' : ''}>
                {l.msg}{l.providers ? ` · ${l.providers.map(providerLabel).join(', ')}` : ''}{l.cached ? ' · cached' : ''}
                {l.fallbacks?.length ? ` · fallbacks: ${l.fallbacks.join('; ')}` : ''}{l.error ? ` · ${l.error}` : ''}
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

export default function TrendRun() {
  const { id } = useParams()
  const [run, setRun] = useState(null)
  const [cfg, setCfg] = useState(null)
  const [selected, setSelected] = useState('script')
  const [error, setError] = useState('')
  const [live, setLive] = useState(false)
  const autoFollow = useRef(true)

  const refetch = useCallback(() => getRun(id).then(setRun).catch((e) => setError(errorMessage(e, 'Could not load this Short.'))), [id])

  useEffect(() => {
    refetch()
    getConfig().then(setCfg).catch(() => {})
    const es = new EventSource(runEventsUrl(id))
    const onRun = (e) => { const d = JSON.parse(e.data); if (d.run) setRun((r) => ({ ...r, ...d.run })) }
    es.addEventListener('snapshot', onRun)
    es.addEventListener('run', onRun)
    es.addEventListener('stage', (e) => {
      const { stage } = JSON.parse(e.data)
      setRun((r) => (r ? { ...r, stages: { ...r.stages, [stage.stage]: stage } } : r))
      if (autoFollow.current && (stage.status === 'running' || stage.status === 'done')) setSelected(stage.stage)
    })
    es.onopen = () => setLive(true)
    es.onerror = () => setLive(false)
    return () => es.close()
  }, [id, refetch])

  if (error && !run) return <p role="alert" className={errorText}>{error}</p>
  if (!run) return <div className={`h-96 ${skeleton}`} />

  const st = run.stages[selected]
  const busy = Object.values(run.stages).some((s) => s.status === 'running')
  const act = (fn, fallback) => async (...a) => {
    setError('')
    try { await fn(...a) } catch (e) { setError(errorMessage(e, fallback)) }
  }
  const select = (s) => { autoFollow.current = false; setSelected(s) }
  const canRerun = selected !== 'publish' && !busy && st && st.status !== 'pending'
  const name = STAGE_NAMES[selected]

  return (
    <div>
      <DetailHeader
        back="/trends"
        backLabel="All trends"
        title={run.idea.title}
        meta={<p className="font-display text-lg font-medium text-ink">“{run.idea.hook_angle}”</p>}
        aside={
          <div className="flex flex-wrap items-center gap-4">
            <span className="flex items-center gap-2 text-sm text-charcoal" aria-live="polite">
              <span className={`size-2 rounded-full ${busy ? 'bg-ink motion-safe:animate-pulse' : run.state === 'failed' ? 'bg-danger' : 'bg-success'}`} />
              {run.awaiting_approval && !busy ? 'Waiting for your approval' : STATE_TEXT[run.state] || run.state}
              {!live && ' (reconnecting)'}
            </span>
            <label className="flex cursor-pointer items-center gap-2 text-sm font-semibold">
              <input
                type="checkbox"
                className="size-4 accent-ink"
                checked={run.mode === 'auto'}
                onChange={act((e) => setRunMode(run.id, e.target.checked ? 'auto' : 'review'), 'Could not change the mode.')}
              />
              Auto-run
            </label>
          </div>
        }
      />

      <div className="mt-10"><StageTracker run={run} selected={selected} onSelect={select} /></div>

      {run.awaiting_approval && run.next_stage && !busy && (
        <div className={`${tile} mt-4 flex flex-wrap items-center gap-3 px-5 py-4`}>
          <p className="text-sm">Check the {name?.toLowerCase() || 'output'}, edit anything you like, then continue to <b>{STAGE_NAMES[run.next_stage]}</b>.</p>
          <button className={`${btn.dark} ml-auto`} onClick={act(() => approveRun(run.id), 'Could not continue.')}>
            <Check size={16} weight="bold" /> Approve & continue
          </button>
        </div>
      )}
      {run.state === 'failed' && (
        <div role="alert" className="mt-4 rounded-md border border-danger/40 bg-card px-5 py-4 text-sm">
          <p><b>{STAGE_NAMES[run.failed_stage] || run.failed_stage} failed.</b> <span className="text-danger">{run.error}</span></p>
          {run.failed_stage !== 'publish' && (
            <button className={`${btn.outlineSm} mt-3`} onClick={act(() => rerunStage(run.id, run.failed_stage), 'Could not retry.')}>
              <ArrowsClockwise size={14} /> Try {STAGE_NAMES[run.failed_stage]?.toLowerCase()} again
            </button>
          )}
        </div>
      )}
      {error && <p role="alert" className={`mt-4 ${errorText}`}>{error}</p>}

      <section aria-labelledby="stage-title" className={`${card} mt-6 p-6 md:p-8`}>
        <div className="mb-6 flex flex-wrap items-center gap-3">
          <h2 id="stage-title" className="display-md">{name}</h2>
          {st?.status === 'stale' && <span className="inline-flex items-center rounded-full border border-hairline-strong px-2.5 py-1 text-xs">Out of date</span>}
          {canRerun && (
            <button className={`${btn.outlineSm} ml-auto`} onClick={act(() => rerunStage(run.id, selected), 'Could not rerun this step.')}>
              <ArrowsClockwise size={14} />
              {st.status === 'stale' ? `Update ${name.toLowerCase()}` : selected === 'assembly' ? 'Re-render' : `Redo ${name.toLowerCase()}`}
            </button>
          )}
        </div>
        {selected !== 'publish' && st?.status === 'done' && <ProviderNote stage={st} />}
        {selected === 'script' && <ScriptPanel run={run} onError={setError} />}
        {selected === 'audio' && <AudioPanel run={run} />}
        {selected === 'visuals' && <VisualsPanel run={run} onError={setError} />}
        {selected === 'assembly' && <AssemblyPanel run={run} onError={setError} />}
        {selected === 'publish' && <PublishPanel run={run} cfg={cfg} onError={setError} onSaved={refetch} />}
      </section>

      <RunLog runId={run.id} state={run.state} />
    </div>
  )
}
