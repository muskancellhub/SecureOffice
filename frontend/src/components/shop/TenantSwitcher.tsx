import { Building2 } from 'lucide-react';
import { useTenant } from '../../context/TenantContext';

/**
 * Global active-tenant dropdown (multi-tenant Phase 2). Rendered only for
 * SUPER_ADMIN; selecting a tenant re-scopes every admin page (the active tenant
 * is attached to all API requests via the axios interceptor).
 */
export const TenantSwitcher = () => {
  const { isSuperAdmin, tenants, activeTenantId, setActiveTenantId, loading } = useTenant();

  if (!isSuperAdmin) return null;

  return (
    <label className="tenant-switcher" title="Active tenant — scopes all admin config">
      <Building2 size={15} aria-hidden="true" />
      <span className="tenant-switcher-label">Tenant</span>
      <select
        value={activeTenantId ?? ''}
        onChange={(e) => setActiveTenantId(e.target.value)}
        disabled={loading || tenants.length === 0}
        aria-label="Active tenant"
      >
        {tenants.length === 0 && <option value="">{loading ? 'Loading…' : 'No tenants'}</option>}
        {tenants.map((t) => (
          <option key={t.id} value={t.id}>
            {t.name}
          </option>
        ))}
      </select>
    </label>
  );
};
