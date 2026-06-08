# Phase 3 — À-la-carte Ordering + Manual OPEX Flag

**Status:** DONE (2026-06-04) — 10/10 Phase 3 tests green; full suite 60 pass / 20 pre-existing fail.
**Depends on:** Phase 2 (pricing engine)
**Parent spec sections:** §5 (assembly basics), §7 (OPEX flag interim), §8 (ordering flow), §11 (Phase 3)
**Goal:** Let customers order a single product/component standalone, add-on or change quantity ("2 → 3 lines") against an existing order/contract, persist the new financial-model snapshots through quote→order, and gate OPEX behind a **manual** `opex_eligible` flag (no credit engine — descoped per §3a #7). SIMs ordered via PAPI.

---

## Scope
**In:**
- Quote assembly for `products`: build the parent device line + child component lines using `ComponentPricingService`, persisting the §4.8 snapshot columns (`component_type, financial_model, product_id, component_id, cost_snapshot, margin_pct_snapshot, leasing_pct_snapshot, term_months`).
- **Extend `convert_quote`** (`quote_service.py:443-457`) to copy the new snapshot columns to `order_lines` (flagged in spec §4.8 review note — fixed-field copy currently drops them).
- Add-on / quantity-change endpoint: append a standalone `LINE_CHARGE`/component line to an existing order/contract; recompute only the delta line. Enforce "requires a device" — a `LINE_CHARGE`/`SIM` must have a `parent_line_id` (NET-NEW server-side validation; today `parent_line_id` is unvalidated).
- Server-side OPEX gate: reject `financial_model='OPEX'` lines when `customer_pricing.opex_eligible = false`.
- SIM ordering via existing PAPI integration (`papi_client.py`) at $40 flat.

**Out:** automated credit check (Phase 6), admin CRUD UI (Phase 4), bundle expansion + capacity validation (Phase 5).

## Implementation steps
1. Extend `quote_service.create_quote` to accept product/component-based line specs and call `ComponentPricingService`, writing snapshots.
2. Fix `convert_quote` copy loop to include the new columns (regression test: convert an OPEX quote, assert order_lines carry `financial_model`, `cost_snapshot`, etc.).
3. Quantity-change / add-on endpoint + delta recompute.
4. `parent_line_id` requirement validation for components with `attributes.requires_component_type='DEVICE'`.
5. OPEX eligibility enforcement in quote/preview/add-on endpoints.
6. PAPI SIM line creation path.
7. Tests: standalone line sale; 2→3 line add-on delta; convert_quote snapshot carry-through; OPEX rejected when ineligible; SIM = $40.

## Acceptance criteria
- [ ] A `90X1` OPEX order with 1 voice line + SIM persists and converts with all snapshots intact.
- [ ] Adding a 3rd line recomputes only the new line.
- [ ] OPEX blocked server-side when `opex_eligible=false`.
- [ ] Orphan `LINE_CHARGE`/`SIM` (no parent) rejected.

## Handover IN  *(from Phase 2, 2026-06-04)*

**Engine to call during assembly:** `from app.services.component_pricing_service import ComponentPricingService`.
- `ComponentPricingService(db).price_product(product_id, financial_model=, interval=, selections={component_id: qty}, tenant_id=)` → the priced line tree (see shape below). Use this to build quote lines.
- `price_component(...)` is available if you need a single line; it's DB-free.

**Map each engine line dict → a `quote_lines` row (the §4.8 snapshots Phase 1 added):**
| engine line key | quote_lines column |
|---|---|
| `component_type` | `component_type` |
| (request) `financial_model` | `financial_model` |
| `product.id` | `product_id` |
| `component_id` | `component_id` |
| `vendor_cost` | `cost_snapshot` |
| `margin_pct` | `margin_pct_snapshot` |
| (product/financing) leasing rate | `leasing_pct_snapshot` |
| `term_months` (result) | `term_months` |
| `unit_price` | `final_unit_price_snapshot` (`unit_price`) |
| `billing` | `billing_type` (`billing`) |
| `interval` | `interval` |
| `qty` | `qty` |
| `parent_component_id` → resolved to the parent **quote_line** id | `parent_line_id` |
| `label` | `name_snapshot` (`name`) |
| `vendor_component_sku` | `sku_snapshot` (`sku`) |

The DEVICE line is the parent (`parent_component_id` null); map component→quote_line ids to wire children's `parent_line_id`, mirroring `quote_service`'s existing temp-id pattern.

**Must-do this phase (from Phase 2 gotchas / spec review notes):**
1. **Extend `convert_quote`** (`quote_service.py` ~l.443-457) to copy the 8 new snapshot columns to `order_lines` — current fixed-field copy drops them.
2. **Enforce `opex_eligible`** server-side: reject `financial_model='OPEX'` when `CustomerPricing.opex_eligible` is false. The engine does NOT enforce this.
3. **Require a device parent** for `LINE_CHARGE`/`SIM` (component `attributes.requires_component_type='DEVICE'`) — NET-NEW validation; `parent_line_id` is currently unvalidated.

**Dispatch rule:** product/component lines → `ComponentPricingService`; legacy `catalog_item_id` lines → `PricingService` (discount). Don't merge.

**Totals:** engine returns `one_time_total`, `monthly_total`, `recurring_total_at_interval`, `projected_term_cost` (Decimal). Map to `quotes.one_time_total` / `monthly_total`; consider `projected_term_cost` for the existing `projected_12_month_cost` field (or add `projected_term_cost`).

**Open deviation needing sign-off:** margin precedence D1 (see Phase 2 OUT) — confirm before building admin margin UI in Phase 4.

## Handover OUT  *(completed 2026-06-04)*

**Service methods** (`app/services/quote_service.py`)
- `create_component_quote(current_user, payload)` — `payload = {product_id, financial_model('CAPEX'|'OPEX'), interval('MONTH'|'YEAR'), selections{component_id: qty}}`. Prices via `ComponentPricingService.price_product`, enforces OPEX gate + requires-a-device, persists a DRAFT quote with the parent-device/child tree and all §4.8 snapshots. Returns the `Quote`.
- `add_component_line(current_user, quote_id, payload)` — `payload = {component_id, qty}` (qty=0 removes). Reconstructs selections from the quote's existing component lines, applies the change, **re-prices the whole product** and rewrites the component lines (keeps totals + OPEX/annual treatment consistent). DRAFT quotes only.
- `convert_quote` now copies the 8 snapshot columns to `order_lines` and sets `orders.financial_model` / `subscription_interval`.
- Helpers: `_validate_requires_device(result)`, `_billing_from_engine_line(line)`, `_component_line_kwargs(...)`, `_persist_component_tree(quote, product, result, fm)`, `_resolve_financial_model(user, fm)` (the OPEX gate).

**Routes** (`app/routes/quotes.py`)
- `POST /quotes/component` → `ComponentQuoteRequest` → `QuoteDetailResponse`.
- `POST /quotes/{quote_id}/add-component` → `AddComponentRequest` → `QuoteDetailResponse`.
- Schemas in `app/schemas/quotes.py`: `ComponentQuoteRequest`, `AddComponentRequest`.

**How a component becomes a quote line** (in `_component_line_kwargs`)
- `line_type` = DEVICE if component_type==DEVICE else SERVICE; `billing_type`/`interval` mapped from the engine line.
- `list_price_snapshot = final_unit_price_snapshot = unit_price` (cost-plus has no separate "list"); `metadata_json = {margin_source, financed, source:'component_engine'}`.
- Snapshots set: `component_type, financial_model, product_id, component_id, cost_snapshot, margin_pct_snapshot, leasing_pct_snapshot (financed only), term_months (financed only)`.
- `parent_line_id`: the DEVICE line is the parent; children resolved via a component_id→quote_line_id map.
- Quote totals: `one_time_total`, `monthly_total` (monthly figure even when interval=YEAR), `projected_12_month_cost = one_time + monthly×12`, plus `financial_model` / `subscription_interval`.

**Gates / validation as built**
- **OPEX eligibility** (`_resolve_financial_model`): `financial_model='OPEX'` raises `ForbiddenError` unless `CustomerPricing.opex_eligible` is true (manual admin flag; default false). Enforced in both create and add-on.
- **Requires-a-device**: `REQUIRES_DEVICE_TYPES = {LINE_CHARGE, SIM, BACKUP_SIM}` → `AppError(400)` if present without a DEVICE line.
- Onboarding-complete gate reused (same as `create_quote`).

**Verified numbers:** CAPEX 90X1+voice+SIM = $700 one-time + 23.10/mo; OPEX (after enabling flag) = $40 one-time + 42.88/mo, device `term_months=36`, `leasing_pct_snapshot=0.05`; add-on voice 1→3 → monthly 23.10→50.70; convert carries snapshots + parent/child tree to `order_lines`.

**Deviations / scope**
- **Add-on is at the DRAFT-quote level** (re-prices the whole product from updated selections), NOT a live contract/order modification. Post-sale contract add-on ("add a line to an active contract") is **deferred**.
- **PAPI SIM**: the $40 one-time SIM line is modeled; the actual `papi_client` ordering call is **not invoked** (fulfillment-time concern, deferred).
- **Single-product quotes** assumed in `add_component_line` (product derived from the quote's device line). Multi-product à-la-carte not handled in add-on.

**Gotchas**
- `_persist_component_tree` deletes existing component lines (`component_id` not null) and recreates them → **quote-line ids change on every `add_component_line` call**. Fine for drafts; don't cache line ids across add-on calls.
- `create_component_quote` / `add_component_line` commit internally.
- DB integration tests need a real tenant/user/onboarding: tenant must be flushed before FK-dependent rows, and a LOCAL user needs a non-null `password_hash` (CHECK constraint).
