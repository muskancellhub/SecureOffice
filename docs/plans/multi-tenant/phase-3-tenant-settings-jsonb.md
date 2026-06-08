# Phase 3 — tenant_settings JSONB (soft toggles)  ✅ BUILT

Typed tables hold money/pricing/financing (Phases 0–1). Soft toggles —
design-ops prefs, managed-service category toggles, feature flags — go in one
JSONB-per-tenant row.

> **Status (built 2026-06-05):** shipped. See "What actually shipped" at the bottom.

## 1. Schema migration (`runtime_migrations.py`, append)

```sql
CREATE TABLE IF NOT EXISTS tenant_settings (
  tenant_id      UUID PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
  design_ops     JSONB NOT NULL DEFAULT '{}'::jsonb,   -- queue prefs, SLA defaults, auto-assign
  admin_services JSONB NOT NULL DEFAULT '{}'::jsonb,   -- managed-service category toggles
  feature_flags  JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- backfill one row per existing tenant
INSERT INTO tenant_settings (tenant_id)
SELECT id FROM tenants
WHERE NOT EXISTS (SELECT 1 FROM tenant_settings ts WHERE ts.tenant_id = tenants.id);
```

## 2. Model + repository + route

- `app/models/tenant_settings.py` — `TenantSettings` with three `JSONB` columns
  (`from sqlalchemy.dialects.postgresql import JSONB`), `Mapped[dict]`.
- `app/repositories/tenant_settings_repository.py` — `get_or_create(tenant_id)`, `update(tenant_id, patch)`.
- `app/routes/tenant_settings.py` — `GET /tenant-settings` and `PUT /tenant-settings`,
  both resolving tenant via `get_tenant_context` (Phase 0). Register in `main.py`.
- Schema in `app/schemas/tenant_settings.py`. **Validate** the JSONB shape in Pydantic
  (typed sub-models for `design_ops` / `admin_services` / `feature_flags`) rather than
  accepting arbitrary blobs, so the UI has a contract.

## 3. Wire the consumers

- **Design-ops queue** (`network_designs` ops views / `AdminDesignSubmissionsPage`):
  read `design_ops` (SLA defaults, auto-assign) for the active tenant.
- **Admin / managed services** (`AdminManagedServicesPage`, `catalog_items` are shared):
  per-tenant *visibility/toggles* live in `admin_services` — the catalog rows stay global,
  the tenant only flips which categories are enabled.

## 4. Clone-on-onboard (extend Phase 1's provisioning helper)

Add a `tenant_settings` insert (defaults) to `TenantProvisioningService.provision`.
Phase 1 said "skip if Phase 3 hasn't landed" — now it lands, so add it here and the
backfill above covers tenants created before this phase.

## Acceptance
- Each tenant has exactly one `tenant_settings` row (backfill + onboard cover all).
- `PUT /tenant-settings` with `X-Tenant-Id: <dell>` (SUPER_ADMIN) writes Dell's toggles only.
- Managed-services category toggles and design-ops SLA defaults differ per tenant and
  drive the respective admin pages.

## Gotchas
- Keep **money/pricing out of JSONB** — that's the hybrid decision. Only soft toggles here.
- JSONB partial updates: merge server-side (`existing || patch`) or read-modify-write in
  the repo; don't blind-overwrite the whole column from a partial PUT.
- Managed services: confirm whether a "disabled" category should hide catalog items at
  read time (filter in `catalog_service`) — that's the actual enforcement of the toggle.

---

## What actually shipped

### Backend
| File | Change |
|------|--------|
| `app/core/runtime_migrations.py` | `CREATE TABLE tenant_settings` (design_ops/admin_services/feature_flags JSONB + updated_at) + backfill one row per existing tenant. Appended after the Phase-1 financing block. |
| `app/models/tenant_settings.py` | **New** `TenantSettings` model (registered in `models/__init__.py`). |
| `app/repositories/tenant_settings_repository.py` | **New** `get_or_create`, `update(tenant_id, patch)` — replaces only the sections in `patch` (`SECTIONS = design_ops, admin_services, feature_flags`); never deep-merges. |
| `app/schemas/tenant_settings.py` | **New** typed sub-models `DesignOpsSettings{sla_default_days,auto_assign}`, `AdminServicesSettings{enabled_categories}`, response + `UpdateTenantSettingsRequest` (all sections optional). |
| `app/routes/tenant_settings.py` | **New** `GET`/`PUT /tenant-settings`, resolved via `get_tenant_context`, admin-gated. PUT replaces only sections present in the request (each stored complete via Pydantic defaults). Registered in `main.py`. |
| `app/services/tenant_provisioning_service.py` | `provision()` now also seeds a `tenant_settings` row. |
| `tests/test_tenant_settings.py` | **New** — get_or_create idempotency, section-scoped update, tenant isolation, provision seeding. |

### Frontend
| File | Change |
|------|--------|
| `frontend/src/types/tenantSettings.ts`, `frontend/src/api/tenantSettingsApi.ts` | **New** types + `getTenantSettings` / `updateTenantSettings`. |
| `frontend/src/pages/AdminManagedServicesPage.tsx` | New **"Service Category Availability"** panel — per-tenant checkboxes for the device category groups (network / security / end-user devices), saved to `admin_services.enabled_categories`. Loads/saves against the active tenant, re-loads on switch. |
| `frontend/src/pages/AdminDesignSubmissionsPage.tsx` | New **"Design Ops Settings"** panel — `sla_default_days` + `auto_assign`, saved to `design_ops`. Loads/saves against the active tenant, re-loads on switch. |

### Contract / decisions (read before Phase 4)
- **PUT replaces a whole section, not a deep merge.** The client sends the full section it
  edited; omitted sections are untouched (`exclude_unset` detects which were provided, then
  each is `model_dump()`-ed complete so it never persists half-set). Documented for the UI.
- **`admin_services.enabled_categories` is opt-out** — an absent key means *enabled*. So a
  fresh tenant (empty `{}`) has every category on.
- **Toggles are stored, not yet enforced.** The category-availability setting is persisted
  per tenant but nothing hides disabled categories at catalog read-time yet. Enforcement
  (filter in `catalog_service` / managed-service options) is a deliberate follow-up — see
  the Gotchas above. The design-ops settings are likewise stored for the ops queue to read.
- **Admin-gated, tenant-scoped:** route requires role ∈ {ADMIN, SUPER_ADMIN}; cross-tenant
  is still SUPER_ADMIN-only via `get_tenant_context`.
- **No `db/schema.sql` change** — `tenant_settings` lives in `runtime_migrations.py` like the
  other Phase 0–1 tables.

### Verification
- `pytest tests/test_tenant_settings.py` → 4 passed. Full suite: **20 failed / 94 passed / 0
  errors** (the 20 are the unchanged pre-existing `test_unified_catalog_and_bom` +
  `test_network_design_service` set).
- `tsc --noEmit`: Phase 3 files clean (only the 2 pre-existing `CustomerDashboardPage` errors).
- `vite build`: succeeds. App boots, admin route redirects to login, zero console errors.
  Rendering the panels needs a SUPER_ADMIN session (backend + DB + OTP email), not stood up here.
