import { api } from './client';
import type { UserRole } from '../types/auth';
import type { CreateUserPayload, PermissionCatalogItem, UserSummary } from '../types/users';

const authHeaders = (accessToken: string) => ({ Authorization: `Bearer ${accessToken}` });

export const listUsers = async (accessToken: string, tenantId?: string) => {
  const { data } = await api.get('/users', {
    headers: authHeaders(accessToken),
    params: tenantId ? { tenant_id: tenantId } : undefined,
  });
  return data as UserSummary[];
};

export const createUser = async (accessToken: string, payload: CreateUserPayload) => {
  const { data } = await api.post('/users', payload, { headers: authHeaders(accessToken) });
  return data as UserSummary;
};

export const updateUserRole = async (accessToken: string, userId: string, role: UserRole) => {
  const { data } = await api.patch(`/users/${userId}/role`, { role }, { headers: authHeaders(accessToken) });
  return data as UserSummary;
};

export const updateUserPermissions = async (accessToken: string, userId: string, permissions: string[]) => {
  const { data } = await api.patch(`/users/${userId}/permissions`, { permissions }, { headers: authHeaders(accessToken) });
  return data as UserSummary;
};

export const getPermissionCatalog = async (accessToken: string) => {
  const { data } = await api.get('/users/permissions/catalog', { headers: authHeaders(accessToken) });
  return data as PermissionCatalogItem[];
};
