import { test, expect } from '../fixtures/evidence-fixture';
import { TEST_USERS, AUTH_STATE_DIR } from '../fixtures/test-data';

/**
 * AUTH SETUP — Runs ONCE before all other tests.
 *
 * Logs in each test user and saves browser cookies/localStorage to JSON files.
 * Other tests load these files to skip the login step.
 *
 * NOTE: Login page defaults to OTP mode. We click "Sign in with a password"
 * to switch to password mode first.
 */

test('authenticate super admin', async ({ page }) => {
  await page.goto('/login');
  await expect(page.getByPlaceholder('Email Address')).toBeVisible({ timeout: 15000 });

  // Switch from OTP mode to password mode
  await page.getByRole('button', { name: /sign in with a password/i }).click();
  await expect(page.getByPlaceholder('Password')).toBeVisible();

  // Fill credentials and submit
  await page.getByPlaceholder('Email Address').fill(TEST_USERS.superAdmin.email);
  await page.getByPlaceholder('Password').fill(TEST_USERS.superAdmin.password);
  
  // Click the "Sign in" button (not "Sign in with a password")
  await page.getByRole('button', { name: /^sign in$/i }).click();

  // Wait until we land on a protected page
  await page.waitForURL(/\/(shop|dashboard)/, { timeout: 30000 });
  
  // Wait a bit for auth state to stabilize
  await page.waitForTimeout(2000);

  // Save the authenticated state
  await page.context().storageState({ path: `${AUTH_STATE_DIR}/super-admin.json` });
});

test('authenticate company1 admin', async ({ page }) => {
  await page.goto('/login');
  await expect(page.getByPlaceholder('Email Address')).toBeVisible({ timeout: 15000 });

  await page.getByRole('button', { name: /sign in with a password/i }).click();
  await expect(page.getByPlaceholder('Password')).toBeVisible();

  await page.getByPlaceholder('Email Address').fill(TEST_USERS.company1Admin.email);
  await page.getByPlaceholder('Password').fill(TEST_USERS.company1Admin.password);
  await page.getByRole('button', { name: /^sign in$/i }).click();

  await page.waitForURL(/\/(shop|dashboard)/, { timeout: 30000 });
  
  // Wait a bit for auth state to stabilize
  await page.waitForTimeout(2000);
  
  await page.context().storageState({ path: `${AUTH_STATE_DIR}/company1-admin.json` });
});

test('authenticate company2 user', async ({ page }) => {
  await page.goto('/login');
  await expect(page.getByPlaceholder('Email Address')).toBeVisible({ timeout: 15000 });

  await page.getByRole('button', { name: /sign in with a password/i }).click();
  await expect(page.getByPlaceholder('Password')).toBeVisible();

  await page.getByPlaceholder('Email Address').fill(TEST_USERS.company2User.email);
  await page.getByPlaceholder('Password').fill(TEST_USERS.company2User.password);
  await page.getByRole('button', { name: /^sign in$/i }).click();

  await page.waitForURL(/\/(shop|dashboard)/, { timeout: 30000 });
  
  // Wait a bit for auth state to stabilize
  await page.waitForTimeout(2000);
  
  await page.context().storageState({ path: `${AUTH_STATE_DIR}/company2-user.json` });
});
