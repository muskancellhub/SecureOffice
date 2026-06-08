// Module-level active-tenant store (multi-tenant Phase 2).
//
// The axios request interceptor in client.ts can't use React hooks, so the
// TenantContext keeps this ref in sync and the interceptor reads it. Only set
// for SUPER_ADMIN sessions — left null for everyone else so no X-Tenant-Id
// header is sent and behaviour is identical to before.
let activeTenantId: string | null = null;

export const getActiveTenantId = (): string | null => activeTenantId;

export const setActiveTenantRef = (id: string | null): void => {
  activeTenantId = id;
};
