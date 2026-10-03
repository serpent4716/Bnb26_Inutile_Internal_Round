export function formatTime(seconds) {
  if (seconds == null) return ''
  const s = Math.floor(seconds)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

/** API datetimes are UTC; values read back from Mongo arrive without a zone suffix. */
export function parseDate(s) {
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? s : `${s}Z`)
}
