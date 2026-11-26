<script lang="ts">
  import AdoptionBars from '../components/AdoptionBars.svelte'
  import HealthBadge from '../components/HealthBadge.svelte'
  import SegmentedBar from '../components/SegmentedBar.svelte'
  import StatTile from '../components/StatTile.svelte'
  import { fmtDateTime, fmtNum, hostOf, plural } from '../lib/format'
  import { HEALTH, HEALTH_ORDER, KIND_INFO, KIND_ORDER, REVIEW_INFO, reviewTitle, safeUrl, type Model } from '../lib/model'
  import { href } from '../lib/router.svelte'

  let { model }: { model: Model } = $props()

  const meta = $derived(model.data.meta)
  const gitlabUrl = $derived(safeUrl(meta.gitlab_url))
  const run = $derived(meta.last_run)
  const t = $derived(model.totals)

  const kindParts = $derived(
    KIND_ORDER.filter((k) => k !== 'unknown' || t.byKind[k]).map((k) => ({
      key: k,
      label: KIND_INFO[k].label,
      value: t.byKind[k] ?? 0,
      color: `var(--kind-${k})`,
      href: href(['repos'], { kind: k }),
    })),
  )
  const healthColor = { current: 'var(--good)', behind: 'var(--warning)', unresolved: 'var(--critical)', unknown: 'var(--muted)' }
</script>

<div class="page">
  <div class="page-head">
    <div>
      <h1>Overview</h1>
      <p>
        Run of {fmtDateTime(meta.generated_at)}
        {#if gitlabUrl}on <a href={gitlabUrl} target="_blank" rel="noreferrer">{hostOf(gitlabUrl)}</a>{/if}
        {#if meta.token_user}as <strong>{meta.token_user}</strong>{/if}
        {#if meta.suffix}· frameworks end with <code>{meta.suffix}</code>{/if}
      </p>
    </div>
  </div>

  <section class="tiles">
    <StatTile label="Active repositories" value={t.active} sub={t.gone ? `${fmtNum(t.gone)} gone` : ''} href="#/repos" />
    <StatTile label="Frameworks" value={model.frameworks.length} href="#/frameworks" />
    <StatTile label="Using a framework" value={t.usingFrameworks} href={href(['repos'], { kind: 'linked' })} />
    <StatTile label="Behind latest" value={t.behindRepos} sub="repos on an older version" href={href(['repos'], { health: 'behind' })} />
    <StatTile label="Unresolved versions" value={t.unresolvedRepos} sub="repos" href={href(['repos'], { health: 'unresolved' })} />
    <StatTile label="To review" value={t.reviewItems} sub="items" href="#/review" />
  </section>

  <section class="card">
    <header><h2>Repositories by kind</h2><span class="muted">{plural(t.active + t.gone, 'repository', 'repositories')}</span></header>
    <SegmentedBar parts={kindParts} label="Repositories by kind" />
  </section>

  <div class="grid cols-2">
    <section class="card">
      <header>
        <h2>Frameworks</h2>
        <a href="#/frameworks">All frameworks →</a>
      </header>
      {#if model.frameworks.length === 0}
        <p class="muted">No framework found. Check the suffix (<code>{meta.suffix}</code>).</p>
      {:else}
        <ul class="plain fw-list">
          {#each model.frameworks as fw (fw.path)}
            <li>
              <div class="fw-head">
                <a href={href(['frameworks', fw.path])}><strong>{fw.name}</strong></a>
                <span class="muted">{fw.group}</span>
                <span class="right">
                  {#if fw.latest}<span class="pill">latest <code>{fw.latest}</code></span>{/if}
                  <span class="secondary">{plural(fw.users.length, 'user')}</span>
                </span>
              </div>
              <SegmentedBar
                legend={false}
                label="{fw.name} users by version health"
                parts={HEALTH_ORDER.map((h) => ({ key: h, label: HEALTH[h].label, value: fw.healthCounts[h], color: healthColor[h] }))}
              />
            </li>
          {/each}
        </ul>
        <ul class="plain legend">
          {#each HEALTH_ORDER as h (h)}<li><HealthBadge health={h} /></li>{/each}
        </ul>
      {/if}
    </section>

    <section class="card">
      <header>
        <h2>Needs review</h2>
        <a href="#/review">Review queue →</a>
      </header>
      {#if model.reviewGroups.length === 0}
        <p class="muted">Nothing flagged.</p>
      {:else}
        <ul class="plain review-list">
          {#each model.reviewGroups as g (g.type)}
            <li>
              <a href={href(['review'], { type: g.type })}>
                <span class="count num">{g.items.length}</span>
                <span>
                  <strong>{reviewTitle(g.type)}</strong>
                  <span class="desc">{REVIEW_INFO[g.type]?.description ?? ''}</span>
                </span>
              </a>
            </li>
          {/each}
        </ul>
      {/if}
    </section>
  </div>

  {#if model.frameworks[0]}
    <section class="card">
      <header>
        <h2>Versions of {model.frameworks[0].name} in use</h2>
        <span class="muted">most used framework</span>
      </header>
      <AdoptionBars adoption={model.frameworks[0].adoption} latest={model.frameworks[0].latest} />
    </section>
  {/if}

  {#if run}
    <section class="card">
      <h2>Last run</h2>
      {#if run.missing_groups?.length}
        <p class="notice">
          Groups not found or not visible to the token: {#each run.missing_groups as g, i (g)}{i ? ', ' : ''}<code>{g}</code>{/each}
        </p>
      {/if}
      <dl class="facts run">
        <dt>Groups</dt>
        <dd>{#each meta.groups ?? [] as g, i (g)}{i ? ', ' : ''}<code>{g}</code>{/each}</dd>
        <dt>Projects</dt><dd>{fmtNum(run.projects)}</dd>
        <dt>Branches</dt>
        <dd>{fmtNum(run.branches)} selected · {fmtNum(run.fetched)} fetched · {fmtNum(run.reused)} unchanged</dd>
        <dt>Fetch errors</dt><dd>{fmtNum(run.fetch_errors)}</dd>
        <dt>Gone</dt><dd>{fmtNum(run.gone)}</dd>
        <dt>API requests</dt><dd>{fmtNum(run.api_requests)}</dd>
        {#if meta.branch_window_days}<dt>Branch window</dt><dd>{meta.branch_window_days} days</dd>{/if}
      </dl>
    </section>
  {/if}
</div>

<style>
  .page > section,
  .page > .grid {
    margin-bottom: 16px;
  }
  .tiles {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 12px;
  }
  .fw-list li {
    padding: 10px 0;
    border-bottom: 1px solid var(--grid);
  }
  .fw-list li:first-child {
    padding-top: 0;
  }
  .fw-head {
    display: flex;
    align-items: baseline;
    gap: 8px;
    margin-bottom: 8px;
    flex-wrap: wrap;
  }
  .fw-head .right {
    margin-left: auto;
    display: inline-flex;
    gap: 10px;
    align-items: center;
  }
  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: 4px 16px;
    margin-top: 12px;
    font-size: 13px;
  }
  .review-list a {
    display: flex;
    gap: 12px;
    padding: 8px;
    margin: 0 -8px;
    border-radius: 6px;
    color: var(--ink);
  }
  .review-list a:hover {
    background: var(--hover);
    text-decoration: none;
  }
  .review-list .count {
    min-width: 32px;
    text-align: right;
    font-weight: 600;
    font-size: 15px;
  }
  .desc {
    display: block;
    color: var(--ink-2);
    font-size: 13px;
  }
  .run {
    margin-top: 8px;
  }
</style>
