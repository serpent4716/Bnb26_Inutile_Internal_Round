import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { ArrowLeft } from '@phosphor-icons/react'
import TranscriptViewer from '../components/TranscriptViewer'
import { getAsset, getTranscript } from '../api/assets'
import { errorMessage, mediaUrl } from '../api/client'
import { formatTime } from '../lib/format'

export default function AssetDetail() {
  const { id } = useParams()
  const [params] = useSearchParams()
  const startAt = Number(params.get('t')) || 0 // from search results
  const [asset, setAsset] = useState(null)
  const [transcript, setTranscript] = useState(null)
  const [error, setError] = useState('')
  const [media, setMedia] = useState(null) // the <video>/<audio> element

  const status = asset?.ai.status
  useEffect(() => {
    getAsset(id).then(setAsset).catch((e) => setError(errorMessage(e, 'Could not load this file.')))
  }, [id])

  // Poll until transcription finishes, then load the transcript once.
  useEffect(() => {
    if (status === 'ready') {
      getTranscript(id).then(setTranscript).catch((e) => setError(errorMessage(e)))
      return
    }
    if (status !== 'pending' && status !== 'processing') return
    const timer = setInterval(() => getAsset(id).then(setAsset).catch(() => {}), 2000)
    return () => clearInterval(timer)
  }, [id, status])

  const back = (
    <Link to="/library" className="inline-flex items-center gap-1.5 text-sm text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100">
      <ArrowLeft size={16} /> Library
    </Link>
  )

  if (error) return <div className="mx-auto max-w-6xl">{back}<p role="alert" className="mt-6 text-sm text-red-600 dark:text-red-400">{error}</p></div>
  if (!asset) return <div className="mx-auto max-w-6xl">{back}<div className="mt-6 aspect-video max-w-3xl rounded-lg bg-zinc-200 motion-safe:animate-pulse dark:bg-zinc-800" /></div>

  const src = mediaUrl(asset.storage_url)
  const transcribable = asset.type === 'video' || asset.type === 'audio'

  return (
    <div className="mx-auto max-w-6xl">
      {back}
      <h1 className="mt-4 truncate text-2xl font-semibold tracking-tight">{asset.filename}</h1>
      <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
        {[formatTime(asset.metadata.duration), asset.metadata.width && `${asset.metadata.width}x${asset.metadata.height}`, transcript?.language]
          .filter(Boolean)
          .join(', ')}
      </p>

      <div className="mt-6 grid grid-cols-1 gap-8 lg:grid-cols-[3fr_2fr]">
        <div className="lg:sticky lg:top-6 lg:self-start">
          {asset.type === 'video' && <video ref={setMedia} src={src} controls onLoadedMetadata={(e) => { e.currentTarget.currentTime = startAt }} className="w-full rounded-lg bg-zinc-950" />}
          {asset.type === 'audio' && <audio ref={setMedia} src={src} controls onLoadedMetadata={(e) => { e.currentTarget.currentTime = startAt }} className="w-full" />}
          {asset.type === 'image' && <img src={src} alt={asset.filename} className="w-full rounded-lg" />}
        </div>

        {transcribable && (
          <section aria-label="Transcript" className="lg:max-h-[75dvh] lg:overflow-y-auto lg:pr-2">
            <h2 className="text-sm font-medium text-zinc-500 dark:text-zinc-400">Transcript</h2>
            <div className="mt-3">
              {transcript ? (
                <TranscriptViewer transcript={transcript} media={media} />
              ) : status === 'failed' ? (
                <p className="text-sm text-red-600 dark:text-red-400">Transcription failed. Try uploading the file again.</p>
              ) : (
                <div className="space-y-3">
                  <p className="text-sm text-zinc-600 dark:text-zinc-400">Transcribing. This page updates when it's done.</p>
                  {[90, 75, 85].map((w) => (
                    <div key={w} style={{ width: `${w}%` }} className="h-4 rounded bg-zinc-200 motion-safe:animate-pulse dark:bg-zinc-800" />
                  ))}
                </div>
              )}
            </div>
          </section>
        )}
      </div>
    </div>
  )
}
