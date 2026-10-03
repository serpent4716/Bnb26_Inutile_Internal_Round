import { useMemo } from 'react'
import { ArrowCounterClockwise } from '@phosphor-icons/react'
import { btn } from './ui'
import { SectionTitle } from './Page'
import { formatTime } from '../lib/format'

/**
 * Descript-style editing: the clip's source words, cut ones struck through. Click a word to cut or restore it;
 * the timeline above shows what's kept and can cut a whole segment. Every change is a new EDL version.
 */
export default function TranscriptEditor({ clip, words, busy, onKeep, onUndo }) {
  const segs = clip.edl.segments
  const { range, inRange } = useMemo(() => {
    const all = [...clip.edl_versions[0].edl.segments, ...segs]
    const range = [Math.min(...all.map((s) => s.start)), Math.max(...all.map((s) => s.end))]
    return { range, inRange: words.filter((w) => w.start >= range[0] - 0.01 && w.end <= range[1] + 0.01) }
  }, [clip.edl_versions, segs, words])

  const isKept = (w) => segs.some((s) => (w.start + w.end) / 2 >= s.start && (w.start + w.end) / 2 <= s.end)
  const keptStarts = inRange.filter(isKept).map((w) => w.start)
  const span = range[1] - range[0] || 1
  const pct = (t) => `${((t - range[0]) / span) * 100}%`

  const toggle = (w) => onKeep(isKept(w) ? keptStarts.filter((t) => t !== w.start) : [...keptStarts, w.start])
  const cutSegment = (s) => onKeep(keptStarts.filter((t) => t < s.start || t > s.end))

  return (
    <section aria-labelledby="edit-heading">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <SectionTitle id="edit-heading">Edit</SectionTitle>
          <p className="mt-2 text-base text-charcoal">Click a word to cut it from the video. Click a struck-out word to bring it back.</p>
        </div>
        <button onClick={onUndo} disabled={busy || clip.edl_versions.length < 2} className={btn.outlineSm}>
          <ArrowCounterClockwise size={16} /> Undo
        </button>
      </div>

      <div className="mt-5">
        <div className="relative h-10 rounded-md bg-bone bg-[repeating-linear-gradient(135deg,var(--color-stone)_0_1px,transparent_1px_7px)]">
          {segs.map((s, i) => (
            <button
              key={i}
              onClick={() => cutSegment(s)}
              disabled={busy || segs.length < 2}
              title={`Cut segment ${i + 1} (${formatTime(s.start)} to ${formatTime(s.end)})`}
              aria-label={`Cut segment ${i + 1}, ${formatTime(s.start)} to ${formatTime(s.end)}`}
              style={{ left: pct(s.start), width: `calc(${pct(s.end)} - ${pct(s.start)} - 2px)` }}
              className="group absolute inset-y-0 rounded-xs bg-dark transition-colors hover:bg-danger focus-ring disabled:cursor-default disabled:hover:bg-dark"
            >
              <span className="sr-only">Cut</span>
            </button>
          ))}
        </div>
        <div className="mt-2 flex justify-between gap-4 text-sm text-mute">
          <span className="font-mono">{formatTime(range[0])}</span>
          <span>{segs.length} segments kept. Hover one and click to cut it.</span>
          <span className="font-mono">{formatTime(range[1])}</span>
        </div>
      </div>

      <p className={`mt-6 rounded-md border border-hairline bg-card p-6 text-lg leading-loose ${busy ? 'opacity-60' : ''}`}>
        {inRange.map((w) => {
          const kept = isKept(w)
          return (
            <button
              key={w.start}
              onClick={() => toggle(w)}
              disabled={busy}
              aria-pressed={!kept}
              title={`${kept ? 'Cut' : 'Restore'} "${w.w}" (${w.start.toFixed(2)}s)`}
              className={`rounded px-0.5 transition-colors focus-ring ${
                kept ? 'hover:bg-danger/10 hover:line-through' : 'text-stone line-through decoration-danger/60 hover:bg-success/15 hover:text-ink hover:no-underline'
              }`}
            >
              {w.w}
            </button>
          )
        })}
      </p>
    </section>
  )
}
