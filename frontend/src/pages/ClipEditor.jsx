import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router'
import { DownloadSimple, Export, Lightning, Sparkle } from '@phosphor-icons/react'
import { DetailHeader, SectionTitle } from '../components/Page'
import EdlPreview from '../components/EdlPreview'
import JobStepper from '../components/JobStepper'
import TranscriptEditor from '../components/TranscriptEditor'
import HookCard from '../components/HookCard'
import { getAsset, getTranscript, waitForJob } from '../api/assets'
import { adaptClip, editWords, getClip, renderClip, undoClip } from '../api/clips'
import { errorMessage, mediaUrl } from '../api/client'
import { generateHooks, listGenerated, selectVariant } from '../api/generate'
import { formatTime } from '../lib/format'
import { badge, btn, errorText, field, fieldArea, link, skeleton, tile } from '../components/ui'

const PLATFORMS = [
  ['shorts', 'Shorts'], ['reels', 'Reels'], ['tiktok', 'TikTok'], ['youtube', 'YouTube'], ['linkedin', 'LinkedIn'], ['x', 'X'],
]
const COPY_FIELDS = [
  ['title', 'Title', 1], ['caption', 'Caption', 4], ['hashtags', 'Hashtags', 1], ['description', 'Description', 3], ['thumbnail_text', 'Thumbnail text', 1],
]
const STEP = { reframing: 'Tracking the speaker', writing_copy: 'Writing copy for each platform', building_variants: 'Building versions', rendering: 'Rendering', publishing: 'Saving' }
const duration = (edl) => edl.segments.reduce((s, x) => s + x.end - x.start, 0)

/** A copy field that saves the creator's edit on blur (PATCH /generated/{id}/select with text). */
function CopyField({ doc, label, rows, onSaved }) {
  const index = Math.max(0, doc.variants.findIndex((v) => v.selected))
  const [value, setValue] = useState(doc.variants[index].text)
  const [state, setState] = useState('')
  const save = async () => {
    if (!value.trim() || value === doc.variants[index].text) return
    setState('Saving')
    try {
      onSaved(await selectVariant(doc.id, index, value.trim()))
      setState('Saved')
    } catch (e) {
      setState(errorMessage(e, 'Not saved'))
    }
  }
  const Input = rows > 1 ? 'textarea' : 'input'
  return (
    <div className="grid gap-1.5">
      <div className="flex items-baseline justify-between">
        <label htmlFor={doc.id} className="text-sm font-semibold">{label}</label>
        <span className="text-xs text-mute" aria-live="polite">{state}</span>
      </div>
      <Input
        id={doc.id}
        rows={rows > 1 ? rows : undefined}
        value={value}
        onChange={(e) => { setValue(e.target.value); setState('') }}
        onBlur={save}
        className={rows > 1 ? fieldArea : field}
      />
    </div>
  )
}

function PlatformPanel({ clip, variant, copy, src, srcAspect, onCopySaved, onRendered }) {
  const [job, setJob] = useState(null)
  const [error, setError] = useState('')
  const render = variant.render
  const exportIt = async () => {
    setError('')
    try {
      const { job_id } = await renderClip(clip.id, variant.platform)
      await waitForJob(job_id, setJob)
      onRendered()
    } catch (e) {
      setError(errorMessage(e, e.message || 'Export failed.'))
    } finally {
      setJob(null)
    }
  }
  return (
    <div className="grid gap-8 md:grid-cols-[auto_minmax(0,1fr)]">
      <div className="grid content-start justify-items-start gap-3">
        <EdlPreview key={variant.platform} edl={variant.edl} src={src} srcAspect={srcAspect} label={variant.platform} />
        <p className="font-mono text-xs text-mute">
          {variant.edl.aspect_ratio}, {formatTime(duration(variant.edl))}, {variant.edl.captions.length ? 'captions on' : 'no captions'}
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <button onClick={exportIt} disabled={!!job} className={btn.dark}>
            <Export size={16} /> {job ? `${STEP[job.current_step] ?? 'Starting'}` : render.url ? 'Export again' : 'Export MP4'}
          </button>
          {render.url && !job && (
            <a href={mediaUrl(render.url)} target="_blank" rel="noreferrer" className={`${link} inline-flex items-center gap-1.5 text-sm`}>
              <DownloadSimple size={16} /> Download
            </a>
          )}
        </div>
        {render.status === 'stale' && !job && (
          <p className="text-xs text-mute">This clip changed after this export. Export again to update the file.</p>
        )}
        {error && <p role="alert" className={errorText}>{error}</p>}
      </div>
      <div className="grid content-start gap-4">
        {copy ? (
          COPY_FIELDS.map(([type, label, rows]) =>
            copy[type] && <CopyField key={copy[type].id} doc={copy[type]} label={label} rows={rows} onSaved={onCopySaved} />,
          )
        ) : (
          <p className={`${tile} px-5 py-6 text-base text-charcoal`}>No copy for this platform yet. Run Adapt for all again.</p>
        )}
      </div>
    </div>
  )
}

