// Hash routing: `#/repos/grp/svc?kind=linked`. Hash URLs need no server rewrites,
// so deep links work on GitHub Pages and GitLab Pages as plain static files.

export type Query = Record<string, string | undefined>

export function parseHash(hash: string): { path: string[]; query: URLSearchParams } {
  const raw = hash.replace(/^#/, '') || '/'
  const qi = raw.indexOf('?')
  const p = qi < 0 ? raw : raw.slice(0, qi)
  const q = qi < 0 ? '' : raw.slice(qi + 1)
  return {
    path: p.split('/').filter(Boolean).map((s) => {
      try {
        return decodeURIComponent(s)
      } catch {
        return s
      }
    }),
    query: new URLSearchParams(q),
  }
}

/** Build a hash href. Segments may contain `/` (repo paths): each part is encoded on its own. */
export function href(segments: (string | null | undefined)[], query: Query = {}): string {
  const path = segments
    .filter((s): s is string => !!s)
    .flatMap((s) => s.split('/'))
    .map(encodeURIComponent)
    .join('/')
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(query)) if (v) qs.set(k, v)
  const s = qs.toString()
  return `#/${path}${s ? `?${s}` : ''}`
}

class Router {
  path = $state<string[]>([])
  query = $state(new URLSearchParams())

  constructor() {
    if (typeof window === 'undefined') return
    this.sync()
    window.addEventListener('hashchange', () => {
      this.sync()
      window.scrollTo(0, 0)
    })
  }

  private sync() {
    const { path, query } = parseHash(window.location.hash)
    this.path = path
    this.query = query
  }

  get section(): string {
    return this.path[0] ?? ''
  }

  /** Everything after the section, joined back into a repo/framework path. */
  get rest(): string {
    return this.path.slice(1).join('/')
  }

  param(name: string): string {
    return this.query.get(name) ?? ''
  }

  /** Change query params in place (no new history entry, no scroll). */
  setQuery(updates: Query) {
    const next: Query = Object.fromEntries(this.query.entries())
    Object.assign(next, updates)
    history.replaceState(null, '', href(this.path, next))
    this.sync()
  }
}

export const router = new Router()
