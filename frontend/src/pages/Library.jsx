import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router'
import { FileText, FilmStrip, ImageSquare, MagnifyingGlass, MusicNotes, VideoCamera, X } from '@phosphor-icons/react'
import { EmptyState, Page } from '../components/Page'
import UploadDropzone from '../components/UploadDropzone'
import { getJob, listAssets, searchAssets, uploadAsset } from '../api/assets'
import { errorMessage, mediaUrl } from '../api/client'
import { formatTime } from '../lib/format'
import { badge, btn, card, errorText, field, skeleton, tile } from '../components/ui'

const TYPE_ICON = { video: VideoCamera, audio: MusicNotes, image: ImageSquare, document: FileText }
const transcribable = (a) => a.type === 'video' || a.type === 'audio'
const inFlight = (a) => transcribable(a) && (a.ai.status === 'pending' || a.ai.status === 'processing')

function StatusBadge({ asset, progress }) {
  if (!transcribable(asset)) return null
  const { status } = asset.ai
  if (status === 'ready') return <span className={badge.success}>Transcribed</span>
  if (status === 'failed') return <span className={badge.danger}>Failed</span>
  return (
    <span className={badge.dark}>
      {status === 'pending' ? 'Queued' : 'Transcribing'}
      {progress != null && <span className="font-mono tabular-nums">{progress}%</span>}
    </span>
  )
}

/** model-card: white, hairline, 10px corners, 16px padding, media full-bleed to the card edge. */
function AssetCard({ asset, progress }) {
  const Icon = TYPE_ICON[asset.type]
  const { duration, width, height } = asset.metadata
  return (
    <Link to={`/assets/${asset.id}`} className={`${card} group block p-4 transition-colors hover:border-hairline-strong focus-ring`}>
      <div className="relative aspect-video overflow-hidden rounded-md bg-bone">
        {asset.thumbnail_url ? (
          <img src={mediaUrl(asset.thumbnail_url)} alt="" className="h-full w-full object-cover" />
        ) : (
          <Icon size={28} className="absolute inset-0 m-auto text-charcoal" />
        )}
        {duration != null && (
          <span className="absolute right-2 bottom-2 rounded-xs bg-deep/80 px-1.5 py-0.5 font-mono text-xs text-on-dark tabular-nums">
            {formatTime(duration)}
          </span>
        )}
      </div>
      <p className="mt-3 truncate font-semibold">{asset.filename}</p>
      <div className="mt-2 flex items-center justify-between gap-2">
        <span className="font-mono text-xs text-mute">{width && height ? `${width}x${height}` : asset.type}</span>
        <StatusBadge asset={asset} progress={progress} />
      </div>
    </Link>
  )
}

function SearchResults({ results, query }) {
  if (!results.length) {
    return <p className={`${tile} px-6 py-8 text-base text-charcoal`}>Nothing matched "{query}". Try the words you said, or describe the moment.</p>
  }
  return (
    <ul className={`${card} divide-y divide-hairline`}>
      {results.map((r, i) => (
        <li key={i}>
          <Link to={`/assets/${r.asset.id}${r.start != null ? `?t=${r.start}` : ''}`} className="group flex gap-5 rounded-md p-4 focus-ring">
            <div className="relative aspect-video w-36 shrink-0 overflow-hidden rounded-md bg-bone">
              {r.asset.thumbnail_url && <img src={mediaUrl(r.asset.thumbnail_url)} alt="" className="h-full w-full object-cover" />}
              {r.start != null && (
                <span className="absolute right-1 bottom-1 rounded-xs bg-deep/80 px-1 font-mono text-[11px] text-on-dark tabular-nums">{formatTime(r.start)}</span>
              )}
            </div>
            <div className="min-w-0 self-center">
              <p className="text-base leading-relaxed group-hover:underline group-hover:underline-offset-4">{r.snippet}</p>
              <p className="mt-1 text-sm text-mute">
                <span className="font-mono">{r.asset.filename}</span>, {r.kind === 'visual_description' ? 'what is on screen' : `said at ${formatTime(r.start)}`}
              </p>
            </div>
          </Link>
        </li>
      ))}
    </ul>
  )
}