export default function ClipEditor() {
  const { id } = useParams()
  const [clip, setClip] = useState(null)
  const [asset, setAsset] = useState(null)
  const [generated, setGenerated] = useState([])
  const [error, setError] = useState('')
  const [hookBusy, setHookBusy] = useState(false)
  const [adaptJob, setAdaptJob] = useState(null)
  const [tab, setTab] = useState(null)
  const [words, setWords] = useState(null)
  const [editBusy, setEditBusy] = useState(false)

  const reload = useCallback(async () => {
    const c = await getClip(id)
    setClip(c)
    setGenerated(await listGenerated({ clip_id: id }))
    return c
  }, [id])

  useEffect(() => {
    reload()
      .then((c) => Promise.all([
        getAsset(c.source_asset_id).then(setAsset),
        getTranscript(c.source_asset_id).then((t) => setWords(t.segments.flatMap((s) => s.words))),
      ]))
      .catch((e) => setError(errorMessage(e, 'Could not load this clip.')))
  }, [reload])

  const hooks = generated.find((g) => g.type === 'hook') // newest first
  const copyByPlatform = useMemo(() => {
    const out = {}
    for (const g of generated) if (g.platform) (out[g.platform] ??= {})[g.type] ??= g
    return out
  }, [generated])

  const replaceGenerated = (doc) => setGenerated((list) => list.map((g) => (g.id === doc.id ? doc : g)))

  const runHooks = async () => {
    setHookBusy(true)
    setError('')
    try {
      const doc = await generateHooks(id)
      setGenerated((list) => [doc, ...list])
    } catch (e) {
      setError(errorMessage(e, 'Could not generate hooks.'))
    } finally {
      setHookBusy(false)
    }
  }
  const pickHook = async (index, text) => {
    setHookBusy(true)
    try {
      replaceGenerated(await selectVariant(hooks.id, index, text))
      setClip(await getClip(id)) // the hook is now an overlay in the EDL
    } catch (e) {
      setError(errorMessage(e, 'Could not set the hook.'))
    } finally {
      setHookBusy(false)
    }
  }
  const edit = async (call) => {
    setEditBusy(true)
    setError('')
    try {
      setClip(await call())
    } catch (e) {
      setError(errorMessage(e, 'Could not apply the edit.'))
    } finally {
      setEditBusy(false)
    }
  }

  const adaptAll = async () => {
    setError('')
    try {
      const { job_id } = await adaptClip(id)
      await waitForJob(job_id, setAdaptJob)
      const c = await reload()
      setTab((t) => t ?? c.variants[0]?.platform)
    } catch (e) {
      setError(errorMessage(e, e.message || 'Adapting failed.'))
    } finally {
      setAdaptJob(null)
    }
  }

  if (!clip || !asset) {
    return error
      ? <p role="alert" className={errorText}>{error}</p>
      : <div className={`h-64 ${skeleton}`} />
  }

  const src = mediaUrl(asset.storage_url)
  const srcAspect = asset.metadata.width / asset.metadata.height
  const variants = Object.fromEntries(clip.variants.map((v) => [v.platform, v]))
  const activeTab = tab ?? clip.variants[0]?.platform

  return (
    <div>
      <DetailHeader
        back={`/projects/${clip.project_id}`}
        backLabel="Project"
        title={clip.title}
        meta={<p className="max-w-[60ch] text-lg leading-relaxed text-body">{clip.reason}</p>}
        aside={
          <p className="text-right">
            <span className="font-display text-6xl leading-none font-bold tracking-tight">{clip.scores.overall.toFixed(1)}</span>
            <span className="mt-1 block text-sm text-mute">score</span>
          </p>
        }
      />
      {error && <p role="alert" className={`mt-6 ${errorText}`}>{error}</p>}

      <div className="mt-12 grid gap-12 md:grid-cols-[auto_minmax(0,1fr)]">
        <div className="grid content-start justify-items-start gap-2">
          <EdlPreview edl={clip.edl} src={src} srcAspect={srcAspect} label="clip" />
          <p className="font-mono text-xs text-mute">
            {formatTime(duration(clip.edl))} edited from {formatTime(clip.edl.segments.at(-1).end - clip.edl.segments[0].start)} of footage, {clip.edl.segments.length} cuts
          </p>
        </div>

        <section aria-labelledby="hooks-heading">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <SectionTitle id="hooks-heading">Hook</SectionTitle>
            <button onClick={runHooks} disabled={hookBusy} className={btn.outlineSm}>
              <Sparkle size={16} /> {hooks ? 'New hooks' : 'Generate hooks'}
            </button>
          </div>
          <p className="mt-2 text-base text-charcoal">The line on screen for the first 2 seconds. Pick one, then edit it if you like.</p>
          {hooks ? (
            <ol className="mt-4 grid gap-2">
              {hooks.variants.map((v, i) => (
                <HookCard
                  key={`${hooks.id}-${i}-${v.text}`}
                  variant={v}
                  busy={hookBusy}
                  onSelect={() => pickHook(i)}
                  onSaveEdit={(text) => pickHook(i, text)}
                />
              ))}
            </ol>
          ) : (
            <p className={`${tile} mt-5 px-5 py-6 text-center text-base text-charcoal`}>
              Five hooks, one of each type: question, bold claim, story, statistic, contrarian.
            </p>
          )}
        </section>
      </div>

      {words && (
        <div className="mt-16 border-t border-hairline pt-10">
          <TranscriptEditor
            clip={clip}
            words={words}
            busy={editBusy}
            onKeep={(kept) => edit(() => editWords(id, kept))}
            onUndo={() => edit(() => undoClip(id))}
          />
        </div>
      )}

      <section aria-labelledby="platforms-heading" className="mt-16 border-t border-hairline pt-10">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <SectionTitle id="platforms-heading">Platforms</SectionTitle>
            <p className="mt-2 text-base text-charcoal">Reframed around the speaker, sized and captioned for each platform, with copy in its style.</p>
          </div>
          <button onClick={adaptAll} disabled={!!adaptJob} className={btn.primary}>
            <Lightning size={16} weight="fill" /> {adaptJob ? 'Adapting' : clip.variants.length ? 'Adapt again' : 'Adapt for all'}
          </button>
        </div>

        {adaptJob && <div className={`${tile} mt-6 px-6 py-5`}><JobStepper job={adaptJob} /></div>}
        {clip.variants.length > 0 && (
          <>
            <div role="tablist" aria-label="Platform" className="mt-8 mb-8 flex gap-1 overflow-x-auto">
              {PLATFORMS.filter(([p]) => variants[p]).map(([p, label]) => (
                <button
                  key={p}
                  role="tab"
                  aria-selected={activeTab === p}
                  onClick={() => setTab(p)}
                  className={`inline-flex h-9 shrink-0 items-center rounded-full px-4 text-sm font-semibold transition-colors focus-ring ${
                    activeTab === p ? 'bg-dark text-on-dark' : 'text-ink hover:bg-bone'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            {variants[activeTab] && (
              <div role="tabpanel" aria-label={activeTab}>
                <PlatformPanel
                  key={activeTab}
                  clip={clip}
                  variant={variants[activeTab]}
                  copy={copyByPlatform[activeTab]}
                  src={src}
                  srcAspect={srcAspect}
                  onCopySaved={replaceGenerated}
                  onRendered={reload}
                />
              </div>
            )}
          </>
        )}
      </section>
    </div>
  )
}
