<script lang="ts">
  import KindBadge from '../components/KindBadge.svelte'
  import VersionChip from '../components/VersionChip.svelte'
  import { fmtDate, fmtNum } from '../lib/format'
  import { filterRepos, HEALTH, HEALTH_ORDER, KIND_INFO, KIND_ORDER, nameOf, type Model, type RepoRow } from '../lib/model'
  import { href, router } from '../lib/router.svelte'

  let { model }: { model: Model } = $props()

  const filter = $derived({
    q: router.param('q'),
    group: router.param('group'),
    kind: router.param('kind'),
    framework: router.param('fw'),
    health: router.param('health'),
  })
  const sort = $derived(router.param('sort') || 'name')

  const sorters: Record<string, (a: RepoRow, b: RepoRow) => number> = {
    name: (a, b) => a.path.localeCompare(b.path),
    commit: (a, b) => (b.lastCommit ?? '').localeCompare(a.lastCommit ?? '') || a.path.localeCompare(b.path),
    review: (a, b) => b.review.length - a.review.length || a.path.localeCompare(b.path),
    health: (a, b) =>
      (b.health ? HEALTH[b.health].rank + 1 : 0) - (a.health ? HEALTH[a.health].rank + 1 : 0) || a.path.localeCompare(b.path),
  }
  const rows = $derived(filterRepos(model.repos, filter).sort(sorters[sort] ?? sorters.name))
  const active = $derived(Object.values(filter).some(Boolean))

  // Typing in the search box updates the URL without adding history entries.
  function setQ(e: Event) {
    router.setQuery({ q: (e.currentTarget as HTMLInputElement).value })
  }
</script>

{#snippet sortHeader(key: string, label: string, cls = '')}
  <th class={cls} aria-sort={sort === key ? (key === 'name' ? 'ascending' : 'descending') : undefined}>
    <button class="sort" onclick={() => router.setQuery({ sort: key === 'name' ? undefined : key })}>
      {label}{sort === key ? (key === 'name' ? ' ↑' : ' ↓') : ''}
    </button>
  </th>
{/snippet}

<div class="page">
  <div class="page-head">
    <div>
      <h1>Repositories</h1>
      <p>{fmtNum(rows.length)} of {fmtNum(model.repos.length)} shown</p>
    </div>
  </div>

  <div class="filters">
    <input type="search" placeholder="Filter by path…" aria-label="Filter by path" value={filter.q} oninput={setQ} />
    <select aria-label="Group" value={filter.group} onchange={(e) => router.setQuery({ group: e.currentTarget.value })}>
      <option value="">All groups</option>
      {#each model.groups as g (g)}<option value={g}>{g}</option>{/each}
    </select>
    <select aria-label="Kind" value={filter.kind} onchange={(e) => router.setQuery({ kind: e.currentTarget.value })}>
      <option value="">All kinds</option>
      {#each KIND_ORDER as k (k)}<option value={k}>{KIND_INFO[k].label} ({model.totals.byKind[k] ?? 0})</option>{/each}
    </select>
    <select aria-label="Framework" value={filter.framework} onchange={(e) => router.setQuery({ fw: e.currentTarget.value })}>
      <option value="">Any framework</option>
      {#each model.frameworks as f (f.path)}<option value={f.path}>{f.name}</option>{/each}
    </select>
    <select aria-label="Version health" value={filter.health} onchange={(e) => router.setQuery({ health: e.currentTarget.value })}>
      <option value="">Any version health</option>
      {#each HEALTH_ORDER as h (h)}<option value={h}>{HEALTH[h].label}</option>{/each}
    </select>
    {#if active}
      <a class="btn ghost" href={href(['repos'], { sort: router.param('sort') })}>Clear filters</a>
    {/if}
  </div>

  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          {@render sortHeader('name', 'Repository')}
          <th>Kind</th>
          {@render sortHeader('health', 'Frameworks')}
          {@render sortHeader('commit', 'Last commit')}
          {@render sortHeader('review', 'Review', 'num')}
        </tr>
      </thead>
      <tbody>
        {#each rows as r (r.path)}
          <tr>
            <td>
              <a href={href(['repos', r.path])}><strong>{r.name}</strong></a>
              <div class="muted small">{r.group}</div>
            </td>
            <td><KindBadge kind={r.kind} /></td>
            <td>
              <div class="chips">
                {#each r.cells.filter((c) => !filter.framework || c.framework === filter.framework) as c (c.framework)}
                  <VersionChip cell={c} prefix={nameOf(c.framework)} />
                {:else}
                  <span class="muted">—</span>
                {/each}
              </div>
            </td>
            <td class="nowrap secondary">{fmtDate(r.lastCommit)}</td>
            <td class="num">
              {#if r.review.length}<a class="pill" href={href(['repos', r.path])}>{r.review.length}</a>{:else}<span class="muted">—</span>{/if}
            </td>
          </tr>
        {:else}
          <tr><td colspan="5" class="empty">No repository matches these filters.</td></tr>
        {/each}
      </tbody>
    </table>
  </div>
</div>

<style>
  .small {
    font-size: 12.5px;
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
</style>
