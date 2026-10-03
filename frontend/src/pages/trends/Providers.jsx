import { useCallback, useEffect, useState } from 'react'
import { ArrowsClockwise } from '@phosphor-icons/react'
import { DetailHeader } from '../../components/Page'
import { badge, btn, card, errorText, skeleton } from '../../components/ui'
import { errorMessage } from '../../api/client'
import { getProviders } from '../../api/trendshort'

const STATUS = {
  available: badge.success, rate_limited: badge.dark, missing_key: badge.tag,
  not_configured: badge.tag, unreachable: badge.danger, missing: badge.danger,
}
const KIND = { llm: 'Writing (LLM)', tts: 'Voice', captions: 'Captions', footage: 'Footage', trends: 'Trends', publish: 'Publishing', media: 'Rendering' }

export default function Providers() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const load = useCallback(() => {
    setData(null)
    setError('')
    getProviders().then(setData).catch((e) => setError(errorMessage(e, 'Could not check providers.')))
  }, [])
  useEffect(load, [load])
  const groups = {}
  for (const p of data?.providers || []) (groups[p.kind] ||= []).push(p)

  return (
    <div className="max-w-3xl">
      <DetailHeader
        back="/trends"
        backLabel="Trend to Short"
        title="Providers"
        meta="Every service is free-tier. Missing ones are skipped and the next one in line takes over."
        aside={<button onClick={load} className={btn.outlineSm}><ArrowsClockwise size={16} /> Check again</button>}
      />
      <div className="mt-10">
        {error && <p role="alert" className={errorText}>{error}</p>}
        {!data && !error && <div className={`h-64 ${skeleton}`} />}
        {data?.mock_mode && <p className="mb-6"><span className={badge.dark}>Mock mode: the pipeline uses demo assets and makes no API calls</span></p>}
        {Object.entries(groups).map(([kind, rows]) => (
          <section key={kind} className="mb-8">
            <h2 className="heading-sm">{KIND[kind] || kind}</h2>
            <ul className={`${card} mt-3 divide-y divide-hairline`}>
              {rows.map((p) => (
                <li key={p.name} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3 text-sm">
                  <span className="w-36 font-mono">{p.name}</span>
                  <span className={STATUS[p.status] || badge.tag}>{p.status.replace('_', ' ')}</span>
                  <span className="min-w-0 flex-1 text-charcoal">{p.detail}</span>
                  {!p.in_chain && <span className="text-xs text-mute">not in active chain</span>}
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  )
}
