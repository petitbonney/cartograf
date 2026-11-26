<script lang="ts" module>
  export interface Part {
    key: string
    label: string
    value: number
    color: string
    href?: string
  }
</script>

<script lang="ts">
  import { fmtNum } from '../lib/format'
  import { tooltip } from '../lib/tooltip.svelte'

  let { parts, legend = true, label }: { parts: Part[]; legend?: boolean; label: string } = $props()

  const total = $derived(parts.reduce((s, p) => s + p.value, 0))
  const pct = (v: number) => (total ? Math.round((v / total) * 100) : 0)
</script>

<div class="wrap">
  <div class="bar" role="img" aria-label="{label}: {parts.map((p) => `${p.label} ${p.value}`).join(', ')}">
    {#each parts.filter((p) => p.value > 0) as p (p.key)}
      <span
        class="seg"
        style:flex-grow={p.value}
        style:background={p.color}
        use:tooltip={`${p.label}: ${fmtNum(p.value)} (${pct(p.value)}%)`}
      ></span>
    {/each}
    {#if total === 0}<span class="seg empty"></span>{/if}
  </div>
  {#if legend}
    <ul class="legend">
      {#each parts as p (p.key)}
        <li>
          <span class="sw" style:background={p.color}></span>
          {#if p.href}<a href={p.href}>{p.label}</a>{:else}{p.label}{/if}
          <span class="num secondary">{fmtNum(p.value)}</span>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .bar {
    display: flex;
    gap: 2px;
    height: 8px;
  }
  .seg {
    flex-basis: 0;
    min-width: 4px;
    border-radius: 999px;
  }
  .seg.empty {
    flex-grow: 1;
    background: var(--grid);
  }
  .legend {
    list-style: none;
    margin: 10px 0 0;
    padding: 0;
    display: flex;
    flex-wrap: wrap;
    gap: 4px 16px;
    font-size: 13px;
  }
  .legend li {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .sw {
    width: 10px;
    height: 10px;
    border-radius: 3px;
  }
</style>
