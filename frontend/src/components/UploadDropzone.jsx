import { useRef, useState } from 'react'
import { UploadSimple } from '@phosphor-icons/react'

export default function UploadDropzone({ onFiles, uploading }) {
  const input = useRef(null)
  const [over, setOver] = useState(false)

  const drop = (e) => {
    e.preventDefault()
    setOver(false)
    if (e.dataTransfer.files.length) onFiles([...e.dataTransfer.files])
  }

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setOver(true) }}
      onDragLeave={() => setOver(false)}
      onDrop={drop}
      className={`rounded-lg border border-dashed px-6 py-10 text-center transition-colors ${
        over ? 'border-orange-500 bg-orange-500/5' : 'border-zinc-300 dark:border-zinc-700'
      }`}
    >
      <UploadSimple size={28} className="mx-auto text-zinc-400 dark:text-zinc-500" />
      {uploading ? (
        <p className="mt-3 text-sm">
          Uploading <span className="font-medium">{uploading.name}</span>
          <span className="ml-2 font-mono text-zinc-500 tabular-nums">{Math.round(uploading.pct * 100)}%</span>
        </p>
      ) : (
        <>
          <p className="mt-3 text-sm">
            Drop footage here or{' '}
            <button
              type="button"
              onClick={() => input.current.click()}
              className="font-medium text-orange-600 underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-orange-500 dark:text-orange-400"
            >
              browse files
            </button>
          </p>
          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">Video, audio or images. Videos are transcribed automatically.</p>
        </>
      )}
      <input
        ref={input}
        type="file"
        multiple
        accept="video/*,audio/*,image/*"
        className="hidden"
        onChange={(e) => { onFiles([...e.target.files]); e.target.value = '' }}
      />
    </div>
  )
}
