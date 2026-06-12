# Phase 7 — Unify on the Component Model: One Catalog, Per-Tenant Pricing, Bundling UI & Admin

**Handover for Claude Code.** Author: usdev@enidususa.com · Date: 2026-06-12
**Builds on:** phases 1–6 (component model, pricing engine, à-la-carte, admin portal, bundles, multi-tenant). Read `docs/plans/00-overview.md` and `phase-1`…`phase-4` first.

> **Decision (locked):** **Option A — unify everything onto the component model.** Migrate the legacy `catalog_items` table into `products` / `product_components`, move every surface (catalog, managed services, cart, quote, order) and every importer (CDW, PAPI, Excel, seeds) onto the component model, then retire `catalog_items`. One catalog table. This is a large, higher-risk rewrite of the shopping flow — sequence it safely (§3 order, §7 retirement).

---

## 0. TL;DR

Today there are **two catalogs**: the legacy flat `catalog_items` (one row = one price; powers the customer catalog, cart, quote, importers) and the new `products`/`product_components` component model (powers the admin + MIX seed + pricing engine). MIX is invisible to customers because the customer surface is still on the old table.

This phase makes the **component model the single source of truth**:
1. **Migrate** all legacy `catalog_items` → `products` (a flat device = a product with one `DEVICE` component; its managed-service price → a `MANAGED_SERVICE` component).
2. **Rewrite importers** (CDW/PAPI/Excel/seeds) to write `products`.
3. **Customer catalog + managed services** read `products`, **priced per tenant**.
4. **Cart → quote → order** carry `product`/`component` lines (not `catalog_item_id`).
5. **Bundling configurator popup** — "bundled" modal with checkboxes; required items locked, optional items uncheckable; live per-tenant repricing; capacity-enforced.
6. **Admin** = one grid (all SKUs), manager's columns, per-tenant markup + per-SKU override, PAPI read-only, **financing merged in**.
7. **Retire `catalog_items`** once everything is migrated and verified.
8. **SIM = one-time $30**; PAPI devices resold at PAPI price (zero margin); default 25% markup; default MS price $15.50.

---

## 1. Current state (verified 2026-06-12)

### Already built — reuse, don't rebuild

| Area | File | Notes |
|---|---|---|
| Component model | `backend/app/models/product.py` | `products`, `product_components`, `bundles`, `bundle_items`, `customer_price_overrides`. `margin_pct`/`leasing_pct` on product & component; `attributes.capacity`/`consumes`. |
| Multi-tenant financing | `backend/app/models/financing.py` | `financing_terms` per `tenant_id`, CellHub master fallback. |
| Pricing engine | `backend/app/services/component_pricing_service.py` | `price_product()` → per-tenant priced line tree (CAPEX/OPEX annuity, SIM flat-price, margin precedence, parent/child). |
| MIX seed | `backend/app/services/mix_seed.py` | Seeds MIX into `products`; wired into startup (`main.py`). SIM currently $40, margins 0.20 (both change below). |
| Admin product CRUD | `backend/app/routes/products.py`, `services/product_admin_service.py` | `/products` + components CRUD. |
| Pricing/commercial routes | `backend/app/routes/pricing.py` | `/pricing/financing-terms`, `/pricing/customers/{tenant}/commercial`, `/pricing/customers/{tenant}/price-overrides`, `/pricing/component-preview`. |
| Tenant context | `backend/app/middleware/tenant_context.py`, `frontend/src/api/activeTenant.ts` | SUPER_ADMIN sends `X-Tenant-Id`; `get_tenant_context().effective_tenant_id`. |
| Admin pages | `frontend/src/pages/AdminProductsPage.tsx`, `AdminFinancingPage.tsx`, `AdminManagedServicesPage.tsx` | Products page already lists products + component editor + live preview, scoped by tenant. |

### The legacy surface to migrate OFF `catalog_items`

