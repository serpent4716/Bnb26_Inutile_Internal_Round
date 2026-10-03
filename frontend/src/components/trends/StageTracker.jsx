import { Check, Warning } from '@phosphor-icons/react'
import { STAGE_NAMES } from '../../api/trendshort'

const ORDER = ['script', 'audio', 'visuals', 'assembly', 'publish']
const STATUS = { pending: 'Waiting', running: 'Working', done: 'Done', stale: 'Out of date', failed: 'Failed' }

/** One tile per pipeline stage (same marker language as JobStepper). Clicking a tile opens that stage. */
export default function StageTracker({ run, selected, onSelect }) {
  return (
    <ol className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5" aria-label="Pipeline stages">
      {ORDER.map((id, i) => {
        const st = run.stages[id] || { status: 'pending' }
        const isSel = selected === id
        const waiting = run.awaiting_approval && run.next_stage === id
        const providers = [...new Set((st.providers || []).map((p) => p.provider))]
        return (
          <li key={id}>
            <button
              onClick={() => onSelect(id)}
              aria-current={isSel ? 'step' : undefined}
              className={`h-full w-full rounded-md px-4 py-3 text-left transition-colors focus-ring ${
                isSel ? 'bg-dark text-on-dark' : 'border border-hairline bg-card hover:bg-bone'
              }`}
            >
              <span className="flex items-center gap-2">
                <span
                  className={`flex size-6 shrink-0 items-center justify-center rounded-full font-mono text-xs ${
                    st.status === 'done' ? (isSel ? 'bg-on-dark text-ink' : 'bg-dark text-on-dark')
                      : st.status === 'failed' ? 'bg-danger text-on-dark'
                        : st.status === 'running' ? `border-2 ${isSel ? 'border-on-dark' : 'border-ink'} motion-safe:animate-pulse`
                          : `border ${isSel ? 'border-divider-dark' : 'border-hairline text-mute'}`
                  }`}
                >
                  {st.status === 'done' ? <Check size={12} weight="bold" /> : st.status === 'failed' ? <Warning size={12} weight="bold" /> : i + 1}
                </span>
                <span className="font-semibold">{STAGE_NAMES[id]}</span>
              </span>
              <span className={`mt-1.5 block text-xs ${isSel ? 'text-on-dark-mute' : 'text-charcoal'}`}>
                {waiting ? 'Ready when you approve' : STATUS[st.status] || st.status}
                {st.status === 'done' && st.duration_ms > 0 && <> · <span className="font-mono">{(st.duration_ms / 1000).toFixed(1)}s</span></>}
                {st.cached && ' · cached'}
              </span>
              {providers.length > 0 && (
                <span className={`mt-0.5 block truncate font-mono text-[11px] ${isSel ? 'text-on-dark-mute' : 'text-mute'}`}>{providers.join(', ')}</span>
              )}
            </button>
          </li>
        )
      })}
    </ol>
  )
}
