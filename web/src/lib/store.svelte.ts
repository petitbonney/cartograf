import { buildModel, type Model } from './model'
import { parseCartography } from './parse'

/**
 * config.json ships with every build and says which data file, if any, the page
 * opens on load: `{"data": "cartography.yaml"}`. The default is `{"data": null}`,
 * so a site without published data makes no request that can 404.
 */
export const CONFIG_FILE = 'config.json'
export const SAMPLE_FILE = 'sample.yaml'

/**
 * Only same-site relative paths are accepted (from config.json or `?data=`):
 * a link must not make the page load a file from somewhere else.
 */
export function dataPath(value: unknown): string | null {
  if (typeof value !== 'string' || !value.trim()) return null
  const v = value.trim()
  if (/^[a-z][a-z0-9+.-]*:/i.test(v) || v.startsWith('//') || v.includes('\\')) return null
  return v
}

class DataStore {
  // $state.raw: the parsed file can be large; it is replaced wholesale, never mutated.
  model = $state.raw<Model | null>(null)
  source = $state<string | null>(null)
  error = $state<string | null>(null)
  loading = $state(false)

  private use(text: string, name: string, source: string) {
    const data = parseCartography(text, name)
    this.model = buildModel(data)
    this.source = source
    this.error = null
  }

  async loadFile(file: File) {
    this.loading = true
    try {
      this.use(await file.text(), file.name, file.name)
    } catch (err) {
      this.error = (err as Error).message
    } finally {
      this.loading = false
    }
  }

  async loadUrl(url: string, label = url) {
    this.loading = true
    try {
      const res = await fetch(url, { cache: 'no-cache' })
      if (!res.ok) throw new Error(`${label}: HTTP ${res.status}`)
      this.use(await res.text(), label, label)
    } catch (err) {
      this.error = (err as Error).message
    } finally {
      this.loading = false
    }
  }

  /** Open the data file named by `?data=` or by config.json, if any. */
  async autoload() {
    const fromQuery = new URLSearchParams(window.location.search).get('data')
    if (fromQuery !== null) {
      const path = dataPath(fromQuery)
      if (path) return this.loadUrl(path, path.split('/').pop())
      this.error = '?data= must be a relative path on this site'
      return
    }
    this.loading = true
    let path: string | null = null
    try {
      const res = await fetch(`./${CONFIG_FILE}`, { cache: 'no-cache' })
      if (res.ok) path = dataPath(((await res.json()) as { data?: unknown }).data)
    } catch {
      // no usable config.json (or a dev server's HTML fallback): nothing to open
    } finally {
      this.loading = false
    }
    if (path) await this.loadUrl(path, path.split('/').pop())
  }

  close() {
    this.model = null
    this.source = null
    this.error = null
  }
}

export const store = new DataStore()
