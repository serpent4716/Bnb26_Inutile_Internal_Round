// Components from DESIGN.md. Interactive elements are pills (rounded-full); content cards are 10px (rounded-md)
// or 16px (rounded-lg); elevation is hairlines and colour-blocking, never shadows on cream.
// Orange (primary) is a stamp: one primary CTA per view. Equal-weight actions use `dark`, lesser ones `outline`.
const base =
  'inline-flex shrink-0 items-center justify-center gap-2 rounded-full font-semibold leading-none whitespace-nowrap transition-colors focus-ring disabled:cursor-not-allowed disabled:opacity-45'
const md = 'h-11 px-6 text-base'
const sm = 'h-9 px-4 text-sm'

export const btn = {
  primary: `${base} ${md} bg-primary text-on-primary hover:bg-primary-deep active:bg-primary-deep`,
  primarySm: `${base} ${sm} bg-primary text-on-primary hover:bg-primary-deep active:bg-primary-deep`,
  dark: `${base} ${md} bg-dark text-on-dark hover:bg-deep`,
  darkSm: `${base} ${sm} bg-dark text-on-dark hover:bg-deep`,
  outline: `${base} ${md} border border-hairline-strong bg-card text-ink hover:bg-bone`,
  outlineSm: `${base} ${sm} border border-hairline-strong bg-card text-ink hover:bg-bone`,
  ghost: `${base} ${sm} bg-transparent text-ink hover:bg-bone`,
  icon: `${base} size-9 border border-hairline bg-card text-ink hover:bg-bone`,
  toggleSm: `${base} ${sm} border`, // caller adds on/off colours
}

// text-input: white pill, hairline, 44px; focus = strong hairline + blue ring
export const field =
  'h-11 rounded-full border border-hairline bg-card px-5 text-base text-ink placeholder:text-ash focus:border-hairline-strong focus-ring'
export const fieldArea =
  'rounded-md border border-hairline bg-card px-4 py-3 text-base leading-relaxed text-ink placeholder:text-ash focus:border-hairline-strong focus-ring'

export const card = 'rounded-md border border-hairline bg-card'          // model-card
export const tile = 'rounded-lg bg-bone'                                  // bone inset group
export const inverse = 'rounded-lg bg-dark text-on-dark'                  // dark inversion (featured)

export const badge = {
  tag: 'inline-flex items-center gap-1 rounded-full border border-hairline bg-canvas px-2.5 py-1 text-xs leading-none text-ink',
  success: 'inline-flex items-center gap-1 rounded-full bg-success px-2.5 py-1 text-xs leading-none text-on-dark',
  dark: 'inline-flex items-center gap-1 rounded-full bg-dark px-2.5 py-1 text-xs leading-none text-on-dark',
  danger: 'inline-flex items-center gap-1 rounded-full border border-danger/40 bg-card px-2.5 py-1 text-xs leading-none text-danger',
}

export const link = 'font-medium text-primary underline-offset-4 hover:underline focus-ring'
export const errorText = 'text-sm text-danger'
export const muted = 'text-mute'
export const skeleton = 'rounded-md bg-bone motion-safe:animate-pulse'
