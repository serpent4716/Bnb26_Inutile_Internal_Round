import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router'
import { ArrowsClockwise, Check, FilmReel, PaperPlaneTilt, PencilSimple, Play, Stop, X } from '@phosphor-icons/react'
import JobStepper from '../components/JobStepper'
import UploadDropzone from '../components/UploadDropzone'
import { DetailHeader, SectionTitle } from '../components/Page'
import { badge, btn, card, errorText, fieldArea, link, skeleton, tile } from '../components/ui'
import { getJob, uploadAsset, waitForJob } from '../api/assets'
import { errorMessage, mediaUrl } from '../api/client'
import { setClipStatus } from '../api/clips'
import { buildRoughCut, getProject, processProject, publishProject, saveScript, setBestTake } from '../api/projects'
import { formatTime } from '../lib/format'
import { useEdlPlayer } from '../lib/useEdlPlayer'

const STATUS = {
  matched: { label: 'Matched', border: 'border-success', badge: badge.success },
  retake: { label: 'Retakes', border: 'border-ink', badge: badge.dark },
  missing: { label: 'Missing', border: 'border-danger', badge: badge.danger },
}
const lineStatus = (m) => (m.status === 'missing' ? 'missing' : m.takes.length > 1 ? 'retake' : 'matched')
const STAGE = { idea: 'Idea', scripting: 'Scripting', recording: 'Recording', editing: 'Editing', review: 'Review', scheduled: 'Scheduled', published: 'Published' }

// sub-nav pill tabs
const tabClass = (active) =>
  `inline-flex h-9 items-center rounded-full px-4 text-sm font-semibold transition-colors focus-ring ${active ? 'bg-dark text-on-dark' : 'text-ink hover:bg-bone'}`

function ScriptStep({ project, onSaved }) {
  const [content, setContent] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  if (project.script) return <p className="text-base"><span className="font-semibold">{project.script.lines.length} lines</span>, each labelled hook, intro, body or CTA.</p>

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
    <div className="grid gap-3">
      <label htmlFor="script" className="text-sm font-semibold">Paste your script</label>
      <textarea
        id="script"
        rows={8}
        value={content}
        onChange={(e) => setContent(e.target.value)}
        placeholder="One line or sentence per beat. Each one gets matched to your footage."
        className={fieldArea}
      />
      {error && <p role="alert" className={errorText}>{error}</p>}
      <div><button onClick={save} disabled={busy || !content.trim()} className={btn.dark}>{busy ? 'Saving' : 'Save script'}</button></div>
    </div>
  )
}

