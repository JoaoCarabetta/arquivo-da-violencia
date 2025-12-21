import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

// API URL: Use service name in Docker, localhost for local dev
// When running in Docker, the service name 'api' resolves to the API container
// Note: In dev mode, Vite proxy runs in Node.js context, so it can use Docker service names
const apiUrl = 'http://api:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    host: '0.0.0.0', // Allow external connections
    proxy: {
      '/api': {
        target: apiUrl,
        changeOrigin: true,
      },
    },
  },
})
