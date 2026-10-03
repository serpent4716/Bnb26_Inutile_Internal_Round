import { useEffect, useState } from 'react'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

// Chart tokens (DESIGN.md is light-only). Single-series marks are charcoal: DESIGN.md forbids orange on large
// surfaces and any second hue. Dataviz validator on the white card: lightness band PASS, contrast >= 3:1 PASS;
// chroma floor deliberately waived (it guards categorical hue identity; these charts have one series).
const VIZ = { series: '#575757', grid: '#ebe8e1', axis: '#8d8d8d', ink: '#575757', ring: '#ffffff' }

function useReducedMotion() {
  const query = '(prefers-reduced-motion: reduce)'
  const [match, setMatch] = useState(() => matchMedia(query).matches)
  useEffect(() => {
    const m = matchMedia(query)
    const onChange = (e) => setMatch(e.matches)
    m.addEventListener('change', onChange)
    return () => m.removeEventListener('change', onChange)
  }, [])
  return match
}

function useViz() {
  return { ...VIZ, animate: !useReducedMotion() }
}

export const compact = (n) => Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 }).format(n)
export const percent = (n, digits = 0) => `${(n * 100).toFixed(digits)}%`

function Tip({ active, payload, label, format, name }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-md border border-hairline-strong bg-card px-3 py-2 text-xs">
      <p className="font-semibold text-ink">{label}</p>
      <p className="mt-0.5 text-charcoal">
        {name}: <span className="font-mono font-semibold text-ink">{format(payload[0].value)}</span>
      </p>
    </div>
  )
}

/** Plain table of the same rows: the accessible view of every chart. */
function TableView({ rows, label, name, format }) {
  return (
    <details className="mt-3 text-sm">
      <summary className="w-fit cursor-pointer rounded-full font-semibold text-charcoal hover:text-ink focus-ring">View as table</summary>
      <table className="mt-2 w-full text-left">
        <thead className="text-mute">
          <tr><th className="py-1 font-medium">{label}</th><th className="py-1 text-right font-medium">{name}</th></tr>
        </thead>
        <tbody className="font-mono text-xs">
          {rows.map((r) => (
            <tr key={r.label} className="border-t border-hairline">
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
    <section className={`rounded-md border border-hairline bg-card p-6 ${className}`}>
      <h3 className="heading-sm">{title}</h3>
      {subtitle && <p className="mt-1 text-sm text-charcoal">{subtitle}</p>}
      <div className="mt-5">{children}</div>
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
