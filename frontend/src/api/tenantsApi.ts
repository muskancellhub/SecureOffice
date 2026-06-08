// Tenant directory for the SUPER_ADMIN switcher (multi-tenant Phase 2).
import { api } from './client';
import type { TenantSummary } from '../types/tenants';

export const listTenants = async (accessToken: string): Promise<TenantSummary[]> => {
  const { data } = await api.get('/tenants', {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  return data as TenantSummary[];
};
