# Secure Office — Catalog, Pricing Engine & Customer Ordering Flow

**Status:** Draft plan for review
**Author:** usdev@enidususa.com
**Date:** 2026-06-03
**Scope of this revision:** Seed **MIX Networks** products only. Existing Meraki / Extreme / SkyMirr / InHand / PAPI catalog rows are dummy data and stay as-is (not migrated into the new component model yet).

---

## 0. Review notes (added 2026-06-04, codebase cross-check)

The §3 pricing math was independently re-derived and **verified to the cent** (660 / 19.78 / 9.30 / 13.80 / 29.08 / 42.88 / 82.88); the amortizing-annuity (PMT) formula is correct. The data model (§4) and bundling design (§5) were checked against the actual backend. Five corrections, each also flagged inline below:

1. **Migration mechanism (§4.1, §11 Phase 1).** This repo has **no SQL migration runner and no Alembic.** Schema is applied via SQLAlchemy `Base.metadata.create_all()` (ORM models) plus idempotent raw SQL in `backend/app/core/runtime_migrations.py` on startup (that's where `customer_pricing`, `list_prices`, `managed_service_price` are actually created). `db/schema.sql` is a static baseline that doesn't even contain `catalog_items`. Phase 1's new enums/tables/ALTERs must go into `runtime_migrations.py` (and/or ORM models), and `CREATE TYPE` needs `DO $$ … IF NOT EXISTS` guards to stay idempotent on every boot.
2. **`convert_quote` copy loop (§4.8).** The new `quote_lines`/`order_lines` snapshot columns (`component_type, financial_model, product_id, component_id, cost_snapshot, margin_pct_snapshot, leasing_pct_snapshot, term_months`) are **not** carried by `parent_line_id` reuse. `convert_quote` copies a fixed field list (`quote_service.py:443-457`); it must be extended or the new columns are dropped order-side.
3. **Managed-service "reuse" is looser than stated (§10).** New MIX SKUs are `products`, not `catalog_items`, and the existing MS path is **design/BOM-driven** (`managed_service_pricing_service` reads `catalog_items.managed_service_price` for devices found in a network BOM, injected only when a `design_id` is passed). A standalone MIX product won't flow through it — the `MANAGED_SERVICE` component and the legacy MS service are parallel mechanisms ("reuse the column" ≠ "reuse the code").
4. **Engine-dispatch seam (§6).** Two pricing models now coexist on `customer_pricing` (legacy `default_discount_pct`, new `default_margin_pct`). The rule for choosing `pricing_service` (discount) vs `ComponentPricingService` (cost-plus) must be written down — natural switch: line references `product_id`/`component_id` → margin engine; references `catalog_item_id` → discount engine.
5. **`MIN` constraint is mis-filed (§5) and the "$19.25" footnote is mislabeled (§3).** See inline.

---

## 1. Goal

Turn the current flat, single-price-per-SKU catalog into a **catalog-driven pricing engine** that assembles any combination of devices, subscriptions, managed services, connectivity lines, SIMs and professional services into either:

- **CAPEX** — customer buys hardware outright (cost + margin, billed one-time), or
- **OPEX** — hardware is financed over a term (annuity lease) and recurring components bill monthly/annually.

Every cost element is a **Component Type row** rather than a hardcoded column, so new vendors/technologies are added by inserting rows, not by changing schema.

---

## 2. Current state (what already exists)

Read before designing — most of the manager's flow already has partial scaffolding.

| Area | Current implementation | File |
|---|---|---|
| Catalog | One `catalog_items` row per SKU: single `price`, single `billing_cycle` (ONE_TIME/MONTHLY/YEARLY), one nullable `managed_service_price`, `attributes` JSONB | `models/catalog.py` |
| Catalog ingest | XLSX loader for Meraki/Extreme/SkyMirr/InHand (devices only); `seed_partner_devices` for PAPI dummies | `services/network_vendor_catalog_loader.py`, `services/catalog_service.py` |
| Pricing | **Discount-off-list** model: `final = list × (1 − default_discount) × (1 − incremental_discount)` | `services/pricing_service.py`, `models/pricing.py` |
| Customer pricing | `customer_pricing(tenant_id, default_discount_pct=0.30)`; per-deal `deal_pricing(quote_id, incremental_discount_pct)`; per-tenant/item `list_prices` | `models/pricing.py` |
| Quote / Order lines | Already have `parent_line_id` self-FK (parent device + child services), `billing_type` (ONE_TIME/RECURRING), `interval` (MONTH/YEAR), `list_price_snapshot` + `final_unit_price_snapshot` | `models/quote.py`, `models/order.py` |
| Bundling at quote time | `quote_service` builds a parent router line + child service lines via `parent_line_id`; `convert_quote` copies the tree to order lines | `services/quote_service.py` |
| BOM | `network_bom_service` derives a BOM from a network design; `managed_service_pricing_service` computes per-device managed-service MRC | `services/network_bom_service.py`, `services/managed_service_pricing_service.py` |
| Onboarding | `tenant_onboarding`: `credit_validation_status`, `tax_validation_status`, `duns_number`, `tax_id`, payment fields, `onboarding_completed` | `models/onboarding.py` |
| Ordering lifecycle | `quotes → orders → contracts → subscriptions`, plus `workflow_instances/steps`, `assets`, `invoices`, `payments` | `db/schema.sql`, `models/lifecycle.py` |

### Gaps vs. the target model

1. **No component-type dimension** — a SKU can't carry Device + Cloud Controller + Line + Managed Service + SIM as separate priced rows.
2. **No CAPEX/OPEX financial model** — `billing_cycle` is not a financing model; there's no MSRP vs. cost separation, no margin %, no leasing %, no financing term/interest.
3. **Pricing math is discount-from-list, not cost-plus-margin + lease annuity** — the target requires markup on cost and an amortization formula for OPEX.
4. **No customer credit/OPEX config** — no credit status, credit limit, OPEX eligibility, or per-customer margin/overrides.
5. **No credit-gated product visibility** — CAPEX/OPEX options aren't filtered by credit result.
6. **No bundle definition layer** — solutions are assembled ad-hoc at quote time; there's no reusable "solution = N products" definition.

---

## 3. The MIX agreement is the Rosetta Stone

The manager's worked example **is** the MIX Networks `90X1` POTS-in-a-Box router. Every number in the notes comes straight out of `MIX Networks Reseller Master Services Agreement.docx`:

| Manager's notes | MIX agreement source | Value |
|---|---|---|
| SKU `P90X1` | `90X1` (PROD7901) | — |
| MSRP `672`/`675` | 90X1 MSRP | $675.00 |
| Extended Price / cost `550` | 90X1 "Customer Cost (Cash)" | $550.00/device |
| "Cloud Controller `7.75`, NOT calculated" | 90X1 **Maintenance Fee** (SERV2158) | $7.75/mo/device |
| Line Charge `11.50` | **PIAB Voice Line** (RJ-11) fee | $11.50/line/mo |
| Managed Service `15` | **PIAB Specialty Line** ($15.50) / MS tier | ~$15.50/line/mo |
| SIM / Backup SIM | **carrier SIM ordered from PAPI** — not a MIX SKU | **$40 fixed** (flat SIM line) |
| Leasing % `5` | financing interest rate input | 5% APR |
| Term 36 mo | financing term | 36 months |

**Reconciled OPEX math (verifies the engine formulas in §6):**

```
CAPEX sell      = cost 550 × (1 + margin 0.20)                      = 660.00
Lease MRC       = annuity(PV=660, annual 5%, n=36)
                = 660 × (0.05/12) / (1 − (1+0.05/12)^-36)           =  19.78   ✓
Cloud Ctrl MRC  = 7.75 × 1.20                                       =   9.30   ✓
Device OPEX     = 19.78 + 9.30                                      =  29.08   ✓
Line MRC        = 11.50 × 1.20                                      =  13.80   ✓
Device+Line     = 29.08 + 13.80                                     =  42.88   ✓
SIM (PAPI)      = 40.00 fixed                                       =  40.00
Customer MRC    = 42.88 + 40                                        =  82.88/mo ✓
                  ⚠️ SUPERSEDED 2026-06-04: SIM reclassified ONE-TIME (see note below)
```

The OPEX device monthly resolves to $19.78 using a 36-month **amortizing annuity (PMT)** at 5%. ✅ **Confirmed by the manager's Excel**, which shows "Opex model $19.78" derived from 660 / 5% / 36 — the PMT annuity matches to the cent. SIM is a flat **$40** line in his sheet (→ $82.88 total).

> **Implementation note (2026-06-04):** During Phase 2 the product owner reclassified the **SIM as a ONE-TIME $40 charge** (a SIM card is bought once), not a monthly line. The engine therefore produces, for the 90X1 OPEX example: **42.88/mo recurring (lease 19.78 + controller 9.30 + line 13.80) + $40 one-time**, rather than the $82.88/mo shown above. The device lease/controller/line figures are unchanged. CAPEX becomes $700 one-time (device 660 + SIM 40) + 23.10/mo.

> **Review note (2026-06-04):** The "$19.25" alternative cited here and in §3a #4 is **mislabeled** — it is not "flat add-on interest." $19.25 = `660 × 1.05 / 36` (apply 5% once, then spread over 36). A genuine simple-interest schedule (5%/yr × 3 yr = 15% total ÷ 36) gives **$21.08/mo**. The conclusion is unaffected — the annuity ($19.78) is correct — but the strawman figure should be relabeled "5% flat fee ÷ term" to avoid confusion.

**Reseller economics (MIX MSA — ⚠️ NOT discussed by manager; vendor-side context only):**

- MIX takes a wholesale cut of customer base billing revenue: **8.0%** ($1–$499,999/mo), **7.5%** ($500k–$999,999), **7.0%** ($1M+). This is *our* cost-of-revenue on recurring services — our margin sits on top of MIX's wholesale rate.
- Platform & Branding Fee $1,500 (waived if training completed within 60 days).
- Minimum 100 activated PIAB lines after a 6-month ramp.
- E911 misconfig penalty: $150/call for unregistered DIDs.

These belong in vendor-level config/notes, not the per-quote engine, but they bound how low margins can go on MIX recurring services.

---

## 3a. Decision log — confirmed vs. assumed (manager recordings, 2026-06-03)

Provenance for every design decision, so we don't build on guesses. **CONFIRMED** = stated by the manager in the recordings. **NOT DISCUSSED** = absent from recordings; our proposal pending sign-off. **OUR DESIGN** = engineering addition the manager never raised.

| # | Topic | Status | Resolution |
|---|---|---|---|
| 1 | Margin = markup on cost (not discount off MSRP) | **CONFIRMED** | `cost × (1 + margin)`. 550×1.2=660, 7.75×1.2=9.30, 11.5×1.2=13.80. |
| 2 | Margin is **per-tenant per-SKU** | **CONFIRMED** | Every customer can have a different margin on the same SKU. Drives §4.5 / §6 precedence (customer margin wins). |
| 3 | Leasing % is admin-configurable, **per-SKU** | **CONFIRMED** | "another column is leasing percentage… admin will configure this." Manager's Excel has `Leasing %ge` as a per-SKU column → lives on the product/SKU row, not per-customer. |
| 4 | OPEX financing = 36-mo amortizing **annuity (PMT)** @ 5% | **CONFIRMED (via Excel)** | Manager's sheet computes "Opex model $19.78" from 660 / 5% / 36. PMT annuity = $19.78 to the cent. So the formula is the amortizing annuity. (The "$19.25" alternative once cited here is `660×1.05/36`, not flat add-on interest — see §3 review note.) |
| 5 | Annual subscription triggers recalculation; **annual = monthly × 12 for now** | **CONFIRMED** | "If annual… recalculate." No annual discount for now — annual = monthly × 12. Revisit if MIX gives an annual rate. |
| 6 | Credit FAIL → CAPEX only | **CONFIRMED** | OPEX not offered on fail. Hidden vs visible-disabled NOT specified. |
| 7 | **Credit-checking layer is out of scope for now** | **CONFIRMED (descoped)** | Manager: don't build the credit layer yet. §7 is deferred; OPEX eligibility handled by a manual admin flag in the interim. |
| 8 | Managed Service is its own Component Type, **price per SKU** | **CONFIRMED** | Admin sets the managed-service price per SKU in `/shop/services` (reuses existing `catalog_items.managed_service_price`). |
| 9 | SIM from **PAPI**, **$40 final price** | **CONFIRMED** | Excel adds a flat `40` SIM line (→ $82.88). $40 is the **final customer price — no margin applied on top** (for now). Backup SIM optional (1 or 2 SIMs). |
| 13 | Margin can be set **per-component within a SKU** | **CONFIRMED** | Not just one rate per SKU — a SKU may carry different margins per component (device vs. line vs. subscription). `product_components.margin_pct` is the per-component override. |
| 10 | À-la-carte assembly is the core requirement | **CONFIRMED** | "Each line item can be a separate product… someone wants only a line." No predefined kit catalog was discussed. |
| 11 | Confirmed component types | **CONFIRMED (partial)** | Only `Device`, `Subscription`, `LineCharge` were explicit. Cloud Controller/SIM/Install/Maintenance/etc. are our generalization (manager's written notes §5 list them, but recordings did not). |
| 12 | Bundling + capacity rules (named kits, port/SIM caps), accessories, MSA commercial terms | **OUR DESIGN / TEAM-REQUESTED** | Manager didn't raise these in recordings, but **bundling is now in scope per the team** (Phase 5). Generic `capacity`/`consumes` model (§5). Specific cap values + overflow behavior are our call (default block + warn). |

---

## 4. Target data model

Design principle: **`products` (SKU header) → `product_components` (priced component rows) → `bundles` (groups of products)**. This is the manager's `Vendor → Technology → SKU → Component Type → Financial Model` hierarchy, normalized.

We **keep `catalog_items` intact** (legacy/dummy devices, BOM lookups, existing FKs from `quote_lines.catalog_item_id`). New MIX products live in the new tables. A `product_components.catalog_item_id` nullable link lets a component point at a real hardware record when one exists; pricing reads from the component row regardless.

### 4.1 New enums

```sql
CREATE TYPE component_type AS ENUM (
    'DEVICE', 'CLOUD_CONTROLLER', 'LINE_CHARGE', 'MANAGED_SERVICE',
    'SIM', 'BACKUP_SIM', 'INSTALLATION', 'PROFESSIONAL_SERVICES',
    'MAINTENANCE', 'LICENSE', 'ACCESSORY'
);

CREATE TYPE financial_model AS ENUM ('CAPEX', 'OPEX', 'BOTH');

-- How a component's cost scales when assembled into a quote
CREATE TYPE component_uom AS ENUM (
    'PER_DEVICE', 'PER_LINE', 'PER_SEAT', 'PER_HOUR', 'ONE_TIME', 'PER_DID'
);
```

### 4.2 `products` — the SKU header (Vendor → Technology → SKU)

```sql
CREATE TABLE products (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vendor          VARCHAR(128) NOT NULL,            -- 'MIX Networks'
    technology      VARCHAR(128) NOT NULL,            -- 'POTS / SD-WAN', 'Voice', ...
    sku             VARCHAR(128) NOT NULL UNIQUE,      -- '90X1'
    vendor_sku      VARCHAR(128),                      -- 'PROD7901'
    name            VARCHAR(255) NOT NULL,
    description     VARCHAR(1024),
    default_financial_model financial_model NOT NULL DEFAULT 'BOTH',
    margin_pct      NUMERIC(6,4),                      -- SKU baseline margin (e.g. 0.25); customer margin overrides per tenant
    leasing_pct     NUMERIC(6,4),                      -- per-SKU OPEX financing rate (manager's 'Leasing %ge' column; e.g. 0.05)
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    attributes      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_products_vendor_tech ON products (vendor, technology);
```

### 4.3 `product_components` — the priced Component Type rows

Replaces hardcoded columns. One product owns many components. A standalone purchase is just a product with a single `DEVICE` (or single `LINE_CHARGE`) component.

```sql
CREATE TABLE product_components (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id         UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    component_type     component_type NOT NULL,
    financial_model    financial_model NOT NULL DEFAULT 'BOTH',
    label              VARCHAR(255) NOT NULL,            -- 'POTS-in-a-Box 90X1 router'
    vendor_component_sku VARCHAR(128),                   -- 'SERV2158' (maintenance), etc.
    vendor_cost        NUMERIC(12,4) NOT NULL,           -- 550.00, 7.75, 11.50 ...
    msrp               NUMERIC(12,2),                    -- 675.00 (nullable)
    uom                component_uom NOT NULL DEFAULT 'PER_DEVICE',
    billing            VARCHAR(16) NOT NULL DEFAULT 'ONE_TIME', -- ONE_TIME | RECURRING
    interval           VARCHAR(16),                      -- MONTH | YEAR (null if ONE_TIME)
    -- Optional per-component overrides; if NULL, fall back to SKU/customer policy.
    margin_pct         NUMERIC(6,4),                     -- e.g. 0.2000
    leasing_pct        NUMERIC(6,4),                     -- annual interest for OPEX financing
    default_qty        INTEGER NOT NULL DEFAULT 1,
    is_required        BOOLEAN NOT NULL DEFAULT TRUE,     -- required vs optional add-on
    catalog_item_id    UUID REFERENCES catalog_items(id) ON DELETE SET NULL,
    is_active          BOOLEAN NOT NULL DEFAULT TRUE,
    attributes         JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT pc_billing_check CHECK (billing IN ('ONE_TIME','RECURRING')),
    CONSTRAINT pc_interval_check CHECK (interval IS NULL OR interval IN ('MONTH','YEAR'))
);
CREATE INDEX idx_product_components_product ON product_components (product_id);
CREATE INDEX idx_product_components_type ON product_components (component_type);
```

This is exactly the manager's recommended catalog row: `Vendor | Area(Technology) | SKU | Component Type | Financial Model | MSRP | Extended Price(vendor_cost) | Margin % | Leasing %` — with `per-line`/`per-device` handled by `uom` instead of separate "Device MRC / Per Line" columns.

### 4.4 `bundles` — reusable complete solutions (groups of products)

A "complete solution" (Router + Firewall + SD-WAN + Switch + AP + Controller + Line + SIM + Install) is a bundle of products; each product carries its own components. Standalone = order a single product, skip the bundle.

```sql
CREATE TABLE bundles (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sku          VARCHAR(128) NOT NULL UNIQUE,    -- 'SOL-POTS-STARTER'
    name         VARCHAR(255) NOT NULL,
    vendor       VARCHAR(128),
    technology   VARCHAR(128),
    description  VARCHAR(1024),
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    attributes   JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE bundle_items (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bundle_id    UUID NOT NULL REFERENCES bundles(id) ON DELETE CASCADE,
    product_id   UUID NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    default_qty  INTEGER NOT NULL DEFAULT 1,
    is_optional  BOOLEAN NOT NULL DEFAULT FALSE,   -- shown but unchecked by default
    is_removable BOOLEAN NOT NULL DEFAULT TRUE,     -- can customer drop it
    sort_order   INTEGER NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (bundle_id, product_id)
);
CREATE INDEX idx_bundle_items_bundle ON bundle_items (bundle_id);
```

### 4.5 Customer commercial config (margin, credit, OPEX eligibility, overrides)

Extend the existing per-tenant pricing. We **add a margin model alongside** the legacy discount model rather than ripping it out (legacy CDW catalog still uses discount).

```sql
-- Option A: extend existing customer_pricing
ALTER TABLE customer_pricing
    ADD COLUMN default_margin_pct NUMERIC(6,4) NOT NULL DEFAULT 0.2000,
    ADD COLUMN credit_status     VARCHAR(16) NOT NULL DEFAULT 'PENDING', -- PENDING|PASS|FAIL
    ADD COLUMN credit_limit      NUMERIC(12,2),
    ADD COLUMN opex_eligible     BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN credit_checked_at TIMESTAMPTZ,
    ADD COLUMN credit_bureau_ref VARCHAR(128),
    ADD CONSTRAINT cp_credit_status_check CHECK (credit_status IN ('PENDING','PASS','FAIL'));

-- Per-customer price overrides (manager's "Pricing Overrides")
CREATE TABLE customer_price_overrides (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    product_id    UUID REFERENCES products(id) ON DELETE CASCADE,
    component_id  UUID REFERENCES product_components(id) ON DELETE CASCADE,
    override_margin_pct NUMERIC(6,4),     -- override margin for this product/component
    override_unit_price NUMERIC(12,2),    -- hard price override (wins over margin)
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT cpo_target_check CHECK (product_id IS NOT NULL OR component_id IS NOT NULL)
);
CREATE UNIQUE INDEX uq_cpo_tenant_component ON customer_price_overrides (tenant_id, component_id) WHERE component_id IS NOT NULL;
CREATE UNIQUE INDEX uq_cpo_tenant_product   ON customer_price_overrides (tenant_id, product_id)   WHERE product_id IS NOT NULL;
```

### 4.6 Financing terms (OPEX lease config; annual vs monthly)

```sql
CREATE TABLE financing_terms (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(128) NOT NULL,           -- 'Standard 36-mo'
    term_months     INTEGER NOT NULL DEFAULT 36,
    annual_rate_pct NUMERIC(6,4) NOT NULL DEFAULT 0.0500,  -- the manager's leasing %
    subscription_interval VARCHAR(16) NOT NULL DEFAULT 'MONTH', -- MONTH | YEAR
    is_default      BOOLEAN NOT NULL DEFAULT FALSE,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Annual vs monthly subscription (§21 of notes) is handled by selecting the matching `financing_terms` row + recomputing recurring components at the chosen `interval` (annual recurring = monthly × 12 unless a distinct annual rate card row exists).

### 4.7 Onboarding extension (business credit inputs — no card required)

Add the business-credit identifiers the credit check consumes. Keep on `tenant_onboarding` (already holds `tax_id`, `duns_number`).

```sql
ALTER TABLE tenant_onboarding
    ADD COLUMN legal_company_name      VARCHAR(255),
    ADD COLUMN ein                     VARCHAR(32),
    ADD COLUMN business_registration_no VARCHAR(64),
    ADD COLUMN business_credit_bureau  VARCHAR(64),   -- 'D&B' | 'Experian'
    ADD COLUMN business_credit_score   INTEGER,
    ADD COLUMN credit_check_result     JSONB NOT NULL DEFAULT '{}'::jsonb;
```

Per §19, **no credit card is required** — creditworthiness is derived from EIN / Tax ID / business registration / legal name / business credit bureau.

### 4.8 Quote/Order line snapshots (carry the financial model)

Add snapshot columns so a quote is reproducible even if catalog/margins change later.

```sql
ALTER TABLE quote_lines
    ADD COLUMN component_type    VARCHAR(32),       -- snapshot of component_type
    ADD COLUMN financial_model   VARCHAR(8),        -- CAPEX | OPEX
    ADD COLUMN product_id        UUID REFERENCES products(id) ON DELETE SET NULL,
    ADD COLUMN component_id      UUID REFERENCES product_components(id) ON DELETE SET NULL,
    ADD COLUMN cost_snapshot     NUMERIC(12,4) NOT NULL DEFAULT 0,
    ADD COLUMN margin_pct_snapshot  NUMERIC(6,4) NOT NULL DEFAULT 0,
    ADD COLUMN leasing_pct_snapshot NUMERIC(6,4),
    ADD COLUMN term_months       INTEGER;
-- identical ALTERs on order_lines

ALTER TABLE quotes
    ADD COLUMN financial_model   VARCHAR(8) NOT NULL DEFAULT 'CAPEX', -- CAPEX|OPEX|MIXED
    ADD COLUMN subscription_interval VARCHAR(16);                      -- MONTH|YEAR (OPEX)
```

`parent_line_id` (already present) groups a bundle/solution: the device line is the parent, its controller/line/managed/SIM components are children — no new *tree* structure needed for bundle representation in a quote.

> **Review note (2026-06-04):** "No new structure" applies to the tree only. The new snapshot columns above (`component_type, financial_model, product_id, component_id, cost_snapshot, margin_pct_snapshot, leasing_pct_snapshot, term_months`) are **not** propagated by the existing tree copy — `convert_quote` copies a fixed field list (`quote_service.py:443-457`) and must be extended to carry them, or they are lost when a quote converts to an order.

---

## 5. Bundling — how it works

Three layers, each independently sellable:

1. **Component** (`product_components`) — smallest priced unit (a maintenance fee, one PIAB line, one SIM). Sold standalone via "add one additional line" → add a `LINE_CHARGE` component line to an existing order/contract.
2. **Product** (`products`) — a SKU with ≥1 component. Buying "just a router" = order the `90X1` product with only its `DEVICE` (+ required `MAINTENANCE`) components; optional components unchecked.
3. **Bundle** (`bundles` + `bundle_items`) — a named solution referencing N products with default quantities and optional/removable flags. Selecting a bundle expands to its products → components, each becoming a quote line tree.

**Assembly rules**

- Expanding a bundle into a quote: for each `bundle_item` → instantiate the product → for each active `product_component` matching the chosen `financial_model`, create a quote line. The device/primary component is the **parent**; controller/line/managed/SIM components reference it via `parent_line_id`.
- `is_optional` components/products render unchecked; `is_removable=false` cannot be dropped (e.g. mandatory device maintenance).
- **Add-on / change-of-quantity** (notes §2: "2 → 3 lines"): a standalone `LINE_CHARGE` component appended to the existing contract; the pricing engine recomputes only the delta line (no need to re-quote the device lease).
- A bundle's price is never stored — it's always recomputed from current component costs × margin/financing so customer-specific margins and credit-driven CAPEX/OPEX apply consistently.

### Composition & compatibility rules

Membership is explicit, admin-curated data — `bundle_items` (which products form a solution) and `product_components` (which components form a product) — never inferred from text. Assembly also enforces hard constraints, modeled **generically** so any device and any resource works without schema changes (a device only declares the properties it actually has).

**Capacity = provide / consume.** A device declares the resources it offers; a component declares what it consumes. Stored as JSONB maps to start (promote to a table later if you need reporting):

```
products.attributes.capacity           = {"fxs_port": 8, "lan_port": 2, "max_sims": 2}   # 90X1
product_components.attributes.consumes = {"fxs_port": 1}                                  # one voice line
```

Each device declares only the keys it has — a data-only router omits `fxs_port`, a switch brings `poe_watt`, a cloud controller brings `device_slots`. A new device or a brand-new resource dimension is **data, not code**.

Validator (resource-agnostic; **missing key = 0**, so "this device doesn't have that resource" is enforced too):

```python
def check_capacity(parent, child_lines):
    provided = parent.capacity or {}
    used = defaultdict(int)
    for line in child_lines:
        for res, amt in (line.consumes or {}).items():   # consumes is optional
            used[res] += amt * line.qty
    return [Violation(res, used[res], provided.get(res, 0))
            for res, total in used.items() if total > provided.get(res, 0)]
```

One function covers all cases: 90X1 + 9 voice lines (8 < 9 → over capacity); a voice line dropped on a port-less router (provides 0 → rejected); install / managed-service children that consume nothing (always pass).

**Three property buckets** — a device fills only the ones that apply:

- *Capacity resources* (balanced by the validator): `capacity` / `consumes` — ports, SIM slots, PoE watts, device-slots.
- *Descriptive specs* (no validation, ignored by the engine): plain `attributes` — Wi-Fi standard, throughput, dimensions.
- *Compatibility flags* (works-with): e.g. `accessory_for_skus` on optional accessories.

**Constraint types** beyond a max cap, each `(resource_key, type, value)`:

- `MAX` — Σ consumed ≤ provided (ports, seats).
- `MIN` — floor, e.g. a per-assembly minimum (Σ seats ≥ N within one solution). ⚠️ **Review note (2026-06-04): the MIX 100-line minimum is NOT this kind of rule.** It's an account-level vendor commitment aggregated across *all* contracts over a 6-month ramp — `check_capacity` only sees one parent + its children in a single quote and cannot evaluate it. The 100-line minimum belongs in vendor-level config (where §3 and the §10 vendor-terms note already file it), enforced by an account-wide aggregate check, not the per-assembly capacity validator.
- `COMPAT` — boolean fitment.

Start with JSONB; promote to a generic `product_constraints(product_id | component_id, resource_key, constraint_type, value)` table when you want admin grids or cross-product queries.

**Other assembly rules:**

- *Requires-a-device* — a `LINE_CHARGE` (PIAB line, SERV1970/1969) or `SIM` can't stand alone; it must attach to a parent device line (`component.attributes.requires_component_type = 'DEVICE'`, enforced by requiring a `parent_line_id`).
- *Quantity scaling* — children scale from `uom` + parent: `PER_DEVICE` (maintenance, SIM) follows device qty, `PER_LINE` follows line count, `PER_SEAT` follows seats.
- *Optional / removable* — `is_optional` renders unchecked; `is_removable = false` can't be dropped (mandatory maintenance).

Validation runs server-side in the quote-assembly / add-on endpoints, so the client can't bypass caps or dependencies. ⚠️ The specific cap **values** and overflow **behavior** (block vs. auto-add a second device) are OUR design — the manager didn't specify them (§3a #12); default is **block + warn**.

---

## 6. Pricing engine

A single service (`ComponentPricingService`) computes a unit price for any component given `(component, financial_model, customer_config, financing_terms, overrides)`.

### Inputs resolution order (per component)

1. `customer_price_overrides.override_unit_price` → use directly (skip math).
2. margin — **customer margin wins, then most-specific catalog margin** (CONFIRMED: per-tenant per-SKU, and margin can vary per-component within a SKU). Resolve first non-null:
   `customer_price_overrides.override_margin_pct` (this tenant + this SKU/component)
   `?? customer_pricing.default_margin_pct` (this tenant's default tier — e.g. A=20%, B=15%)
   `?? product_components.margin_pct` (per-component baseline — device vs. line vs. subscription)
   `?? products.margin_pct` (SKU baseline — e.g. 25%).
   A customer-specific margin always overrides the catalog; within the catalog, a per-component margin overrides the SKU baseline.
   **Exception — SIM:** the PAPI SIM is billed at its **$40 final price; no margin is applied** (for now).
3. leasing rate = `products.leasing_pct` (per-SKU, the manager's `Leasing %ge` column) `?? financing_terms.annual_rate_pct` default; `term_months` from `financing_terms`. Formula = amortizing annuity (✅ confirmed via Excel).

### CAPEX (one-time)

```
sell_unit = round( vendor_cost × (1 + margin), 2 )      # 550 × 1.20 = 660.00
line_total = sell_unit × qty                            # billed ONE_TIME
```

### OPEX

**Financed (DEVICE / one-time components turned into a lease)** — ✅ amortizing annuity (PMT), confirmed by the manager's Excel ($19.78 from 660 / 5% / 36):

```
financed_principal = vendor_cost × (1 + margin)         # 660.00
r = annual_rate / 12                                    # 0.05/12   (annual_rate = admin-configurable leasing %)
lease_mrc = financed_principal × r / (1 − (1+r)^(−term_months))   # 19.78  (amortizing annuity)
```

**Recurring components (controller, line, managed service, SIM):**

```
mrc_unit = round( vendor_cost × (1 + margin), 2 )       # 7.75×1.2=9.30, 11.50×1.2=13.80
```

**Device OPEX bundle MRC** = lease_mrc + Σ(required recurring component MRCs).
**Customer MRC** = Σ all selected recurring lines (including SIMs).
**Projected term cost** = `one_time_total + monthly_total × term_months` (extend existing `projected_12_month_cost`, or add `projected_term_cost`).

### Annual vs monthly (notes §21)

Manager CONFIRMED that choosing **Annual** must **recalculate CAPEX and OPEX**, and that **annual = monthly × 12 for now** (no annual discount). Recurring lines bill at `interval = YEAR` = 12 × the monthly MRC; the engine recomputes all lines on toggle — no stored prices to invalidate. Leave room in `financing_terms` for a distinct annual rate later if MIX offers one.

### Rounding

Keep the existing `Decimal` + `ROUND_HALF_UP` to 2 dp money / 4 dp pct convention from `pricing_service.py`. `vendor_cost` is `NUMERIC(12,4)` so sub-cent vendor rates (e.g. $0.0085/min usage) survive; round only at the line total.

---

## 7. Credit check & OPEX eligibility gating — ⚠️ DEFERRED (out of scope this revision)

**Manager CONFIRMED: do not build the credit-checking layer yet.** What *is* confirmed about the eventual behavior: a credit-check **FAIL means CAPEX only** (OPEX is not offered); whether failed OPEX is hidden vs. visible-but-disabled was not specified. What `credit_limit` caps (financed principal vs. MRC vs. contract value) was not discussed.

**Interim approach for this revision:** ship the `opex_eligible` boolean on `customer_pricing` as a **manual admin flag** (no automated bureau check). The pricing/quote endpoints still enforce it server-side — reject `financial_model='OPEX'` lines when `opex_eligible = false` — but eligibility is set by an admin, not a credit engine. The business-credit onboarding fields (§4.7) can be collected now but aren't wired to any check.

**Future phase (when credit layer is built):** automated business-credit check consuming EIN / Tax ID / DUNS / legal name from `tenant_onboarding`, writing `credit_status` / `credit_limit` / `credit_checked_at`, with the FAIL→CAPEX-only gate above. No customer credit card required (per notes §19).

---

## 8. Customer ordering flow

Maps the notes' 11 steps onto existing tables (`quotes → orders → contracts → subscriptions → workflow_instances`):

```
1  Onboarding              tenant_onboarding (+ business-credit fields)
2  Credit check            DEFERRED — for now opex_eligible is a manual admin flag (§7)
3  Eligibility             gate CAPEX/OPEX visibility off opex_eligible
4  Select product/bundle   products / bundles
5  Choose CAPEX | OPEX     quotes.financial_model  (+ per-line snapshot)
6  If OPEX: Monthly|Annual  quotes.subscription_interval + financing_terms
7  Recalculate pricing     ComponentPricingService → quote line tree (parent_line_id)
8  Generate proposal       quote (existing PDF/email proposal path)
9  Approval                quotes.status: DRAFT→SENT→ACCEPTED
10 Contract execution      convert_quote → orders + contracts
11 Order fulfillment       workflow_instances/steps, assets, subscriptions, invoices
```

No new top-level tables for the flow — it reuses the lifecycle that already exists; we only add the financial-model fields and the (manual, for now) OPEX-eligibility flag.

---

## 9. Admin configuration & APIs

Goal (§13): **zero Excel dependency** after launch; everything editable in-portal.

New/changed endpoints (FastAPI, under existing auth + `AuthorizationService` permissions):

```
# Catalog admin
POST   /products                      create SKU header
PATCH  /products/{id}
POST   /products/{id}/components       add a Component Type row
PATCH  /products/components/{id}       edit cost/msrp/margin/leasing/uom/billing
GET    /products                       filter by vendor, technology, financial_model
POST   /bundles  /  POST /bundles/{id}/items   define solutions

# Pricing config
PATCH  /customers/{tenant_id}/commercial   margin, credit_status, credit_limit, opex_eligible
POST   /customers/{tenant_id}/price-overrides
GET    /financing-terms  /  POST /financing-terms

# Quoting (extend existing quote_service)
POST   /quotes/preview                 body: {product_id|bundle_id, financial_model, interval, qty map}
                                       → returns computed line tree + CAPEX/OPEX totals
POST   /quotes                         persists snapshots

# Credit (FUTURE — descoped this revision, §7)
POST   /onboarding/{tenant_id}/credit-check   runs check, writes result + eligibility
```

### Admin views (portal screens) — all prices/costs visible & editable

Maps the manager's §13 (admin manages every field), §14 (Add Product screen), §15 (Customer config). **No Excel after launch — every value below is read *and* write in the portal.**

1. **Catalog / Product list** — table of all `products` (Vendor, Technology, SKU, financial model, active). Filter/search by vendor + technology. Row → product editor. Shows SKU-level `margin_pct` and `leasing_pct`.
2. **Product editor (Add/Edit Product, §14)** — header fields (Vendor, Technology, SKU, name, default financial model, SKU margin %, leasing %) **plus a grid of component rows**. Each `product_components` row is inline-editable: Component Type, Financial Model (CAPEX/OPEX/BOTH), **vendor cost (Extended Price)**, **MSRP**, uom, billing/interval, **per-component margin %**, **leasing %**, required/optional. "Add Component" appends a row. This is the manager's "every cost element is a Component Type row."
3. **Managed-service pricing (`/shop/services`)** — per-SKU managed-service price grid (reuses existing `managed_service_price` + `managed_service_pricing_service`); admin edits the MS price for each device SKU.
4. **Customer commercial config (§15)** — per tenant: default margin %, **per-SKU margin overrides**, hard price overrides, `opex_eligible` flag (manual for now), and (future) credit status / limit. Visible read-only: the customer's effective price per SKU under CAPEX and OPEX.
5. **Financing terms** — manage `financing_terms` rows (term months, annual leasing rate, default flag). Drives the OPEX annuity.
6. **Live price preview** — on any product, admin sees the computed CAPEX price and OPEX monthly (lease + recurring components) for a chosen customer/term, recomputed from current costs × margin/financing — so they can sanity-check before quoting (the §3 worked example, on screen).

Every field that feeds the pricing engine (cost, MSRP, margin at SKU and component level, leasing %, financing term, managed-service price, OPEX eligibility) is editable in one of these screens; nothing requires a DB edit or spreadsheet.

---

## 10. MIX seed data (this revision's deliverable)

Seed **only** these. Source: `MIX Networks Reseller Master Services Agreement.docx` (Annex pricing tables). New method `catalog_service.seed_mix_products()` (mirrors `seed_partner_devices`, writes to `products`/`product_components`).

### Products + DEVICE/MAINTENANCE components

| Product SKU | vendor_sku | Technology | name | DEVICE cost | MSRP | MAINTENANCE (Cloud Controller) MRC | maint vendor_sku |
|---|---|---|---|---|---|---|---|
| `90X1` | PROD7901 | POTS / Cellular Router | POTS-in-a-Box 4G/5G LTE multi-carrier router (1 WAN/2 LAN, 8 FXS) | 550.00 | 675.00 | 7.75/mo | SERV2158 |
| `90X2` | PROD2279 | POTS / Cellular Router | POTS-in-a-Box 4G/LTE multi-carrier router (1 WAN/4 LAN, 8 FXS) | 280.00 | 365.00 | 5.75/mo | SERV2290 |
| `90X2-NFR` | PROD2279-NFR | POTS / Lab | NFR POTS-in-a-Box (lab/training) | 240.00 | 0.00 | 5.75/mo | SERV2290-NFR |

Set `product.attributes.capacity` per the §5 model: `90X1` → `{"fxs_port": 8, "lan_port": 2, "wan_port": 1, "max_sims": 2}`; `90X2` / `90X2-NFR` → `{"fxs_port": 8, "lan_port": 4, "wan_port": 1, "max_sims": 2}`. Voice/specialty line components carry `consumes = {"fxs_port": 1}`; SIM components `consumes = {"max_sims": 1}`. Accessories (DEVICE/ACCESSORY, CAPEX one-time): Power Inverter `PROD7933` $30.00; Power Supply `PROD7643` $22.00; Battery `PROD7956` $106.25.

### LINE_CHARGE components (RECURRING, PER_LINE / PER_SEAT)

| Component | vendor_sku | vendor_cost | uom |
|---|---|---|---|
| PIAB Voice Line (RJ-11) | SERV1970 | 11.50/mo | PER_LINE |
| PIAB Specialty Line (Fax/Alarm/Modem) | SERV1969 | 15.50/mo | PER_LINE |
| Hosted PBX Seat | SERV075 | 5.50/mo | PER_SEAT |
| Non-Continental DID add-on (AK/HI/PR) | SERV1986 | 3.50/mo (+3.50 NRC) | PER_LINE |

### INSTALLATION / PROFESSIONAL_SERVICES components

| Component | vendor_sku | cost | uom | billing |
|---|---|---|---|---|
| Staging/Kitting/Provisioning | SERV1987 | 40.00 | PER_DEVICE | ONE_TIME |
| On-site Installation | SERV1817 | 150.00/hr (2 hr min) | PER_HOUR | ONE_TIME |
| Remote Install Assistance | SERV069 | 125.00/hr | PER_HOUR | ONE_TIME |
| Remote Training/Support | SERV049 | 500 setup + 200/hr | PER_HOUR | ONE_TIME |

### Ancillary (LICENSE/MANAGED_SERVICE, optional, RECURRING/PER_DID)

911 Services SERV052 $0.59/mo/DID; Additional USA/Canada DID SERV100 $0.20/mo (+$0.50 NRC); Caller ID SERV013 $2.00/mo; CNAM SERV1990 $2.00 NRC; Call Recording SERV077 $1.00/mo/seat; Toll-Free SERV027 $1.50/mo. (Load as inactive-by-default optional components; activate as offered.)

### Vendor-level config (notes, not per-quote math)

`products.attributes` / a `vendor_terms` note on MIX (⚠️ NOT discussed by manager — vendor context only): wholesale revenue share 8.0/7.5/7.0% tiers, $1,500 platform fee (waivable), 100-line minimum after 6-mo ramp, $150 E911 penalty.

**SIM / Backup SIM — sourced from PAPI (CONFIRMED), not MIX. Price = $40 fixed.** Order SIMs via the existing PAPI integration (`papi_client.py`); model `SIM` / `BACKUP_SIM` components against the PAPI source rather than MIX. The manager's Excel uses a flat **$40** SIM line (→ $82.88 total). **Backup SIM is optional** (a device may carry one SIM or a primary + backup). Open: is $40 per SIM or for the primary+backup pair — see §12 Q4.

**Managed Service — own Component Type, priced per SKU (CONFIRMED).** Admin sets each SKU's managed-service price in `/shop/services`, which already maps to `catalog_items.managed_service_price` + `managed_service_pricing_service`. Reuse that mechanism for the new `products` rows (carry the per-SKU MS price on the `MANAGED_SERVICE` component); do not hardcode a single managed-service rate.

> **Review note (2026-06-04):** "Reuse" here means reuse the *concept/column*, not the *code path*. The existing MS service is design/BOM-driven — `managed_service_pricing_service` reads `catalog_items.managed_service_price` for devices found in a network BOM and `quote_service` injects those lines only when a `design_id` is passed. New MIX SKUs are `products` (not `catalog_items`) and a standalone MIX quote has no network design, so it won't flow through that path. The `MANAGED_SERVICE` component and the legacy MS service are parallel mechanisms; the plan should state explicitly that a MIX quote line's MS price comes from the **component row**, with the legacy service reserved for design-driven quotes.

---

## 11. Migration & phasing

**Phase 1 — schema & seed (no behavior change).** Add enums + tables (`products`, `product_components`, `bundles`, `bundle_items`, `financing_terms`, `customer_price_overrides`); `ALTER` for `customer_pricing`, `tenant_onboarding`, `quotes`, `quote_lines`, `order_lines`. Seed MIX products + one `financing_terms` default (36 mo / 5%). Idempotent schema changes + a `seed_mix_products()` service method. Tests: schema loads, MIX seed reproduces the §3 numbers.

> **Review note (2026-06-04):** There is **no standalone SQL migration runner or Alembic** in this repo. "Idempotent SQL migration" must be realized as either ORM models picked up by `Base.metadata.create_all()` or hand-written blocks appended to `backend/app/core/runtime_migrations.py` (the existing pattern — that's where `customer_pricing`/`list_prices`/`managed_service_price` are created at startup). `CREATE TYPE` enums need `DO $$ … IF NOT EXISTS` guards so re-running on every boot doesn't error. `db/schema.sql` is a static baseline and is not the application path.

**Phase 2 — pricing engine.** `ComponentPricingService` (CAPEX, OPEX amortizing annuity — ✅ confirmed, annual/monthly recalculation). Margin resolution = customer-wins (§6); leasing rate per-SKU. Unit tests pinned to the §3 reconciliation (660 / 19.78 / 9.30 / 13.80 / 82.88 with SIM = $40). `POST /quotes/preview` returns the computed tree.

**Phase 3 — à-la-carte ordering + manual OPEX flag.** Standalone component sale and add-on/quantity-change ("2 → 3 lines"); `opex_eligible` as a **manual admin flag** (no credit engine — descoped per §3a #7). SIMs ordered via PAPI integration.

**Phase 4 — admin portal.** Product/component CRUD + per-SKU managed-service pricing (`/shop/services`), customer commercial config (margins, OPEX flag), financing terms — removes Excel dependency (§13).

**Phase 5 — bundles + capacity rules (in scope).** `bundles` / `bundle_items` for named reusable solutions; bundle expansion into the `parent_line_id` quote tree; generic `capacity`/`consumes` validation + `MIN`/`MAX`/`COMPAT` constraints (§5). Requested by the team (not from manager recordings — see §3a #12).

**Phase 6 (future) — credit layer.** Automated business-credit check → OPEX eligibility, credit status/limit, FAIL→CAPEX-only gate (§7).

**Compatibility:** legacy `catalog_items` + discount pricing remain for dummy Meraki/Extreme/SkyMirr/InHand/PAPI rows. New component model is additive; existing quote/order serializers keep working via the current `synonym` aliases. Nothing in the dummy catalog is migrated in this revision.

---

## 12. Open questions for the manager

Resolved (recordings + Excel + follow-ups, see §3a): margin = markup-on-cost ✓; per-tenant-per-SKU **and** per-component ✓; **OPEX = amortizing annuity ($19.78)** ✓; leasing % per-SKU ✓; **annual = monthly × 12** ✓; **SIM from PAPI, $40 final, no margin** ✓; managed service per-SKU ✓; credit FAIL → CAPEX-only, credit layer descoped ✓; à-la-carte ✓. **Nothing blocking remains for Phase 1–4.** Still open (minor / future):

1. **SIM $40 basis** — is $40 per SIM or the primary+backup pair? (Doesn't block the engine — modeled as a flat $40 line either way.)
2. **Failed-OPEX UI (future)** — on credit FAIL, is OPEX hidden entirely or shown-but-disabled?
3. **Credit limit semantics (future)** — when the credit layer is built, does the limit cap financed principal, monthly MRC, or full contract value?
4. **Annual rate (future)** — if MIX ever offers an annual discount, replace the ×12 rule with a rate card.
