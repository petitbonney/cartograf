<script lang="ts">
  import { HEALTH, type Adoption } from '../lib/model'
  import { tooltip } from '../lib/tooltip.svelte'
  import { plural } from '../lib/format'

  let { adoption, latest }: { adoption: Adoption[]; latest: string | null } = $props()

  const max = $derived(Math.max(1, ...adoption.map((a) => a.repos.length)))
  const color: Record<string, string> = {
    current: 'var(--good)',
    behind: 'var(--warning)',
    unresolved: 'var(--critical)',
    unknown: 'var(--muted)',
  }
</script>

{#if adoption.length === 0}
  <p class="muted">No repository uses this framework.</p>
{:else}
  <table class="bars" aria-label="Repositories per version">
    <tbody>
      {#each adoption as a (a.version)}
        <tr use:tooltip={`${a.version}: ${plural(a.repos.length, 'repo')}\n${a.repos.join('\n')}`}>
          <th scope="row">
            <span class="icon {a.health}" aria-hidden="true">{HEALTH[a.health].icon}</span>
            <span class="v">{a.version}</span>
            {#if a.version === latest}<span class="tag">latest</span>{/if}
          </th>
          <td class="track">
            <span class="fill" style:width="{(a.repos.length / max) * 100}%" style:background={color[a.health]}></span>
          </td>
          <td class="count num">{a.repos.length}</td>
        </tr>
      {/each}
    </tbody>
  </table>
{/if}

<style>
  .bars {
    width: 100%;
    border-collapse: collapse;
  }
  .bars th,
  .bars td {
    border: 0;
    padding: 3px 0;
    background: none;
    position: static;
    vertical-align: middle;
  }
  .bars tr:hover td,
  .bars tr:hover th {
    background: none;
  }
  .bars tr:hover .fill {
    filter: brightness(1.1);
  }
  th {
    width: 1%;
    padding-right: 12px !important;
    white-space: nowrap;
    font-weight: 400;
    color: var(--ink);
    font-size: 13px;
  }
  .v {
    font-family: var(--mono);
    font-size: 12.5px;
  }
  .icon {
    display: inline-grid;
    place-items: center;
    width: 15px;
    height: 15px;
    margin-right: 6px;
    border-radius: 50%;
    font-size: 10px;
    font-weight: 700;
    color: #fff;
    vertical-align: -3px;
  }
  .icon.current {
    background: var(--good);
  }
  .icon.behind {
    background: var(--warning);
    color: #0b0b0b;
  }
  .icon.unresolved {
    background: var(--critical);
  }
  .icon.unknown {
    background: var(--muted);
  }
  .tag {
    margin-left: 6px;
    font-size: 11px;
    color: var(--good-ink);
  }
  .track {
    width: 100%;
  }
  .fill {
    display: block;
    height: 14px;
    min-width: 4px;
    border-radius: 0 4px 4px 0;
  }
  .count {
    width: 1%;
    padding-left: 10px !important;
    color: var(--ink-2);
    text-align: right;
  }
</style>
