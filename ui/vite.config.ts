import { defineConfig } from 'vite';
import type { IncomingMessage } from 'http';
import react from '@vitejs/plugin-react';

function spaBypass(req: IncomingMessage): string | undefined {
  const accepts = req.headers.accept ?? '';
  if (accepts.includes('text/html')) {
    return '/index.html';
  }
  return undefined;
}

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    css: true,
    include: ['src/__tests__/**/*.test.{ts,tsx}', 'src/**/*.test.{ts,tsx}'],
  },
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
        changeOrigin: true,
        bypass: spaBypass
      },
      '/integrations': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        bypass: spaBypass
      },
      '/tasks': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        bypass: spaBypass
      },
      '/models': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        bypass: spaBypass
      },
      '/settings': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        bypass: spaBypass
      }
    }
  }
});
