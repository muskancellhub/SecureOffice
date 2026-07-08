import { Page, Locator, expect } from '@playwright/test';

/**
 * Page Object for the Login page (/login).
 *
 * Encapsulates all locators and actions so tests stay clean.
 * If the UI changes, update only this file.
 */
export class LoginPage {
  readonly page: Page;
  readonly emailInput: Locator;
  readonly passwordInput: Locator;
  readonly submitButton: Locator;
  readonly otpLink: Locator;
  readonly googleButton: Locator;
  readonly microsoftButton: Locator;
  readonly errorMessage: Locator;

  constructor(page: Page) {
    this.page = page;
    this.emailInput = page.getByLabel(/email/i);
    this.passwordInput = page.getByLabel(/password/i);
    this.submitButton = page.getByRole('button', { name: /sign in|log in|login/i });
    this.otpLink = page.getByText(/otp|code|passwordless/i);
    this.googleButton = page.getByRole('button', { name: /google/i });
    this.microsoftButton = page.getByRole('button', { name: /microsoft/i });
    this.errorMessage = page.getByRole('alert');
  }

  async goto() {
    await this.page.goto('/login');
  }

  async loginWithPassword(email: string, password: string) {
    await this.emailInput.fill(email);
    await this.passwordInput.fill(password);
    await this.submitButton.click();
  }

  async expectLoggedIn() {
    await this.page.waitForURL(/\/(shop|dashboard)/, { timeout: 15000 });
    await expect(this.page).not.toHaveURL(/\/login/);
  }

  async expectError(message: string | RegExp) {
    await expect(this.errorMessage).toBeVisible();
    await expect(this.errorMessage).toContainText(message);
  }
}
