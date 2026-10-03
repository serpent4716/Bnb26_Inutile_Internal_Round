import { useEffect, useState } from 'react'
import { useParams, useSearchParams } from 'react-router'
import { DetailHeader, SectionTitle } from '../components/Page'
import { badge, card, errorText, skeleton } from '../components/ui'
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

  if (error || !asset) {
    return (
      <div>
        <DetailHeader back="/library" backLabel="Library" title={error ? 'Could not open this file' : ' '} />
        {error ? <p role="alert" className={`mt-6 ${errorText}`}>{error}</p> : <div className={`mt-10 aspect-video max-w-3xl ${skeleton}`} />}
      </div>
    )
  }

  const src = mediaUrl(asset.storage_url)
  const transcribable = asset.type === 'video' || asset.type === 'audio'
  const { duration, width, height } = asset.metadata

  return (
    <div>
      <DetailHeader
        back="/library"
        backLabel="Library"
        title={asset.filename}
        meta={
          <div className="flex flex-wrap items-center gap-2">
            {duration != null && <span className={badge.tag}><span className="font-mono">{formatTime(duration)}</span></span>}
            {width && <span className={badge.tag}><span className="font-mono">{width}x{height}</span></span>}
            {transcript?.language && <span className={badge.tag}>{transcript.language}</span>}
            {asset.ai.tags.slice(0, 5).map((t) => <span key={t} className={badge.tag}>{t}</span>)}
          </div>
        }
      />

      <div className="mt-10 grid grid-cols-1 gap-10 lg:grid-cols-[3fr_2fr]">
        <div className="lg:sticky lg:top-24 lg:self-start">
          {asset.type === 'video' && <video ref={setMedia} src={src} controls onLoadedMetadata={(e) => { e.currentTarget.currentTime = startAt }} className="w-full rounded-md bg-dark" />}
          {asset.type === 'audio' && <audio ref={setMedia} src={src} controls onLoadedMetadata={(e) => { e.currentTarget.currentTime = startAt }} className="w-full" />}
          {asset.type === 'image' && <img src={src} alt={asset.filename} className="w-full rounded-md" />}
          {asset.ai.description && <p className="mt-4 text-base leading-relaxed text-body">{asset.ai.description}</p>}
        </div>

        {transcribable && (
          <section aria-labelledby="transcript-heading" className={`${card} p-6 lg:max-h-[75dvh] lg:overflow-y-auto`}>
            <SectionTitle id="transcript-heading" sub="Click any word to jump the video there.">Transcript</SectionTitle>
            <div className="mt-5">
              {transcript ? (
                <TranscriptViewer transcript={transcript} media={media} />
              ) : status === 'failed' ? (
                <p className={errorText}>Transcription failed. Try uploading the file again.</p>
              ) : (
                <div className="space-y-3">
                  <p className="text-base text-charcoal">Transcribing. This page updates when it's done.</p>
                  {[90, 75, 85].map((w) => <div key={w} style={{ width: `${w}%` }} className={`h-4 ${skeleton}`} />)}
                </div>
              )}
            </div>
          </section>
        )}
      </div>
    </div>
  )
}
