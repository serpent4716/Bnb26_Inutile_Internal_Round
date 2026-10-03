import { useRef, useState } from 'react'
import { UploadSimple } from '@phosphor-icons/react'
import { btn } from './ui'

/** Bone inset drop area; the upload button is an outline pill (the page keeps its one orange CTA elsewhere). */
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
      className={`flex flex-col items-center rounded-lg border border-dashed px-6 py-10 text-center transition-colors ${
        over ? 'border-hairline-strong bg-card' : 'border-hairline bg-bone'
      }`}
    >
      <UploadSimple size={28} className="text-charcoal" />
      {uploading ? (
        <p className="mt-4 text-base">
          Uploading <span className="font-semibold">{uploading.name}</span>
          <span className="ml-2 font-mono text-charcoal tabular-nums">{Math.round(uploading.pct * 100)}%</span>
        </p>
      ) : (
        <>
          <p className="mt-4 font-display text-2xl font-semibold tracking-tight">Drop footage here</p>
          <p className="mt-1 text-sm text-charcoal">Video, audio or images. Videos are transcribed automatically.</p>
          <button type="button" onClick={() => input.current.click()} className={`${btn.outlineSm} mt-5`}>Browse files</button>
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
