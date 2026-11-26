const dateFmt = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
const dateTimeFmt = new Intl.DateTimeFormat(undefined, {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})
const numFmt = new Intl.NumberFormat()

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const t = Date.parse(iso)
  return Number.isNaN(t) ? iso : dateFmt.format(t)
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const t = Date.parse(iso)
  return Number.isNaN(t) ? iso : dateTimeFmt.format(t)
}

/** Whole days between two ISO dates (b - a), or null. */
export function daysBetween(a: string | null | undefined, b: string | null | undefined): number | null {
  if (!a || !b) return null
  const d = (Date.parse(b) - Date.parse(a)) / 86_400_000
  return Number.isNaN(d) ? null : Math.floor(d)
}

export function fmtNum(n: number | null | undefined): string {
  return n == null ? '—' : numFmt.format(n)
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${fmtNum(n)} ${n === 1 ? one : many}`
}

export function hostOf(url: string | null | undefined): string {
  if (!url) return ''
  try {
    return new URL(url).host
  } catch {
    return url
  }
}

export function shortSha(sha: string | null | undefined): string {
  return sha ? sha.slice(0, 8) : ''
}
