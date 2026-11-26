<script lang="ts">
  import HealthBadge from '../components/HealthBadge.svelte'
  import VersionChip from '../components/VersionChip.svelte'
  import { fmtNum } from '../lib/format'
  import { filterRepos, HEALTH, HEALTH_ORDER, type Model, type RepoRow } from '../lib/model'
  import { href, router } from '../lib/router.svelte'

  let { model }: { model: Model } = $props()

  const filter = $derived({ q: router.param('q'), group: router.param('group'), health: router.param('health') })
  const rows = $derived(filterRepos(model.repos, filter).filter((r) => r.cells.length > 0))
  const byGroup = $derived.by(() => {
    const m = new Map<string, RepoRow[]>()
    for (const r of rows) m.set(r.group, [...(m.get(r.group) ?? []), r])
    return [...m.entries()].sort(([a], [b]) => a.localeCompare(b))
  })
  const cols = $derived(model.frameworks)
</script>

<div class="page wide">
  <div class="page-head">
    <div>
      <h1>Matrix</h1>
      <p>
        Which version of each framework every repository uses, on its default branch (or its recent branch when only that
        one uses the framework). <span class="nowrap">≠ marks a branch that differs.</span>
      </p>
    </div>
  </div>

  <div class="filters">
    <input
      type="search"
      placeholder="Filter by path…"
      aria-label="Filter by path"
      value={filter.q}
      oninput={(e) => router.setQuery({ q: e.currentTarget.value })}
    />
    <select aria-label="Group" value={filter.group} onchange={(e) => router.setQuery({ group: e.currentTarget.value })}>
      <option value="">All groups</option>
      {#each model.groups as g (g)}<option value={g}>{g}</option>{/each}
    </select>
    <select aria-label="Version health" value={filter.health} onchange={(e) => router.setQuery({ health: e.currentTarget.value })}>
      <option value="">Any version health</option>
      {#each HEALTH_ORDER as h (h)}<option value={h}>{HEALTH[h].label}</option>{/each}
    </select>
    <span class="secondary">{fmtNum(rows.length)} repositories</span>
    <ul class="plain legend" aria-label="Legend">
      {#each HEALTH_ORDER as h (h)}<li><HealthBadge health={h} /></li>{/each}
    </ul>
  </div>

  {#if rows.length === 0}
    <div class="card empty">No repository uses a framework with these filters.</div>
  {:else}
    <div class="table-wrap matrix">
      <table>
        <thead>
          <tr>
            <th class="repo-col">Repository</th>
            {#each cols as c (c.path)}
              <th class="fw-col">
                <a href={href(['frameworks', c.path])} title={c.path}>{c.name}</a>
                <div class="muted latest">{c.latest ? `latest ${c.latest}` : 'no version'}</div>
              </th>
            {/each}
          </tr>
        </thead>
        <tbody>
          {#each byGroup as [group, groupRows] (group)}
            <tr class="group-row">
              <th colspan={cols.length + 1} scope="colgroup">{group || '(no group)'}</th>
            </tr>
            {#each groupRows as r (r.path)}
              <tr>
                <th scope="row" class="repo-col">
                  <a href={href(['repos', r.path])}>{r.name}</a>
                </th>
                {#each cols as c (c.path)}
                  {@const cell = r.cells.find((x) => x.framework === c.path)}
                  <td>
                    {#if cell}
                      <a class="cell" href={href(['repos', r.path])}><VersionChip {cell} /></a>
                    {:else if r.path === c.path}
                      <span class="self" title="the framework itself">◆</span>
                    {/if}
                  </td>
                {/each}
              </tr>
            {/each}
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>

<style>
  .wide {
    max-width: none;
  }
  .legend {
    display: flex;
    gap: 4px 14px;
    flex-wrap: wrap;
    margin-left: auto;
    font-size: 13px;
  }
  .matrix {
    max-height: calc(100vh - 220px);
  }
  .matrix th,
  .matrix td {
    padding: 6px 10px;
    vertical-align: middle;
  }
  .matrix thead th {
    z-index: 3;
  }
  .fw-col {
    min-width: 140px;
  }
  .latest {
    font-weight: 400;
    font-size: 11.5px;
  }
  .repo-col {
    position: sticky;
    left: 0;
    z-index: 2;
    background: var(--surface);
    font-weight: 500;
    color: var(--ink);
    font-size: 13.5px;
    min-width: 180px;
    border-right: 1px solid var(--grid);
  }
  thead .repo-col {
    background: var(--surface-2);
    z-index: 4;
  }
  tbody tr:hover .repo-col {
    background: var(--surface-2);
  }
  .group-row th {
    position: static;
    background: var(--page);
    color: var(--ink-2);
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    padding-top: 14px;
  }
  .cell:hover {
    text-decoration: none;
  }
  .self {
    color: var(--kind-framework);
    font-size: 12px;
  }
</style>
