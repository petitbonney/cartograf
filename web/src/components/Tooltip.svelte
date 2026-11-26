<script lang="ts">
  import { tip } from '../lib/tooltip.svelte'

  // Above the element, or below it when there is no room at the top.
  const below = $derived(tip.top < 120)
</script>

<svelte:window onscroll={() => (tip.text = null)} />

{#if tip.text}
  <div
    class="tip"
    class:below
    role="tooltip"
    style:left="{Math.min(Math.max(tip.x, 140), window.innerWidth - 140)}px"
    style:top="{below ? tip.bottom + 8 : tip.top - 8}px"
  >
    {tip.text}
  </div>
{/if}

<style>
  .tip {
    position: fixed;
    z-index: 100;
    transform: translate(-50%, -100%);
    max-width: 320px;
    padding: 8px 10px;
    border-radius: 6px;
    background: var(--surface);
    color: var(--ink);
    border: 1px solid var(--border);
    box-shadow: var(--shadow);
    font-size: 12.5px;
    line-height: 1.45;
    white-space: pre-line;
    pointer-events: none;
  }
  .tip.below {
    transform: translate(-50%, 0);
  }
</style>
