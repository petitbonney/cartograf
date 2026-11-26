import { svelte } from '@sveltejs/vite-plugin-svelte'
import { defineConfig } from 'vitest/config'

// `base: './'` makes every asset path relative, so the same build works at any
// subpath: user.github.io/cartograf/, group.gitlab.io/cartograf/, or a file server.
export default defineConfig({
  base: './',
  plugins: [svelte()],
  test: {
    include: ['src/**/*.test.ts'],
  },
})
