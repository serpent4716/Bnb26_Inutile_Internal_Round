import { Link } from 'react-router'
import { ArrowLeft } from '@phosphor-icons/react'

/** Secondary pages open on cream with a display-xl title (DESIGN.md: "secondary pages open with cream + display-xl"). */
export function Page({ title, description, actions, children }) {
  return (
    <div>
      <header className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <h1 className="display-xl">{title}</h1>
          {description && <p className="mt-4 max-w-[60ch] text-lg leading-relaxed text-body">{description}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </header>
      <div className="mt-12">{children}</div>
    </div>
  )
}

/** Detail pages: back link + display-lg title (titles here are user content and can run long). */
export function DetailHeader({ back, backLabel, title, meta, aside }) {
  return (
    <header>
      <Link to={back} className="inline-flex items-center gap-1.5 rounded-full text-sm font-semibold text-charcoal hover:text-ink focus-ring">
        <ArrowLeft size={16} /> {backLabel}
      </Link>
      <div className="mt-5 flex flex-wrap items-end justify-between gap-6">
        <div className="min-w-0">
          <h1 className="display-lg break-words">{title}</h1>
          {meta && <div className="mt-4 text-base text-charcoal">{meta}</div>}
        </div>
        {aside}
      </div>
    </header>
  )
}

export function SectionTitle({ id, children, sub }) {
  return (
    <div>
      <h2 id={id} className="heading-md">{children}</h2>
      {sub && <p className="mt-1 text-sm text-charcoal">{sub}</p>}
    </div>
  )
}

export function EmptyState({ icon: Icon, title, children }) {
  return (
    <div className="flex flex-col items-center rounded-lg bg-bone px-6 py-16 text-center">
      <Icon size={32} className="text-charcoal" />
      <p className="mt-4 font-display text-2xl font-semibold tracking-tight">{title}</p>
      <p className="mt-2 max-w-sm text-base text-charcoal">{children}</p>
    </div>
  )
}

/** Stat tile: the value changes family (display face), not weight. */
export function StatTile({ label, value, sub, inverse = false }) {
  return (
    <div>
      <p className={`text-sm ${inverse ? 'text-on-dark-mute' : 'text-charcoal'}`}>{label}</p>
      <p className="mt-2 font-display text-4xl font-bold tracking-tight">{value}</p>
      {sub && <p className={`mt-1 text-sm ${inverse ? 'text-on-dark-mute' : 'text-mute'}`}>{sub}</p>}
    </div>
  )
}
