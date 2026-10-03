import { useEffect, useMemo, useRef, useState } from 'react'
import { Play, Stop } from '@phosphor-icons/react'
import { useEdlPlayer } from '../lib/useEdlPlayer'

// Explicit widths: the frame's contents are all absolutely positioned, so it has no intrinsic size
// and would collapse to 0 inside auto-sized grid columns.
const FRAME = { '9:16': 'aspect-[9/16] w-[300px] max-w-full', '1:1': 'aspect-square w-[420px] max-w-full', '16:9': 'aspect-video w-[560px] max-w-full' }

/** Last point at or before t (crop_track is sampled at ~5 fps). */
function cropAt(track, t) {
  let x = track[0]?.x_center ?? 0.5
  for (const p of track) {
    if (p.t > t) break
    x = p.x_center
  }
  return x
}

/**
 * Plays an EDL in the browser the way the renderer will draw it: segment jumps, crop following
 * crop_track, zoom punches, captions and the hook overlay. No render needed.
 */
export default function EdlPreview({ edl, src, srcAspect, label }) {
  const [media, setMedia] = useState(null)
  const player = useEdlPlayer(media)
  const frame = useRef(null)
  const layer = useRef(null)
  const [shown, setShown] = useState({ caption: null, hook: null })
  const segs = edl.segments
  const offsets = useMemo(() => segs.reduce((acc, s, i) => [...acc, i ? acc[i - 1] + segs[i - 1].end - segs[i - 1].start : 0], []), [segs])
  const playing = player.playing

  useEffect(() => {
    if (!media || !frame.current) return
    let raf
    const draw = () => {
      const i = playing ? playing.seg : 0
      const t = playing ? offsets[i] + Math.max(0, media.currentTime - segs[i].start) : 0
      const W = frame.current.clientWidth
      const H = frame.current.clientHeight
      if (edl.aspect_ratio === '16:9') {
        media.style.width = `${W}px`
        media.style.transform = 'none'
      } else {
        const vw = H * srcAspect
        media.style.width = `${vw}px`
        const tx = Math.min(0, Math.max(W - vw, W / 2 - cropAt(edl.crop_track, t) * vw))
        media.style.transform = `translateX(${tx}px)`
      }
      const zoom = edl.zooms.find((z) => t >= z.start && t < z.end)
      layer.current.style.transform = `scale(${zoom ? zoom.scale : 1})`
      const caption = edl.captions.find((c) => t >= c.start && t < c.end) ?? null
      const hook = edl.overlays.find((o) => o.text && t >= o.start && t < o.end) ?? null
      setShown((prev) => (prev.caption === caption && prev.hook === hook ? prev : { caption, hook }))
      raf = requestAnimationFrame(draw)
    }
    draw()
    return () => cancelAnimationFrame(raf)
  }, [media, playing, edl, segs, offsets, srcAspect])

  const clean = edl.caption_style === 'clean_bottom'
  return (
    <div>
      <div ref={frame} className={`relative overflow-hidden rounded-md bg-dark [container-type:size] ${FRAME[edl.aspect_ratio]}`}>
        <div ref={layer} className="absolute inset-0 origin-center transition-transform duration-150">
          <video
            ref={setMedia}
            src={src}
            preload="auto"
            playsInline
            onLoadedMetadata={(e) => { e.currentTarget.currentTime = segs[0]?.start ?? 0 }}
            className="absolute top-0 left-0 h-full max-w-none"
          />
        </div>
        {shown.hook && (
          <p className="absolute inset-x-[6%] top-[9%] text-center">
            <span className="box-decoration-clone bg-dark/80 px-[0.3em] py-[0.1em] leading-snug font-bold text-white" style={{ fontSize: '7cqmin' }}>
              {shown.hook.text}
            </span>
          </p>
        )}
        {shown.caption && (
          <p
            className={`absolute inset-x-[6%] text-center leading-tight font-bold [paint-order:stroke_fill] ${clean ? 'bottom-[6%]' : 'bottom-[20%]'} ${shown.caption.style === 'emphasis' ? 'text-[#F9A516]' : 'text-white'}`}
            style={{ fontSize: clean ? '3.2cqh' : '4.5cqh', WebkitTextStroke: `${clean ? 0.25 : 0.4}cqh #000` }}
          >
            {shown.caption.text}
          </p>
        )}
        <button
          onClick={() => (playing ? player.stop() : player.play(label, segs))}
          aria-label={playing ? `Stop ${label} preview` : `Play ${label} preview`}
          className="absolute bottom-3 left-3 inline-flex size-10 items-center justify-center rounded-full bg-deep/75 text-on-dark transition-colors hover:bg-deep focus-ring"
        >
          {playing ? <Stop size={18} weight="fill" /> : <Play size={18} weight="fill" />}
        </button>
      </div>
    </div>
  )
}
