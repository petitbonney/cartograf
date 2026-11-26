// Derived, read-only views over a Cartography file. Built once per loaded file.

import type { Cartography, Framework, FrameworkLink, Repo, ReviewItem } from './types'

// -- link health ------------------------------------------------------------------

/** How a link compares to the framework's latest version. */
export type Health = 'current' | 'behind' | 'unresolved' | 'unknown'

export const HEALTH: Record<Health, { label: string; icon: string; rank: number; hint: string }> = {
  current: { label: 'Up to date', icon: '✓', rank: 0, hint: 'uses the framework’s latest version' },
  unknown: { label: 'Not comparable', icon: '?', rank: 1, hint: 'version range, or versions that cannot be ordered' },
  behind: { label: 'Behind', icon: '↓', rank: 2, hint: 'older than the framework’s latest version' },
  unresolved: { label: 'Unresolved', icon: '!', rank: 3, hint: 'the version could not be determined' },
}
export const HEALTH_ORDER: Health[] = ['current', 'behind', 'unresolved', 'unknown']

export function linkHealth(l: FrameworkLink): Health {
  if (l.status === 'unresolved' || l.resolved == null) return 'unresolved'
  if (l.behind === true) return 'behind'
  if (l.behind === false) return 'current'
  return 'unknown'
}

export function worstHealth(hs: Iterable<Health>): Health | null {
  let worst: Health | null = null
  for (const h of hs) if (worst === null || HEALTH[h].rank > HEALTH[worst].rank) worst = h
  return worst
}

// -- versions ---------------------------------------------------------------------

/** Rough Maven-like ordering, only used to sort versions for display. */
export function compareVersions(a: string, b: string): number {
  const pa = a.split(/[.\-+_]/)
  const pb = b.split(/[.\-+_]/)
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const x = pa[i]
    const y = pb[i]
    if (x === undefined) return /^\d/.test(y) ? -1 : 1 // 1.0 < 1.0.1, 1.0-SNAPSHOT < 1.0
    if (y === undefined) return /^\d/.test(x) ? 1 : -1
    const nx = /^\d+$/.test(x) ? Number(x) : NaN
    const ny = /^\d+$/.test(y) ? Number(y) : NaN
    if (!Number.isNaN(nx) && !Number.isNaN(ny)) {
      if (nx !== ny) return nx < ny ? -1 : 1
    } else if (Number.isNaN(nx) !== Number.isNaN(ny)) {
      return Number.isNaN(nx) ? -1 : 1 // qualifiers sort before numbers
    } else if (x !== y) {
      return x.toLowerCase() < y.toLowerCase() ? -1 : 1
    }
  }
  return 0
}

// -- repo x framework usage ------------------------------------------------------

export interface BranchUse {
  branch: string
  isDefault: boolean
  versions: string[]
  health: Health
  links: FrameworkLink[]
}

/** How one repo uses one framework: on its primary branch, plus the other branches. */
export interface UseCell extends BranchUse {
  repo: string
  framework: string
  others: BranchUse[]
  /** another branch uses different versions than the primary one */
  disagrees: boolean
}

export interface RepoRow {
  path: string
  group: string
  name: string
  repo: Repo
  kind: string
  gone: boolean
  defaultBranch: string | null
  branchNames: string[]
  lastCommit: string | null
  webUrl: string | null
  cells: UseCell[]
  /** worst health over the primary branch of every framework used */
  health: Health | null
  review: ReviewItem[]
}

export interface Adoption {
  version: string
  health: Health
  repos: string[]
}

export interface FrameworkRow {
  path: string
  name: string
  group: string
  fw: Framework
  latest: string | null
  webUrl: string | null
  /** active repos that use this framework, one cell each */
  users: UseCell[]
  adoption: Adoption[]
  healthCounts: Record<Health, number>
  linksTo: string[]
  linkedFrom: string[]
}

export interface ReviewGroup {
  type: string
  items: ReviewItem[]
}

export interface Model {
  data: Cartography
  repos: RepoRow[]
  repoByPath: Map<string, RepoRow>
  frameworks: FrameworkRow[]
  frameworkByPath: Map<string, FrameworkRow>
  groups: string[]
  reviewGroups: ReviewGroup[]
  totals: {
    active: number
    gone: number
    byKind: Record<string, number>
    usingFrameworks: number
    behindRepos: number
    unresolvedRepos: number
    reviewItems: number
  }
}

