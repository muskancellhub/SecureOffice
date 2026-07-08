import { test as base } from '@playwright/test';
import path from 'path';
import { AUTH_STATE_DIR, TEST_USERS } from './test-data';

/**
 * Extended test fixtures that provide pre-authenticated pages.
 *
 * Usage in tests:
 *   import { test } from '../fixtures/auth.fixture';
 *   test('my test', async ({ authedPage }) => { ... });
 */

// Paths to saved auth states
export const authFiles = {
  superAdmin: path.join(AUTH_STATE_DIR, 'super-admin.json'),
  company1Admin: path.join(AUTH_STATE_DIR, 'company1-admin.json'),
  company2User: path.join(AUTH_STATE_DIR, 'company2-user.json'),
};

/**
 * Custom test fixture that gives you a page already logged in as company1 admin.
 * This is the most common test user (a regular customer).
 */
export const test = base.extend<{ authedPage: typeof base }>({});

export { expect } from '@playwright/test';
