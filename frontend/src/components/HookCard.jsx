import { useState } from 'react'
import { Check } from '@phosphor-icons/react'

const TYPE_LABEL = { question: 'Question', bold_claim: 'Bold claim', story: 'Story', statistic: 'Statistic', contrarian: 'Contrarian' }

/** One hook variant. Selecting it puts it on screen for the clip's first 2s; the selected one is editable. */
export default function HookCard({ variant, onSelect, onSaveEdit, busy }) {
  const [draft, setDraft] = useState(variant.text)
  const dirty = draft.trim() && draft.trim() !== variant.text

  return (
    <li className={`rounded-lg border p-3 transition ${variant.selected ? 'border-orange-500 bg-orange-500/5' : 'border-zinc-200 dark:border-zinc-800'}`}>
      <div className="flex items-center justify-between gap-3 text-xs">
        <span className="font-medium text-zinc-500 dark:text-zinc-400">{TYPE_LABEL[variant.label] ?? variant.label}</span>
        <span className="font-mono text-zinc-500 tabular-nums dark:text-zinc-400">{variant.score?.toFixed(1)}</span>
      </div>
      {variant.selected ? (
        <div className="mt-2 grid gap-2">
          <label className="sr-only" htmlFor={`hook-${variant.label}`}>Edit hook</label>
          <textarea
            id={`hook-${variant.label}`}
            rows={2}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm font-medium focus:border-orange-500 focus:outline-2 focus:outline-orange-500/30 dark:border-zinc-700 dark:bg-zinc-900"
          />
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center gap-1 text-xs font-medium text-orange-700 dark:text-orange-400">
              <Check size={12} weight="bold" /> On screen for the first 2s
            </span>
            {dirty && (
              <button onClick={() => onSaveEdit(draft.trim())} disabled={busy} className="ml-auto text-xs font-medium text-orange-600 hover:underline disabled:opacity-50 dark:text-orange-400">
                Save edit
              </button>
            )}
          </div>
        </div>
      ) : (
        <button
          onClick={onSelect}
          disabled={busy}
          className="mt-1 w-full text-left text-sm font-medium hover:text-orange-600 focus-visible:outline-2 focus-visible:outline-orange-500 disabled:opacity-50 dark:hover:text-orange-400"
        >
          {variant.text}
        </button>
      )}
    </li>
  )
}
