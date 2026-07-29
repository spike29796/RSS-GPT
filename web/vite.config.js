import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  // Deployed as a GitHub Pages project site under /RSS-GPT/.
  base: '/RSS-GPT/',
  build: {
    // Build straight into the pipeline's docs/ (the Pages publish dir).
    // emptyOutDir MUST stay false: docs/ also holds the JSONL/XML data.
    outDir: '../RSS-GPT/docs',
    emptyOutDir: false,
  },
  server: {
    proxy: {
      // Dev against the live published data.
      '/RSS-GPT': {
        target: 'https://spike29796.github.io',
        changeOrigin: true,
      },
    },
  },
})
