<script lang="ts">
  import { HEALTH, type BranchUse, type UseCell } from '../lib/model'
  import { tooltip } from '../lib/tooltip.svelte'

  let { cell, prefix = '', detailed = true }: { cell: UseCell | BranchUse; prefix?: string; detailed?: boolean } =
    $props()

  const others = $derived('others' in cell ? cell.others : [])
  const disagrees = $derived('disagrees' in cell && cell.disagrees)
  const text = $derived(cell.versions.length ? cell.versions.join(', ') : 'unresolved')

  function describe(u: BranchUse): string {
    return `${u.branch}${u.isDefault ? ' (default)' : ''}: ${u.versions.join(', ') || 'unresolved'} · ${HEALTH[u.health].label}`
  }
  const tip = $derived(
    detailed
      ? [
          'framework' in cell ? cell.framework : '',
          describe(cell),
          ...others.map(describe),
          ...cell.links.map((l) => `  ${l.type === 'inherited' ? `inherited ${l.inherited_type}` : l.type} ${l.artifact}`),
        ]
          .filter(Boolean)
          .join('\n')
      : null,
  )
</script>

<span class="chip {cell.health}" use:tooltip={tip}>
  <span class="icon" aria-hidden="true">{HEALTH[cell.health].icon}</span>
  <span class="sr-only">{HEALTH[cell.health].label}:</span>
  {#if prefix}<span class="prefix">{prefix}</span>{/if}
  <span class="v">{text}</span>
  {#if disagrees}<span class="diff" title="another branch uses a different version">≠</span>{/if}
</span>

<style>
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 1px 8px 1px 3px;
    border-radius: 999px;
    font-family: var(--mono);
    font-size: 12px;
    line-height: 20px;
    white-space: nowrap;
    background: var(--unknown-wash);
    color: var(--ink);
  }
  .icon {
    display: inline-grid;
    place-items: center;
    width: 15px;
    height: 15px;
    border-radius: 50%;
    font-family: var(--font);
    font-size: 10px;
    font-weight: 700;
    color: #fff;
    background: var(--muted);
  }
  .prefix {
    font-family: var(--font);
    color: var(--ink-2);
  }
  .current {
    background: var(--good-wash);
  }
  .current .icon {
    background: var(--good);
  }
  .behind {
    background: var(--warning-wash);
  }
  .behind .icon {
    background: var(--warning);
    color: #0b0b0b;
  }
  .unresolved {
    background: var(--critical-wash);
  }
  .unresolved .icon {
    background: var(--critical);
  }
  .diff {
    font-family: var(--font);
    font-weight: 700;
    color: var(--ink-2);
  }
</style>
