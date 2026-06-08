# Phase 2 — Pricing Engine

**Status:** DONE (2026-06-04) — 16/16 Phase 2 tests green; §3 reconciliation reproduced to the cent.
**Depends on:** Phase 1 (schema + seed)
**Parent spec sections:** §6 (pricing engine), §11 (Phase 2)
**Goal:** A single `ComponentPricingService` that computes a unit price for any component given `(component, financial_model, customer_config, financing_terms, overrides)`, plus `POST /quotes/preview` returning the computed line tree + CAPEX/OPEX totals. Pinned to the §3 reconciliation.

---

## Scope
**In:**
- `backend/app/services/component_pricing_service.py` — CAPEX, OPEX (amortizing annuity), recurring components, margin resolution, SIM flat-price exception, annual = monthly × 12.
- Margin resolution precedence (§6): `override_unit_price` → `override_margin_pct` → `customer_pricing.default_margin_pct` → `product_components.margin_pct` → `products.margin_pct`. SIM/BACKUP_SIM → flat, no margin.
- Leasing rate: `products.leasing_pct` ?? `financing_terms.annual_rate_pct`; term from `financing_terms`.
- `POST /quotes/preview` — body `{product_id|bundle_id, financial_model, interval, qty map}` → computed line tree + `one_time_total`, `monthly_total`, `projected_term_cost`.
- Unit tests pinned to §3: 660.00 / 19.78 / 9.30 / 13.80 / 29.08 / 42.88 / 82.88.

**Out:** persisting quotes with the new snapshots (Phase 3 wires assembly + snapshot copy through `quote_service`/`convert_quote`), admin CRUD (Phase 4), bundle expansion (Phase 5).

---

## Key formulas (verified 2026-06-04)
```
CAPEX:   sell_unit = round(vendor_cost × (1 + margin), 2)
OPEX financed (DEVICE one-time → lease):
         principal = vendor_cost × (1 + margin)
         r = annual_rate / 12
         lease_mrc = principal × r / (1 − (1+r)^(−term_months))   # amortizing annuity
OPEX recurring (controller/line/MS/SIM):
         mrc_unit = round(vendor_cost × (1 + margin), 2)
SIM:     flat 40.00, no margin
Annual:  recurring lines bill at interval=YEAR = 12 × monthly MRC (no annual discount yet)
projected_term_cost = one_time_total + monthly_total × term_months
```
`Decimal` + `ROUND_HALF_UP`; round only at the line total; `vendor_cost` keeps 4dp.

