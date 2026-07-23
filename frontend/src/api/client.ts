import axios from 'axios';
import { getActiveTenantId } from './activeTenant';
import { API_BASE_URL } from './config';

export const api = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
});

// Multi-tenant Phase 2: attach the active tenant to every request. Only set for
// SUPER_ADMIN sessions (the store stays null otherwise), so non-super requests
// carry no X-Tenant-Id and behave exactly as before. The backend resolves a
// header equal to the actor's own tenant as a no-op (see tenant_context.py).
api.interceptors.request.use((config) => {
  const tenantId = getActiveTenantId();
  if (tenantId) {
    config.headers = config.headers ?? {};
    (config.headers as Record<string, string>)['X-Tenant-Id'] = tenantId;
  }
  return config;
});
