# Phase 4 — Admin Portal (zero Excel dependency)

**Status:** DONE (2026-06-04) — backend 11/11 tests green; frontend type-checks clean. Browser walkthrough pending (see Handover OUT).
**Depends on:** Phase 3 (ordering) — and Phases 1–2 for the data/engine.
**Parent spec sections:** §9 (APIs + admin views), §11 (Phase 4)
**Goal:** Every field that feeds the pricing engine is read AND write in-portal — no DB edits, no spreadsheet.

---

## Scope
**In (APIs, FastAPI under existing auth + `AuthorizationService`):**
- Catalog admin: `POST /products`, `PATCH /products/{id}`, `POST /products/{id}/components`, `PATCH /products/components/{id}`, `GET /products` (filter vendor/technology/financial_model).
- Pricing config: `PATCH /customers/{tenant_id}/commercial` (margin, opex_eligible, [credit fields stored but manual]), `POST /customers/{tenant_id}/price-overrides`, `GET/POST /financing-terms`.
- Per-SKU managed-service pricing grid (`/shop/services`) — reuse `managed_service_pricing_service` concept for `products` rows (carry MS price on the `MANAGED_SERVICE` component; see Phase 1/2 note that this is parallel to the legacy `catalog_items.managed_service_price` path).

**In (portal screens, §9):** Product list; Product editor (header + inline component grid); Managed-service pricing; Customer commercial config; Financing terms; Live price preview (reuses Phase 2 `/quotes/preview`).

**Out:** credit automation (Phase 6); bundles UI (Phase 5).

## Implementation steps
1. Product/component CRUD endpoints + repository.
2. Customer commercial config + price-overrides endpoints.
3. Financing-terms CRUD.
4. Frontend screens (React, `frontend/src/pages/...`) mirroring existing catalog/admin pages; wire live preview to `/quotes/preview`.
5. Tests: CRUD round-trips; permission enforcement; preview reflects edited cost/margin/leasing.

## Acceptance criteria
- [ ] Admin can create/edit a product + components and see the computed CAPEX/OPEX preview update.
- [ ] Customer margin / OPEX flag / overrides editable; effective price visible.
- [ ] Financing terms editable; drives the annuity.
- [ ] No engine input requires a DB edit.

## Handover IN  *(from Phases 1–3, 2026-06-04)*

**Everything the admin edits already feeds the live engine — no recompute wiring needed.** The pricing engine (`ComponentPricingService`) and the quote flow (`create_component_quote`) read straight from these tables, so admin edits take effect on the next preview/quote.

**Tables + models to CRUD**
- `products` / `product_components` → `app/models/product.py` (`Product`, `ProductComponent`). **Markup is one-per-SKU: `Product.margin_pct`** (the value the engine uses); `leasing_pct` per SKU drives the OPEX annuity. `product_components` carries `vendor_cost, msrp, uom, billing, interval, component_type, is_required, is_active, attributes` (capacity/consumes/flat_price).
- `customer_pricing` → `app/models/pricing.py` (`CustomerPricing`): `default_margin_pct`, **`opex_eligible`** (manual flag the OPEX gate checks), credit fields (manual for now).
- `customer_price_overrides` → per-customer special deal (`override_margin_pct` / `override_unit_price`).
- `financing_terms` → `app/models/financing.py`: the default `is_default` row (36mo/5%) drives the lease. Editing it changes every OPEX quote.

**Live preview to embed in the admin UI:** `POST /pricing/component-preview` (body `{product_id, financial_model, interval, selections}`) returns the full CAPEX/OPEX tree + totals (`one_time_total`, `monthly_total`, `recurring_total_at_interval`, `projected_term_cost`). This is the §9 "live price preview" screen — no new endpoint needed.

**Permissions:** existing pattern is `AuthorizationService(db).require(current_user, PERM_MANAGE_PRICING)` (see `app/routes/pricing.py`). Reuse / add perms for product CRUD.

**Managed-service caveat (from Phase 1/2):** the new `MANAGED_SERVICE` component (`MIX-MS`, $15.50) is parallel to the legacy `catalog_items.managed_service_price` + `managed_service_pricing_service` (which is design/BOM-driven). The `/shop/services` grid should edit the **component** price for MIX products; don't conflate with the legacy path.

