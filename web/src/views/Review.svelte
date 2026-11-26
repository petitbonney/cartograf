<script lang="ts">
  import ReviewItemCard from '../components/ReviewItemCard.svelte'
  import { fmtNum } from '../lib/format'
  import { REVIEW_INFO, reviewTitle, type Model } from '../lib/model'
  import { href, router } from '../lib/router.svelte'

  let { model }: { model: Model } = $props()

  const type = $derived(router.param('type'))
  const q = $derived(router.param('q').trim().toLowerCase())
  const groups = $derived(
    model.reviewGroups
      .filter((g) => !type || g.type === type)
      .map((g) => ({
        ...g,
        items: q ? g.items.filter((i) => JSON.stringify(i).toLowerCase().includes(q)) : g.items,
      }))
      .filter((g) => g.items.length > 0),
  )
  const shown = $derived(groups.reduce((n, g) => n + g.items.length, 0))
</script>

<div class="page">
  <div class="page-head">
    <div>
      <h1>Review queue</h1>
      <p>Items the analysis could not settle on its own. Start with unresolved parents: one fix there often resolves many links.</p>
    </div>
  </div>

  {#if model.reviewGroups.length === 0}
    <div class="card empty">Nothing flagged in this run.</div>
  {:else}
    <div class="layout">
      <nav class="types" aria-label="Review types">
        <a href={href(['review'], { q: router.param('q') })} aria-current={!type ? 'page' : undefined}>
          <span>All</span><span class="num">{fmtNum(model.totals.reviewItems)}</span>
        </a>
        {#each model.reviewGroups as g (g.type)}
          <a href={href(['review'], { type: g.type, q: router.param('q') })} aria-current={type === g.type ? 'page' : undefined}>
            <span>{reviewTitle(g.type)}</span><span class="num">{fmtNum(g.items.length)}</span>
          </a>
        {/each}
      </nav>

      <div class="stack">
        <div class="filters">
          <input
            type="search"
            placeholder="Filter by repo, artifact, text…"
            aria-label="Filter review items"
            value={router.param('q')}
            oninput={(e) => router.setQuery({ q: e.currentTarget.value })}
          />
          <span class="secondary">{fmtNum(shown)} items</span>
        </div>

        {#each groups as g (g.type)}
          <section class="card">
            <header>
              <h2>{reviewTitle(g.type)} <span class="muted">· {g.items.length}</span></h2>
            </header>
            {#if REVIEW_INFO[g.type]}<p class="desc">{REVIEW_INFO[g.type].description}</p>{/if}
            {#each g.items as item, i (i)}
              <ReviewItemCard {item} />
            {/each}
          </section>
        {:else}
          <div class="card empty">No item matches.</div>
        {/each}
      </div>
    </div>
  {/if}
</div>

<style>
  .layout {
    display: grid;
    grid-template-columns: 240px 1fr;
    gap: 24px;
    align-items: start;
  }
  @media (max-width: 800px) {
    .layout {
      grid-template-columns: 1fr;
    }
  }
  .types {
    position: sticky;
    top: 72px;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .types a {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    padding: 6px 10px;
    border-radius: 6px;
    color: var(--ink-2);
  }
  .types a:hover {
    background: var(--hover);
    text-decoration: none;
    color: var(--ink);
  }
  .types a[aria-current='page'] {
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--ink);
    font-weight: 500;
  }
  .stack .filters {
    margin-bottom: 0;
  }
  .desc {
    margin: -4px 0 4px;
    color: var(--ink-2);
  }
</style>
