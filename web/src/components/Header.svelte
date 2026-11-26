<script lang="ts">
  import { fmtDate } from '../lib/format'
  import { router } from '../lib/router.svelte'
  import { store } from '../lib/store.svelte'

  let input: HTMLInputElement

  const nav = [
    { section: '', label: 'Overview' },
    { section: 'frameworks', label: 'Frameworks' },
    { section: 'repos', label: 'Repositories' },
    { section: 'matrix', label: 'Matrix' },
    { section: 'review', label: 'Review' },
  ]

  function onPick(e: Event) {
    const file = (e.currentTarget as HTMLInputElement).files?.[0]
    if (file) store.loadFile(file)
    ;(e.currentTarget as HTMLInputElement).value = ''
  }
</script>

<header>
  <div class="inner">
    <a class="brand" href="#/">
      <img src="./favicon.svg" alt="" width="22" height="22" />
      cartograf
    </a>
    {#if store.model}
      <nav aria-label="Sections">
        {#each nav as item (item.section)}
          <a href="#/{item.section}" aria-current={router.section === item.section ? 'page' : undefined}>
            {item.label}
            {#if item.section === 'review' && store.model.totals.reviewItems}
              <span class="count">{store.model.totals.reviewItems}</span>
            {/if}
          </a>
        {/each}
      </nav>
    {/if}
    <div class="right">
      {#if store.model}
        <span class="source" title="Loaded file">
          <code>{store.source}</code>
          <span class="muted">· {fmtDate(store.model.data.meta.generated_at)}</span>
        </span>
      {/if}
      <input bind:this={input} type="file" accept=".yaml,.yml,.json" hidden onchange={onPick} />
      <button class="btn" onclick={() => input.click()}>Open file…</button>
    </div>
  </div>
</header>

<style>
  header {
    position: sticky;
    top: 0;
    z-index: 50;
    background: color-mix(in srgb, var(--surface) 88%, transparent);
    backdrop-filter: blur(8px);
    border-bottom: 1px solid var(--border);
  }
  .inner {
    max-width: 1320px;
    margin: 0 auto;
    padding: 0 24px;
    height: 56px;
    display: flex;
    align-items: center;
    gap: 24px;
  }
  .brand {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-weight: 650;
    font-size: 15px;
    color: var(--ink);
    letter-spacing: -0.01em;
  }
  .brand:hover {
    text-decoration: none;
  }
  nav {
    display: flex;
    gap: 2px;
    overflow-x: auto;
  }
  nav a {
    color: var(--ink-2);
    padding: 6px 10px;
    border-radius: 6px;
    white-space: nowrap;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  nav a:hover {
    background: var(--hover);
    color: var(--ink);
    text-decoration: none;
  }
  nav a[aria-current='page'] {
    color: var(--ink);
    background: var(--surface-2);
    font-weight: 500;
  }
  .count {
    font-size: 11.5px;
    line-height: 18px;
    padding: 0 6px;
    border-radius: 999px;
    background: var(--warning-wash);
    color: var(--ink);
  }
  .right {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .source {
    font-size: 12.5px;
    white-space: nowrap;
  }
  @media (max-width: 900px) {
    .source {
      display: none;
    }
  }
</style>
