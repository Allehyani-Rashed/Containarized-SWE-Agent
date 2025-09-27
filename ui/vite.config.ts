import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/healthz': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/projects': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/integrations': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/tasks': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
});
