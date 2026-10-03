import { useEffect, useMemo, useState } from 'react'
import { formatTime } from '../lib/format'

/** Click a word to seek `media` there; the word under the playhead is highlighted. */
export default function TranscriptViewer({ transcript, media }) {
  const { segments, words } = useMemo(() => {
    let n = 0
    const segments = transcript.segments.map((s) => ({ ...s, offset: (n += s.words.length) - s.words.length }))
    return { segments, words: segments.flatMap((s) => s.words) }
  }, [transcript])
  const [active, setActive] = useState(-1)

  useEffect(() => {
    if (!media) return
    const onTime = () => {
      // binary search: last word starting at or before the playhead
      const t = media.currentTime
      let lo = 0, hi = words.length - 1, found = -1
      while (lo <= hi) {
        const mid = (lo + hi) >> 1
        if (words[mid].start <= t) { found = mid; lo = mid + 1 } else hi = mid - 1
      }
      setActive(found >= 0 && t <= words[found].end + 0.25 ? found : -1)
    }
    media.addEventListener('timeupdate', onTime)
    return () => media.removeEventListener('timeupdate', onTime)
  }, [media, words])

  const seek = (t) => {
    if (!media) return
    media.currentTime = t
    media.play()
  }

  if (!segments.length) return <p className="text-sm text-mute">No speech was detected in this file.</p>

  return (
    <div className="space-y-5">
      {segments.map((s) => (
        <div key={s.idx} className={s.is_filler ? 'opacity-50' : ''}>
          <button
            onClick={() => seek(s.start)}
            className="rounded-xs font-mono text-xs text-mute hover:text-ink hover:underline focus-ring"
          >
            {formatTime(s.start)}
          </button>
          <p className="mt-1 text-base leading-relaxed">
            {s.words.map((w, i) => (
              <button
                key={i}
                onClick={() => seek(w.start)}
                title={`${w.start.toFixed(2)}s`}
                className={`rounded px-0.5 transition-colors focus-ring ${
                  s.offset + i === active
                    ? 'bg-dark text-on-dark'
                    : 'hover:bg-bone'
                }`}
              >
                {w.w}
              </button>
            ))}
          </p>
          {s.silence_after >= 0.5 && (
            <p className="mt-1 text-xs text-mute">{s.silence_after.toFixed(1)}s pause</p>
          )}
        </div>
      ))}
    </div>
  )
}
