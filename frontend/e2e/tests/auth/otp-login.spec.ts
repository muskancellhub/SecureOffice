import { test, expect } from '../../fixtures/evidence-fixture';
import { TEST_USERS } from '../../fixtures/test-data';

test.describe('OTP Login Flow', () => {
  test('login page defaults to OTP mode', async ({ page }) => {
    await page.goto('/login', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    // Should show "Send OTP" button by default (not password field)
    await expect(page.getByRole('button', { name: /send otp/i })).toBeVisible({ timeout: 10000 });
    await expect(page.getByPlaceholder('Password')).not.toBeVisible();
  });

  test('OTP request with valid email shows success notice', async ({ page }) => {
    await page.goto('/login', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    await page.getByPlaceholder('Email Address').fill(TEST_USERS.company1Admin.email);
    await page.getByRole('button', { name: /send otp/i }).click();
    // Should show notice about OTP being sent
    await expect(page.locator('.mini-note')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('.mini-note')).toContainText(/otp.*sent|account exists/i);
  });

  test('OTP request shows 6-digit input after sending', async ({ page }) => {
    await page.goto('/login', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    await page.getByPlaceholder('Email Address').fill(TEST_USERS.company1Admin.email);
    await page.getByRole('button', { name: /send otp/i }).click();
    // After OTP sent, should show the 6-digit OTP input
    await expect(page.getByPlaceholder('6-digit OTP')).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole('button', { name: /verify/i })).toBeVisible();
  });

  test('OTP verify with wrong code shows error', async ({ page }) => {
    await page.goto('/login', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    await page.getByPlaceholder('Email Address').fill(TEST_USERS.company1Admin.email);
    await page.getByRole('button', { name: /send otp/i }).click();
    await expect(page.getByPlaceholder('6-digit OTP')).toBeVisible({ timeout: 10000 });
    // Enter wrong OTP
    await page.getByPlaceholder('6-digit OTP').fill('999999');
    await page.getByRole('button', { name: /verify/i }).click();
    // Should show error
    await expect(page.locator('.error-text')).toBeVisible({ timeout: 10000 });
  });

  test('resend OTP button has cooldown timer', async ({ page }) => {
    await page.goto('/login', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    await page.getByPlaceholder('Email Address').fill(TEST_USERS.company1Admin.email);
    await page.getByRole('button', { name: /send otp/i }).click();
    await expect(page.getByPlaceholder('6-digit OTP')).toBeVisible({ timeout: 10000 });
    // Resend button should show countdown
    const resendBtn = page.getByRole('button', { name: /resend/i });
    await expect(resendBtn).toBeVisible();
    await expect(resendBtn).toBeDisabled();
    // Should contain countdown text
    await expect(resendBtn).toContainText(/\d+s/);
  });

  test('can switch between OTP and password mode', async ({ page }) => {
    await page.goto('/login', { timeout: 30000 });
    await page.waitForLoadState('domcontentloaded');
    // Default: OTP mode
    await expect(page.getByRole('button', { name: /send otp/i })).toBeVisible({ timeout: 10000 });
    // Switch to password
    await page.getByRole('button', { name: /sign in with a password/i }).click();
    await expect(page.getByPlaceholder('Password')).toBeVisible();
    await expect(page.getByRole('button', { name: /^sign in/i })).toBeVisible();
    // Switch back to OTP
    await page.getByRole('button', { name: /use a one-time code/i }).click();
    await expect(page.getByRole('button', { name: /send otp/i })).toBeVisible();
  });
});
