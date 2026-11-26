<script lang="ts">
  import { HEALTH, type Health } from '../lib/model'

  let { health, label = true }: { health: Health; label?: boolean } = $props()
</script>

<span class="hb" title={HEALTH[health].hint}>
  <span class="icon {health}" aria-hidden="true">{HEALTH[health].icon}</span>
  {#if label}{HEALTH[health].label}{:else}<span class="sr-only">{HEALTH[health].label}</span>{/if}
</span>

<style>
  .hb {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    white-space: nowrap;
  }
  .icon {
    display: inline-grid;
    place-items: center;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    font-size: 10.5px;
    font-weight: 700;
    line-height: 1;
    color: #fff;
    flex: none;
  }
  .current {
    background: var(--good);
  }
  .behind {
    background: var(--warning);
    color: #0b0b0b;
  }
  .unresolved {
    background: var(--critical);
  }
  .unknown {
    background: var(--muted);
  }
</style>