export default function Library() {
  const [assets, setAssets] = useState(null) // null while loading
  const [jobs, setJobs] = useState({}) // assetId -> jobId, for uploads made this session
  const [progress, setProgress] = useState({}) // assetId -> %
  const [uploading, setUploading] = useState(null)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null) // null = not searching
  const [searching, setSearching] = useState(false)
  const runSearch = async (e) => {
    e.preventDefault()
    if (query.trim().length < 2) return
    setSearching(true)
    try {
      setResults(await searchAssets(query.trim()))
    } catch (err) {
      setError(errorMessage(err, 'Search failed.'))
    } finally {
      setSearching(false)
    }
  }

  const load = useCallback(
    () => listAssets().then(setAssets).catch((e) => setError(errorMessage(e, 'Could not load your library.'))),
    [],
  )
  useEffect(() => { load() }, [load])

  // Poll while anything is transcribing; job docs give the % for uploads we started.
  const busy = assets?.some(inFlight)
  useEffect(() => {
    if (!busy) return
    const timer = setInterval(() => {
      load()
      Object.entries(jobs).forEach(([assetId, jobId]) =>
        getJob(jobId).then((j) => setProgress((p) => ({ ...p, [assetId]: j.progress }))).catch(() => {}),
      )
    }, 2000)
    return () => clearInterval(timer)
  }, [busy, jobs, load])

  const upload = async (files) => {
    setError('')
    for (const file of files) {
      setUploading({ name: file.name, pct: 0 })
      try {
        const { asset, job_id } = await uploadAsset(file, (pct) => setUploading({ name: file.name, pct }))
        setAssets((prev) => [asset, ...(prev ?? [])])
        if (job_id) setJobs((j) => ({ ...j, [asset.id]: job_id }))
      } catch (e) {
        setError(`${file.name}: ${errorMessage(e, 'Upload failed.')}`)
      }
    }
    setUploading(null)
  }

  return (
    <Page title="Library" description="Every file you upload, described and searchable by what was said in it.">
      <form role="search" onSubmit={runSearch} className="flex flex-wrap gap-2">
        <label htmlFor="library-search" className="sr-only">Search your footage</label>
        <div className="relative min-w-64 flex-1">
          <MagnifyingGlass size={18} className="pointer-events-none absolute top-1/2 left-5 -translate-y-1/2 text-charcoal" />
          <input
            id="library-search"
            type="search"
            value={query}
            onChange={(e) => { setQuery(e.target.value); if (!e.target.value) setResults(null) }}
            placeholder="Find a moment: the bit where I talk about index funds"
            className={`${field} w-full pl-12`}
          />
        </div>
        <button disabled={searching} className={btn.dark}>{searching ? 'Searching' : 'Search'}</button>
        {results && (
          <button type="button" onClick={() => { setResults(null); setQuery('') }} aria-label="Clear search" className={`${btn.icon} size-11`}>
            <X size={16} />
          </button>
        )}
      </form>
      {error && <p role="alert" className={`mt-4 ${errorText}`}>{error}</p>}

      <div className="mt-8">
        {results ? <SearchResults results={results} query={query} /> : (
          <>
            <UploadDropzone onFiles={upload} uploading={uploading} />
            {assets?.length === 0 ? (
              <div className="mt-10">
                <EmptyState icon={FilmStrip} title="Nothing here yet">Uploads appear here, with their transcript, tags and search.</EmptyState>
              </div>
            ) : (
              <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {assets === null
                  ? Array.from({ length: 4 }, (_, i) => <div key={i} className={`h-64 ${skeleton}`} />)
                  : assets.map((a) => <AssetCard key={a.id} asset={a} progress={progress[a.id]} />)}
              </div>
            )}
          </>
        )}
      </div>
    </Page>
  )
}
