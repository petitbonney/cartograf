<script lang="ts">
  import AdoptionBars from '../components/AdoptionBars.svelte'
  import HealthBadge from '../components/HealthBadge.svelte'
  import VersionChip from '../components/VersionChip.svelte'
  import { plural, shortSha } from '../lib/format'
  import { HEALTH, HEALTH_ORDER, treeUrl, type Model } from '../lib/model'
  import { href, router } from '../lib/router.svelte'

  let { model, path }: { model: Model; path: string } = $props()

  const fw = $derived(model.frameworkByPath.get(path))
  const health = $derived(router.param('health'))
  const users = $derived(
    (fw?.users ?? [])
      .filter((u) => !health || u.health === health)
      .sort((a, b) => HEALTH[b.health].rank - HEALTH[a.health].rank || a.repo.localeCompare(b.repo)),
  )
</script>

<div class="page">
  {#if !fw}
    <div class="card empty">
      <p>No framework <code>{path}</code> in this file.</p>
      <a href="#/frameworks">All frameworks</a>
    </div>
  {:else}
    <div class="page-head">
      <div>
        <p class="crumbs"><a href="#/frameworks">Frameworks</a> / {fw.group}</p>
        <h1>{fw.name}</h1>
      </div>
      <div class="row">
        <a class="btn" href={href(['repos', fw.path])}>Repository details</a>
        {#if fw.webUrl}<a class="btn" href={fw.webUrl} target="_blank" rel="noreferrer">Open in GitLab ↗</a>{/if}
      </div>
    </div>

    <div class="grid cols-3 top">
      <section class="card">
        <h2>Versions</h2>
        <dl class="facts">
          <dt>Latest</dt>
          <dd><code>{fw.latest ?? '—'}</code></dd>
          <dt>Latest tag</dt>
          <dd>{#if fw.fw.latest_tag}<code>{fw.fw.latest_tag}</code>{:else}<span class="muted">none: default branch version is used</span>{/if}</dd>
          {#each Object.entries(fw.fw.branches ?? {}) as [b, info] (b)}
            <dt>{b}</dt>
            <dd>
              <code>{info.version ?? 'unknown'}</code>
              {#if info.sha}<a class="muted mono" href={treeUrl(fw.webUrl, info.sha)} target="_blank" rel="noreferrer">{shortSha(info.sha)}</a>{/if}
            </dd>
          {/each}
          <dt>Status</dt>
          <dd>{fw.fw.status ?? 'active'}</dd>
        </dl>
      </section>

      <section class="card">
        <h2>Artifacts</h2>
        <ul class="plain artifacts">
          {#each fw.fw.artifacts ?? [] as a (a)}<li><code>{a}</code></li>{:else}<li class="muted">No pom found.</li>{/each}
        </ul>
        {#if fw.linksTo.length || fw.linkedFrom.length}
          <h3 class="sub">Other frameworks</h3>
          <dl class="facts">
            {#if fw.linksTo.length}
              <dt>Uses</dt>
              <dd>{#each fw.linksTo as l, i (l)}{i ? ', ' : ''}<a href={href(['frameworks', l])}>{l}</a>{/each}</dd>
            {/if}
            {#if fw.linkedFrom.length}
              <dt>Used by</dt>
              <dd>{#each fw.linkedFrom as l, i (l)}{i ? ', ' : ''}<a href={href(['frameworks', l])}>{l}</a>{/each}</dd>
            {/if}
          </dl>
        {/if}
      </section>

      <section class="card">
        <h2>Versions in use</h2>
        <AdoptionBars adoption={fw.adoption} latest={fw.latest} />
      </section>
    </div>

    <section>
      <div class="filters">
        <h2 class="grow">Used by {plural(fw.users.length, 'repository', 'repositories')}</h2>
        <label class="sr-only" for="health">Health</label>
        <select id="health" value={health} onchange={(e) => router.setQuery({ health: e.currentTarget.value })}>
          <option value="">Any version health</option>
          {#each HEALTH_ORDER as h (h)}<option value={h}>{HEALTH[h].label} ({fw.healthCounts[h]})</option>{/each}
        </select>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Repository</th>
              <th>Version</th>
              <th>Health</th>
              <th>Through</th>
              <th>Other branches</th>
            </tr>
          </thead>
          <tbody>
            {#each users as u (u.repo)}
              <tr>
                <td><a href={href(['repos', u.repo])}>{u.repo}</a></td>
                <td>
                  <VersionChip cell={u} detailed={false} />
                  {#if !u.isDefault}<span class="muted"> on {u.branch}</span>{/if}
                </td>
                <td><HealthBadge health={u.health} /></td>
                <td class="secondary">
                  {#each u.links as l, i (i)}
                    <div>
                      {l.type === 'inherited' ? `inherited ${l.inherited_type}` : l.type}
                      <code>{l.artifact.split(':').pop()}</code>
                    </div>
                  {/each}
                </td>
                <td>
                  {#each u.others as o (o.branch)}
                    <VersionChip cell={o} prefix={o.branch} detailed={false} />
                  {:else}
                    <span class="muted">—</span>
                  {/each}
                </td>
              </tr>
            {:else}
              <tr><td colspan="5" class="empty">No repository matches.</td></tr>
            {/each}
          </tbody>
        </table>
      </div>
    </section>
  {/if}
</div>

<style>
  .crumbs {
    margin: 0 0 4px !important;
    font-size: 13px;
  }
  .top {
    margin-bottom: 24px;
  }
  .artifacts li {
    padding: 2px 0;
  }
  .sub {
    margin: 16px 0 8px;
    color: var(--ink-2);
    font-weight: 500;
  }
  .grow {
    flex: 1;
  }
</style>
