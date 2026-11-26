<script lang="ts">
  import { parseLocator, reviewTitle } from '../lib/model'
  import { href } from '../lib/router.svelte'
  import type { ReviewItem } from '../lib/types'

  let { item, showType = false }: { item: ReviewItem; showType?: boolean } = $props()

  // Known keys first, in a useful reading order; anything else after.
  const ORDER = ['repo', 'branch', 'framework', 'artifact', 'parent', 'pom', 'link_type', 'declared', 'resolved',
    'versions', 'available', 'frameworks', 'count', 'poms', 'facts_sha', 'detail']
  const LABELS: Record<string, string> = {
    link_type: 'Link type',
    poms: 'Poms',
    available: 'Available versions',
    facts_sha: 'Facts from commit',
  }
  const entries = $derived(
    Object.entries(item)
      .filter(([k, v]) => k !== 'type' && v !== null && v !== undefined)
      .sort(([a], [b]) => (ORDER.indexOf(a) + 1 || 99) - (ORDER.indexOf(b) + 1 || 99)),
  )
  const label = (k: string) => LABELS[k] ?? k.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase())
  const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)
</script>

{#snippet locator(s: string)}
  {@const loc = parseLocator(s)}
  {#if loc}
    <a href={href(['repos', loc.repo])}>{loc.repo}</a><span class="muted">@{loc.branch}:</span><code>{loc.pom}</code>
  {:else}
    <code>{s}</code>
  {/if}
{/snippet}

<article class="item">
  {#if showType}<h3>{reviewTitle(item.type)}</h3>{/if}
  <dl class="facts">
    {#each entries as [k, v] (k)}
      <dt>{label(k)}</dt>
      <dd>
        {#if k === 'repo' && typeof v === 'string'}
          <a href={href(['repos', v])}>{v}</a>
        {:else if (k === 'framework' && typeof v === 'string')}
          <a href={href(['frameworks', v])}>{v}</a>
        {:else if k === 'poms' && Array.isArray(v)}
          <ul class="plain">
            {#each v as p, i (i)}<li>{@render locator(String(p))}</li>{/each}
          </ul>
        {:else if Array.isArray(v)}
          {#each v as x, i (i)}{i ? ', ' : ''}<code>{String(x)}</code>{/each}
        {:else if isRecord(v)}
          {#each Object.entries(v) as [b, vs] (b)}
            <div><span class="secondary">{b}:</span> <code>{Array.isArray(vs) ? vs.join(', ') : String(vs)}</code></div>
          {/each}
        {:else if k === 'detail' || k === 'count'}
          {String(v)}
        {:else}
          <code>{String(v)}</code>
        {/if}
      </dd>
    {/each}
  </dl>
</article>

<style>
  .item {
    padding: 12px 0;
    border-bottom: 1px solid var(--grid);
  }
  .item:last-child {
    border-bottom: 0;
  }
  h3 {
    margin-bottom: 6px;
  }
  .facts {
    font-size: 13px;
  }
</style>
