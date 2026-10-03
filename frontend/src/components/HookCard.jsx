import { useState } from 'react'
import { Check } from '@phosphor-icons/react'

const TYPE_LABEL = { question: 'Question', bold_claim: 'Bold claim', story: 'Story', statistic: 'Statistic', contrarian: 'Contrarian' }

/** One hook variant. Selecting it puts it on screen for the clip's first 2s; the selected one is editable. */
export default function HookCard({ variant, onSelect, onSaveEdit, busy }) {
  const [draft, setDraft] = useState(variant.text)
  const dirty = draft.trim() && draft.trim() !== variant.text

  return (
    <li className={`rounded-md border p-3 transition ${variant.selected ? 'border-dark bg-dark text-on-dark' : 'border-hairline bg-card'}`}>
      <div className="flex items-center justify-between gap-3 text-xs">
        <span className="font-medium text-mute">{TYPE_LABEL[variant.label] ?? variant.label}</span>
        <span className="font-mono text-mute tabular-nums">{variant.score?.toFixed(1)}</span>
      </div>
      {variant.selected ? (
        <div className="mt-2 grid gap-2">
          <label className="sr-only" htmlFor={`hook-${variant.label}`}>Edit hook</label>
          <textarea
            id={`hook-${variant.label}`}
            rows={2}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="rounded-md border border-divider-dark bg-deep/40 px-3 py-2 text-base font-semibold text-on-dark focus-ring"
          />
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center gap-1 text-xs font-semibold text-on-dark-mute">
              <Check size={12} weight="bold" /> On screen for the first 2s
            </span>
            {dirty && (
              <button onClick={() => onSaveEdit(draft.trim())} disabled={busy} className="ml-auto rounded-full text-xs font-semibold text-on-dark underline underline-offset-4 focus-ring disabled:opacity-50">
                Save edit
              </button>
            )}
          </div>
        </div>
      ) : (
        <button
          onClick={onSelect}
          disabled={busy}
          className="mt-1 w-full rounded-xs text-left text-base font-semibold hover:underline hover:underline-offset-4 focus-ring disabled:opacity-50"
        >
          {variant.text}
        </button>
      )}
    </li>
  )
}
