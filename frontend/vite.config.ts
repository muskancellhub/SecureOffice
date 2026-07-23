import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Dev stand-in for the production reverse proxy (nginx). Both strip the
    // /api prefix before hitting FastAPI, whose routers are mounted at bare
    // /auth, /orders, … — so the app only ever builds relative URLs and dev
    // exercises exactly the code path production takes.
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  test: {
    coverage: {
      provider: 'v8',
      // QA_FRAMEWORK §1.1 scope: deterministic calculator + suggestions logic.
      include: ['src/calculator/**/*.ts', 'src/suggestions/**/*.ts'],
      exclude: [
        'src/suggestions/exampleUsage.ts', // demo data only, not a production entry
        '**/__tests__/**',
        'src/**/types.ts', // type-only modules
        'src/**/index.ts', // re-export barrels
      ],
      thresholds: {
        // Glob-scoped pools: suggestions gated at the framework's 90%;
        // calculator ratcheted at its measured level (target 90).
        'src/suggestions/**/*.ts': { lines: 90 },
        'src/calculator/**/*.ts': { lines: 90 },
      },
    },
  },
});
