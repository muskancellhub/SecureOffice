import { Page, Locator, expect } from '@playwright/test';

/**
 * Page Object for the main Shop shell (sidebar + content area).
 * Used after login when user lands on /shop or any /shop/* route.
 */
export class ShopPage {
  readonly page: Page;
  readonly sidebar: Locator;
  readonly designsLink: Locator;
  readonly routersLink: Locator;
  readonly servicesLink: Locator;
  readonly cartLink: Locator;
  readonly ordersLink: Locator;
  readonly billingLink: Locator;
  readonly userMenu: Locator;
  readonly logoutButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.sidebar = page.getByRole('navigation');
    this.designsLink = page.getByRole('link', { name: /design/i });
    this.routersLink = page.getByRole('link', { name: /router/i });
    this.servicesLink = page.getByRole('link', { name: /service/i });
    this.cartLink = page.getByRole('link', { name: /cart/i });
    this.ordersLink = page.getByRole('link', { name: /order/i });
    this.billingLink = page.getByRole('link', { name: /billing/i });
    this.userMenu = page.getByTestId('user-menu');
    this.logoutButton = page.getByRole('button', { name: /log\s*out|sign\s*out/i });
  }

  async expectLoaded() {
    await expect(this.page).toHaveURL(/\/shop/);
  }

  async navigateToDesigns() {
    await this.designsLink.click();
    await this.page.waitForURL(/\/shop\/designs/);
  }

  async navigateToRouters() {
    await this.routersLink.click();
    await this.page.waitForURL(/\/shop\/routers/);
  }

  async navigateToCart() {
    await this.cartLink.click();
    await this.page.waitForURL(/\/shop\/cart/);
  }

  async navigateToOrders() {
    await this.ordersLink.click();
    await this.page.waitForURL(/\/shop\/orders/);
  }

  async logout() {
    await this.userMenu.click();
    await this.logoutButton.click();
    await this.page.waitForURL(/\/(login)?$/);
  }
}
