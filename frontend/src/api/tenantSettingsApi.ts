// Tenant soft-settings API (multi-tenant Phase 3). Scoped to the active tenant
// via the X-Tenant-Id interceptor (Phase 2).
import { api } from './client';
import type { TenantSettings, UpdateTenantSettingsPayload } from '../types/tenantSettings';

const authHeaders = (accessToken: string) => ({ Authorization: `Bearer ${accessToken}` });

export const getTenantSettings = async (accessToken: string): Promise<TenantSettings> => {
  const { data } = await api.get('/tenant-settings', { headers: authHeaders(accessToken) });
  return data as TenantSettings;
};

export const updateTenantSettings = async (
  accessToken: string,
  payload: UpdateTenantSettingsPayload,
): Promise<TenantSettings> => {
  const { data } = await api.put('/tenant-settings', payload, { headers: authHeaders(accessToken) });
  return data as TenantSettings;
};
