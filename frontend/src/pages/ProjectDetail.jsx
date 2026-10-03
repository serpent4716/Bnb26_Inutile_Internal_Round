import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router'
import { ArrowLeft, ArrowsClockwise, Check, FilmReel, PaperPlaneTilt, PencilSimple, Play, Stop, X } from '@phosphor-icons/react'
import UploadDropzone from '../components/UploadDropzone'
import { getJob, uploadAsset } from '../api/assets'
import { errorMessage, mediaUrl } from '../api/client'
import { buildRoughCut, getProject, processProject, publishProject, saveScript, setBestTake } from '../api/projects'
import { formatTime } from '../lib/format'
import { useEdlPlayer } from '../lib/useEdlPlayer'
import { setClipStatus } from '../api/clips'

const STEP_LABEL = {
  extracting_keyframes: 'Extracting keyframes',
  extracting_audio: 'Extracting audio',
  transcribing: 'Transcribing',
  saving: 'Saving transcript',
  tagging: 'Describing footage',
  aligning: 'Matching script to footage',
  finding_clips: 'Finding clips',
  building_edls: 'Building edits',
}
const STATUS = {
  matched: { label: 'Matched', border: 'border-emerald-500', text: 'text-emerald-700 dark:text-emerald-400' },
  retake: { label: 'Retakes', border: 'border-orange-500', text: 'text-orange-700 dark:text-orange-400' },
  missing: { label: 'Missing', border: 'border-red-500', text: 'text-red-700 dark:text-red-400' },
}
const lineStatus = (m) => (m.status === 'missing' ? 'missing' : m.takes.length > 1 ? 'retake' : 'matched')
const button =
  'rounded-lg bg-orange-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-orange-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-500 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50'

