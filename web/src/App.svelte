<script lang="ts">
  import { onMount } from 'svelte'
  import { router } from './lib/router.svelte'
  import { store } from './lib/store.svelte'
  import Header from './components/Header.svelte'
  import Landing from './components/Landing.svelte'
  import Tooltip from './components/Tooltip.svelte'
  import Overview from './views/Overview.svelte'
  import Frameworks from './views/Frameworks.svelte'
  import FrameworkView from './views/Framework.svelte'
  import Repos from './views/Repos.svelte'
  import RepoView from './views/Repo.svelte'
  import Matrix from './views/Matrix.svelte'
  import Review from './views/Review.svelte'

  onMount(() => {
    store.autoload()
  })

  // Drop a file anywhere on the page to open it.
  let dragDepth = $state(0)
  const hasFiles = (e: DragEvent) => !!e.dataTransfer?.types.includes('Files')

  function onDragEnter(e: DragEvent) {
    if (!hasFiles(e)) return
    e.preventDefault()
    dragDepth++
  }
  function onDragOver(e: DragEvent) {
    if (hasFiles(e)) e.preventDefault()
  }
  function onDragLeave(e: DragEvent) {
    if (hasFiles(e)) dragDepth = Math.max(0, dragDepth - 1)
  }
  function onDrop(e: DragEvent) {
    if (!hasFiles(e)) return
    e.preventDefault()
    dragDepth = 0
    const file = e.dataTransfer?.files[0]
    if (file) store.loadFile(file)
  }

  const title = $derived.by(() => {
    const s = router.section
    const name = router.rest ? router.rest : ''
    const label = { frameworks: 'Frameworks', repos: 'Repositories', matrix: 'Matrix', review: 'Review' }[s] ?? 'Overview'
    return `${name || label} · cartograf`
  })
</script>

<svelte:head><title>{store.model ? title : 'cartograf'}</title></svelte:head>
<svelte:window ondragenter={onDragEnter} ondragover={onDragOver} ondragleave={onDragLeave} ondrop={onDrop} />

<Header />

{#if store.error}
  <div class="page error-row">
    <div class="notice critical row" role="alert">
      <span>{store.error}</span>
      <button class="btn ghost" onclick={() => (store.error = null)}>Dismiss</button>
    </div>
  </div>
{/if}

<main>
  {#if store.model}
    {#key store.model}
      {#if router.section === ''}
        <Overview model={store.model} />
      {:else if router.section === 'frameworks' && router.rest}
        <FrameworkView model={store.model} path={router.rest} />
      {:else if router.section === 'frameworks'}
        <Frameworks model={store.model} />
      {:else if router.section === 'repos' && router.rest}
        <RepoView model={store.model} path={router.rest} />
      {:else if router.section === 'repos'}
        <Repos model={store.model} />
      {:else if router.section === 'matrix'}
        <Matrix model={store.model} />
      {:else if router.section === 'review'}
        <Review model={store.model} />
      {:else}
        <div class="page empty">
          <p>Nothing here. <a href="#/">Back to the overview</a></p>
        </div>
      {/if}
    {/key}
  {:else if store.loading}
    <div class="page empty">Loading…</div>
  {:else}
    <Landing />
  {/if}
</main>

<Tooltip />

{#if dragDepth > 0}
  <div class="drop-overlay" aria-hidden="true">
    <div>Drop a cartograf <code>.yaml</code> or <code>.json</code> file to open it</div>
  </div>
{/if}

<style>
  .error-row {
    padding-bottom: 0;
  }
  .error-row .notice {
    justify-content: space-between;
  }
  .drop-overlay {
    position: fixed;
    inset: 0;
    z-index: 200;
    display: grid;
    place-items: center;
    background: var(--accent-wash);
    backdrop-filter: blur(2px);
    pointer-events: none;
  }
  .drop-overlay > div {
    padding: 24px 32px;
    border: 2px dashed var(--accent);
    border-radius: 12px;
    background: var(--surface);
    font-size: 16px;
  }
</style>