export const KIND_ORDER = ['framework', 'linked', 'adhoc', 'non-maven', 'unknown', 'gone'] as const

export const KIND_INFO: Record<string, { label: string; hint: string }> = {
  framework: { label: 'Framework', hint: 'repo name ends with the framework suffix' },
  linked: { label: 'Linked', hint: 'Maven repo that uses at least one framework' },
  adhoc: { label: 'Ad hoc', hint: 'Maven repo that uses no framework' },
  'non-maven': { label: 'Non-Maven', hint: 'no pom.xml on the selected branches' },
  unknown: { label: 'Unknown', hint: 'could not be read yet: the GitLab API failed and there are no earlier facts' },
  gone: { label: 'Gone', hint: 'no longer visible to the token' },
}

/** Strip the " (gone #123)" disambiguation the tool adds to a reused path. */
export function displayPath(path: string): string {
  return path.replace(/ \(gone #\d+\)$/, '')
}

export function groupOf(path: string): string {
  const p = displayPath(path)
  const i = p.lastIndexOf('/')
  return i < 0 ? '' : p.slice(0, i)
}

export function nameOf(path: string): string {
  const p = displayPath(path)
  return p.slice(p.lastIndexOf('/') + 1)
}

function uniqueSorted(vs: Iterable<string>): string[] {
  return [...new Set(vs)].sort(compareVersions)
}

function branchUse(branch: string, isDefault: boolean, links: FrameworkLink[]): BranchUse {
  return {
    branch,
    isDefault,
    links,
    versions: uniqueSorted(links.flatMap((l) => (l.resolved == null ? [] : [l.resolved]))),
    health: worstHealth(links.map(linkHealth)) ?? 'unknown',
  }
}

function sortedBranchNames(repo: Repo): string[] {
  const branches = repo.branches ?? {}
  return Object.keys(branches).sort((a, b) => {
    const da = branches[a].default ? 0 : 1
    const db = branches[b].default ? 0 : 1
    return da - db || a.localeCompare(b)
  })
}

function buildCells(path: string, repo: Repo): UseCell[] {
  const perFw = new Map<string, BranchUse[]>()
  for (const name of sortedBranchNames(repo)) {
    const b = repo.branches![name]
    const byFw = new Map<string, FrameworkLink[]>()
    for (const l of b.framework_links ?? []) {
      if (!byFw.has(l.framework)) byFw.set(l.framework, [])
      byFw.get(l.framework)!.push(l)
    }
    for (const [fw, links] of byFw) {
      if (!perFw.has(fw)) perFw.set(fw, [])
      perFw.get(fw)!.push(branchUse(name, !!b.default, links))
    }
  }
  return [...perFw.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([framework, uses]) => {
      const [primary, ...others] = uses // default branch first when it has links
      const key = (u: BranchUse) => `${u.versions.join(',')}|${u.health === 'unresolved'}`
      return {
        ...primary,
        repo: path,
        framework,
        others,
        disagrees: others.some((o) => key(o) !== key(primary)),
      }
    })
}

// -- review -----------------------------------------------------------------------

export const REVIEW_INFO: Record<string, { title: string; description: string }> = {
  unresolved_parent: {
    title: 'Unresolved parent',
    description:
      'Parent pom not in the crawl (e.g. a corporate or Spring parent in Nexus). Check this first: a recurring corporate parent shows up here.',
  },
  parent_version_not_in_crawl: {
    title: 'Parent version not in crawl',
    description:
      'The parent is crawled, but not at that version (typically an older framework version). Versions managed by it stay unresolved.',
  },
  inventory_error: {
    title: 'Branch listing error',
    description: 'GitLab could not list the branches. The branches and facts of the previous run are kept. Retried on the next run.',
  },
  fetch_error: {
    title: 'Fetch error',
    description:
      'GitLab API failure while reading a branch. The facts of the last commit that was read, if any, are kept. Retried on the next run.',
  },
  pom_error: { title: 'Pom error', description: 'Unparsable or empty pom.xml.' },
  unresolved_version: { title: 'Unresolved version', description: 'A framework link whose version could not be determined.' },
  range_version: { title: 'Version range', description: 'A framework link declared with a version range.' },
  snapshot_version: { title: 'Snapshot version', description: 'A framework link on a -SNAPSHOT version.' },
  branch_disagreement: {
    title: 'Branch disagreement',
    description: 'The default branch and the recent branch use different framework versions.',
  },
  weak_signal: {
    title: 'Weak signal',
    description:
      'The suffix appears in coordinates or URLs that match no known framework: a framework outside the crawl, or naming drift.',
  },
  artifact_collision: { title: 'Artifact collision', description: 'The same artifact is published by two frameworks.' },
  framework_without_pom: { title: 'Framework without pom', description: 'A framework repo has no pom.xml.' },
}

const REVIEW_ORDER = Object.keys(REVIEW_INFO)

export function reviewTitle(type: string): string {
  return REVIEW_INFO[type]?.title ?? type.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase())
}

/** Locator strings look like `group/repo@branch:path/to/pom.xml`. */
export function parseLocator(s: string): { repo: string; branch: string; pom: string } | null {
  const at = s.indexOf('@')
  if (at < 0) return null
  const colon = s.indexOf(':', at)
  if (colon < 0) return null
  return { repo: s.slice(0, at), branch: s.slice(at + 1, colon), pom: s.slice(colon + 1) }
}

/** Every repo a review item is about. */
export function reviewRepos(item: ReviewItem): string[] {
  const out = new Set<string>()
  if (typeof item.repo === 'string') out.add(item.repo)
  if (Array.isArray(item.poms)) {
    for (const p of item.poms) {
      const loc = typeof p === 'string' ? parseLocator(p) : null
      if (loc) out.add(loc.repo)
    }
  }
  return [...out]
}

// -- GitLab links -----------------------------------------------------------------

/**
 * The URL itself if it is http(s), else null. Links are built from file contents,
 * and a crafted file must not be able to inject a `javascript:` link.
 */
export function safeUrl(url: unknown): string | null {
  if (typeof url !== 'string') return null
  try {
    const u = new URL(url)
    return u.protocol === 'https:' || u.protocol === 'http:' ? url : null
  } catch {
    return null
  }
}

export function repoWebUrl(data: Cartography, path: string, repo?: Repo): string | null {
  const own = safeUrl(repo?.web_url)
  if (own) return own
  const base = safeUrl(data.meta.gitlab_url)
  return base ? `${base.replace(/\/$/, '')}/${displayPath(path)}` : null
}

export function treeUrl(base: string | null, ref: string): string | null {
  return base ? `${base}/-/tree/${encodeURI(ref)}` : null
}

export function blobUrl(base: string | null, ref: string, file: string): string | null {
  return base ? `${base}/-/blob/${encodeURI(ref)}/${encodeURI(file)}` : null
}

// -- the model --------------------------------------------------------------------

export function buildModel(data: Cartography): Model {
  const reviewByRepo = new Map<string, ReviewItem[]>()
  for (const item of data.review) {
    for (const r of reviewRepos(item)) {
      if (!reviewByRepo.has(r)) reviewByRepo.set(r, [])
      reviewByRepo.get(r)!.push(item)
    }
  }

  const repos: RepoRow[] = Object.entries(data.repos)
    .map(([path, repo]) => {
      const gone = repo.status === 'gone' || repo.kind === 'gone'
      const branchNames = sortedBranchNames(repo)
      const commits = branchNames.map((b) => repo.branches![b].committed_at).filter((d): d is string => !!d)
      const cells = gone ? [] : buildCells(path, repo)
      return {
        path,
        group: groupOf(path),
        name: nameOf(path),
        repo,
        kind: gone ? 'gone' : (repo.kind ?? 'unknown'),
        gone,
        defaultBranch: repo.default_branch ?? branchNames.find((b) => repo.branches![b].default) ?? null,
        branchNames,
        lastCommit: commits.length ? commits.reduce((a, b) => (Date.parse(a) >= Date.parse(b) ? a : b)) : null,
        webUrl: repoWebUrl(data, path, repo),
        cells,
        health: worstHealth(cells.map((c) => c.health)),
        review: reviewByRepo.get(path) ?? [],
      }
    })
    .sort((a, b) => a.path.localeCompare(b.path))
  const repoByPath = new Map(repos.map((r) => [r.path, r]))

  const linkedFrom = new Map<string, string[]>()
  for (const [path, fw] of Object.entries(data.frameworks)) {
    for (const target of fw.links_to ?? []) {
      if (!linkedFrom.has(target)) linkedFrom.set(target, [])
      linkedFrom.get(target)!.push(path)
    }
  }

  const frameworks: FrameworkRow[] = Object.entries(data.frameworks)
    .map(([path, fw]) => {
      const users = repos.flatMap((r) => r.cells.filter((c) => c.framework === path))
      const buckets = new Map<string, { health: Health[]; repos: Set<string> }>()
      for (const cell of users) {
        for (const l of cell.links) {
          const v = l.resolved ?? 'unresolved'
          if (!buckets.has(v)) buckets.set(v, { health: [], repos: new Set() })
          const bucket = buckets.get(v)!
          bucket.health.push(linkHealth(l))
          bucket.repos.add(cell.repo)
        }
      }
      const adoption = [...buckets.entries()]
        .map(([version, b]) => ({ version, health: worstHealth(b.health)!, repos: [...b.repos].sort() }))
        .sort((a, b) =>
          a.version === 'unresolved' ? 1 : b.version === 'unresolved' ? -1 : compareVersions(b.version, a.version),
        )
      const healthCounts: Record<Health, number> = { current: 0, behind: 0, unresolved: 0, unknown: 0 }
      for (const c of users) healthCounts[c.health]++
      return {
        path,
        name: nameOf(path),
        group: groupOf(path),
        fw,
        latest: fw.latest ?? null,
        webUrl: repoWebUrl(data, path, data.repos[path]),
        users,
        adoption,
        healthCounts,
        linksTo: fw.links_to ?? [],
        linkedFrom: (linkedFrom.get(path) ?? []).sort(),
      }
    })
    .sort((a, b) => b.users.length - a.users.length || a.path.localeCompare(b.path))

  const byType = new Map<string, ReviewItem[]>()
  for (const item of data.review) {
    if (!byType.has(item.type)) byType.set(item.type, [])
    byType.get(item.type)!.push(item)
  }
  const rank = (t: string) => (REVIEW_ORDER.includes(t) ? REVIEW_ORDER.indexOf(t) : REVIEW_ORDER.length)
  const reviewGroups = [...byType.entries()]
    .map(([type, items]) => ({ type, items }))
    .sort((a, b) => rank(a.type) - rank(b.type) || a.type.localeCompare(b.type))

  const byKind: Record<string, number> = {}
  for (const r of repos) byKind[r.kind] = (byKind[r.kind] ?? 0) + 1
  const active = repos.filter((r) => !r.gone)

  return {
    data,
    repos,
    repoByPath,
    frameworks,
    frameworkByPath: new Map(frameworks.map((f) => [f.path, f])),
    groups: [...new Set(repos.map((r) => r.group))].sort(),
    reviewGroups,
    totals: {
      active: active.length,
      gone: repos.length - active.length,
      byKind,
      usingFrameworks: active.filter((r) => r.cells.length > 0 && r.kind !== 'framework').length,
      behindRepos: active.filter((r) => r.cells.some((c) => c.health === 'behind')).length,
      unresolvedRepos: active.filter((r) => r.cells.some((c) => c.health === 'unresolved')).length,
      reviewItems: data.review.length,
    },
  }
}

// -- filtering --------------------------------------------------------------------

export interface RepoFilter {
  q?: string
  group?: string
  kind?: string
  framework?: string
  health?: string
}

export function filterRepos(rows: RepoRow[], f: RepoFilter): RepoRow[] {
  const q = f.q?.trim().toLowerCase()
  return rows.filter((r) => {
    if (q && !r.path.toLowerCase().includes(q)) return false
    if (f.group && r.group !== f.group && !r.group.startsWith(f.group + '/')) return false
    if (f.kind && r.kind !== f.kind) return false
    const cells = f.framework ? r.cells.filter((c) => c.framework === f.framework) : r.cells
    if (f.framework && cells.length === 0) return false
    if (f.health && !cells.some((c) => c.health === f.health)) return false
    return true
  })
}
