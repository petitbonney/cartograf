<script lang="ts">
  import AdoptionBars from '../components/AdoptionBars.svelte'
  import SegmentedBar from '../components/SegmentedBar.svelte'
  import { plural } from '../lib/format'
  import { HEALTH, HEALTH_ORDER, type Model } from '../lib/model'
  import { href } from '../lib/router.svelte'

  let { model }: { model: Model } = $props()

  const healthColor = { current: 'var(--good)', behind: 'var(--warning)', unresolved: 'var(--critical)', unknown: 'var(--muted)' }
</script>

<div class="page">
  <div class="page-head">
    <div>
      <h1>Frameworks</h1>
      <p>{plural(model.frameworks.length, 'framework')}, by number of repositories using them.</p>
    </div>
  </div>

  {#if model.frameworks.length === 0}
    <div class="card empty">No framework in this file.</div>
  {/if}

  <div class="grid cols-2">
    {#each model.frameworks as fw (fw.path)}
      <section class="card">
        <header>
          <div>
            <h2><a href={href(['frameworks', fw.path])}>{fw.name}</a></h2>
            <span class="muted">{fw.group}</span>
          </div>
          <div class="row">
            {#if fw.latest}
              <span class="pill" title={fw.fw.latest_tag ? 'latest release tag' : 'default branch version (no release tag)'}>
                latest <code>{fw.latest}</code>{fw.fw.latest_tag ? '' : ' · branch'}
              </span>
            {/if}
          </div>
        </header>
        <p class="secondary meta">
          {plural(fw.users.length, 'repository', 'repositories')} ·
          {plural(fw.fw.artifacts?.length ?? 0, 'artifact')}
          {#if fw.linksTo.length}
            · uses {#each fw.linksTo as l, i (l)}{i ? ', ' : ''}<a href={href(['frameworks', l])}>{l.split('/').pop()}</a>{/each}
          {/if}
        </p>
        <SegmentedBar
          label="{fw.name} users by version health"
          parts={HEALTH_ORDER.map((h) => ({ key: h, label: HEALTH[h].label, value: fw.healthCounts[h], color: healthColor[h] }))}
        />
        <h3 class="sub">Versions in use</h3>
        <AdoptionBars adoption={fw.adoption} latest={fw.latest} />
      </section>
    {/each}
  </div>
</div>

<style>
  .meta {
    margin: -4px 0 14px;
  }
  .sub {
    margin: 18px 0 8px;
    color: var(--ink-2);
    font-weight: 500;
  }
</style>
