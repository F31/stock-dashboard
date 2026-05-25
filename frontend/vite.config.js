import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],

  server: {
    port: 5173,
    host: '0.0.0.0',
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },

  build: {
    chunkSizeWarningLimit: 400,

    rollupOptions: {
      output: {
        manualChunks(id) {
          // Vue ecosystem — tiny, always needed on first paint
          if (
            id.includes('node_modules/vue/') ||
            id.includes('node_modules/@vue/') ||
            id.includes('node_modules/vue-router/') ||
            id.includes('node_modules/pinia/')
          ) {
            return 'vue-vendor'
          }
          // chart.js — heavy (~200 kB). Lives in IndustrialProfitMonitor
          // which is lazy-loaded, so this chunk is only fetched on demand.
          if (id.includes('node_modules/chart.js')) {
            return 'chart-vendor'
          }
          // axios — small, separate from app code for better cache stability
          if (id.includes('node_modules/axios')) {
            return 'axios-vendor'
          }
        },
      },
    },
  },
})
