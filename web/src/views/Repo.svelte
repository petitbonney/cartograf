<script lang="ts">
  import HealthBadge from '../components/HealthBadge.svelte'
  import KindBadge from '../components/KindBadge.svelte'
  import ReviewItemCard from '../components/ReviewItemCard.svelte'
  import VersionChip from '../components/VersionChip.svelte'
  import { fmtDate, fmtDateTime, plural, shortSha } from '../lib/format'
  import { blobUrl, linkHealth, nameOf, treeUrl, type Model } from '../lib/model'
  import { href } from '../lib/router.svelte'
  import type { PomCoords } from '../lib/types'

  let { model, path }: { model: Model; path: string } = $props()

  const row = $derived(model.repoByPath.get(path))
  const isFramework = $derived(model.frameworkByPath.has(path))

  const coords = (c: PomCoords | undefined) =>
    c ? [c.groupId ?? '?', c.artifactId ?? '?', c.version ?? '?'].join(':') : ''
  const linkType = (l: { type: string; inherited_type?: string }) =>
    l.type === 'inherited' ? `inherited ${l.inherited_type ?? ''}` : l.type
</script>

<div class="page">
  {#if !row}
    <div class="card empty">
      <p>No repository <code>{path}</code> in this file.</p>
      <a href="#/repos">All repositories</a>
    </div>
  {:else}
    {@const repo = row.repo}
    <div class="page-head">
      <div>
        <p class="crumbs"><a href="#/repos">Repositories</a> / <a href={href(['repos'], { group: row.group })}>{row.group}</a></p>
        <h1 class="row">{row.name} <KindBadge kind={row.kind} /></h1>
      </div>
      <div class="row">
        {#if isFramework}<a class="btn" href={href(['frameworks', path])}>Framework view</a>{/if}
        {#if row.webUrl}<a class="btn" href={row.webUrl} target="_blank" rel="noreferrer">Open in GitLab ↗</a>{/if}
      </div>
    </div>

    {#if row.gone}
      <p class="notice">
        This repository is no longer visible to the token{repo.gone_since ? ` (since ${fmtDate(repo.gone_since)})` : ''}. Its last known
        facts are kept below.
      </p>
    {/if}
    {#if repo.inventory_error}<p class="notice critical">Inventory error: {repo.inventory_error}</p>{/if}
    {#if repo.empty_repo}<p class="notice">Empty repository: no branch.</p>{/if}

    <div class="grid cols-2 top">
      <section class="card">
        <h2>Summary</h2>
        <dl class="facts">
          <dt>Path</dt><dd><code>{path}</code></dd>
          {#if repo.project_id}<dt>Project ID</dt><dd>{repo.project_id}</dd>{/if}
          <dt>Default branch</dt><dd>{row.defaultBranch ?? '—'}</dd>
          <dt>Branches analysed</dt><dd>{row.branchNames.join(', ') || '—'}</dd>
          <dt>Last commit</dt><dd>{fmtDateTime(row.lastCommit)}</dd>
          {#if repo.latest_tag}<dt>Latest tag</dt><dd><code>{repo.latest_tag}</code></dd>{/if}
          <dt>Frameworks</dt>
          <dd>
            <div class="chips">
              {#each row.cells as c (c.framework)}
                <a href={href(['frameworks', c.framework])}><VersionChip cell={c} prefix={nameOf(c.framework)} /></a>
              {:else}
                <span class="muted">none</span>
              {/each}
            </div>
          </dd>
        </dl>
      </section>

      <section class="card">
        <h2>Needs review</h2>
        {#each row.review as item, i (i)}
          <ReviewItemCard {item} showType />
        {:else}
          <p class="muted">Nothing flagged for this repository.</p>
        {/each}
      </section>
    </div>

    {#each row.branchNames as name (name)}
      {@const b = repo.branches![name]}
      {@const links = b.framework_links ?? []}
      <section class="card branch">
        <header>
          <div class="row">
            <h2>{name}</h2>
            {#if b.default}<span class="pill">default</span>{/if}
            {#if b.kind}<span class="pill">{b.kind}</span>{/if}
          </div>
          <span class="secondary">
            {#if b.sha}<a class="mono" href={treeUrl(row.webUrl, b.sha)} target="_blank" rel="noreferrer">{shortSha(b.sha)}</a> ·{/if}
            {fmtDateTime(b.committed_at)}
          </span>
        </header>

        {#if b.fetch_error}<p class="notice critical">Fetch error: {b.fetch_error}</p>{/if}

        {#if links.length}
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Framework</th>
                  <th>Artifact</th>
                  <th>Type</th>
                  <th>Pom</th>
                  <th>Declared</th>
                  <th>Resolved</th>
                  <th>Latest</th>
                  <th>Health</th>
                </tr>
              </thead>
              <tbody>
                {#each links as l, i (i)}
                  <tr>
                    <td><a href={href(['frameworks', l.framework])}>{nameOf(l.framework)}</a></td>
                    <td><code>{l.artifact}</code></td>
                    <td class="nowrap">{linkType(l)}</td>
                    <td>
                      {#if b.sha && row.webUrl}
                        <a href={blobUrl(row.webUrl, b.sha, l.pom)} target="_blank" rel="noreferrer"><code>{l.pom}</code></a>
                      {:else}<code>{l.pom}</code>{/if}
                    </td>
                    <td><code>{l.declared ?? '—'}</code></td>
                    <td><code>{l.resolved ?? '—'}</code> <span class="muted small">{l.status}</span></td>
                    <td><code>{l.framework_latest ?? '—'}</code></td>
                    <td><HealthBadge health={linkHealth(l)} /></td>
                  </tr>
                  {#if l.via || l.managed_by || l.reason}
                    <tr class="note">
                      <td></td>
                      <td colspan="7" class="secondary small">
                        {#if l.via}via <code>{l.via}</code>{/if}
                        {#if l.managed_by}managed by <code>{l.managed_by}</code>{/if}
                        {#if l.reason}<span class="reason">{l.reason}</span>{/if}
                      </td>
                    </tr>
                  {/if}
                {/each}
              </tbody>
            </table>
          </div>
        {:else if b.maven}
          <p class="muted">No framework link on this branch.</p>
        {:else if !b.fetch_error}
          <p class="muted">No pom.xml on this branch.</p>
        {/if}

        {#if b.poms?.length}
          <details>
            <summary>{plural(b.poms.length, 'pom')} parsed</summary>
            <ul class="plain poms">
              {#each b.poms as p (p.path)}
                <li>
                  <code>{p.path}</code>
                  {#if p.error}
                    <span class="err">{p.error}</span>
                  {:else}
                    <span class="secondary">{coords(p)}</span>
                    {#if p.packaging && p.packaging !== 'jar'}<span class="pill">{p.packaging}</span>{/if}
                    {#if p.parent}<span class="muted">parent {coords(p.parent)}</span>{/if}
                  {/if}
                </li>
              {/each}
            </ul>
          </details>
        {/if}
      </section>
    {/each}
  {/if}
</div>

<style>
  .crumbs {
    margin: 0 0 4px !important;
    font-size: 13px;
  }
  h1.row {
    gap: 12px;
  }
  .top {
    margin-bottom: 16px;
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .chips a:hover {
    text-decoration: none;
  }
  .branch {
    margin-bottom: 16px;
  }
  .branch .notice {
    margin: 0 0 12px;
  }
  tr.note td {
    border-top: 0;
    padding-top: 0;
  }
  tbody tr:has(+ tr.note) td {
    border-bottom: 0;
  }
  .reason {
    color: var(--critical-ink);
  }
  .small {
    font-size: 12px;
  }
  details {
    margin-top: 12px;
  }
  .poms {
    margin-top: 8px;
    font-size: 13px;
  }
  .poms li {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    align-items: baseline;
    padding: 3px 0;
  }
  .err {
    color: var(--critical-ink);
  }
</style>
