import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
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
