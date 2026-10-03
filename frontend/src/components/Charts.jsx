import { useEffect, useState } from 'react'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

// Chart tokens per mode. Series orange validated (dataviz validator) against zinc-50 / zinc-950 surfaces.
const LIGHT = { series: '#eb6834', grid: '#e4e4e7', axis: '#71717a', ink: '#52525b', ring: '#fafafa' }
const DARK = { series: '#d95926', grid: '#27272a', axis: '#71717a', ink: '#a1a1aa', ring: '#09090b' }

function useMedia(query) {
  const [match, setMatch] = useState(() => matchMedia(query).matches)
  useEffect(() => {
    const m = matchMedia(query)
    const onChange = (e) => setMatch(e.matches)
    m.addEventListener('change', onChange)
    return () => m.removeEventListener('change', onChange)
  }, [query])
  return match
}

function useViz() {
  const dark = useMedia('(prefers-color-scheme: dark)')
  const reduced = useMedia('(prefers-reduced-motion: reduce)')
  return { ...(dark ? DARK : LIGHT), animate: !reduced }
}

export const compact = (n) => Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 }).format(n)
export const percent = (n, digits = 0) => `${(n * 100).toFixed(digits)}%`

function Tip({ active, payload, label, format, name }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-md border border-zinc-200 bg-white px-3 py-2 text-xs shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <p className="font-medium text-zinc-900 dark:text-zinc-100">{label}</p>
      <p className="mt-0.5 text-zinc-600 dark:text-zinc-400">
        {name}: <span className="font-medium text-zinc-900 tabular-nums dark:text-zinc-100">{format(payload[0].value)}</span>
      </p>
    </div>
  )
}

/** Plain table of the same rows: the accessible view of every chart. */
function TableView({ rows, label, name, format }) {
  return (
    <details className="mt-2 text-xs">
      <summary className="cursor-pointer text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100">View as table</summary>
      <table className="mt-2 w-full text-left">
        <thead className="text-zinc-500 dark:text-zinc-400">
          <tr><th className="py-1 font-medium">{label}</th><th className="py-1 text-right font-medium">{name}</th></tr>
        </thead>
        <tbody className="tabular-nums">
          {rows.map((r) => (
            <tr key={r.label} className="border-t border-zinc-200 dark:border-zinc-800">
              <td className="py-1">{r.label}</td><td className="py-1 text-right">{format(r.value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  )
}

export function ChartCard({ title, subtitle, children, className = '' }) {
  return (
    <section className={`rounded-lg border border-zinc-200 p-5 dark:border-zinc-800 ${className}`}>
      <h3 className="text-sm font-medium">{title}</h3>
      {subtitle && <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">{subtitle}</p>}
      <div className="mt-4">{children}</div>
    </section>
  )
}

/** Single-series horizontal bars, value at each tip (few categories). rows: [{label, value}] */
export function HBars({ rows, name, format = compact, labelWidth = 92, tipWidth = 52 }) {
  const t = useViz()
  return (
    <>
      <ResponsiveContainer width="100%" height={rows.length * 38 + 8}>
        <BarChart data={rows} layout="vertical" margin={{ top: 0, right: tipWidth, bottom: 0, left: 0 }} barCategoryGap={8}>
          <CartesianGrid horizontal={false} stroke={t.grid} />
          <XAxis type="number" hide domain={[0, 'dataMax']} />
          <YAxis type="category" dataKey="label" width={labelWidth} tickLine={false} axisLine={false} tick={{ fill: t.ink, fontSize: 12 }} />
          <Tooltip cursor={{ fill: t.grid, opacity: 0.5 }} content={<Tip format={format} name={name} />} />
          <Bar dataKey="value" name={name} fill={t.series} radius={[0, 4, 4, 0]} maxBarSize={24} isAnimationActive={t.animate}>
            <LabelList dataKey="value" position="right" formatter={format} fill={t.ink} fontSize={12} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <TableView rows={rows} label="" name={name} format={format} />
    </>
  )
}

/** Single-series columns; only the peak gets a direct label. */
export function Columns({ rows, name, format = compact, height = 200 }) {
  const t = useViz()
  const peak = Math.max(...rows.map((r) => r.value))
  return (
    <>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={rows} margin={{ top: 20, right: 4, bottom: 0, left: 0 }} barCategoryGap="30%">
          <CartesianGrid vertical={false} stroke={t.grid} />
          <XAxis dataKey="label" tickLine={false} axisLine={{ stroke: t.grid }} tick={{ fill: t.ink, fontSize: 12 }} />
          <YAxis width={40} tickLine={false} axisLine={false} tick={{ fill: t.axis, fontSize: 11 }} tickFormatter={compact} />
          <Tooltip cursor={{ fill: t.grid, opacity: 0.5 }} content={<Tip format={format} name={name} />} />
          <Bar dataKey="value" name={name} fill={t.series} radius={[4, 4, 0, 0]} maxBarSize={24} isAnimationActive={t.animate}>
            <LabelList
              dataKey="value"
              content={({ x, y, width, value }) =>
                value === peak ? <text x={x + width / 2} y={y - 6} textAnchor="middle" fill={t.ink} fontSize={12}>{format(value)}</text> : null}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <TableView rows={rows} label="" name={name} format={format} />
    </>
  )
}

/** Single-series trend: 2px line, ~10% wash, crosshair tooltip, ringed hover dot. */
export function Trend({ rows, name, format = compact, height = 200 }) {
  const t = useViz()
  return (
    <>
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke={t.grid} />
          <XAxis dataKey="label" tickLine={false} axisLine={{ stroke: t.grid }} tick={{ fill: t.axis, fontSize: 11 }} minTickGap={24} />
          <YAxis width={40} tickLine={false} axisLine={false} tick={{ fill: t.axis, fontSize: 11 }} tickFormatter={compact} />
          <Tooltip cursor={{ stroke: t.axis, strokeWidth: 1 }} content={<Tip format={format} name={name} />} />
          <Area
            type="monotone" dataKey="value" name={name} stroke={t.series} strokeWidth={2} fill={t.series} fillOpacity={0.1}
            dot={false} activeDot={{ r: 5, fill: t.series, stroke: t.ring, strokeWidth: 2 }} isAnimationActive={t.animate}
          />
        </AreaChart>
      </ResponsiveContainer>
      <TableView rows={rows} label="" name={name} format={format} />
    </>
  )
}
