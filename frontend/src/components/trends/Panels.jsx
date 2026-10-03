import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { ArrowSquareOut, FloppyDisk, UploadSimple } from '@phosphor-icons/react'
import { badge, btn, card, field, fieldArea, link, tile } from '../ui'
import { errorMessage } from '../../api/client'
import { fileUrl, patchEdl, patchScript, providerLabel, publishRun, saveToCreatorAi, swapVisual } from '../../api/trendshort'

const lbl = 'mb-1.5 block text-sm font-semibold'

function Empty({ stage }) {
  if (stage?.status === 'running') return <p className="text-charcoal" aria-live="polite">Working on it…</p>
  if (stage?.status === 'failed') return <p role="alert" className="text-danger">This step failed: {stage.error}</p>
  return <p className="text-charcoal">Nothing here yet. This step runs after the ones before it.</p>
}

export function ProviderNote({ stage }) {
  if (!stage) return null
  const uniq = [...new Set((stage.providers || []).map((p) => providerLabel(p.provider)))]
  const fell = (stage.fallbacks || []).filter((f) => !f.includes('skipped'))
  const skipped = (stage.fallbacks || []).filter((f) => f.includes('skipped'))
  const cost = stage.cost
  return (
    <div className={`${tile} mb-6 px-5 py-3 text-sm`}>
      {uniq.length > 0 && <p><span className="font-semibold">Made by</span> {uniq.join(', ')}{stage.cached && ' (from cache, no quota used)'}</p>}
      {fell.length > 0 && <p className="mt-1">Fell back: {fell.join('; ')}</p>}
      {skipped.length > 0 && (
        <details className="mt-1 text-charcoal">
          <summary className="cursor-pointer">{skipped.length} provider(s) skipped</summary>
          <ul className="mt-1 list-disc pl-5">{skipped.map((s) => <li key={s}>{s}</li>)}</ul>
        </details>
      )}
      {cost && (cost.llm_tokens_est > 0 || cost.tts_chars > 0) && (
        <p className="mt-1 text-mute">
          Free-tier usage: ~<span className="font-mono">{cost.llm_tokens_est}</span> tokens, <span className="font-mono">{cost.tts_chars}</span> TTS characters, <span className="font-mono">{cost.api_requests}</span> requests.
        </p>
      )}
    </div>
  )
}

export function ScriptPanel({ run, onError }) {
  const out = run.stages.script.output
  const [draft, setDraft] = useState(out)
  const [saving, setSaving] = useState(false)
  useEffect(() => setDraft(out), [JSON.stringify(out)]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!draft) return <Empty stage={run.stages.script} />
  const dirty = JSON.stringify(draft) !== JSON.stringify(out)
  const setScene = (i, k, v) => setDraft({
    ...draft,
    scenes: draft.scenes.map((s, j) => (j === i ? { ...s, [k]: v } : s)),
    ...(i === 0 && k === 'narration' ? { hook: v } : {}),
  })
  const save = async () => {
    setSaving(true)
    try {
      await patchScript(run.id, { ...draft, scenes: draft.scenes.map((s) => ({ ...s, duration_sec: Number(s.duration_sec) })) })
    } catch (e) {
      onError(errorMessage(e, 'Could not save the script.'))
    } finally {
      setSaving(false)
    }
  }
  const total = draft.scenes.reduce((a, s) => a + Number(s.duration_sec), 0)
  return (
    <div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div><label htmlFor="s-title" className={lbl}>Title</label><input id="s-title" className={`${field} w-full`} value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} /></div>
        <div><label htmlFor="s-hook" className={lbl}>Hook (first 3 seconds)</label><input id="s-hook" className={`${field} w-full`} value={draft.hook} onChange={(e) => setScene(0, 'narration', e.target.value)} /></div>
      </div>
      <p className="mt-6 mb-3 text-sm text-charcoal">{draft.scenes.length} scenes · about <span className="font-mono">{total.toFixed(0)}s</span> before voiceover timing</p>
      <ol className="grid gap-3">
        {draft.scenes.map((s, i) => (
          <li key={s.id} className={`${card} grid gap-3 p-4 sm:grid-cols-[2rem_1fr_16rem]`}>
            <span className="font-display text-xl font-bold text-mute">{i + 1}</span>
            <div>
              <label htmlFor={`n-${s.id}`} className={lbl}>{i === 0 ? 'Hook line' : i === draft.scenes.length - 1 ? 'Call to action' : 'Narration'}</label>
              <textarea id={`n-${s.id}`} rows={3} className={`${fieldArea} w-full resize-y`} value={s.narration} onChange={(e) => setScene(i, 'narration', e.target.value)} />
            </div>
            <div className="grid gap-3">
              <div><label htmlFor={`q-${s.id}`} className={lbl}>Footage search</label><input id={`q-${s.id}`} className={`${field} w-full`} value={s.visual_query} onChange={(e) => setScene(i, 'visual_query', e.target.value)} /></div>
              <div><label htmlFor={`o-${s.id}`} className={lbl}>On-screen text</label><input id={`o-${s.id}`} className={`${field} w-full`} value={s.on_screen_text} onChange={(e) => setScene(i, 'on_screen_text', e.target.value)} /></div>
            </div>
          </li>
        ))}
      </ol>
      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        <div><label htmlFor="s-tags" className={lbl}>Hashtags</label><input id="s-tags" className={`${field} w-full`} value={draft.hashtags.join(' ')} onChange={(e) => setDraft({ ...draft, hashtags: e.target.value.split(/\s+/).filter(Boolean) })} /></div>
        <div><label htmlFor="s-desc" className={lbl}>Description</label><input id="s-desc" className={`${field} w-full`} value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></div>
      </div>
      <div className="mt-6 flex flex-wrap items-center gap-3">
        <button className={btn.dark} disabled={!dirty || saving} onClick={save}>{saving ? 'Saving' : 'Save script'}</button>
        {dirty && <span className="text-sm text-charcoal">Saving marks voiceover, footage and video as out of date.</span>}
      </div>
    </div>
  )
}

