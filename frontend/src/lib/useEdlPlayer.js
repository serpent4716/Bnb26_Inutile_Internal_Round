import { useCallback, useEffect, useState } from 'react'

/**
 * Previews an EDL on the source <video> by jumping between its segments (no render needed).
 * One player per video: play(key, segments) replaces whatever was playing.
 * `playing` is { key, seg, count } while previewing, else null.
 */
export function useEdlPlayer(media) {
  const [state, setState] = useState(null) // { key, segs, seg }

  useEffect(() => {
    if (!state || !media) return
    const { segs, seg } = state
    let raf
    const tick = () => {
      const t = media.currentTime
      const { start, end } = segs[seg]
      if (t < start - 0.5 || t > end + 0.5) return setState(null) // viewer jumped elsewhere
      if (t >= end) {
        if (seg + 1 < segs.length) {
          media.currentTime = segs[seg + 1].start
          return setState((s) => s && { ...s, seg: seg + 1 })
        }
        media.pause()
        return setState(null)
      }
      raf = requestAnimationFrame(tick) // per-frame check so cuts land on the word boundary
    }
    raf = requestAnimationFrame(tick)
    const stop = () => setState(null)
    media.addEventListener('pause', stop)
    return () => {
      cancelAnimationFrame(raf)
      media.removeEventListener('pause', stop)
    }
  }, [state, media])

  const play = useCallback(
    (key, segs) => {
      if (!media || !segs?.length) return
      media.currentTime = segs[0].start
      media.play()
      setState({ key, segs, seg: 0 })
    },
    [media],
  )
  const stop = useCallback(() => media?.pause(), [media])

  return { playing: state && { key: state.key, seg: state.seg, count: state.segs.length }, play, stop }
}
