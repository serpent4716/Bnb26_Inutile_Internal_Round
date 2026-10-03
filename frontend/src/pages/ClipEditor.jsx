import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router'
import { ArrowLeft, DownloadSimple, Export, Lightning, Sparkle } from '@phosphor-icons/react'
import EdlPreview from '../components/EdlPreview'
import HookCard from '../components/HookCard'
import { getAsset, waitForJob } from '../api/assets'
import { adaptClip, getClip, renderClip } from '../api/clips'
import { errorMessage, mediaUrl } from '../api/client'
import { generateHooks, listGenerated, selectVariant } from '../api/generate'
import { formatTime } from '../lib/format'

const PLATFORMS = [
  ['shorts', 'Shorts'], ['reels', 'Reels'], ['tiktok', 'TikTok'], ['youtube', 'YouTube'], ['linkedin', 'LinkedIn'], ['x', 'X'],
]
const COPY_FIELDS = [
  ['title', 'Title', 1], ['caption', 'Caption', 4], ['hashtags', 'Hashtags', 1], ['description', 'Description', 3], ['thumbnail_text', 'Thumbnail text', 1],
]
const STEP = { reframing: 'Tracking the speaker', writing_copy: 'Writing copy for each platform', building_variants: 'Building versions', rendering: 'Rendering', publishing: 'Saving' }
const primary =
  'inline-flex items-center gap-2 rounded-lg bg-orange-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-orange-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-500 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50'
const secondary =
  'inline-flex items-center gap-2 rounded-lg border border-zinc-300 px-3 py-1.5 text-sm font-medium transition hover:bg-zinc-100 focus-visible:outline-2 focus-visible:outline-orange-500 active:scale-[0.98] disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800'
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
        <label htmlFor={doc.id} className="text-sm font-medium">{label}</label>
        <span className="text-xs text-zinc-500 dark:text-zinc-400" aria-live="polite">{state}</span>
      </div>
      <Input
        id={doc.id}
        rows={rows > 1 ? rows : undefined}
        value={value}
        onChange={(e) => { setValue(e.target.value); setState('') }}
        onBlur={save}
        className="rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm leading-relaxed focus:border-orange-500 focus:outline-2 focus:outline-orange-500/30 dark:border-zinc-700 dark:bg-zinc-900"
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
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          {variant.edl.aspect_ratio}, {formatTime(duration(variant.edl))}, {variant.edl.captions.length ? 'captions on' : 'no captions'}
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <button onClick={exportIt} disabled={!!job} className={primary}>
            <Export size={16} /> {job ? `${STEP[job.current_step] ?? 'Starting'}` : render.url ? 'Export again' : 'Export MP4'}
          </button>
          {render.url && !job && (
            <a href={mediaUrl(render.url)} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 text-sm font-medium text-orange-600 hover:underline dark:text-orange-400">
              <DownloadSimple size={16} /> Download
            </a>
          )}
        </div>
        {render.status === 'stale' && !job && (
          <p className="text-xs text-zinc-500 dark:text-zinc-400">The hook changed after this export. Export again to update the file.</p>
        )}
        {error && <p role="alert" className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      </div>
      <div className="grid content-start gap-4">
        {copy ? (
          COPY_FIELDS.map(([type, label, rows]) =>
            copy[type] && <CopyField key={copy[type].id} doc={copy[type]} label={label} rows={rows} onSaved={onCopySaved} />,
          )
        ) : (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">No copy for this platform yet. Run Adapt for all again.</p>
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

  const reload = useCallback(async () => {
    const c = await getClip(id)
    setClip(c)
    setGenerated(await listGenerated({ clip_id: id }))
    return c
  }, [id])

  useEffect(() => {
    reload()
      .then((c) => getAsset(c.source_asset_id).then(setAsset))
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
      ? <p role="alert" className="text-sm text-red-600 dark:text-red-400">{error}</p>
      : <div className="mx-auto h-64 max-w-6xl rounded-lg bg-zinc-200 motion-safe:animate-pulse dark:bg-zinc-800" />
  }

  const src = mediaUrl(asset.storage_url)
  const srcAspect = asset.metadata.width / asset.metadata.height
  const variants = Object.fromEntries(clip.variants.map((v) => [v.platform, v]))
  const activeTab = tab ?? clip.variants[0]?.platform

  return (
    <div className="mx-auto max-w-6xl">
      <Link to={`/projects/${clip.project_id}`} className="inline-flex items-center gap-1.5 text-sm text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100">
        <ArrowLeft size={16} /> Project
      </Link>
      <div className="mt-4 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">{clip.title}</h1>
          <p className="mt-1 max-w-[65ch] text-sm text-zinc-600 dark:text-zinc-400">{clip.reason}</p>
        </div>
        <p className="text-right">
          <span className="font-mono text-2xl font-semibold tabular-nums">{clip.scores.overall.toFixed(1)}</span>
          <span className="block text-xs text-zinc-500 dark:text-zinc-400">score</span>
        </p>
      </div>
      {error && <p role="alert" className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>}

      <div className="mt-8 grid gap-10 md:grid-cols-[auto_minmax(0,1fr)]">
        <div className="grid content-start justify-items-start gap-2">
          <EdlPreview edl={clip.edl} src={src} srcAspect={srcAspect} label="clip" />
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            {formatTime(duration(clip.edl))} edited from {formatTime(clip.edl.segments.at(-1).end - clip.edl.segments[0].start)} of footage, {clip.edl.segments.length} cuts
          </p>
        </div>

        <section aria-labelledby="hooks-heading">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 id="hooks-heading" className="font-medium">Hook</h2>
            <button onClick={runHooks} disabled={hookBusy} className={secondary}>
              <Sparkle size={16} /> {hooks ? 'New hooks' : 'Generate hooks'}
            </button>
          </div>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">The line on screen for the first 2 seconds. Pick one, then edit it if you like.</p>
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
            <p className="mt-4 rounded-lg border border-dashed border-zinc-300 px-4 py-6 text-center text-sm text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
              Five hooks, one of each type: question, bold claim, story, statistic, contrarian.
            </p>
          )}
        </section>
      </div>

      <section aria-labelledby="platforms-heading" className="mt-14 border-t border-zinc-200 pt-8 dark:border-zinc-800">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 id="platforms-heading" className="font-medium">Platforms</h2>
            <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">Reframed around the speaker, sized and captioned for each platform, with copy in its style.</p>
          </div>
          <button onClick={adaptAll} disabled={!!adaptJob} className={primary}>
            <Lightning size={16} weight="fill" /> {adaptJob ? STEP[adaptJob.current_step] ?? 'Starting' : clip.variants.length ? 'Adapt again' : 'Adapt for all'}
          </button>
        </div>

        {clip.variants.length > 0 && (
          <>
            <div role="tablist" aria-label="Platform" className="mt-6 mb-6 flex gap-1 overflow-x-auto border-b border-zinc-200 dark:border-zinc-800">
              {PLATFORMS.filter(([p]) => variants[p]).map(([p, label]) => (
                <button
                  key={p}
                  role="tab"
                  aria-selected={activeTab === p}
                  onClick={() => setTab(p)}
                  className={`-mb-px shrink-0 border-b-2 px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-orange-500 ${
                    activeTab === p ? 'border-orange-500' : 'border-transparent text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100'
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