export function AudioPanel({ run }) {
  const out = run.stages.audio.output
  if (!out) return <Empty stage={run.stages.audio} />
  const text = Object.fromEntries((run.stages.script.output?.scenes || []).map((s) => [s.id, s.narration]))
  return (
    <div>
      <p className="mb-4 text-sm text-charcoal">Total <span className="font-mono">{out.total_duration.toFixed(1)}s</span>. Each scene's audio length sets how long its footage plays.</p>
      <ol className="grid gap-2">
        {out.scenes.map((a, i) => (
          <li key={a.scene_id} className={`${card} flex flex-wrap items-center gap-4 p-4`}>
            <span className="w-6 font-display text-lg font-bold text-mute">{i + 1}</span>
            <p className="min-w-[200px] flex-1 text-sm">{text[a.scene_id]}</p>
            <audio controls preload="none" src={fileUrl(a.path)} className="h-9" />
            <span className="w-32 text-right text-xs text-mute">
              <span className="font-mono">{a.duration_sec.toFixed(2)}s</span> · {providerLabel(a.tts_provider)}<br />{providerLabel(a.caption_provider)}
            </span>
          </li>
        ))}
      </ol>
    </div>
  )
}

function Thumb({ c }) {
  const src = c.local_path ? fileUrl(c.local_path) : c.kind === 'video' ? '' : c.url
  if (c.kind === 'video' && c.local_path) return <video src={src} muted loop playsInline autoPlay className="size-full object-cover" />
  const img = c.preview_url || src
  return img
    ? <img src={img} alt={c.description || ''} className="size-full object-cover" />
    : <div className="grid size-full place-items-center bg-bone text-xs text-charcoal">{c.kind}</div>
}

