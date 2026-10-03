import { Check, Warning } from '@phosphor-icons/react'

// Jobs report fine-grained `current_step`s; group them into the few stages a creator cares about.
const FLOWS = {
  pipeline: [
    ['Transcribe', ['extracting_keyframes', 'extracting_audio', 'transcribing', 'saving']],
    ['Describe footage', ['tagging', 'indexing']],
    ['Match script', ['aligning']],
    ['Find clips', ['finding_clips']],
    ['Build edits', ['building_edls']],
  ],
  transcription: [
    ['Extract audio', ['extracting_keyframes', 'extracting_audio']],
    ['Transcribe', ['transcribing', 'saving']],
    ['Describe footage', ['tagging']],
    ['Index for search', ['indexing']],
  ],
  adapt: [
    ['Track speaker', ['reframing']],
    ['Write copy', ['writing_copy']],
    ['Build versions', ['building_variants']],
  ],
  render: [
    ['Render', ['rendering']],
    ['Save', ['publishing']],
  ],
}

/** Horizontal stepper for a job: done / current / upcoming, with the job's own progress. */
export default function JobStepper({ job }) {
  const flow = FLOWS[job.type] ?? []
  const done = job.status === 'done'
  const failed = job.status === 'failed'
  const current = flow.findIndex(([, steps]) => steps.includes(job.current_step))
  // A cached run can start mid-flow (e.g. transcript already exists): earlier stages count as done.
  const at = done ? flow.length : Math.max(current, 0)

  return (
    <div aria-live="polite">
      <ol className="flex flex-wrap items-center gap-x-2 gap-y-2 text-sm">
        {flow.map(([label], i) => {
          const state = i < at ? 'done' : i === at && !done ? (failed ? 'failed' : 'current') : 'todo'
          return (
            <li key={label} className="flex items-center gap-2">
              <span
                className={`flex size-7 shrink-0 items-center justify-center rounded-full font-mono text-xs ${
                  state === 'done' ? 'bg-dark text-on-dark'
                    : state === 'current' ? 'border-2 border-ink text-ink'
                      : state === 'failed' ? 'bg-danger text-on-dark'
                        : 'border border-hairline text-mute'
                }`}
              >
                {state === 'done' ? <Check size={12} weight="bold" /> : state === 'failed' ? <Warning size={12} weight="bold" /> : i + 1}
              </span>
              <span className={state === 'todo' ? 'text-mute' : 'font-semibold'}>{label}</span>
              {i < flow.length - 1 && <span aria-hidden className="mx-1 h-px w-6 bg-stone" />}
            </li>
          )
        })}
      </ol>
      {!done && !failed && (
        <div className="mt-4 h-1 w-full max-w-md overflow-hidden rounded-full bg-stone/50" role="progressbar" aria-valuenow={job.progress} aria-valuemin={0} aria-valuemax={100}>
          <div className="h-full rounded-full bg-ink transition-[width] duration-500" style={{ width: `${job.progress}%` }} />
        </div>
      )}
      {failed && <p role="alert" className="mt-2 text-sm text-danger">{job.error}</p>}
    </div>
  )
}
