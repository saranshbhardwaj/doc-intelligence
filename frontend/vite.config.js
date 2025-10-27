import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  preview: {
    port: 4173,
    strictPort: true,
    // Ensure SPA routing works correctly in preview mode
    open: '/',
  },
})
