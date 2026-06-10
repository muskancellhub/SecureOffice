import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { useAuth } from './AuthContext';
import * as tenantsApi from '../api/tenantsApi';
import { setActiveTenantRef } from '../api/activeTenant';
import type { TenantSummary } from '../types/tenants';

/**
 * Active-tenant context (multi-tenant Phase 2).
 *
 * A CellHub SUPER_ADMIN picks an active tenant; every admin page reads it and
 * every API request carries it (via the axios interceptor). Non-super users
 * have no switcher and send no X-Tenant-Id — behaviour is unchanged for them.
 */
const STORAGE_KEY = 'so2_active_tenant';

interface TenantContextValue {
  isSuperAdmin: boolean;
  tenants: TenantSummary[];
  activeTenantId: string | null;
  activeTenant: TenantSummary | null;
  setActiveTenantId: (id: string) => void;
  loading: boolean;
}

const TenantContext = createContext<TenantContextValue | undefined>(undefined);

export const TenantProvider = ({ children }: { children: React.ReactNode }) => {
  const { user, accessToken } = useAuth();
  const isSuperAdmin = user?.role === 'SUPER_ADMIN';

  const [tenants, setTenants] = useState<TenantSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeTenantId, setActiveTenantIdState] = useState<string | null>(
    () => window.localStorage.getItem(STORAGE_KEY),
  );

  // Default to the user's own tenant when nothing was stored.
  useEffect(() => {
    if (!user) return;
    setActiveTenantIdState((cur) => cur ?? user.tenant_id ?? null);
  }, [user]);

  // Load the tenant directory for super-admins (drives the switcher).
  useEffect(() => {
    let cancelled = false;
    if (!accessToken || !isSuperAdmin) {
      setTenants([]);
      return;
    }
    setLoading(true);
    tenantsApi
      .listTenants(accessToken)
      .then((list) => {
        if (cancelled) return;
        setTenants(list);
        // If the stored tenant is stale (deleted / not a real tenant), fall back.
        setActiveTenantIdState((cur) => {
          if (cur && list.some((t) => t.id === cur)) return cur;
          return user?.tenant_id ?? list[0]?.id ?? null;
        });
      })
      .catch(() => {
        if (!cancelled) setTenants([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken, isSuperAdmin, user?.tenant_id]);

  const setActiveTenantId = useCallback((id: string) => {
    if (id === activeTenantId) return; // reselecting the same tenant — no reload
    // Persist first, then hard-reload so every page re-fetches its data under the
    // newly selected tenant. Pages fetch on mount and don't react to a tenant
    // change otherwise, so a reload is the reliable way to re-scope the whole UI.
    // The session survives the reload (it's restored from the refresh cookie in
    // AuthContext.ensureSession on load).
    window.localStorage.setItem(STORAGE_KEY, id);
    setActiveTenantIdState(id);
    window.location.reload();
  }, [activeTenantId]);

  // Keep the interceptor's ref current. Done during render (not an effect) so the
  // header is set before any child page's data-fetch effect fires. Only
  // super-admins send the header; everyone else stays header-less.
  setActiveTenantRef(isSuperAdmin ? activeTenantId : null);

  const activeTenant = useMemo(
    () => tenants.find((t) => t.id === activeTenantId) ?? null,
    [tenants, activeTenantId],
  );

  const value = useMemo(
    () => ({ isSuperAdmin, tenants, activeTenantId, activeTenant, setActiveTenantId, loading }),
    [isSuperAdmin, tenants, activeTenantId, activeTenant, setActiveTenantId, loading],
  );

  return <TenantContext.Provider value={value}>{children}</TenantContext.Provider>;
};

export const useTenant = () => {
  const ctx = useContext(TenantContext);
  if (!ctx) {
    throw new Error('useTenant must be used inside TenantProvider');
  }
  return ctx;
};