export function VisualsPanel({ run, onError }) {
  const out = run.stages.visuals.output
  const [busy, setBusy] = useState(null)
  if (!out) return <Empty stage={run.stages.visuals} />
  const q = Object.fromEntries((run.stages.script.output?.scenes || []).map((s) => [s.id, s.visual_query]))
  const pick = async (sid, i) => {
    setBusy(`${sid}-${i}`)
    try {
      await swapVisual(run.id, sid, i)
    } catch (e) {
      onError(errorMessage(e, 'Could not swap the clip.'))
    } finally {
      setBusy(null)
    }
  }
  return (
    <div>
      <p className="mb-4 text-sm text-charcoal">Best match picked by {providerLabel(out.ranking_provider)}. Choose another clip to swap it in; the video then needs a re-render.</p>
      <div className="grid gap-5">
        {out.scenes.map((sv, n) => (
          <div key={sv.scene_id}>
            <p className="mb-2 text-sm"><span className="font-display font-bold text-mute">{n + 1}</span> <span className="text-charcoal">“{q[sv.scene_id]}”</span></p>
            <div className="flex gap-2 overflow-x-auto pb-1">
              {sv.candidates.map((c, i) => {
                const chosen = i === sv.chosen_index
                return (
                  <button
                    key={i}
                    onClick={() => !chosen && pick(sv.scene_id, i)}
                    disabled={!!busy}
                    aria-pressed={chosen}
                    aria-label={`Clip ${i + 1} from ${c.provider}${chosen ? ' (in use)' : ''}`}
                    title={`${c.provider}${c.attribution?.author ? ` · ${c.attribution.author}` : ''}`}
                    className={`relative aspect-[9/16] w-24 shrink-0 overflow-hidden rounded-sm border-2 focus-ring ${chosen ? 'border-ink' : 'border-transparent opacity-70 hover:opacity-100'}`}
                  >
                    <Thumb c={c} />
                    <span className="absolute inset-x-0 bottom-0 bg-dark/80 px-1 py-0.5 text-[10px] text-on-dark">
                      {busy === `${sv.scene_id}-${i}` ? 'Swapping…' : `${c.kind === 'image' ? 'still' : `${Math.round(c.duration_sec)}s`} · ${c.provider}`}
                    </span>
                  </button>
                )
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function AssemblyPanel({ run, onError }) {
  const out = run.stages.assembly.output
  const [edlText, setEdlText] = useState('')
  const [open, setOpen] = useState(false)
  useEffect(() => { if (out) setEdlText(JSON.stringify(out.edl, null, 2)) }, [out?.video_path]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!out) return <Empty stage={run.stages.assembly} />
  const rerender = async () => {
    let edl
    try { edl = JSON.parse(edlText) } catch { return onError("The timeline isn't valid JSON. Fix it and try again.") }
    try { await patchEdl(run.id, edl) } catch (e) { onError(errorMessage(e, 'Could not re-render.')) }
  }
  return (
    <div className="grid gap-8 md:grid-cols-[280px_1fr]">
      <video key={out.video_path} src={fileUrl(out.video_path)} controls className="aspect-[9/16] w-full rounded-md bg-dark" />
      <div className="text-sm">
        <p>
          <span className="font-mono">{out.edl.total_duration.toFixed(1)}s</span> · <span className="font-mono">{out.edl.width}×{out.edl.height}</span> · {out.edl.video.length} scenes · {out.edl.words.length} caption words{out.edl.music ? ' · music ducked under voice' : ''}
        </p>
        {out.render_seconds > 0 && <p className="mt-1 text-mute">Rendered in <span className="font-mono">{out.render_seconds}s</span> with FFmpeg</p>}
        {run.edl_edited && <p className="mt-2"><span className={badge.dark}>Using your edited timeline</span></p>}
        <button className={`${link} mt-4`} onClick={() => setOpen(!open)} aria-expanded={open}>{open ? 'Hide timeline (EDL)' : 'Edit timeline (EDL)'}</button>
        {open && (
          <div className="mt-3">
            <p className="mb-2 text-charcoal">Change durations, captions, overlays or clip paths. Re-rendering uses this timeline only, with no new AI calls.</p>
            <label htmlFor="edl" className="sr-only">Timeline JSON</label>
            <textarea
              id="edl"
              value={edlText}
              onChange={(e) => setEdlText(e.target.value)}
              spellCheck={false}
              className="h-80 w-full rounded-md bg-dark p-4 font-mono text-xs leading-relaxed text-on-dark focus-ring"
            />
            <button className={`${btn.dark} mt-3`} onClick={rerender}>Re-render from timeline</button>
          </div>
        )}
      </div>
    </div>
  )
}

function SaveToCreatorAi({ run, ready, onError, onSaved }) {
  const [busy, setBusy] = useState(false)
  if (run.project_id) {
    return (
      <div className={`${tile} flex flex-wrap items-center gap-3 px-5 py-4`}>
        <span className={badge.success}>Saved</span>
        <span className="text-sm">This Short is a project in review, with its video in your Library.</span>
        <Link to={`/projects/${run.project_id}`} className={`${btn.outlineSm} ml-auto`}><ArrowSquareOut size={16} /> Open project</Link>
      </div>
    )
  }
  const save = async () => {
    setBusy(true)
    try {
      await saveToCreatorAi(run.id)
      onSaved?.()  // saving isn't a pipeline event, so the SSE stream won't carry it
    } catch (e) {
      onError(errorMessage(e, 'Could not save to CreatorAi.'))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className={`${tile} flex flex-wrap items-center gap-3 px-5 py-4`}>
      <p className="min-w-[220px] flex-1 text-sm">Add the video to your Library and create a project in <b>Review</b> with this script, so you can schedule, publish and track it like any other.</p>
      <button className={btn.primary} disabled={!ready || busy} onClick={save}><FloppyDisk size={16} /> {busy ? 'Saving' : 'Save to CreatorAi'}</button>
    </div>
  )
}

export function PublishPanel({ run, cfg, onError, onSaved }) {
  const asm = run.stages.assembly.output
  const script = run.stages.script.output
  const [meta, setMeta] = useState(null)
  const [dry, setDry] = useState(true)
  const [busy, setBusy] = useState(null)
  useEffect(() => {
    if (script) setMeta({ title: script.title, description: script.description, hashtags: script.hashtags.join(' ') })
  }, [script?.title]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!asm || !meta) return <p className="text-charcoal">Publishing opens once the video is rendered.</p>
  const ready = run.stages.assembly.status === 'done'
  const results = run.stages.publish.output || []
  const go = async (target) => {
    setBusy(target)
    try {
      await publishRun(run.id, {
        target, dry_run: target === 'youtube' ? dry : false, title: meta.title,
        description: meta.description, hashtags: meta.hashtags.split(/\s+/).filter(Boolean),
      })
    } catch (e) {
      onError(errorMessage(e, 'Publishing failed.'))
    } finally {
      setBusy(null)
    }
  }
  return (
    <div className="grid gap-8 md:grid-cols-[280px_1fr]">
      <video src={fileUrl(asm.video_path)} controls className="aspect-[9/16] w-full rounded-md bg-dark" />
      <div>
        <SaveToCreatorAi run={run} ready={ready} onError={onError} onSaved={onSaved} />
        <div className="mt-6 grid gap-4">
          <div><label htmlFor="p-title" className={lbl}>Title</label><input id="p-title" className={`${field} w-full`} value={meta.title} onChange={(e) => setMeta({ ...meta, title: e.target.value })} /></div>
          <div><label htmlFor="p-desc" className={lbl}>Description</label><textarea id="p-desc" rows={3} className={`${fieldArea} w-full`} value={meta.description} onChange={(e) => setMeta({ ...meta, description: e.target.value })} /></div>
          <div><label htmlFor="p-tags" className={lbl}>Hashtags</label><input id="p-tags" className={`${field} w-full`} value={meta.hashtags} onChange={(e) => setMeta({ ...meta, hashtags: e.target.value })} /></div>
        </div>
        {!ready && <p className="mt-3 text-sm text-danger">The video is out of date. Re-render it before publishing.</p>}
        <div className="mt-6 grid gap-3">
          {(cfg?.publish_targets || []).map((t) => (
            <div key={t.id} className={`${card} p-4`}>
              <div className="flex flex-wrap items-center gap-3">
                <span className="font-display text-lg font-semibold">{t.label}</span>
                <span className={t.kind === 'real' ? badge.dark : badge.tag}>{t.kind === 'real' ? 'Real upload' : 'Export only'}</span>
                {t.id === 'youtube' && (
                  <label className="ml-auto flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={dry} onChange={(e) => setDry(e.target.checked)} className="size-4 accent-ink" /> Dry run
                  </label>
                )}
                <button
                  className={t.id === 'youtube' ? btn.darkSm : btn.outlineSm}
                  disabled={!ready || !!busy || (t.id === 'youtube' && !dry && !t.configured)}
                  onClick={() => go(t.id)}
                >
                  <UploadSimple size={14} /> {busy === t.id ? 'Working' : t.id === 'youtube' ? (dry ? 'Simulate upload' : 'Upload as private') : 'Create package'}
                </button>
              </div>
              <p className="mt-2 text-xs text-charcoal">{t.notice}</p>
              {t.id === 'youtube' && !t.configured && <p className="mt-1 text-xs text-mute">Real upload needs YOUTUBE_CLIENT_SECRETS on the server. Dry run still works.</p>}
            </div>
          ))}
        </div>
        {results.length > 0 && (
          <div className="mt-6">
            <h3 className="heading-sm">Published</h3>
            <ul className="mt-3 grid gap-2 text-sm">
              {results.map((r, i) => (
                <li key={i} className={`${tile} px-4 py-3`}>
                  <span className="font-semibold">{r.target === 'youtube' ? (r.dry_run ? 'YouTube (dry run)' : 'YouTube') : 'Export package'}</span>{' '}
                  {r.url && <a href={r.url} target="_blank" rel="noreferrer" className={link}>{r.url}</a>}
                  {r.files?.length > 0 && (
                    <span className="mt-1 block">{r.files.map((f) => <a key={f} href={fileUrl(f)} className={`${link} mr-3 font-mono text-xs`}>{f.split(/[\\/]/).pop()}</a>)}</span>
                  )}
                  {r.privacy && <span className="mt-1 block text-xs text-mute">Privacy: {r.privacy}</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}
