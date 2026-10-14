import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// In development the API runs on :8000. The proxy keeps requests same-origin, so no CORS setup is needed.
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
