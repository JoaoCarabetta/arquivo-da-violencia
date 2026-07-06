import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import Sitemap from 'vite-plugin-sitemap'
import path from 'path'

// API URL: Docker service name in compose; localhost when running Vite on the host.
const apiUrl = process.env.VITE_API_PROXY || 'http://localhost:8000'

// Site URL for sitemap generation (default to production URL)
const siteUrl = process.env.VITE_SITE_URL || 'https://arquivodaviolencia.com.br'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    Sitemap({
      hostname: siteUrl,
      dynamicRoutes: [
        '/',
        '/eventos',
        '/dados',
        '/sobre',
        '/metodologia',
      ],
    }),
  ],
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