function FootageStep({ project, onUploaded }) {
  const [uploading, setUploading] = useState(null)
  const [job, setJob] = useState(null)
  const [error, setError] = useState('')
  const footage = project.assets.at(-1)
  if (job) return <JobStepper job={job} />
  if (footage) {
    const s = footage.ai.status
    return (
      <p className="flex flex-wrap items-center gap-2 text-base">
        <span className="font-mono text-sm">{footage.filename}</span>
        <span className={s === 'ready' ? badge.success : s === 'failed' ? badge.danger : badge.dark}>
          {s === 'ready' ? 'Transcribed' : s === 'failed' ? 'Transcription failed' : 'Transcribing'}
        </span>
      </p>
    )
  }
  const upload = async ([file]) => {
    setError('')
    setUploading({ name: file.name, pct: 0 })
    try {
      const { job_id } = await uploadAsset(file, (pct) => setUploading({ name: file.name, pct }), project.id)
      setUploading(null)
      // Show the job's steps while it runs; clear them when it succeeds, keep them (with the error) if it fails.
      const ok = job_id ? await waitForJob(job_id, setJob).then(() => true, () => false) : true
      if (ok) setJob(null)
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
      {error && <p role="alert" className={`mt-3 ${errorText}`}>{error}</p>}
    </>
  )
}

function RoughCutBar({ clip, stale, building, onBuild, player, footageDuration }) {
  const segs = clip?.edl.segments
  const total = segs?.reduce((sum, x) => sum + x.end - x.start, 0) ?? 0
  const playing = player.playing?.key === clip?.id ? player.playing : null

  return (
    <div className={`${tile} flex flex-wrap items-center gap-x-5 gap-y-3 px-5 py-4`}>
      {!clip ? (
        <>
          <button onClick={onBuild} disabled={building} className={btn.darkSm}>
            <FilmReel size={16} /> {building ? 'Building' : 'Build rough cut'}
          </button>
          <span className="text-sm text-charcoal">The best take of every line, in script order.</span>
        </>
      ) : (
        <>
          {!playing ? (
            <button onClick={() => player.play(clip.id, segs)} disabled={!segs.length} className={btn.darkSm}>
              <Play size={14} weight="fill" /> Play rough cut
            </button>
          ) : (
            <button onClick={player.stop} className={btn.darkSm}><Stop size={14} weight="fill" /> Stop</button>
          )}
          <span className="text-sm text-charcoal" aria-live="polite">
            {!playing
              ? <>Rough cut: {segs.length} takes, <span className="font-mono">{formatTime(total)}</span>{footageDuration ? <> from <span className="font-mono">{formatTime(footageDuration)}</span> of footage</> : null}</>
              : <>Playing take {playing.seg + 1} of {playing.count}</>}
          </span>
          {stale && (
            <span className="text-sm text-charcoal">
              Takes changed since it was built.{' '}
              <button onClick={onBuild} disabled={building} className={link}>{building ? 'Rebuilding' : 'Rebuild'}</button>
            </span>
          )}
        </>
      )}
    </div>
  )
}

/** model-card for a suggested clip: score in the display face, actions as small pills. */
function ClipCard({ clip, player, onStatus }) {
  const segs = clip.edl.segments
  const duration = segs.reduce((sum, s) => sum + s.end - s.start, 0)
  const playing = player.playing?.key === clip.id
  const { hook, completeness, virality, overall } = clip.scores
  const toggle = (status) => onStatus(clip, clip.status === status ? 'suggested' : status)
  const approved = clip.status === 'approved' || clip.status === 'exported'
  const rejected = clip.status === 'rejected'

  return (
    <li className={`${card} p-5 transition-opacity ${approved ? 'border-success' : ''} ${rejected ? 'opacity-55' : ''}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="heading-sm">{clip.title}</h3>
          <p className="mt-1 text-sm text-mute">
            <span className="font-mono">{formatTime(duration)}</span> clip from <span className="font-mono">{formatTime(segs[0].start)}</span> to{' '}
            <span className="font-mono">{formatTime(segs.at(-1).end)}</span>
          </p>
        </div>
        <p className="shrink-0 text-right">
          <span className="font-display text-4xl leading-none font-bold tracking-tight">{overall.toFixed(1)}</span>
          <span className="mt-1 block text-xs text-mute">score</span>
        </p>
      </div>
      <p className="mt-3 text-base leading-relaxed text-body">{clip.reason}</p>
      <dl className="mt-4 flex flex-wrap gap-2">
        {[['Hook', hook], ['Complete', completeness], ['Viral', virality]].map(([label, v]) => (
          <div key={label} className={badge.tag}>
            <dt className="text-charcoal">{label}</dt>
            <dd className="font-mono font-semibold">{v}</dd>
          </div>
        ))}
      </dl>
      <div className="mt-5 flex flex-wrap gap-2">
        <Link to={`/clips/${clip.id}`} className={btn.darkSm}><PencilSimple size={14} /> Edit</Link>
        <button onClick={() => (playing ? player.stop() : player.play(clip.id, segs))} className={btn.outlineSm}>
          {playing ? <><Stop size={14} weight="fill" /> Stop</> : <><Play size={14} weight="fill" /> Play</>}
        </button>
        <button
          onClick={() => toggle('approved')}
          aria-pressed={clip.status === 'approved'}
          className={`${btn.toggleSm} ${clip.status === 'approved' ? 'border-success bg-success text-on-dark' : 'border-hairline-strong bg-card text-ink hover:bg-bone'}`}
        >
          <Check size={14} weight="bold" /> {clip.status === 'approved' ? 'Approved' : 'Approve'}
        </button>
        <button
          onClick={() => toggle('rejected')}
          aria-pressed={rejected}
          className={`${btn.toggleSm} ${rejected ? 'border-dark bg-dark text-on-dark' : 'border-hairline bg-transparent text-charcoal hover:bg-bone'}`}
        >
          <X size={14} weight="bold" /> {rejected ? 'Rejected' : 'Reject'}
        </button>
      </div>
    </li>
  )
}

function ScriptLine({ line, match, active, onSeek, onPickTake }) {
  const status = lineStatus(match)
  const take = match.takes[match.best_take_index]
  return (
    <li className={`rounded-r-md border-l-[3px] py-4 pr-3 pl-5 transition-colors ${STATUS[status].border} ${active ? 'bg-bone' : ''}`}>
      <div className="flex items-start justify-between gap-3">
        <button
          onClick={() => take && onSeek(take.start)}
          disabled={!take}
          className="rounded-xs text-left text-base leading-relaxed enabled:hover:underline enabled:hover:underline-offset-4 focus-ring disabled:text-mute"
        >
          {line.text}
        </button>
        <span className={`${badge.tag} shrink-0`}>{line.section === 'cta' ? 'CTA' : line.section[0].toUpperCase() + line.section.slice(1)}</span>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
        <span className={STATUS[status].badge}>{STATUS[status].label}</span>
        {take ? (
          <>
            <button onClick={() => onSeek(take.start)} className="rounded-xs font-mono text-charcoal hover:text-ink hover:underline focus-ring">
              {formatTime(take.start)}
            </button>
            <span className="text-mute"><span className="font-mono">{Math.round(take.similarity * 100)}%</span> match</span>
            {match.takes.length > 1 && (
              <label className="flex items-center">
                <span className="sr-only">Take for line {line.idx + 1}</span>
                <select
                  value={match.best_take_index}
                  onChange={(e) => onPickTake(Number(e.target.value))}
                  className="h-8 rounded-full border border-hairline-strong bg-card pr-8 pl-3 text-sm font-semibold focus-ring"
                >
                  {match.takes.map((t, i) => (
                    <option key={i} value={i}>Take {i + 1} at {formatTime(t.start)} ({Math.round(t.similarity * 100)}%)</option>
                  ))}
                </select>
              </label>
            )}
          </>
        ) : (
          <span className="text-charcoal">Not found in the footage. Re-record it or cover it with B-roll.</span>
        )}
      </div>
      {take?.visual && <p className="mt-2 text-sm text-mute">On screen: {take.visual}</p>}
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
      setJob({ id: job_id, type: 'pipeline', status: 'queued', current_step: '', progress: 0 })
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
      ? <p role="alert" className={errorText}>{error}</p>
      : <div className={`h-40 ${skeleton}`} />
  }

  const canProcess = project.script && footage?.ai.status === 'ready' && !jobRunning
  const canPublish = project.stage !== 'published' && shorts.some((c) => ['approved', 'exported'].includes(c.status))
  const matchByLine = Object.fromEntries((alignment?.matches ?? []).map((m) => [m.script_line_idx, m]))
  const activeLine = alignment?.matches.find((m) => {
    const t = m.takes[m.best_take_index]
    return t && now >= t.start && now <= t.end
  })?.script_line_idx

  return (
    <div>
      <DetailHeader
        back="/projects"
        backLabel="Projects"
        title={project.title}
        meta={<span className={project.stage === 'published' ? badge.success : badge.tag}>{STAGE[project.stage]}</span>}
        aside={
          <div className="flex flex-wrap items-center gap-2">
            {alignment && (
              <button onClick={process} disabled={!canProcess} className={btn.outlineSm}>
                <ArrowsClockwise size={16} /> Re-run processing
              </button>
            )}
            {canPublish && (
              <button onClick={publish} disabled={publishing} title="Mock publish: no platform is connected; records sample analytics" className={btn.primary}>
                <PaperPlaneTilt size={16} /> {publishing ? 'Publishing' : 'Publish (mock)'}
              </button>
            )}
          </div>
        }
      />
      {error && <p role="alert" className={`mt-6 ${errorText}`}>{error}</p>}
      {job && <div className={`${tile} mt-8 px-6 py-5`}><JobStepper job={job} /></div>}

      {!alignment ? (
        <ol className="mt-10 grid max-w-3xl gap-4">
          {[
            ['Script', <ScriptStep key="s" project={project} onSaved={load} />],
            ['Footage', <FootageStep key="f" project={project} onUploaded={load} />],
          ].map(([label, body], i) => (
            <li key={label} className={`${tile} p-6`}>
              <h2 className="heading-sm"><span className="mr-3 font-mono text-base text-mute">0{i + 1}</span>{label}</h2>
              <div className="mt-4">{body}</div>
            </li>
          ))}
          <li className={`${tile} flex flex-wrap items-center gap-4 p-6`}>
            <h2 className="heading-sm"><span className="mr-3 font-mono text-base text-mute">03</span>Match</h2>
            <button onClick={process} disabled={!canProcess} className={btn.primary}>Match script to footage</button>
            {!canProcess && !jobRunning && <p className="text-sm text-charcoal">Needs a script and transcribed footage.</p>}
          </li>
        </ol>
      ) : (
        <>
          <div className="mt-10 flex flex-wrap items-end gap-x-8 gap-y-4">
            <p>
              <span className="font-display text-6xl leading-none font-bold tracking-tight">{Math.round(alignment.coverage * 100)}%</span>
              <span className="ml-3 text-base text-charcoal">coverage</span>
            </p>
            <p className="flex flex-wrap gap-2 pb-1">
              <span className={badge.success}>{counts.matched + counts.retake} of {alignment.matches.length} lines found</span>
              <span className={badge.dark}>{counts.retake} with retakes</span>
              <span className={counts.missing ? badge.danger : badge.tag}>{counts.missing} missing</span>
            </p>
          </div>
          <div className="mt-6">
            <RoughCutBar clip={roughCut} stale={roughCutStale} building={building} onBuild={buildCut} player={player} footageDuration={footage.metadata.duration} />
          </div>

          <div className="mt-10 grid grid-cols-1 gap-10 lg:grid-cols-2">
            <div className="order-2 lg:order-1">
              <div role="tablist" aria-label="Project view" className="mb-6 flex gap-1">
                {[['script', 'Script'], ['clips', `Clips (${shorts.length})`]].map(([key, label]) => (
                  <button
                    key={key}
                    role="tab"
                    id={`tab-${key}`}
                    aria-selected={tab === key}
                    aria-controls={`panel-${key}`}
                    onClick={() => setTab(key)}
                    className={tabClass(tab === key)}
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
                    <ol className="space-y-4">
                      {shorts.map((c) => <ClipCard key={c.id} clip={c} player={player} onStatus={changeStatus} />)}
                    </ol>
                  ) : (
                    <p className={`${tile} px-6 py-8 text-base text-charcoal`}>
                      No clips yet. Each clip needs 15 to 60 seconds of self-contained material, so short footage may not have any.
                    </p>
                  )}
                </section>
              )}
            </div>

            <div className="order-1 lg:sticky lg:top-24 lg:order-2 lg:self-start">
              <video ref={setMedia} src={mediaUrl(footage.storage_url)} controls className="w-full rounded-md bg-dark" />
              {alignment.unscripted_ranges.length > 0 && (
                <section aria-labelledby="adlib-heading" className={`${card} mt-6 p-6`}>
                  <SectionTitle id="adlib-heading" sub="Unscripted moments. Ad-libs often make the best clips.">Ad-libs</SectionTitle>
                  <ul className="mt-4 space-y-3">
                    {alignment.unscripted_ranges.map((r) => (
                      <li key={r.start}>
                        <button onClick={() => seek(r.start)} className="group rounded-xs text-left text-base leading-relaxed focus-ring">
                          <span className="mr-2 font-mono text-sm text-mute">{formatTime(r.start)}</span>
                          <span className="group-hover:underline group-hover:underline-offset-4">{r.text}</span>
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