**Open item to confirm before building margin UI:** none blocking — markup is one-per-SKU (`product.margin_pct`), confirmed by product owner 2026-06-04. The per-component / tenant-default layers exist in schema but are dormant; the admin UI should expose the single per-SKU markup (+ optional per-customer override).

## Handover OUT  *(completed 2026-06-04)*

**Backend** — `app/services/product_admin_service.py` (`ProductAdminService`): `list_products`, `get_product`, `create_product`, `update_product`, `add_component`, `update_component`, `list_financing_terms`, `create_financing_terms` (auto-unsets other defaults), `update_customer_commercial`, `upsert_price_override` (idempotent by tenant+product/component).
- **Routes** — products router (`app/routes/products.py`, registered in main.py): `GET /products` (filters vendor/technology/financial_model/is_active), `GET /products/{id}`, `POST /products`, `PATCH /products/{id}`, `POST /products/{id}/components`, `PATCH /products/components/{component_id}`. Pricing router additions (`app/routes/pricing.py`): `GET|POST /pricing/financing-terms`, `PATCH /pricing/customers/{tenant_id}/commercial`, `POST /pricing/customers/{tenant_id}/price-overrides`.
- **Permissions** — `PERM_VIEW_CATALOG` for product reads; `PERM_MANAGE_PRODUCTS` for product/component writes; `PERM_MANAGE_PRICING` for financing/commercial/overrides.
- **Schemas** — `app/schemas/products.py`. Validation: invalid enum values → 422; duplicate sku → 409; price override requires `product_id` or `component_id`.
- **Tests** — `tests/test_product_admin.py` (11), incl. `test_admin_edit_feeds_pricing_engine` (admin-created product prices correctly through `ComponentPricingService`), financing default-exclusivity, override idempotency.

**Frontend** (React+TS, type-checks clean)
- `src/types/products.ts`, `src/api/productsApi.ts`.
- `src/pages/AdminProductsPage.tsx` — catalog list + create product + inline component grid (edit cost/msrp/margin/billing/interval/req/active, save per row) + add component + **live price preview** (calls `/pricing/component-preview`). Covers §9 #1, #2, #6.
- `src/pages/AdminFinancingPage.tsx` — financing-terms list+create + per-tenant commercial config (margin, OPEX eligible, credit status/limit). Covers §9 #4, #5.
- Routes `/shop/admin/products`, `/shop/admin/financing` (`AppRouter.tsx`); nav links in `ShopShell.tsx` gated on `manage_products` / `manage_pricing`.

**Deviations / scope**
- **API paths** for financing/commercial are under the `/pricing` prefix (`/pricing/financing-terms`, `/pricing/customers/{tenant_id}/commercial`) rather than §9's bare `/financing-terms` / `/customers/...` — keeps them in the existing pricing router. Update the spec or rename if exact paths matter.
- **§9 screen #3** (standalone per-SKU managed-service grid at `/shop/services`) is NOT a separate page — the managed-service price is editable as a `MANAGED_SERVICE` component row in the product editor, which covers the need without a parallel screen.
- **Managed-service caveat** still applies: the component-row price is separate from the legacy `catalog_items.managed_service_price` / `managed_service_pricing_service` (design/BOM-driven) path.

**Verification done / pending**
- Done: backend 11 API tests; frontend `tsc -b` clean for all Phase 4 files.
- **Pending: browser walkthrough.** The admin screens are auth-gated (need a running backend+frontend and an admin user with `manage_products`/`manage_pricing`). Not exercised in a browser this session.

**Gotchas**
- `useAuth().accessToken` is `string | null` — guard `if (!accessToken) return;` before API calls (TS won't narrow otherwise).
- **Pre-existing build breakage:** `frontend/src/pages/CustomerDashboardPage.tsx` has 2 type errors (`MeResponse.name`, `created_at` vs `createdAt`) unrelated to Phase 4; they make `npm run build` fail repo-wide. Spawned a separate task to fix.
- To use the portal, grant the admin user the `manage_products` permission (new) via User Access; `manage_pricing` already exists.
