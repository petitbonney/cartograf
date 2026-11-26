import { buildModel, type Model } from './model'
import { parseCartography } from './parse'

/** Where the page looks for published data, next to index.html. */
export const PUBLISHED_FILES = ['cartography.yaml', 'cartography.json']
export const SAMPLE_FILE = 'sample.yaml'

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

  /** Try the published files quietly. Missing files are expected, not an error. */
  async autoload() {
    this.loading = true
    try {
      for (const f of PUBLISHED_FILES) {
        let text: string
        try {
          const res = await fetch(`./${f}`, { cache: 'no-cache' })
          if (!res.ok) continue
          text = await res.text()
        } catch {
          continue // network error: try the next one
        }
        if (text.trimStart().startsWith('<')) continue // a dev server's SPA fallback page
        try {
          this.use(text, f, f)
        } catch (err) {
          this.error = (err as Error).message // the file is there but broken: say so
        }
        return
      }
    } finally {
      this.loading = false
    }
  }

  close() {
    this.model = null
    this.source = null
    this.error = null
  }
}

export const store = new DataStore()