## Implementation steps
1. `ComponentPricingService(db)` with `price_component(component, *, financial_model, customer_config, financing_terms, overrides)` → structured result (sell_unit / mrc / billing / interval / which margin source won). Pure-ish: no DB writes.
2. Margin/leasing resolution helpers honoring the §6 precedence and the SIM exception.
3. `price_product(product, financial_model, interval, qty_map, customer_config)` → builds the parent device line + child component lines (controller/line/MS/SIM) and totals. Mirrors the `parent_line_id` tree shape that `quote_service` already uses (don't persist here).
4. `POST /quotes/preview` route under existing auth + `AuthorizationService`. Returns tree + totals; no persistence.
5. Tests in `backend/tests/test_component_pricing.py` pinned to §3; plus annual-toggle test (×12), margin-precedence tests, SIM-flat test, OPEX annuity edge (term=36, rate=0.05).

## Dispatch rule (cross-cutting)
This engine handles lines that reference `product_id`/`component_id`. Legacy `catalog_item_id` lines keep using `pricing_service` (discount-off-list). Don't merge the two.

## Acceptance criteria
- [ ] §3 numbers reproduce to the cent in tests.
- [ ] Margin precedence + SIM exception covered by tests.
- [ ] Annual = monthly × 12 verified.
- [ ] `/quotes/preview` returns a correct tree + totals for a `90X1` OPEX 36-mo example (= $82.88/mo with one voice line + SIM).
- [ ] No persistence side effects; legacy pricing untouched.

## Handover IN  *(from Phase 1, 2026-06-04)*

**Models to import**
- `from app.models.product import Product, ProductComponent, ComponentType, FinancialModel, ComponentUom`
- `from app.models.financing import FinancingTerms`
- `from app.models.pricing import CustomerPricing` (now has `default_margin_pct`, `opex_eligible`, `credit_status`, `credit_limit`)
- `from app.models.product import CustomerPriceOverride`

**Reading a component for pricing** — fields on `ProductComponent`: `vendor_cost` (Decimal, 4dp), `msrp`, `margin_pct` (nullable per-component override), `leasing_pct` (nullable), `uom` (ComponentUom), `billing` ('ONE_TIME'|'RECURRING'), `interval` ('MONTH'|'YEAR'|None), `component_type`, `is_required`, `is_active`, `default_qty`, `attributes` (JSONB). Parent `Product` has `margin_pct` (=0.20 seeded), `leasing_pct` (=0.05 seeded).

**Margin precedence to implement (§6):** `CustomerPriceOverride.override_unit_price` → `CustomerPriceOverride.override_margin_pct` → `CustomerPricing.default_margin_pct` → `ProductComponent.margin_pct` → `Product.margin_pct`.

**SIM special-case:** skip margin entirely when `component_type in (ComponentType.SIM, ComponentType.BACKUP_SIM)` — use `vendor_cost` as the final price ($40). Seeded ONE_TIME (a SIM is bought once; product-owner decision 2026-06-04), `attributes.flat_price=True`. NOT financed under OPEX.

**Leasing/term source:** `Product.leasing_pct` ?? default `FinancingTerms.annual_rate_pct`; term from the `is_default=True` FinancingTerms row (`Standard 36-mo`, 36 mo, 0.0500, interval MONTH).

**Worked-example fixtures (90X1, all keyed by `vendor_component_sku`):** `PROD7901` DEVICE cost 550 → CAPEX 660 / OPEX lease 19.78; `SERV2158` MAINT 7.75 → 9.30; `SERV1970` voice 11.50 → 13.80; `PAPI-SIM` 40 flat one-time. Engine target (SIM one-time): OPEX = 42.88/mo + $40 once; CAPEX = $700 once + 23.10/mo. Margin 0.20, leasing 0.05, term 36.

**All values are `Decimal`.** Reuse `pricing_service.py` quantizers (`MONEY_QUANT=0.01`, `PCT_QUANT=0.0001`, ROUND_HALF_UP). Round only at the line total.

**Snapshot columns now on `quote_lines`/`order_lines`** (for when preview becomes persistence in Phase 3): `component_type, financial_model, product_id, component_id, cost_snapshot, margin_pct_snapshot, leasing_pct_snapshot, term_months`. Phase 2 (`/quotes/preview`) does NOT persist — just return the computed tree.

**Dispatch reminder:** this engine only handles `product_id`/`component_id` lines; legacy `catalog_item_id` lines stay on `pricing_service` (discount). Don't merge.

## Handover OUT  *(completed 2026-06-04)*

**Module:** `backend/app/services/component_pricing_service.py` — `ComponentPricingService(db)`.

**Public methods**
- `ComponentPricingService.lease_mrc(principal: Decimal, annual_rate: Decimal, term_months: int) -> Decimal` (staticmethod) — amortizing annuity (PMT); rounded only here. `lease_mrc(660, 0.05, 36) == 19.78`. Zero rate → straight-line.
- `price_component(component, *, product, financial_model, interval, qty, customer_pricing=None, override=None, annual_rate=None, term_months=None) -> dict` — **reads only its arguments, never the DB** (unit-testable with fakes).
- `price_product(product_id, *, financial_model='CAPEX', interval='MONTH', selections=None, tenant_id=None) -> dict` — queries components/product/financing.

**`price_component` line dict** (all money = `Decimal`): `component_id, component_type, label, vendor_component_sku, qty, vendor_cost, margin_pct, margin_source, billing('ONE_TIME'|'RECURRING'), interval, financed(bool), unit_price (at chosen cadence), monthly_unit, one_time_unit, line_total, monthly_total, one_time_total`. `price_product` adds `parent_component_id` (DEVICE line is the parent; others reference it).

**`price_product` result:** `{product:{id,sku,name,vendor}, financial_model, interval, term_months, annual_rate_pct, lines:[…], one_time_total, monthly_total, recurring_total_at_interval, projected_term_cost}`. All money `Decimal`.

**Route:** `POST /pricing/component-preview` (body `ComponentPreviewRequest`: `product_id`, `financial_model` CAPEX|OPEX, `interval` MONTH|YEAR, `selections` `{component_id: qty}`). Auth: `get_current_user` only (no manage-pricing perm — previewing a price is part of quoting). Returns the `price_product` dict; FastAPI's `jsonable_encoder` serializes `Decimal` → JSON number. **Not** at `/quotes/preview` (taken by the network-design BOM preview).

**Resolution rules as built**
- **Margin precedence (DEVIATION D1):** `override_unit_price` → `override_margin_pct` → `product_components.margin_pct` → `products.margin_pct` → `customer_pricing.default_margin_pct`. This reorders §6 (which lists tenant default *above* catalog) — see "Deviations". `margin_source` in each line reports which won.
- **SIM flat:** `component_type in {SIM, BACKUP_SIM}` OR `attributes.flat_price` → final price = `vendor_cost`, margin 0, `margin_source='flat_price'`.
- **OPEX financing:** only `FINANCEABLE_TYPES = {DEVICE, ACCESSORY}` one-time components become a lease MRC; INSTALLATION/PROFESSIONAL_SERVICES stay one-time even under OPEX. Rate = `product.leasing_pct` ?? default `FinancingTerms.annual_rate_pct`; term from the `is_default` FinancingTerms.
- **Recurring components** (controller/line/MS/SIM) bill monthly in BOTH CAPEX and OPEX — only hardware treatment differs.
- **Annual:** recurring (incl. lease) ×12 when `interval='YEAR'`; `monthly_unit` keeps the monthly figure, `unit_price`/totals show the annual cadence.
- **Selection:** required active components always included (`default_qty` unless overridden); optional only when in `selections` with qty>0; component skipped if `component.financial_model not in ('BOTH', requested)`.

**Verified** (SIM reclassified ONE-TIME per product owner 2026-06-04 — see deviation D4): OPEX 90X1+voice+SIM = **42.88/mo + $40 one-time**, projected_term 1583.68; CAPEX = **$700 one-time + 23.10/mo** (device 660 + SIM 40); annual recurring = 514.56; lease 19.78; controller 9.30; line 13.80; SIM 40 (flat, one-time, no margin, not financed under OPEX).

**Deviations**
- **D1 (margin precedence)** — reordered vs §6 literal text. Rationale: Phase 1 created `customer_pricing.default_margin_pct` NOT NULL DEFAULT 0.20, so §6's literal order would make the CONFIRMED per-component margin (Decision #13) permanently unreachable. **Needs manager sign-off** — if they truly want tenant-default to outrank catalog margins, flip the order (and make the column nullable). Worked example is unaffected (90X1 uses `product.margin_pct=0.20`).
- **D2 (endpoint path)** — `/pricing/component-preview`, not `/quotes/preview` (collision).
- **D3 (financeable types)** — only DEVICE+ACCESSORY financed under OPEX; OUR design (spec said "DEVICE / one-time components" loosely).
- **D4 (SIM one-time)** — SIM/BACKUP_SIM billed ONE_TIME at $40 (product-owner decision 2026-06-04), overriding §3's worked example which folded $40 into the monthly total. Changes the canonical 90X1 example from 82.88/mo to 42.88/mo + $40 once.
- **D1 retired** — the margin "deviation" is moot: admin sets one markup per SKU (`product.margin_pct`), which is exactly what the engine uses. The other layers are dormant fallbacks. No sign-off needed.

**Gotchas**
- `price_component` is intentionally DB-free; `price_product` is the DB entry point.
- No persistence yet — `/pricing/component-preview` is read-only. Phase 3 maps the line dict onto the `quote_lines` snapshot columns and must also enforce `opex_eligible` (not enforced here) and fix `convert_quote`.
- Decimals throughout; never compare with float.
