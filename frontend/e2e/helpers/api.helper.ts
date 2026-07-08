import { request } from '@playwright/test';
import { API_BASE_URL } from '../fixtures/test-data';

/**
 * Helper for making direct API calls in tests.
 * Use for test setup/teardown (creating test data, cleaning up).
 */
export class ApiHelper {
  private token: string | null = null;

  async login(email: string, password: string): Promise<string> {
    const context = await request.newContext({ baseURL: API_BASE_URL });
    const response = await context.post('/auth/login', {
      data: { email, password },
    });
    const body = await response.json();
    this.token = body.access_token;
    await context.dispose();
    return this.token!;
  }

  async get(path: string) {
    const context = await request.newContext({
      baseURL: API_BASE_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${this.token}` },
    });
    const response = await context.get(path);
    const body = await response.json();
    await context.dispose();
    return body;
  }

  async post(path: string, data: Record<string, unknown>) {
    const context = await request.newContext({
      baseURL: API_BASE_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${this.token}` },
    });
    const response = await context.post(path, { data });
    const body = await response.json();
    await context.dispose();
    return body;
  }

  async delete(path: string) {
    const context = await request.newContext({
      baseURL: API_BASE_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${this.token}` },
    });
    const response = await context.delete(path);
    await context.dispose();
    return response.status();
  }
}
