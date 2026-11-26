<script lang="ts">
  import { KIND_INFO } from '../lib/model'

  let { kind }: { kind: string } = $props()
</script>

<span class="pill" title={KIND_INFO[kind]?.hint}>
  <span class="dot" style:background="var(--kind-{kind}, var(--series-gray))"></span>
  {KIND_INFO[kind]?.label ?? kind}
</span>

<style>
  .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
  }
</style>
