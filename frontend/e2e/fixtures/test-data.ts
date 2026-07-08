/**
 * Test user credentials and constants used across all E2E tests.
 *
 * Set these in your local environment before running Playwright. Values are
 * intentionally required so local credentials are not committed to git.
 */
function requiredEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing ${name}. Set it in your local environment before running E2E tests.`);
  }
  return value;
}

export const TEST_USERS = {
  superAdmin: {
    email: requiredEnv('E2E_SUPER_ADMIN_EMAIL'),
    password: requiredEnv('E2E_SUPER_ADMIN_PASSWORD'),
    role: 'SUPER_ADMIN',
  },
  company1Admin: {
    email: requiredEnv('E2E_COMPANY1_EMAIL'),
    password: requiredEnv('E2E_COMPANY1_PASSWORD'),
    role: 'ADMIN',
  },
  company2User: {
    email: requiredEnv('E2E_COMPANY2_EMAIL'),
    password: requiredEnv('E2E_COMPANY2_PASSWORD'),
    role: 'USER',
  },
};

/** Directory where authenticated browser states are stored */
export const AUTH_STATE_DIR = './e2e/.auth';

/** Backend API base URL */
export const API_BASE_URL = process.env.E2E_API_URL || 'http://localhost:8000';
