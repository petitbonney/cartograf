import { describe, expect, it } from 'vitest'
import { safeUrl } from './model'
import { parseCartography } from './parse'
import { href, parseHash } from './router.svelte'
import { dataPath } from './store.svelte'

describe('parseCartography', () => {
  it('reads YAML with quoted versions and dates as strings', () => {
    const d = parseCartography(
      'meta:\n  generated_at: "2026-11-20T08:30:00+00:00"\nrepos:\n  g/a:\n    latest_tag: "3.10"\n',
    )
    expect(d.meta.generated_at).toBe('2026-11-20T08:30:00+00:00')
    expect(d.repos['g/a'].latest_tag).toBe('3.10')
    expect(d.frameworks).toEqual({})
    expect(d.review).toEqual([])
  })

  it('does not turn unquoted timestamps into dates (core schema)', () => {
    const d = parseCartography('meta:\n  generated_at: 2026-11-20\nrepos: {}\n')
    expect(d.meta.generated_at).toBe('2026-11-20')
  })

  it('reads JSON', () => {
    const d = parseCartography('{"meta": {"suffix": "-fw"}, "repos": {}}')
    expect(d.meta.suffix).toBe('-fw')
  })

  it('rejects HTML, empty and foreign files with a clear message', () => {
    expect(() => parseCartography('<!doctype html><html>', 'x.yaml')).toThrow(/HTML page/)
    expect(() => parseCartography('  \n', 'x.yaml')).toThrow(/empty/)
    expect(() => parseCartography('a: 1\n', 'x.yaml')).toThrow(/no "repos" section/)
    expect(() => parseCartography('a: [\n', 'x.yaml')).toThrow(/could not be parsed/)
  })
})

describe('untrusted paths and URLs', () => {
  it('accepts only same-site relative data paths', () => {
    expect(dataPath('cartography.yaml')).toBe('cartography.yaml')
    expect(dataPath('data/c.json')).toBe('data/c.json')
    expect(dataPath(' ')).toBeNull()
    expect(dataPath(null)).toBeNull()
    for (const bad of ['https://evil.test/c.yaml', '//evil.test/c.yaml', '/\\evil.test/c.yaml', 'javascript:alert(1)', 'data:text/plain,x']) {
      expect(dataPath(bad)).toBeNull()
    }
  })

  it('links only to http(s) URLs', () => {
    expect(safeUrl('https://gitlab.example.com/g/r')).toBe('https://gitlab.example.com/g/r')
    expect(safeUrl('javascript:alert(1)')).toBeNull()
    expect(safeUrl('not a url')).toBeNull()
    expect(safeUrl(42)).toBeNull()
  })
})

describe('hash routes', () => {
  it('round-trips repo paths and query', () => {
    const h = href(['repos', 'grp/sub/svc (gone #12)'], { kind: 'linked', q: undefined })
    expect(h).toBe('#/repos/grp/sub/svc%20(gone%20%2312)?kind=linked')
    const { path, query } = parseHash(h)
    expect(path.slice(1).join('/')).toBe('grp/sub/svc (gone #12)')
    expect(query.get('kind')).toBe('linked')
  })

  it('defaults to the root', () => {
    expect(parseHash('').path).toEqual([])
  })
})
