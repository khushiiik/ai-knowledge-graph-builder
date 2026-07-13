import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const BACKEND_URL = process.env.BACKEND_API_URL || 'http://localhost:8000';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/auth': {
        target: BACKEND_URL,
        changeOrigin: true
      },
      '/documents': {
        target: BACKEND_URL,
        changeOrigin: true
      },
      '/chat': {
        target: BACKEND_URL,
        changeOrigin: true
      }
    }
  }
})
