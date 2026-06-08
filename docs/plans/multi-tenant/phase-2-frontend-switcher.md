# Phase 2 — frontend tenant switcher + X-Tenant-Id  ✅ BUILT

Give super-admins one global active-tenant control and make every API call carry it.
Remove the free-text tenant UUID boxes.

> **Status (built 2026-06-05):** shipped. See "What actually shipped" at the bottom.

## 1. Active-tenant context — new `frontend/src/context/TenantContext.tsx`

- `activeTenantId: string | null`, `setActiveTenantId`, `tenants: TenantSummary[]`.
- On mount, **iff `user.role === 'SUPER_ADMIN'`**, fetch `GET /tenants` (Phase 0 endpoint)
  and default `activeTenantId` to the user's own `tenant_id`.
- Persist the selection (localStorage) so a reload keeps the active tenant.
- Wrap the app inside `AuthProvider` (needs `user`) but outside the shop pages.

Add `productsApi`-style client call + a `TenantSummary` type (`{id, name, tenant_type}`)
to `frontend/src/types/`.

## 2. Axios interceptor — attach the header

In `frontend/src/api/client.ts` (the `api` axios instance), add a **request**
interceptor that sets `X-Tenant-Id: activeTenantId` when present. Source the value from
a module-level ref the TenantContext keeps in sync (interceptors can't use hooks).

> Mirror the existing single-flight refresh interceptor already in `AuthContext.tsx`
> for the pattern. Only attach the header for SUPER_ADMIN sessions / when it differs
> from home — sending your own tenant id is harmless (Phase 0 treats it as not-cross).

## 3. TenantSwitcher component

- Dropdown in the top nav (`frontend/src/components/shop/ShopShell.tsx`), rendered
  **only** when `user.role === 'SUPER_ADMIN'`.
- Options from `tenants`; onChange → `setActiveTenantId`. Show the active tenant name.

## 4. Remove free-text tenant inputs

- `frontend/src/pages/AdminFinancingPage.tsx` — drop the raw tenant-id text box; read
  `activeTenantId` from context (the header now carries it; backend resolves via
  `get_tenant_context`).
- `frontend/src/pages/AdminUserManagementPage.tsx` — same; the user-management service
  already accepts a resolved target tenant.

## 5. Migrate the pricing path-param endpoints (optional, cleanup)

Now that the header is always sent, the Phase 0 `/pricing/customers/{tenant_id}/...`
endpoints can move from path-param + `assert_tenant_access` to `get_tenant_context`.
Keep `assert_tenant_access` if you'd rather not change the route shape — both are safe.

## Acceptance
- A SUPER_ADMIN picks "Dell" → every subsequent request carries `X-Tenant-Id: <dell>`,
  and the admin pages show/edit Dell's config.
- A non-super never sees the switcher and never sends the header.
- `AdminFinancingPage` / `AdminUserManagementPage` have no UUID text boxes.
- Switching tenant and reloading preserves the selection.

## Gotchas
- The `ProtectedRoute` → `RequireSuperAdmin` (Phase 0) guards the *pages*; the switcher
  guards the *data*. Both gate on `user.role` — keep them consistent.
- Don't attach `X-Tenant-Id` on the unauthenticated routes (`/auth/*`) — the interceptor
  should no-op when there's no active tenant.
- `GET /tenants` returns all tenant types; decide whether the switcher lists VENDOR/COMPANY
  tenants or only COMPANY customers.

---

## What actually shipped

### New files
| File | Purpose |
|------|---------|
| `frontend/src/api/activeTenant.ts` | Module-level active-tenant store (`getActiveTenantId` / `setActiveTenantRef`). Lets the axios interceptor read the active tenant without hooks. Null for non-super sessions. |
| `frontend/src/api/client.ts` | **Request interceptor** added: attaches `X-Tenant-Id` from the store to every request when set. |
| `frontend/src/types/tenants.ts` | `TenantSummary { id, name, tenant_type }`. |
| `frontend/src/api/tenantsApi.ts` | `listTenants(accessToken)` → `GET /tenants`. |
| `frontend/src/context/TenantContext.tsx` | `TenantProvider` + `useTenant()`. Fetches the directory for super-admins, defaults active tenant to own/localStorage, persists selection, and **syncs the interceptor ref during render** so the header is set before any child page's fetch effect fires. |
| `frontend/src/components/shop/TenantSwitcher.tsx` | Top-bar dropdown, rendered only for SUPER_ADMIN. |

### Wiring / edits
| File | Change |
|------|--------|
| `frontend/src/router/AppRouter.tsx` | `<TenantProvider>` wraps `<ShopProvider><ShopShell/>` inside the protected shop route group. |
| `frontend/src/components/shop/ShopShell.tsx` | `<TenantSwitcher />` rendered first in `.shop-main-topbar`. |
| `frontend/src/styles/global.css` | `.tenant-switcher` styles (left-aligned via `margin-right:auto`; cart stays right). |
| `frontend/src/pages/AdminFinancingPage.tsx` | Removed the free-text "Tenant ID" box; commercial config now targets `activeTenantId`; financing list re-fetches on tenant switch; "Viewing tenant: **‹name›**" indicator added. |
| `frontend/src/pages/AdminUserManagementPage.tsx` | Removed the "Tenant ID (optional)" box; super-admin user creation targets `activeTenantId` (shown read-only); user list re-fetches on tenant switch. |

### Decisions / notes (read before Phase 3)
- **Interceptor ref is synced in render, not an effect.** Child effects fire before
  parent effects, so an effect-based sync would let the first admin fetch go out
  header-less. Setting `setActiveTenantRef(...)` in the provider body guarantees order.
- **Non-super sessions stay header-less** — the store is null for them, so behaviour is
  byte-identical to pre-Phase-2. The switcher returns `null` for non-super.
- **`/pricing/customers/{tenant_id}` still uses the path param** (Phase 0 `assert_tenant_access`).
  `AdminFinancingPage` passes `activeTenantId` as that path arg, and the interceptor also
  sends the header — both agree. Migrating these routes to `get_tenant_context` is optional
  cleanup, not done.
- **localStorage key**: `so2_active_tenant`. Stale/deleted-tenant ids fall back to the
  user's own tenant after the directory loads.
- **`GET /tenants` returns all tenant types** (CELLHUB/VENDOR/COMPANY); the switcher lists
  them all. Filter later if only COMPANY customers should be switchable.

### Verification
- `tsc --noEmit`: Phase 2 files clean (only 2 pre-existing errors remain in the untouched
  `CustomerDashboardPage.tsx`).
- `vite build`: succeeds.
- Dev server boot + page render: public app renders, **zero console errors** — provider and
  interceptor load correctly. The switcher's authenticated appearance needs a SUPER_ADMIN
  session (backend + DB + OTP email), not stood up in this environment.
