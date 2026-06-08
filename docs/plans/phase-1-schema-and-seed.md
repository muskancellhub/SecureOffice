# Phase 1 — Schema & MIX Seed

**Status:** DONE (2026-06-04) — validated against live Postgres 16; 8/8 Phase 1 tests green.
**Depends on:** nothing (foundation phase)
**Parent spec sections:** §4 (data model), §10 (seed data), §11 (Phase 1)
**Goal:** Add the component-pricing schema with **zero behavior change**, and seed the real MIX Networks catalog. No pricing math yet (that's Phase 2) — this phase only stores costs/MSRP/margins/leasing inputs and the capacity metadata.

---

## Scope

**In:**
- New pg enums: `component_type`, `financial_model`, `component_uom`.
- New tables: `products`, `product_components`, `bundles`, `bundle_items`, `financing_terms`, `customer_price_overrides`.
- ALTERs on existing tables: `customer_pricing`, `tenant_onboarding`, `quotes`, `quote_lines`, `order_lines`.
- `catalog_service.seed_mix_products()` + one default `financing_terms` row (36 mo / 5%).
- Tests: schema loads; seed creates expected rows with expected cost/MSRP/capacity.

**Out (later phases):** any pricing computation, `/quotes/preview`, admin CRUD, bundle assembly logic, capacity *validation* (we only store capacity JSON here), credit checks.

---

## Pre-read (verified facts from codebase, 2026-06-04)

- `backend/app/models/catalog.py` — `catalog_items` (UUID pk via `gen_random_uuid()`, `Enum` types, `JSONB`, `TIMESTAMPTZ`).
- `backend/app/models/pricing.py` — `CustomerPricing` (pk `tenant_id`, `default_discount_pct NUMERIC(6,4) DEFAULT 0.30`), `ListPrice`, `DealPricing`.
- `backend/app/models/quote.py` / `order.py` — `quote_lines`/`order_lines` already have `parent_line_id` self-FK, `billing_type`(`billing`), `interval`, `list_price_snapshot`, `final_unit_price_snapshot`(`unit_price`), `catalog_item_id`; synonyms map snapshot cols.
- `backend/app/models/onboarding.py` — `tenant_onboarding` has `credit_validation_status`, `tax_validation_status`, `duns_number`, `tax_id`, payment fields, `onboarding_completed`.
- `backend/app/core/runtime_migrations.py` — `apply_runtime_migrations()` opens `engine.begin()` and runs idempotent `text(...)` statements. Pattern: `CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`.
- `backend/app/services/catalog_service.py` — `seed_partner_devices()` (l.303) and `seed_managed_services()` (l.229) build dict lists and call `self.repo.upsert_item(...)`, then `self.db.commit()`. Mirror this shape for `seed_mix_products()`.
- `backend/main.py` — calls `Base.metadata.create_all()` then `apply_runtime_migrations()` on startup. **Find where seeds are invoked** and add `seed_mix_products()` alongside.

---

## Implementation steps

### 1. ORM models for the new tables
Create `backend/app/models/product.py`:
- `Product` (table `products`) — columns per spec §4.2: `id, vendor, technology, sku (unique), vendor_sku, name, description, default_financial_model (Enum financial_model), margin_pct NUMERIC(6,4), leasing_pct NUMERIC(6,4), is_active, attributes JSONB, created_at, updated_at`. Index `(vendor, technology)`.
- `ProductComponent` (table `product_components`) — per §4.3: FK `product_id` (CASCADE), `component_type (Enum)`, `financial_model (Enum)`, `label`, `vendor_component_sku`, `vendor_cost NUMERIC(12,4)`, `msrp NUMERIC(12,2)`, `uom (Enum component_uom)`, `billing VARCHAR(16)`, `interval VARCHAR(16)`, `margin_pct`, `leasing_pct`, `default_qty`, `is_required`, `catalog_item_id` (FK SET NULL, nullable), `is_active`, `attributes JSONB`, timestamps. CHECK constraints on `billing`/`interval`.
- `Bundle`, `BundleItem` (tables `bundles`, `bundle_items`) per §4.4.
- `CustomerPriceOverride` (table `customer_price_overrides`) per §4.5, with the partial unique indexes.

Create `backend/app/models/financing.py`:
- `FinancingTerms` (table `financing_terms`) per §4.6.

Define the three enums as Python `str, enum.Enum` and wrap in SQLAlchemy `Enum(name='component_type', ...)` etc. **Let `create_all` emit `CREATE TYPE`** — do not hand-write it in migrations.

Register the new model modules wherever models are imported for `create_all` (check `backend/app/models/__init__.py` / `database.py` `Base`).

### 2. Extend EXISTING ORM models (new columns)
Add the spec §4.5/§4.7/§4.8 columns to the existing model classes so the ORM can read them:
- `pricing.py CustomerPricing`: `+default_margin_pct, credit_status, credit_limit, opex_eligible, credit_checked_at, credit_bureau_ref`.
- `onboarding.py TenantOnboarding`: `+legal_company_name, ein, business_registration_no, business_credit_bureau, business_credit_score, credit_check_result JSONB`.
- `quote.py Quote`: `+financial_model, subscription_interval`. `QuoteLine`: `+component_type, financial_model, product_id, component_id, cost_snapshot, margin_pct_snapshot, leasing_pct_snapshot, term_months`.
- `order.py Order`/`OrderLine`: same line-level additions as quote (Order header gets `financial_model`, `subscription_interval` too for parity).

### 3. runtime_migrations.py — ALTER existing tables (idempotent)
Append a clearly-commented block to `apply_runtime_migrations()`:
```
-- §4.5 customer_pricing margin + credit
ALTER TABLE customer_pricing ADD COLUMN IF NOT EXISTS default_margin_pct NUMERIC(6,4) NOT NULL DEFAULT 0.2000;
ALTER TABLE customer_pricing ADD COLUMN IF NOT EXISTS credit_status VARCHAR(16) NOT NULL DEFAULT 'PENDING';
... (credit_limit, opex_eligible DEFAULT FALSE, credit_checked_at, credit_bureau_ref)
-- §4.7 tenant_onboarding business-credit inputs
ALTER TABLE tenant_onboarding ADD COLUMN IF NOT EXISTS legal_company_name VARCHAR(255); ... etc
-- §4.8 quotes / quote_lines / order_lines snapshots
ALTER TABLE quotes ADD COLUMN IF NOT EXISTS financial_model VARCHAR(8) NOT NULL DEFAULT 'CAPEX'; ...
ALTER TABLE quote_lines ADD COLUMN IF NOT EXISTS component_type VARCHAR(32); ... etc
ALTER TABLE order_lines ADD COLUMN IF NOT EXISTS ... (mirror quote_lines)
```
Use `VARCHAR` for the snapshot enum-ish columns (matches existing snapshot convention — `quote_lines.billing` etc. are app-enums but snapshots stay loose). New-table creation is handled by `create_all`; do **not** duplicate it here (safety-net `CREATE TABLE IF NOT EXISTS` optional but redundant).

### 4. Seed — `catalog_service.seed_mix_products()`
Mirror `seed_partner_devices`. Because `upsert_item` writes `catalog_items`, add a small repo/helper to upsert into `products`/`product_components` (idempotent on `products.sku` unique + `(product_id, vendor_component_sku, component_type)`), or do ORM `merge`. Seed the rows in the table below, then commit. Also insert the default `financing_terms` row (`name='Standard 36-mo', term_months=36, annual_rate_pct=0.0500, subscription_interval='MONTH', is_default=TRUE`) if none exists.

Wire `seed_mix_products()` into startup next to the existing seed calls.

### 5. Tests — `backend/tests/test_mix_seed.py`
- App boot / `create_all` + `apply_runtime_migrations()` succeeds (no SQL errors).
- After `seed_mix_products()`: `products` has `90X1/90X2/90X2-NFR`; `90X1` has DEVICE `vendor_cost=550.00`, `msrp=675.00`, and a MAINTENANCE component `vendor_cost=7.75` `vendor_component_sku='SERV2158'`; `attributes.capacity == {"fxs_port":8,"lan_port":2,"wan_port":1,"max_sims":2}`.
- LINE_CHARGE components exist (SERV1970 11.50 PER_LINE, SERV1969 15.50 PER_LINE, SERV075 5.50 PER_SEAT).
- Seed is **idempotent** — running twice yields the same row counts.
- One default `financing_terms` row with `annual_rate_pct=0.05`, `term_months=36`.
- (No price math asserted here — Phase 2 owns 660/19.78/82.88.)

---

## MIX seed data (verified against the agreement, 2026-06-04)

All values confirmed from `MIX Networks Reseller Master Services Agreement.docx`. `vendor_cost` = "Customer Cost (Cash)".

### Products + DEVICE / MAINTENANCE components
| SKU | vendor_sku | technology | DEVICE cost | MSRP | MAINTENANCE MRC | maint sku | capacity |
|---|---|---|---|---|---|---|---|
| `90X1` | PROD7901 | POTS / Cellular Router | 550.00 | 675.00 | 7.75 | SERV2158 | `{fxs_port:8, lan_port:2, wan_port:1, max_sims:2}` |
| `90X2` | PROD2279 | POTS / Cellular Router | 280.00 | 365.00 | 5.75 | SERV2290 | `{fxs_port:8, lan_port:4, wan_port:1, max_sims:2}` |
| `90X2-NFR` | PROD2279-NFR | POTS / Lab | 240.00 | 0.00 | 5.75 | SERV2290-NFR | `{fxs_port:8, lan_port:4, wan_port:1, max_sims:2}` |

Accessories (DEVICE/ACCESSORY, CAPEX one-time): Power Inverter `PROD7933` 30.00; Power Supply `PROD7643` 22.00; Battery `PROD7956` 106.25.

### LINE_CHARGE / seat components (RECURRING, MONTH)
| component | vendor_sku | vendor_cost | uom | consumes |
|---|---|---|---|---|
| PIAB Voice Line (RJ-11) | SERV1970 | 11.50 | PER_LINE | `{fxs_port:1}` |
| PIAB Specialty Line (Fax/Alarm/Modem) | SERV1969 | 15.50 | PER_LINE | `{fxs_port:1}` |
| Hosted PBX Seat | SERV075 | 5.50 | PER_SEAT | — |
| Non-Continental DID add-on (AK/HI/PR) | SERV1986 | 3.50 (+3.50 NRC) | PER_LINE | — |

### INSTALLATION / PROFESSIONAL_SERVICES (ONE_TIME)
| component | vendor_sku | cost | uom |
|---|---|---|---|
| Staging/Kitting/Provisioning | SERV1987 | 40.00 | PER_DEVICE |
| On-site Installation | SERV1817 | 150.00/hr (2hr min) | PER_HOUR |
| Remote Install Assistance | SERV069 | 125.00/hr | PER_HOUR |
| Remote Training/Support | SERV049 | 500 setup + 200/hr | PER_HOUR |

### Ancillary (LICENSE/MANAGED_SERVICE — load inactive-by-default, RECURRING / PER_DID)
911 Services `SERV052` 0.59/mo/DID; Additional USA/Canada DID `SERV100` 0.20/mo (+0.50 NRC); Caller ID `SERV013` 2.00/mo; CNAM `SERV1990` 2.00 NRC; Call Recording `SERV077` 1.00/mo/seat; Toll-Free `SERV027` 1.50/mo.

### SIM / Managed Service
- **SIM / BACKUP_SIM** — sourced from PAPI, **$40 fixed final price, no margin** (Phase 2 special-case). Model as components on the product with `vendor_cost` carrying the $40 and `consumes={max_sims:1}`; mark the no-margin intent in `attributes` (e.g. `{"flat_price": true}`).
- **MANAGED_SERVICE** — per-SKU price; carry on the `MANAGED_SERVICE` component. (Wiring to the legacy `managed_service_price` path is Phase 2/3 — they are parallel mechanisms.)

### Vendor-level config (notes only — NOT per-quote math)
On `Product('90X1').attributes.vendor_terms` or a MIX note: wholesale revenue share 8.0% ($1–499,999) / 7.5% ($500k–999,999) / 7.0% ($1M+); $1,500 platform fee (waived if trained within 60 days); 100-line minimum after 6-mo ramp; $150 E911 penalty per unregistered-DID call. **The 100-line minimum is an account-level aggregate, NOT a per-assembly capacity rule** (see Phase 5).
- ℹ️ Data point: MIX's own financed hardware price (with credit approval) is 90X1 @ $591, 90X2 @ $303 — a *different* mechanism from our cost-plus-annuity; informational, not used by the engine.

---

## Acceptance criteria
- [ ] App boots; `create_all` + `apply_runtime_migrations()` run clean on a fresh DB and on a DB that already has the legacy tables.
- [ ] All new tables + enums exist; all ALTER'd columns present.
- [ ] `seed_mix_products()` is idempotent and produces the rows above.
- [ ] Default `financing_terms` row exists.
- [ ] Existing quote/order/pricing behavior is unchanged (legacy tests still green).

---

## Handover IN
*(none — first phase)*

## Handover OUT  *(completed 2026-06-04)*

**Module paths**
- `backend/app/models/product.py` — `Product`, `ProductComponent`, `Bundle`, `BundleItem`, `CustomerPriceOverride` + enums `ComponentType`, `FinancialModel`, `ComponentUom`.
- `backend/app/models/financing.py` — `FinancingTerms`.
- `backend/app/services/mix_seed.py` — seed data + `seed_mix_products(db) -> dict`.
- Registered in `backend/app/models/__init__.py`; ALTERs in `backend/app/core/runtime_migrations.py`; startup wiring in `backend/app/main.py` (after `seed_partner_devices`).

**Enums (stored as VARCHAR + CHECK, `native_enum=False` — matches quote.py/order.py; no pg `CREATE TYPE`)**
- `ComponentType` = DEVICE, CLOUD_CONTROLLER, LINE_CHARGE, MANAGED_SERVICE, SIM, BACKUP_SIM, INSTALLATION, PROFESSIONAL_SERVICES, MAINTENANCE, LICENSE, ACCESSORY
- `FinancialModel` = CAPEX, OPEX, BOTH
- `ComponentUom` = PER_DEVICE, PER_LINE, PER_SEAT, PER_HOUR, ONE_TIME, PER_DID

**New tables (created in BOTH `runtime_migrations` raw SQL AND ORM — see gotcha #1)**
- `products` (pk id; unique `sku`; `margin_pct`, `leasing_pct` NUMERIC(6,4); `attributes` JSONB holds `capacity` + `vendor_terms`).
- `product_components` (fk `product_id` CASCADE; `component_type`, `vendor_cost` NUMERIC(12,4), `msrp`, `uom`, `billing`, `interval`, `margin_pct`, `leasing_pct`, `default_qty`, `is_required`, `is_active`, `catalog_item_id` fk SET NULL, `attributes` JSONB; **unique `(product_id, component_type, vendor_component_sku)`** — the idempotency key).
- `bundles`, `bundle_items`, `financing_terms`, `customer_price_overrides` (partial unique indexes on tenant+product / tenant+component).

**ALTERs applied (idempotent `ADD COLUMN IF NOT EXISTS`)**
- `customer_pricing`: +`default_margin_pct`(0.2000), `credit_status`('PENDING'), `credit_limit`, `opex_eligible`(FALSE), `credit_checked_at`, `credit_bureau_ref`.
- `tenant_onboarding`: +`legal_company_name`, `ein`, `business_registration_no`, `business_credit_bureau`, `business_credit_score`, `credit_check_result`(JSONB).
- `quotes`: +`financial_model`('CAPEX'), `subscription_interval`. `orders`: same.
- `quote_lines` & `order_lines` (both): +`component_type`, `financial_model`, `product_id`(fk SET NULL), `component_id`(fk SET NULL), `cost_snapshot`(12,4), `margin_pct_snapshot`(6,4), `leasing_pct_snapshot`, `term_months`.

**Seed** — `CatalogService(db).seed_mix_products()` → returns `{'products':3,'components':46,'financing_terms':1}`. Idempotent (re-run = identical counts, verified). Each MIX product gets `margin_pct=0.20`, `leasing_pct=0.05`.
- SKUs: `90X1`, `90X2`, `90X2-NFR`. 90X1/90X2 carry 22 components each; 90X2-NFR carries only DEVICE+MAINTENANCE.
- Component lookup is by `vendor_component_sku`: `PROD7901`(DEVICE 550/675), `SERV2158`(MAINT 7.75 RECURRING/MONTH), `SERV1970`(11.50), `SERV1969`(15.50), `SERV075`(5.50), `SERV1986`(3.50), `PAPI-SIM`(40 flat), `PAPI-SIM-BACKUP`(40, inactive), `MIX-MS`(15.50), `SERV1987/1817/069/049`(install/pro-svc), `PROD7933/7643/7956`(accessories), and inactive ancillary `SERV052/100/013/1990/077/027`.
- Default `financing_terms`: `Standard 36-mo`, 36 mo, 0.0500, MONTH, `is_default=TRUE`.

**Deviations from plan**
1. **SIM modeled ONE_TIME at $40** (product-owner decision 2026-06-04, overriding §3's worked example which folded $40 into the monthly total). `attributes.flat_price=True`, `attributes.source='PAPI'`. Phase 2 skips margin for `component_type IN (SIM, BACKUP_SIM)` and bills it once. New OPEX 90X1 example: 42.88/mo + $40 one-time (was 82.88/mo).
2. **Service/line/SIM/MS/install/accessory/ancillary components are attached to each sellable device product** (90X1, 90X2), not modeled as standalone products. À-la-carte still works via `component_id` on a quote line.
3. **MANAGED_SERVICE seeded at $15.50 PER_DEVICE** with synthetic `vendor_component_sku='MIX-MS'` (manager's "~15.50"); admin-editable in Phase 4.
4. **Components requiring idempotency get a non-null `vendor_component_sku`** (SIM→`PAPI-SIM`, MS→`MIX-MS`) because Postgres treats NULL as distinct in the unique constraint.

**Gotchas**
1. `apply_runtime_migrations()` runs **before** `create_all()` (main.py:80-81). The FK ALTERs (`quote_lines.product_id REFERENCES products`) need the targets to exist at migration time → new tables are created in `runtime_migrations` too (raw SQL), with the ORM models as the query layer. `create_all` is then a `checkfirst` no-op for them. (Mirrors the existing `customer_pricing` convention.)
2. **Don't reorder startup.** `quotes/orders.public_id` server defaults use `nextval(seq)::regclass` — a DDL-time dependency — which is why migrations must precede `create_all`.
3. `vendor_cost`/`cost_snapshot` are NUMERIC(12,4) → come back as `Decimal`. Compare with `Decimal` in the engine/tests, never float.
4. **Pre-existing, unrelated:** 20 failures in `test_unified_catalog_and_bom.py` + `test_network_design_service.py` (`FakeItem` lacks `managed_service_price`) fail with or without Phase 1 — confirmed by stash test. Not introduced here.
