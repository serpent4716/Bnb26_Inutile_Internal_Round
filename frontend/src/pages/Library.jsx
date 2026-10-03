import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router'
import { FileText, ImageSquare, MagnifyingGlass, MusicNotes, VideoCamera, X } from '@phosphor-icons/react'
import { Page } from '../components/Page'
import UploadDropzone from '../components/UploadDropzone'
import { getJob, listAssets, searchAssets, uploadAsset } from '../api/assets'
import { errorMessage, mediaUrl } from '../api/client'
import { formatTime } from '../lib/format'

const TYPE_ICON = { video: VideoCamera, audio: MusicNotes, image: ImageSquare, document: FileText }
const transcribable = (a) => a.type === 'video' || a.type === 'audio'
const inFlight = (a) => transcribable(a) && (a.ai.status === 'pending' || a.ai.status === 'processing')

function StatusBadge({ asset, progress }) {
  if (!transcribable(asset)) return null
  const { status } = asset.ai
  if (status === 'ready') return <span className="text-xs text-zinc-500 dark:text-zinc-400">Transcribed</span>
  if (status === 'failed') return <span className="text-xs font-medium text-red-600 dark:text-red-400">Failed</span>
  return (
    <span className="text-xs font-medium text-orange-600 dark:text-orange-400">
      {status === 'pending' ? 'Queued' : 'Transcribing'}
      {progress != null && <span className="ml-1 font-mono tabular-nums">{progress}%</span>}
    </span>
  )
}

function AssetCard({ asset, progress }) {
  const Icon = TYPE_ICON[asset.type]
  const { duration, width, height } = asset.metadata
  return (
    <Link
      to={`/assets/${asset.id}`}
      className="group block rounded-lg focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-orange-500"
    >
      <div className="relative aspect-video overflow-hidden rounded-lg bg-zinc-200 dark:bg-zinc-800">
        {asset.thumbnail_url ? (
          <img src={mediaUrl(asset.thumbnail_url)} alt="" className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]" />
        ) : (
          <Icon size={28} className="absolute inset-0 m-auto text-zinc-400 dark:text-zinc-500" />
        )}
        {duration != null && (
          <span className="absolute right-2 bottom-2 rounded bg-zinc-950/75 px-1.5 py-0.5 font-mono text-xs text-zinc-50 tabular-nums">
            {formatTime(duration)}
          </span>
        )}
      </div>
      <p className="mt-2 truncate text-sm font-medium">{asset.filename}</p>
      <div className="mt-0.5 flex items-center justify-between gap-2">
        <span className="text-xs text-zinc-500 dark:text-zinc-400">{width && height ? `${width}x${height}` : asset.type}</span>
        <StatusBadge asset={asset} progress={progress} />
      </div>
    </Link>
  )
}

function SearchResults({ results, query }) {
  if (!results.length) {
    return <p className="mt-6 text-sm text-zinc-600 dark:text-zinc-400">Nothing matched "{query}". Try the words you said, or describe the moment.</p>
  }
  return (
    <ul className="mt-6 divide-y divide-zinc-200 dark:divide-zinc-800">
      {results.map((r, i) => (
        <li key={i}>
          <Link
            to={`/assets/${r.asset.id}${r.start != null ? `?t=${r.start}` : ''}`}
            className="flex gap-4 py-3 hover:text-orange-600 focus-visible:outline-2 focus-visible:outline-orange-500 dark:hover:text-orange-400"
          >
            <div className="relative aspect-video w-32 shrink-0 overflow-hidden rounded-md bg-zinc-200 dark:bg-zinc-800">
              {r.asset.thumbnail_url && <img src={mediaUrl(r.asset.thumbnail_url)} alt="" className="h-full w-full object-cover" />}
              {r.start != null && (
                <span className="absolute right-1 bottom-1 rounded bg-zinc-950/75 px-1 font-mono text-[11px] text-zinc-50 tabular-nums">{formatTime(r.start)}</span>
              )}
            </div>
            <div className="min-w-0">
              <p className="text-sm leading-relaxed">{r.snippet}</p>
              <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                {r.asset.filename}, {r.kind === 'visual_description' ? 'what is on screen' : `said at ${formatTime(r.start)}`}
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
    <Page title="Library" description="Every file you upload, auto-tagged and searchable by what was said in it.">
      <form role="search" onSubmit={runSearch} className="mb-6 flex gap-2">
        <label htmlFor="library-search" className="sr-only">Search your footage</label>
        <div className="relative flex-1">
          <MagnifyingGlass size={16} className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-zinc-500" />
          <input
            id="library-search"
            type="search"
            value={query}
            onChange={(e) => { setQuery(e.target.value); if (!e.target.value) setResults(null) }}
            placeholder="Find a moment: the bit where I talk about index funds"
            className="w-full rounded-lg border border-zinc-300 bg-white py-2 pr-3 pl-9 text-sm placeholder:text-zinc-500 focus:border-orange-500 focus:outline-2 focus:outline-orange-500/30 dark:border-zinc-700 dark:bg-zinc-900 dark:placeholder:text-zinc-400"
          />
        </div>
        <button disabled={searching} className="rounded-lg bg-orange-600 px-4 py-2 text-sm font-medium text-white hover:bg-orange-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-500 active:scale-[0.98] disabled:opacity-60">
          {searching ? 'Searching' : 'Search'}
        </button>
        {results && (
          <button type="button" onClick={() => { setResults(null); setQuery('') }} aria-label="Clear search" className="rounded-lg border border-zinc-300 px-2.5 text-zinc-600 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800">
            <X size={16} />
          </button>
        )}
      </form>
      {results ? <SearchResults results={results} query={query} /> : <>
      <UploadDropzone onFiles={upload} uploading={uploading} />
      {error && <p role="alert" className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>}

      <div className="mt-10 grid grid-cols-1 gap-x-5 gap-y-8 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {assets === null
          ? Array.from({ length: 4 }, (_, i) => (
              <div key={i}>
                <div className="aspect-video rounded-lg bg-zinc-200 motion-safe:animate-pulse dark:bg-zinc-800" />
                <div className="mt-2 h-4 w-2/3 rounded bg-zinc-200 motion-safe:animate-pulse dark:bg-zinc-800" />
              </div>
            ))
          : assets.map((a) => <AssetCard key={a.id} asset={a} progress={progress[a.id]} />)}
      </div>
      {assets?.length === 0 && (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">Nothing here yet. Your uploads will show up in this grid.</p>
      )}
      </>}
    </Page>
  )
}
