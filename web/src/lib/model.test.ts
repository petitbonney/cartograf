/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import {
  buildModel,
  compareVersions,
  filterRepos,
  linkHealth,
  parseLocator,
  reviewRepos,
  worstHealth,
} from './model'
import { parseCartography } from './parse'
import type { FrameworkLink } from './types'

const sample = readFileSync(new URL('../../public/sample.yaml', import.meta.url), 'utf8')
const model = buildModel(parseCartography(sample, 'sample.yaml'))

function link(over: Partial<FrameworkLink>): FrameworkLink {
  return { framework: 'f', artifact: 'g:a', type: 'dependency', pom: 'pom.xml', declared: '1', resolved: '1', status: 'resolved', ...over }
}

describe('linkHealth', () => {
  it('maps status and behind', () => {
    expect(linkHealth(link({ behind: false }))).toBe('current')
    expect(linkHealth(link({ behind: true }))).toBe('behind')
    expect(linkHealth(link({ status: 'range', resolved: '[1,2)' }))).toBe('unknown')
    expect(linkHealth(link({ status: 'unresolved', resolved: null }))).toBe('unresolved')
  })

  it('worstHealth ranks unresolved over behind over unknown over current', () => {
    expect(worstHealth(['current', 'unknown'])).toBe('unknown')
    expect(worstHealth(['current', 'behind', 'unknown'])).toBe('behind')
    expect(worstHealth(['behind', 'unresolved'])).toBe('unresolved')
    expect(worstHealth([])).toBeNull()
  })
})

describe('compareVersions', () => {
  it('orders numerically, with qualifiers before the release', () => {
    const vs = ['3.10.0', '3.5.0', '3.6.0-SNAPSHOT', '3.6.0', '3.5']
    expect([...vs].sort(compareVersions)).toEqual(['3.5', '3.5.0', '3.6.0-SNAPSHOT', '3.6.0', '3.10.0'])
  })
})

describe('locators', () => {
  it('parses repo@branch:pom', () => {
    expect(parseLocator('grp/svc@feature/x:mod/pom.xml')).toEqual({ repo: 'grp/svc', branch: 'feature/x', pom: 'mod/pom.xml' })
    expect(parseLocator('nope')).toBeNull()
  })

  it('finds every repo a review item is about', () => {
    expect(reviewRepos({ type: 't', repo: 'a/b' })).toEqual(['a/b'])
    expect(reviewRepos({ type: 't', poms: ['a/b@main:pom.xml', 'c/d@dev:x/pom.xml', 'a/b@dev:pom.xml'] })).toEqual(['a/b', 'c/d'])
  })
})

describe('buildModel on the sample', () => {
  it('counts repos like the CLI summary', () => {
    const c = model.data.meta.counts!
    expect(model.totals.active).toBe(c.repos_seen)
    expect(model.totals.gone).toBe(c.gone)
    expect(model.totals.byKind.linked).toBe(c.linked)
    expect(model.totals.byKind.framework).toBe(c.frameworks)
    expect(model.totals.byKind.unknown).toBe(c.unknown)
  })

  it('keeps the links of a repo whose last fetch failed, and marks unread repos unknown', () => {
    const media = model.repoByPath.get('web/media-service')!
    expect(media.kind).toBe('linked')
    expect(media.repo.branches!.main.facts_sha).toBeTruthy()
    expect(media.cells.map((c) => c.framework)).toEqual(['platform/acme-framework'])
    expect(model.repoByPath.get('web/analytics-proxy')!.kind).toBe('unknown')
    expect(model.repoByPath.get('data/warehouse-sync')!.review.map((r) => r.type)).toEqual(['inventory_error'])
  })

  it('keeps versions and dates as strings', () => {
    const fw = model.frameworkByPath.get('platform/acme-framework')!
    expect(fw.latest).toBe('3.5.0')
    expect(typeof model.repoByPath.get('web/search')!.lastCommit).toBe('string')
  })

  it('uses the default branch as primary and flags other branches that disagree', () => {
    const cell = model.repoByPath.get('payments/notifications')!.cells.find((c) => c.framework === 'platform/messaging-framework')!
    expect(cell.branch).toBe('main')
    expect(cell.versions).toEqual(['2.2.1'])
    expect(cell.health).toBe('current')
    expect(cell.others.map((o) => [o.branch, o.versions, o.health])).toEqual([['develop', ['2.1.0'], 'behind']])
    expect(cell.disagrees).toBe(true)
  })

  it('takes the worst health over a repo’s links (inherited links included)', () => {
    const store = model.repoByPath.get('web/storefront')!
    const acme = store.cells.find((c) => c.framework === 'platform/acme-framework')!
    expect(acme.links.map((l) => l.type).sort()).toEqual(['dependency', 'inherited'])
    expect(acme.health).toBe('unresolved')
    expect(store.health).toBe('unresolved')
  })

  it('builds framework adoption, latest first and unresolved last, without gone repos', () => {
    const fw = model.frameworkByPath.get('platform/acme-framework')!
    const versions = fw.adoption.map((a) => a.version)
    expect(versions[0]).toBe('3.5.0')
    expect(versions.at(-1)).toBe('unresolved')
    expect(fw.adoption[0].health).toBe('current')
    expect(fw.users.map((u) => u.repo)).not.toContain('payments/old-gateway')
    expect(fw.linkedFrom).toEqual(['platform/messaging-framework'])
  })

  it('attaches review items to repos, including grouped pom locators', () => {
    expect(model.repoByPath.get('web/gateway')!.review.map((r) => r.type)).toEqual(['unresolved_parent'])
    expect(model.reviewGroups[0].type).toBe('unresolved_parent')
  })

  it('marks gone repos and gives them no usage', () => {
    const gone = model.repoByPath.get('payments/old-gateway')!
    expect(gone.gone).toBe(true)
    expect(gone.cells).toEqual([])
  })
})

describe('filterRepos', () => {
  it('filters by text, group, kind, framework and health', () => {
    const paths = (f: Parameters<typeof filterRepos>[1]) => filterRepos(model.repos, f).map((r) => r.path)
    expect(paths({ q: 'LEDG' })).toEqual(['payments/ledger'])
    expect(paths({ group: 'data', kind: 'non-maven' })).toEqual(['data/notebooks'])
    expect(paths({ framework: 'data/etl-framework', health: 'behind' })).toEqual(['data/warehouse-sync'])
    expect(paths({ kind: 'gone' })).toEqual(['payments/old-gateway'])
  })
})