function ScriptStep({ project, onSaved }) {
  const [content, setContent] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  if (project.script) return <p className="text-sm">{project.script.lines.length} lines, labelled by section.</p>

  const save = async () => {
    setBusy(true)
    setError('')
    try {
      await saveScript(project.id, content)
      onSaved()
    } catch (e) {
      setError(errorMessage(e, 'Could not save the script.'))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="grid gap-2">
      <label htmlFor="script" className="text-sm font-medium">Paste your script</label>
      <textarea
        id="script"
        rows={8}
        value={content}
        onChange={(e) => setContent(e.target.value)}
        placeholder="One line or sentence per beat. We split it into lines and match each one to your footage."
        className="rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm leading-relaxed placeholder:text-zinc-500 focus:border-orange-500 focus:outline-2 focus:outline-orange-500/30 dark:border-zinc-700 dark:bg-zinc-900 dark:placeholder:text-zinc-400"
      />
      {error && <p role="alert" className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      <div><button onClick={save} disabled={busy || !content.trim()} className={button}>{busy ? 'Saving' : 'Save script'}</button></div>
    </div>
  )
}

function FootageStep({ project, onUploaded }) {
  const [uploading, setUploading] = useState(null)
  const [error, setError] = useState('')
  const footage = project.assets.at(-1)
  if (footage) {
    const s = footage.ai.status
    return (
      <p className="text-sm">
        {footage.filename}
        <span className="ml-2 text-zinc-500 dark:text-zinc-400">
          {s === 'ready' ? 'transcribed' : s === 'failed' ? 'transcription failed' : 'transcribing...'}
        </span>
      </p>
    )
  }
  const upload = async ([file]) => {
    setError('')
    setUploading({ name: file.name, pct: 0 })
    try {
      await uploadAsset(file, (pct) => setUploading({ name: file.name, pct }), project.id)
      onUploaded()
    } catch (e) {
      setError(errorMessage(e, 'Upload failed.'))
    } finally {
      setUploading(null)
    }
  }
  return (
    <>
      <UploadDropzone onFiles={upload} uploading={uploading} />
      {error && <p role="alert" className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>}
    </>
  )
}

function JobProgress({ job }) {
  if (job.status === 'failed') return <p role="alert" className="text-sm text-red-600 dark:text-red-400">Processing failed: {job.error}</p>
  return (
    <p className="text-sm text-zinc-600 dark:text-zinc-400" aria-live="polite">
      {STEP_LABEL[job.current_step] ?? 'Starting'}
      <span className="ml-2 font-mono tabular-nums">{job.progress}%</span>
    </p>
  )
}

function RoughCutBar({ clip, stale, building, onBuild, player, footageDuration }) {
  const segs = clip?.edl.segments
  const total = segs?.reduce((sum, x) => sum + x.end - x.start, 0) ?? 0
  const playing = player.playing?.key === clip?.id ? player.playing : null

  if (!clip) {
    return (
      <div className="flex flex-wrap items-center gap-3">
        <button onClick={onBuild} disabled={building} className={`${button} inline-flex items-center gap-2`}>
          <FilmReel size={18} /> {building ? 'Building' : 'Build rough cut'}
        </button>
        <span className="text-xs text-zinc-500 dark:text-zinc-400">The best take of every line, in script order.</span>
      </div>
    )
  }
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      {!playing ? (
        <button onClick={() => player.play(clip.id, segs)} disabled={!segs.length} className={`${button} inline-flex items-center gap-2`}>
          <Play size={16} weight="fill" /> Play rough cut
        </button>
      ) : (
        <button onClick={player.stop} className={`${button} inline-flex items-center gap-2`}>
          <Stop size={16} weight="fill" /> Stop
        </button>
      )}
      <span className="text-sm text-zinc-600 dark:text-zinc-400" aria-live="polite">
        {!playing
          ? <>Rough cut: {segs.length} takes, <span className="tabular-nums">{formatTime(total)}</span>{footageDuration ? <> from <span className="tabular-nums">{formatTime(footageDuration)}</span> of footage</> : null}</>
          : <>Playing take {playing.seg + 1} of {playing.count}</>}
      </span>
      {stale && (
        <span className="text-sm text-zinc-600 dark:text-zinc-400">
          Takes changed since it was built.{' '}
          <button onClick={onBuild} disabled={building} className="font-medium text-orange-600 underline-offset-4 hover:underline dark:text-orange-400">
            {building ? 'Rebuilding' : 'Rebuild'}
          </button>
        </span>
      )}
    </div>
  )
}

const secondary =
  'inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-500 active:scale-[0.98]'
const idle = 'border-zinc-300 text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800'

function ClipCard({ clip, player, onStatus }) {
  const segs = clip.edl.segments
  const duration = segs.reduce((sum, s) => sum + s.end - s.start, 0)
  const playing = player.playing?.key === clip.id
  const { hook, completeness, virality, overall } = clip.scores
  const toggle = (status) => onStatus(clip, clip.status === status ? 'suggested' : status)

  return (
    <li
      className={`rounded-lg border p-4 transition ${
        clip.status === 'approved'
          ? 'border-emerald-500/70'
          : clip.status === 'rejected'
            ? 'border-zinc-200 opacity-55 dark:border-zinc-800'
            : 'border-zinc-200 dark:border-zinc-800'
      }`}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="font-medium">{clip.title}</h3>
          <p className="mt-0.5 text-xs text-zinc-500 tabular-nums dark:text-zinc-400">
            {formatTime(duration)} clip, from {formatTime(segs[0].start)} to {formatTime(segs.at(-1).end)} of the footage
          </p>
        </div>
        <p className="shrink-0 text-right">
          <span className="font-mono text-2xl font-semibold tabular-nums">{overall.toFixed(1)}</span>
          <span className="block text-xs text-zinc-500 dark:text-zinc-400">score</span>
        </p>
      </div>
      <p className="mt-2 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">{clip.reason}</p>
      <dl className="mt-3 flex gap-5 text-xs">
        {[['Hook', hook], ['Complete', completeness], ['Viral', virality]].map(([label, v]) => (
          <div key={label} className="flex gap-1.5">
            <dt className="text-zinc-500 dark:text-zinc-400">{label}</dt>
            <dd className="font-mono font-medium tabular-nums">{v}</dd>
          </div>
        ))}
      </dl>
      <div className="mt-4 flex flex-wrap gap-2">
        <button onClick={() => (playing ? player.stop() : player.play(clip.id, segs))} className={`${secondary} ${idle}`}>
          {playing ? <><Stop size={14} weight="fill" /> Stop</> : <><Play size={14} weight="fill" /> Play</>}
        </button>
        <Link to={`/clips/${clip.id}`} className={`${secondary} ${idle}`}>
          <PencilSimple size={14} /> Edit
        </Link>
        <button
          onClick={() => toggle('approved')}
          aria-pressed={clip.status === 'approved'}
          className={`${secondary} ${clip.status === 'approved' ? 'border-emerald-600 bg-emerald-600 text-white hover:bg-emerald-700' : idle}`}
        >
          <Check size={14} weight="bold" /> {clip.status === 'approved' ? 'Approved' : 'Approve'}
        </button>
        <button
          onClick={() => toggle('rejected')}
          aria-pressed={clip.status === 'rejected'}
          className={`${secondary} ${clip.status === 'rejected' ? 'border-zinc-500 bg-zinc-500 text-white dark:border-zinc-600 dark:bg-zinc-600' : idle}`}
        >
          <X size={14} weight="bold" /> {clip.status === 'rejected' ? 'Rejected' : 'Reject'}
        </button>
      </div>
    </li>
  )
}

function ScriptLine({ line, match, active, onSeek, onPickTake }) {
  const status = lineStatus(match)
  const take = match.takes[match.best_take_index]
  return (
    <li className={`border-l-2 py-3 pl-4 transition-colors ${STATUS[status].border} ${active ? 'bg-orange-500/5' : ''}`}>
      <div className="flex items-start justify-between gap-3">
        <button
          onClick={() => take && onSeek(take.start)}
          disabled={!take}
          className="text-left leading-relaxed enabled:hover:text-orange-600 focus-visible:outline-2 focus-visible:outline-orange-500 disabled:text-zinc-500 dark:enabled:hover:text-orange-400"
        >
          {line.text}
        </button>
        <span className="shrink-0 text-xs text-zinc-500 capitalize dark:text-zinc-400">{line.section === 'cta' ? 'CTA' : line.section}</span>
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        <span className={`font-medium ${STATUS[status].text}`}>{STATUS[status].label}</span>
        {take ? (
          <>
            <button onClick={() => onSeek(take.start)} className="font-mono text-zinc-600 tabular-nums hover:text-orange-600 dark:text-zinc-400 dark:hover:text-orange-400">
              {formatTime(take.start)}
            </button>
            <span className="text-zinc-500 dark:text-zinc-400">{Math.round(take.similarity * 100)}% match</span>
            {match.takes.length > 1 && (
              <label className="flex items-center gap-1.5 text-zinc-600 dark:text-zinc-400">
                <span className="sr-only">Take for line {line.idx + 1}</span>
                <select
                  value={match.best_take_index}
                  onChange={(e) => onPickTake(Number(e.target.value))}
                  className="rounded-md border border-zinc-300 bg-white px-1.5 py-0.5 text-xs dark:border-zinc-700 dark:bg-zinc-900"
                >
                  {match.takes.map((t, i) => (
                    <option key={i} value={i}>
                      Take {i + 1} at {formatTime(t.start)} ({Math.round(t.similarity * 100)}%)
                    </option>
                  ))}
                </select>
              </label>
            )}
          </>
        ) : (
          <span className="text-zinc-500 dark:text-zinc-400">Not found in the footage. Re-record it or cover it with B-roll.</span>
        )}
      </div>
      {take?.visual && <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">On screen: {take.visual}</p>}
    </li>
  )
}

export default function ProjectDetail() {
  const { id } = useParams()
  const [project, setProject] = useState(null)
  const [job, setJob] = useState(null)
  const [error, setError] = useState('')
  const [media, setMedia] = useState(null)
  const [now, setNow] = useState(0)

  const load = useCallback(() => getProject(id).then(setProject).catch((e) => setError(errorMessage(e, 'Could not load this project.'))), [id])
  useEffect(() => { load() }, [load])

  const footage = project?.assets.at(-1)
  const footageBusy = footage && ['pending', 'processing'].includes(footage.ai.status)
  useEffect(() => {
    if (!footageBusy) return
    const t = setInterval(load, 2000)
    return () => clearInterval(t)
  }, [footageBusy, load])

  const jobRunning = job && !['done', 'failed'].includes(job.status)
  useEffect(() => {
    if (!jobRunning) return
    const t = setInterval(async () => {
      const j = await getJob(job.id).catch(() => null)
      if (!j) return
      if (j.status === 'done') {
        setJob(null)
        load()
      } else setJob(j)
    }, 1500)
    return () => clearInterval(t)
  }, [jobRunning, job?.id, load])

  useEffect(() => {
    if (!media) return
    const onTime = () => setNow(media.currentTime)
    media.addEventListener('timeupdate', onTime)
    return () => media.removeEventListener('timeupdate', onTime)
  }, [media])

  const process = async () => {
    setError('')
    try {
      const { job_id } = await processProject(id)
      setJob({ id: job_id, status: 'queued', current_step: '', progress: 0 })
    } catch (e) {
      setError(errorMessage(e, 'Could not start processing.'))
    }
  }

  const seek = (t) => {
    if (!media) return
    media.currentTime = t
    media.play()
  }

  const alignment = project?.alignment
  const pickTake = async (lineIdx, takeIndex) => {
    try {
      const updated = await setBestTake(alignment.id, lineIdx, takeIndex)
      setProject((p) => ({ ...p, alignment: updated }))
      seek(updated.matches.find((m) => m.script_line_idx === lineIdx).takes[takeIndex].start)
    } catch (e) {
      setError(errorMessage(e, 'Could not switch takes.'))
    }
  }

  const player = useEdlPlayer(media)
  const [tab, setTab] = useState('script')
  const shorts = useMemo(
    () => (project?.clips ?? []).filter((c) => c.kind !== 'rough_cut').sort((a, b) => b.scores.overall - a.scores.overall),
    [project?.clips],
  )
  const changeStatus = async (clip, status) => {
    try {
      const updated = await setClipStatus(clip.id, status)
      setProject((p) => ({ ...p, clips: p.clips.map((c) => (c.id === updated.id ? updated : c)) }))
    } catch (e) {
      setError(errorMessage(e, 'Could not update the clip.'))
    }
  }

  const [publishing, setPublishing] = useState(false)
  const publish = async () => {
    setPublishing(true)
    setError('')
    try {
      const updated = await publishProject(id)
      setProject((p) => ({ ...p, ...updated }))
    } catch (e) {
      setError(errorMessage(e, 'Could not publish.'))
    } finally {
      setPublishing(false)
    }
  }

  const [building, setBuilding] = useState(false)
  const roughCut = project?.clips.find((c) => c.kind === 'rough_cut')
  const buildCut = async () => {
    setBuilding(true)
    setError('')
    try {
      const clip = await buildRoughCut(id)
      setProject((p) => ({ ...p, clips: [clip, ...p.clips.filter((c) => c.id !== clip.id)] }))
    } catch (e) {
      setError(errorMessage(e, 'Could not build the rough cut.'))
    } finally {
      setBuilding(false)
    }
  }
  // Same rule as the backend's rough_cut_edl: best take per line, script order.
  const roughCutStale = useMemo(() => {
    if (!roughCut || !alignment) return false
    const expected = [...alignment.matches]
      .sort((a, b) => a.script_line_idx - b.script_line_idx)
      .filter((m) => m.takes.length)
      .map((m) => m.takes[m.best_take_index])
      .filter((t) => t.end > t.start)
    const built = roughCut.edl.segments
    return expected.length !== built.length || expected.some((t, i) => t.start !== built[i].start || t.end !== built[i].end)
  }, [roughCut, alignment])

  const counts = useMemo(() => {
    const c = { matched: 0, retake: 0, missing: 0 }
    alignment?.matches.forEach((m) => c[lineStatus(m)]++)
    return c
  }, [alignment])

  if (!project) {
    return error
      ? <p role="alert" className="text-sm text-red-600 dark:text-red-400">{error}</p>
      : <div className="mx-auto h-40 max-w-6xl rounded-lg bg-zinc-200 motion-safe:animate-pulse dark:bg-zinc-800" />
  }

  const canProcess = project.script && footage?.ai.status === 'ready' && !jobRunning
  const matchByLine = Object.fromEntries((alignment?.matches ?? []).map((m) => [m.script_line_idx, m]))
  const activeLine = alignment?.matches.find((m) => {
    const t = m.takes[m.best_take_index]
    return t && now >= t.start && now <= t.end
  })?.script_line_idx

  return (
    <div className="mx-auto max-w-6xl">
      <Link to="/projects" className="inline-flex items-center gap-1.5 text-sm text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100">
        <ArrowLeft size={16} /> Projects
      </Link>
      <div className="mt-4 flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">{project.title}</h1>
          <span className="rounded-full border border-zinc-300 px-2.5 py-0.5 text-xs text-zinc-600 capitalize dark:border-zinc-700 dark:text-zinc-400">{project.stage}</span>
        </div>
        <div className="flex flex-wrap items-center gap-4">
          {alignment && (
            <button onClick={process} disabled={!canProcess} className="inline-flex items-center gap-2 text-sm text-zinc-600 hover:text-zinc-900 disabled:opacity-50 dark:text-zinc-400 dark:hover:text-zinc-100">
              <ArrowsClockwise size={16} /> Re-run processing
            </button>
          )}
          {project.stage !== 'published' && shorts.some((c) => ['approved', 'exported'].includes(c.status)) && (
            <button onClick={publish} disabled={publishing} title="Mock publish: no platform is connected; records sample analytics" className={`${button} inline-flex items-center gap-2`}>
              <PaperPlaneTilt size={16} /> {publishing ? 'Publishing' : 'Publish (mock)'}
            </button>
          )}
        </div>
      </div>
      {error && <p role="alert" className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>}
      {job && <div className="mt-3"><JobProgress job={job} /></div>}

      {!alignment ? (
        <ol className="mt-8 grid max-w-2xl gap-8">
          <li>
            <h2 className="mb-3 font-medium">Script</h2>
            <ScriptStep project={project} onSaved={load} />
          </li>
          <li>
            <h2 className="mb-3 font-medium">Footage</h2>
            <FootageStep project={project} onUploaded={load} />
          </li>
          <li>
            <button onClick={process} disabled={!canProcess} className={button}>Match script to footage</button>
            {!canProcess && !jobRunning && (
              <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">Needs a script and transcribed footage.</p>
            )}
          </li>
        </ol>
      ) : (
        <>
          <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
            <span className="font-semibold text-zinc-900 tabular-nums dark:text-zinc-100">{Math.round(alignment.coverage * 100)}% coverage</span>
            {', '}{counts.matched + counts.retake} of {alignment.matches.length} lines found, {counts.retake} with retakes, {counts.missing} missing
          </p>
          <div className="mt-5">
            <RoughCutBar
              clip={roughCut}
              stale={roughCutStale}
              building={building}
              onBuild={buildCut}
              player={player}
              footageDuration={footage.metadata.duration}
            />
          </div>

          <div className="mt-6 grid grid-cols-1 gap-8 lg:grid-cols-2">
            <div className="order-2 lg:order-1">
              <div role="tablist" aria-label="Project view" className="mb-4 flex gap-1 border-b border-zinc-200 dark:border-zinc-800">
                {[['script', 'Script'], ['clips', `Clips (${shorts.length})`]].map(([key, label]) => (
                  <button
                    key={key}
                    role="tab"
                    id={`tab-${key}`}
                    aria-selected={tab === key}
                    aria-controls={`panel-${key}`}
                    onClick={() => setTab(key)}
                    className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-orange-500 ${
                      tab === key
                        ? 'border-orange-500 text-zinc-900 dark:text-zinc-100'
                        : 'border-transparent text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>

              {tab === 'script' ? (
                <section role="tabpanel" id="panel-script" aria-labelledby="tab-script">
                  <ol className="space-y-1">
                    {project.script.lines.map((line) =>
                      matchByLine[line.idx] && (
                        <ScriptLine
                          key={line.idx}
                          line={line}
                          match={matchByLine[line.idx]}
                          active={line.idx === activeLine}
                          onSeek={seek}
                          onPickTake={(i) => pickTake(line.idx, i)}
                        />
                      ),
                    )}
                  </ol>
                </section>
              ) : (
                <section role="tabpanel" id="panel-clips" aria-labelledby="tab-clips">
                  {shorts.length ? (
                    <ol className="space-y-3">
                      {shorts.map((c) => <ClipCard key={c.id} clip={c} player={player} onStatus={changeStatus} />)}
                    </ol>
                  ) : (
                    <p className="text-sm text-zinc-600 dark:text-zinc-400">
                      No clips yet. Each clip needs 15 to 60 seconds of self-contained material, so short footage may not have any.
                    </p>
                  )}
                </section>
              )}
            </div>

            <div className="order-1 lg:sticky lg:top-6 lg:order-2 lg:self-start">
              <video ref={setMedia} src={mediaUrl(footage.storage_url)} controls className="w-full rounded-lg bg-zinc-950" />
              {alignment.unscripted_ranges.length > 0 && (
                <section className="mt-6">
                  <h2 className="text-sm font-medium">Unscripted moments</h2>
                  <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">Ad-libs often make the best clips.</p>
                  <ul className="mt-3 space-y-2">
                    {alignment.unscripted_ranges.map((r) => (
                      <li key={r.start}>
                        <button onClick={() => seek(r.start)} className="text-left text-sm hover:text-orange-600 dark:hover:text-orange-400">
                          <span className="mr-2 font-mono text-xs text-zinc-500 tabular-nums">{formatTime(r.start)}</span>
                          {r.text}
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
