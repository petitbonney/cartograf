<script lang="ts">
  import { fmtNum } from '../lib/format'

  let { label, value, sub = '', href = '' }: { label: string; value: number; sub?: string; href?: string } = $props()
</script>

{#if href}
  <a class="tile card" {href}>
    <span class="label">{label}</span>
    <span class="value">{fmtNum(value)}</span>
    {#if sub}<span class="sub">{sub}</span>{/if}
  </a>
{:else}
  <div class="tile card">
    <span class="label">{label}</span>
    <span class="value">{fmtNum(value)}</span>
    {#if sub}<span class="sub">{sub}</span>{/if}
  </div>
{/if}

<style>
  .tile {
    display: flex;
    flex-direction: column;
    gap: 2px;
    color: var(--ink);
  }
  a.tile:hover {
    text-decoration: none;
    border-color: var(--axis);
  }
  .label {
    color: var(--ink-2);
    font-size: 13px;
  }
  .value {
    font-size: 28px;
    font-weight: 600;
    line-height: 1.2;
  }
  .sub {
    color: var(--muted);
    font-size: 12.5px;
  }
</style>
