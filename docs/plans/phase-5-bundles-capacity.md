# Phase 5 — Bundles + Capacity Rules

**Status:** DONE (backend, 2026-06-04) — 8/8 Phase 5 tests green; full suite 79 pass / 20 pre-existing fail. Frontend bundle UI pending.
**Depends on:** Phases 1–4.
**Parent spec sections:** §4.4 (bundles), §5 (composition & capacity), §11 (Phase 5)
**Goal:** Named reusable solutions (`bundles`/`bundle_items`) that expand into the `parent_line_id` quote tree, plus generic capacity/`MIN`/`MAX`/`COMPAT` validation. Team-requested (not from manager recordings — §3a #12). Default overflow behavior: **block + warn**.

---

## Scope
**In:**
- Bundle CRUD + `bundle_items` (default qty, optional/removable flags, sort order).
- Bundle expansion into a quote: each `bundle_item` → product → active components matching the chosen `financial_model` → quote line tree (device = parent).
- `check_capacity(parent, child_lines)` validator — provide/consume from `attributes.capacity` / `attributes.consumes`; **missing key = 0**; runs server-side in assembly/add-on endpoints.
- Constraint types `(resource_key, type, value)`: `MAX` (Σ consumed ≤ provided), `COMPAT` (boolean fitment), and per-assembly `MIN` (floor within one solution).
- "Requires a device" + quantity scaling by `uom` (reuse Phase 3 validation).

**Out / explicitly NOT here:**
- ⚠️ The MIX **100-line minimum is NOT a per-assembly `MIN`** — it's an account-level aggregate across all contracts over the 6-month ramp (spec §5 review note). If implemented, it's a separate account-level check, not `check_capacity`.
- Credit automation (Phase 6).

## Implementation steps
1. Bundle CRUD + expansion service.
2. `check_capacity` + constraint evaluation; wire into quote-assembly and add-on endpoints (block + warn on violation).
3. Frontend: bundle selection → expanded editable line tree (optional unchecked, non-removable locked).
4. Tests: 90X1 + 9 voice lines → over-capacity (8 fxs_port); voice line on a port-less device → rejected; install/MS children (no consumes) → pass; bundle expansion produces correct parent/child tree; optional/removable honored.

## Acceptance criteria
- [ ] A bundle expands to the correct product/component line tree.
- [ ] Capacity over-subscription is blocked server-side with a clear warning.
- [ ] `MIN`/`MAX`/`COMPAT` evaluated; account-level 100-line min is documented as out-of-scope-here.

## Handover IN  *(from Phase 4, 2026-06-04)*

**Admin-CRUD pattern to reuse for bundles:** `ProductAdminService` (`app/services/product_admin_service.py`) + a dedicated router (`app/routes/products.py`) + schemas (`app/schemas/products.py`) + serializers in the route. Mirror this for `bundles`/`bundle_items` (a `BundleAdminService` + `/bundles` router). Frontend pattern: a page like `AdminProductsPage.tsx` (list + create + nested grid) under `/shop/admin/...`, nav link in `ShopShell.tsx`, API module in `src/api/`.

**Already in place for Phase 5:**
- `bundles` / `bundle_items` tables + ORM (`app/models/product.py`) exist from Phase 1.
- Capacity data is already seeded: `products.attributes.capacity` (e.g. 90X1 `{fxs_port:8,...}`) and `product_components.attributes.consumes` (voice line `{fxs_port:1}`, SIM `{max_sims:1}`) + `requires_component_type`.
- The quote-assembly entry point to extend for bundle expansion is `QuoteService.create_component_quote` / `_persist_component_tree` (Phase 3). The requires-a-device validation (`_validate_requires_device`, `REQUIRES_DEVICE_TYPES`) is the model for adding `check_capacity` server-side.
- `ComponentPricingService.price_product` prices one product; bundle expansion = price each product in the bundle and merge trees.

**Reminders:** the MIX 100-line minimum is account-level, NOT a per-assembly `check_capacity` rule (keep it out). Default overflow behavior = block + warn.

## Handover OUT  *(completed 2026-06-04, backend)*

**Capacity validator** — `app/services/capacity_service.py`:
- `check_capacity(provided: dict, consumers: list[(consumes, qty)]) -> list[violations]` — resource-agnostic; missing key = 0. Violation shape: `{resource, used, provided}`.
- `evaluate_constraints(constraints, used, provided)` — generic MAX/MIN/COMPAT from `[{resource_key, type, value}]`. Violation shape: `{resource, type, used, limit}`.
- `format_violations(violations)` — human string for error messages.

**Wired into assembly** — `QuoteService._check_capacity(product, result)` runs in `create_component_quote`, `add_component_line`, and `create_bundle_quote`. On violation → `AppError(409, 'Device capacity exceeded — …')` (block + warn). Reads `product.attributes.capacity` (provide) vs `component.attributes.consumes` (consume).

**Bundles** — `ProductAdminService`: `list_bundles`, `get_bundle`, `create_bundle`, `add_bundle_item`. Routes in `app/routes/bundles.py` (registered in main.py): `GET /bundles`, `GET /bundles/{id}`, `POST /bundles`, `POST /bundles/{id}/items` (`PERM_VIEW_CATALOG` read / `PERM_MANAGE_PRODUCTS` write). Schemas in `app/schemas/products.py`.

**Bundle expansion** — `QuoteService.create_bundle_quote(current_user, {bundle_id, financial_model, interval, include[]})` → multi-product DRAFT quote. Prices each non-optional item (required components) via `ComponentPricingService.price_product`, validates requires-a-device + capacity per product, appends each tree (one DEVICE parent per product). Optional items included when their `product_id` is in `include[]`. Route `POST /quotes/bundle`. Helper `_write_component_lines` (append one product's tree, no delete/totals) extracted from `_persist_component_tree`.

**Verified:** capacity blocks 9 voice lines on 90X1 (8 fxs ports) and allows 8; bundle of 90X1+90X2 expands to a quote with 2 device lines, CAPEX one-time $996, monthly $16.20.

**Deviations / scope**
- **MIN/COMPAT not yet wired into assembly** — `evaluate_constraints` exists and is tested, but only capacity MAX (`check_capacity`) is enforced in the quote flow. Wiring per-product `attributes.constraints` (incl. the MIX "≥1 line per device" MIN) is a follow-up.
- **Bundle items priced at qty 1** — multi-unit bundle items (e.g. 3× a product) deferred.
- **Account-level 100-line minimum** remains out of scope (it's cross-contract, not per-assembly).
- **Frontend bundle UI not built** — backend only, consistent with the Phase 4 split. Build on the `AdminProductsPage.tsx` pattern (a bundle list + item editor) + a bundle-selection flow that calls `POST /quotes/bundle`.

**Gotchas**
- `add_component_line` assumes a single-product quote — don't use it on a bundle-expanded quote (multiple device subtrees).
- Capacity check issues one extra `SELECT` over the assembled components per quote — fine at this scale.

## Handover OUT → Phase 6
Phase 6 (credit layer) stays **deferred** (§3a #7). When picked up: the business-credit fields are already on `tenant_onboarding` (Phase 1), and `customer_pricing.opex_eligible` is the gate the engine/assembly already enforces — the credit check just needs to set it automatically instead of the manual admin flag.