| Surface | File(s) | Today |
|---|---|---|
| Customer catalog | `RoutersCatalogPage.tsx` → `commerceApi.getCatalog()` → `GET /catalog` → `catalog_service.list_items()` | reads `catalog_items`, raw price, no per-tenant pricing |
| Managed services (customer) | `ManagedServicesCatalogPage.tsx` | reads `catalog_items.managed_service_price` |
| Cart | `models/cart.py`, `cart_service.py` | `cart_lines.catalog_item_id` **NOT NULL FK → catalog_items** |
| Quote/Order | `quote_service.py`, `models/quote.py`/`order.py` | snapshot from catalog_items; legacy discount `PricingService` |
| Importers | `catalog_service.py` (`upsert_network_vendor_catalog`, `seed_partner_devices`, `seed_managed_services`, CDW/PAPI sync), `network_vendor_catalog_loader.py` | all upsert into `catalog_items` |
| Historical refs | `quote_lines`, `order_lines`, `cart_lines`, `assets`, `subscriptions` | carry `catalog_item_id` FKs |

---

## 2. Decisions (locked)

| # | Decision | Detail |
|---|---|---|
| D1 | Margin = markup on cost | `unit = cost × (1 + margin)`. |
| D2 | **Per-tenant, per-SKU markup override; 25% default** | Precedence: `override (tenant+SKU)` → `customer_pricing.default_margin_pct (tenant-wide)` → `products.margin_pct (SKU default)` → component margin → **0.25 global**. Changing a SKU's markup for one tenant affects only that tenant. |
| D3 | **UNIFY on the component model (Option A)** | Migrate `catalog_items` → `products`/`product_components`; all surfaces + importers move to `products`; retire `catalog_items` (§7). One catalog table. |
| D4 | Managed service = per-product `MANAGED_SERVICE` component | `/shop/admin/managed-services` edits the per-SKU default MS price; per-tenant markup applies on top. |
| D5 | Merge financing into `/shop/admin/products` | Fold `/shop/admin/financing` in; redirect the route. Manager's multi-row grid (§4). |
| D6 | **SIM = one-time $30, per-tenant editable** | `mix_seed` SIM/Backup `vendor_cost` 40 → 30, `billing='ONE_TIME'`, `flat_price`. Monthly excludes SIM → the §3 example becomes **$42.88/mo + $30 one-time**. Per-tenant price via `override_unit_price` (already beats `flat_price` in the engine). |
| D7 | Default 25% markup; default MS price $15.50 | `GLOBAL_DEFAULT_MARGIN = 0.25`; MIX MS components default $15.50, editable. |
| D8 | **PAPI = zero margin, read-only** | PAPI-sourced products (`attributes.source_type='paapi'`/vendor PAPI) resell at PAPI's exact price — **no markup applied, not editable**. Surface `price_editable: false`. (SIM is exempt — D6.) |
| D9 | **Bundling configurator popup** | On add-to-cart/configure, a "bundled" modal lists the product's components (and, for named bundles, the member products) with checkboxes: required = checked + locked; optional = uncheckable; qty steppers for `PER_LINE`/`PER_SEAT`; live per-tenant repricing; capacity-enforced. |
| D10 | **Product + components; components purchasable separately** | No named multi-product kits for go-live. A solution = a product + its components (handled by the popup, D9). Additionally, **individual components are sellable standalone** (à-la-carte): "add one more line" / "buy just a SIM" / "router only" without re-buying the whole product. A standalone line/SIM still respects `requires_component_type='DEVICE'` (attaches to the customer's existing device/contract). |

---

## 3. Workstreams

> **Safe order:** WS1 (migrate data + dual-write) → WS2 (pricing) → WS3 (catalog reads) → WS4 (cart/quote writes) → WS5 (bundling UI) + WS6 (admin) → WS7 (retire `catalog_items`). Don't drop the old table until WS7. Each task lists **files** + **acceptance criteria (AC)**.

### WS1 — Unify the data model: migrate + redirect importers

**Migration** (`backend/app/core/runtime_migrations.py` + a one-shot backfill in `catalog_service`/a `migrations` helper):
- For every active `catalog_items` row, upsert a `product`:
  - `vendor` ← item.vendor; `technology` ← `attributes.category`/product_type; `sku` ← item.sku; `vendor_sku` ← item.vendor_sku; `name`/`description` carry over; `attributes` carry over (`source_type`, `category`, etc.); `margin_pct = NULL` (inherit), except PAPI → mark `attributes.source_type='paapi'` so D8 applies.
  - one `DEVICE` (or appropriate type) `product_component`: `vendor_cost ← item.price`, `billing` from `billing_cycle` (ONE_TIME/RECURRING + interval), `uom=PER_DEVICE`.
  - if `item.managed_service_price` is set → a `MANAGED_SERVICE` component at that cost.
  - keep a mapping `catalog_item_id → product_id`/`component_id` (store on `product.attributes.legacy_catalog_item_id`) for historical-ref repointing in WS4/WS7.
- Idempotent (upsert by sku). Re-runnable.

**Importers → write `products`** (rewrite to upsert products/components instead of catalog_items): `catalog_service.upsert_network_vendor_catalog` (Excel/`network_vendor_catalog_loader.py`), `seed_partner_devices`, `seed_managed_services`, CDW sync, PAPI sync (`papi_client`/integrations). PAPI sync sets `source_type='paapi'` so pricing stays read-only (D8). `mix_seed` already writes products.
- **Dual-write window:** during WS1–WS3 keep the importers ALSO writing catalog_items (or keep catalog_items populated) so nothing breaks mid-migration. Stop dual-writing at WS7.

**Seed fixes** (`mix_seed.py`): SIM/Backup `vendor_cost` → `'30.00'` (D6); stop hardcoding `margin_pct=0.20` on products (set `None`, D2); keep `leasing_pct=0.05`; MS default $15.50 (D7).

**AC:** After startup, every former `catalog_items` SKU exists as a `product` (Meraki/Extreme/PAPI + MIX); PAPI products flagged; SIM cost 30; product margins null; managed-service costs present.

### WS2 — Pricing: one engine, per-tenant, PAPI zero-margin

`backend/app/services/component_pricing_service.py`:
- Margin precedence per D2; add `GLOBAL_DEFAULT_MARGIN = Decimal('0.25')` as the final fallback in `_resolve_margin`.
- Make `customer_pricing.default_margin_pct` **nullable** (null = inherit global 25%) via runtime migration; new tenants default null. (So "tenant hasn't customized" ≠ a real 0.)
- **PAPI zero-margin (D8):** if product `attributes.source_type=='paapi'` (or vendor PAPI), force margin 0 and ignore markup/overrides; return PAPI price as-is; set `price_editable=False` in output.
- Legacy discount `PricingService` (`pricing_service.py`) is retired from the live path once WS4 lands (keep only for reading historical quotes if needed).
- Update the pinned test: a tenant at 20% reproduces **$42.88/mo + $30 one-time** for the 90X1 (lease 19.78 + ctrl 9.30 + line 13.80, SIM one-time 30). Document in `phase-2-pricing-engine.md`.

**AC:** `/pricing/component-preview` returns per-tenant prices that change with `X-Tenant-Id`; PAPI products always same price, `price_editable=false`; default 25% when a tenant has no markup.

### WS3 — Customer catalog + managed services on `products` (per-tenant)

**Backend** — `GET /catalog` (rewrite `catalog.py`/`catalog_service.list_items`) returns **products** priced for `get_tenant_context().effective_tenant_id` via `ComponentPricingService` (headline CAPEX price + OPEX $/mo from required/default components). Managed-services feed = each sellable product's `MANAGED_SERVICE` component priced per tenant. Keep response shape compatible with the catalog cards (or update `types/commerce.ts`).

**Frontend** — `RoutersCatalogPage.tsx`, `ManagedServicesCatalogPage.tsx`, `commerceApi.ts`, `types/commerce.ts`: read the product-backed feed; show per-tenant price; respect the active tenant.

**AC:** `/shop/routers` shows MIX **and** migrated legacy SKUs at the tenant's price; switching active tenant reprices; PAPI items show fixed price. `/shop/services` shows per-tenant managed-service prices.

### WS4 — Cart → quote → order on `products`

**Schema** (`runtime_migrations.py` + models):
- `cart_lines`: add `product_id` (FK `products`) + `component_id` (FK `product_components`); make `catalog_item_id` **nullable**; CHECK exactly one source set. (After WS7, `catalog_item_id` is removed.)
- `quote_lines`/`order_lines`: verify `product_id`/`component_id` + component snapshot columns exist (phase-1/2); add if missing.
- **Historical refs:** existing quote/order lines already snapshot `name`/`sku`/`unit_price`, so make `catalog_item_id` nullable and keep old rows as-is (don't break history). `assets`/`subscriptions` similarly null the FK; repoint to product via the WS1 mapping where useful.

**Services:** `cart_service.add_line` accepts `product_id` + component selections; prices via `ComponentPricingService(tenant_id=...)`; stores the device parent + component children (via `applies_to_line_id`). `quote_service` converts cart product lines using the component engine; legacy `catalog_item` lines on the old path only for any not-yet-migrated data.

**Standalone components (D10):** `add_line` also accepts a **single `component_id`** (e.g. one extra voice line, or a SIM) to buy à-la-carte — "add one more line" / "router only" / "buy just a SIM". A standalone line/SIM with `requires_component_type='DEVICE'` attaches to the customer's existing device line/contract (validate it exists; enforce capacity). Pricing still flows through `ComponentPricingService` per tenant.

**AC:** Add a 90X1 (OPEX, 2 lines, SIM) → cart shows parent+children with per-tenant prices → quote totals match `component-preview` → order preserves the tree. Separately, adding a single extra line to an existing 90X1 contract creates one priced line (no new device), and is blocked if it would exceed the device's FXS capacity.

### WS5 — Bundling configurator popup (D9)

**Concept:** when a customer adds a product (or a named bundle) that has more than the bare device, open a **"Bundled" modal** before it lands in the cart.

**Frontend** — new component e.g. `frontend/src/components/BundleConfigurator.tsx`, used from `RoutersCatalogPage`/`RouterDetailsPage`:
- **Header:** product/bundle name + "This solution includes:".
- **Rows:** each `product_component` (and for named bundles each `bundle_item`/its components):
  - **required** (`is_required` / `bundle_item.is_removable=false`) → checkbox **checked + disabled**, lock icon.
  - **optional** → checkbox (default per `is_required`/`default_qty`), user can **uncheck** to drop it.
  - **qty stepper** for `PER_LINE`/`PER_SEAT` components.
  - per-line **per-tenant price** shown.
- **Live total:** on every check/qty change, call `POST /pricing/component-preview` with the current `selections` map → update CAPEX/OPEX totals in the modal.
- **Capacity guard (§5 of master plan):** enforce `consumes`/`capacity` (e.g. voice lines ≤ `fxs_port`); block/warn on overflow.
- **CAPEX/OPEX + Monthly/Annual** toggles in the modal (feed `financial_model`/`interval` to the preview).
- **Confirm** → add the assembled selection (device parent + checked children) to the cart (WS4).

**Backend:** none new — `/pricing/component-preview` already takes `{product_id, financial_model, interval, selections}` and returns the priced tree. For named bundles add a `bundle-preview` that expands `bundle_items` → products → components (optional; only if multi-product kits are used).

**AC:** Adding a 90X1 opens the modal showing Device + Cloud Controller (locked), Voice Line / SIM / Managed Service (optional, checked/unchecked), with a qty stepper on lines; unchecking the SIM drops $30 and the total updates live; adding a 9th line on one device is blocked (8 FXS ports); Confirm adds exactly the checked items.

### WS6 — Admin: one grid, manager's columns, per-tenant, financing merged

`AdminProductsPage.tsx` (+ `AppRouter.tsx`):
- **One grid of ALL products** (migrated legacy + MIX). Component products expand to one row **per component** (manager's §4 columns); flat migrated devices show as single rows.
- **Per-tenant scope** (tenant switcher / `X-Tenant-Id`) with two controls: tenant-wide markup → `PATCH /pricing/customers/{tenant}/commercial`; per-SKU-per-tenant override → `POST /pricing/customers/{tenant}/price-overrides` (`override_margin_pct` / `override_unit_price`).
- **PAPI rows read-only** on price (`price_editable=false`), tagged "PAPI-priced". SIM editable.
- Live per-tenant price column via `/pricing/component-preview`.
- **Merge financing (D5):** financing-terms section/tab here; remove/redirect `/shop/admin/financing`.

**Backend:** confirm `update_customer_commercial` accepts `default_margin_pct` (it does); price-override endpoint already targets product/component (legacy now ARE products, so no `catalog_item_id` needed post-unification).

**AC:** Super-admin picks a tenant, sees all SKUs in the manager's columns, sets a per-SKU markup for Meraki → only that tenant's catalog reprices; PAPI laptop not editable; financing managed on the same page; `/shop/admin/financing` gone.

### WS7 — Retire `catalog_items` (do last)

**Not in production → drop it directly** once migrated and verified; no archive-for-a-release window needed.
- Stop dual-writing; confirm all importers + surfaces write/read `products`.
- Make `cart_lines.catalog_item_id` / `quote_lines` / `order_lines` / `assets` / `subscriptions` FKs nullable (or repoint via the WS1 mapping); historical lines keep their name/sku/price snapshots so nothing is lost.
- Verify no code path still reads/writes `catalog_items`, then **drop** `catalog_items` (and legacy `list_prices` / discount `PricingService` if fully unused) in a cleanup migration.

**AC:** App runs with `catalog_items` dropped; no endpoint depends on it; historical quotes/orders still render from their snapshots.

### WS8 — Tests / verification

- Migration: every legacy SKU → product; PAPI flagged; counts match. (`test_catalog_unification_migration`.)
- Pricing precedence + PAPI zero-margin + 25% default. (`test_component_pricing_margin_precedence`, `test_papi_zero_margin`.)
- SIM one-time: 90X1 quote = $42.88/mo + $30 one-time at 20%. (update pricing test.)
- Catalog/managed-services reprice per tenant via `X-Tenant-Id`.
- Bundle configurator: optional uncheck drops price; capacity overflow blocked; confirm adds checked items only.
- Cart → quote → order for a product matches `component-preview`.
- Historical quotes/orders still render after `catalog_items` archived.
- No regression: existing orders/quotes/billing unaffected.

---

## 4. Manager's required columns (admin grid)

One row **per component** under each SKU (single row for flat migrated devices), columns from his Excel:

`Vendor` · `Area` (=`technology`) · `SKU` · `Component Type` · `Financial Engagement` (=`financial_model`) · `MSRP` · `Extended Price` (=`vendor_cost`) · `Device MRC` · `Per line` · `Margin %` · `Leasing %ge`

`Device MRC`/`Per line` render from the component's `vendor_cost` by `uom` (`PER_DEVICE`→Device MRC, `PER_LINE`→Per line). Add a derived **per-tenant price** column (CAPEX price + OPEX $/mo) from `component-preview`. Margin/Leasing editable per SKU & per component (PAPI rows read-only).

---

## 5. Risks & sequencing notes

- **Not in production**, so we can move directly — no real customer data to protect, the full buy-flow ships now, and `catalog_items` is dropped outright after migration + verification (no archive window). The dual-write window in WS1 is just to avoid breaking the app *mid-migration*, not a prod safety net.
- **Historical data:** quotes/orders already snapshot name/sku/price, so nulling `catalog_item_id` doesn't lose history — verify rendering before dropping.
- **Importers:** CDW/PAPI/Excel must be re-pointed to `products` *before* dropping `catalog_items`, or they'll recreate legacy rows.
- Suggested order: WS1–WS3 (+WS6) to get MIX **visible + priced + admin**; WS4–WS5 (buy-flow + bundling UI); WS7 last.

---

## 6. Open questions / assumptions

**All resolved:** unify on component model (Option A) ✅; SIM one-time $30 ✅; PAPI zero-margin read-only ✅; per-tenant per-SKU override, 25% default ✅; managed service per-product component ✅; default MS $15.50 ✅; bundling = configurator popup with uncheckable optional items ✅; no named multi-product kits — product + components, components individually purchasable (à-la-carte) ✅ (D10); **drop `catalog_items` directly — not in production, no archive-for-a-release window needed; full buy-flow (WS4) is in scope now** ✅; **PAPI devices will not carry a managed service**, so the MS-markup question is moot ✅.

No open questions — ready to hand off.
