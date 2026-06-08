# Secure Office Pricing Engine — Phased Implementation Plans

**Parent spec:** [../SECURE_OFFICE_CATALOG_PRICING_PLAN.md](../SECURE_OFFICE_CATALOG_PRICING_PLAN.md)
**Source of truth for seed data:** `MIX Networks Reseller Master Services Agreement.docx` (pricing rows verified 2026-06-04 against the doc text).
**Created:** 2026-06-04

---

## How these plans work (the handover chain)

Each phase from §11 of the parent spec gets its own plan doc. Phases are implemented **in order**. Every plan doc has two handover sections:

- **Handover IN** — context inherited from the previous phase. Empty at first; **filled from the previous phase's "Handover OUT" the moment that phase completes**, so the next phase starts with the *actual* table names, column names, function signatures, and gotchas that were built (not the guesses from the original spec).
- **Handover OUT** — filled when the phase is marked `DONE`. Records exactly what was built, any deviations from plan, the public surface (enum names, table/column names, service methods + signatures), and known gotchas. This becomes the next phase's Handover IN.

**Completion ritual for each phase:**
1. Implement the steps; get tests green.
2. Set `Status: DONE` and the completion date.
3. Fill **Handover OUT** with the real built artifacts.
4. Copy the salient facts into the next phase's **Handover IN**.

This keeps each phase grounded in reality instead of drifting from the original design as decisions get made during implementation.

---

## Phase index

| Phase | Doc | Scope | Status |
|---|---|---|---|
| 1 | [phase-1-schema-and-seed.md](phase-1-schema-and-seed.md) | Enums, tables, ALTERs, MIX seed | ✅ DONE (2026-06-04) |
| 2 | [phase-2-pricing-engine.md](phase-2-pricing-engine.md) | `ComponentPricingService` (CAPEX/OPEX), `/pricing/component-preview` | ✅ DONE (2026-06-04) |
| 3 | [phase-3-alacarte-ordering.md](phase-3-alacarte-ordering.md) | Standalone + add-on component sale, manual OPEX flag, PAPI SIM | ✅ DONE (2026-06-04) |
| 4 | [phase-4-admin-portal.md](phase-4-admin-portal.md) | Product/component CRUD, customer commercial config, financing terms UI | ✅ DONE (2026-06-04) — browser walkthrough pending |
| 5 | [phase-5-bundles-capacity.md](phase-5-bundles-capacity.md) | Bundles + capacity/MIN/MAX/COMPAT validation | ✅ DONE (backend, 2026-06-04) — frontend pending |
| 6 | [phase-6-credit-layer.md](phase-6-credit-layer.md) | Automated business-credit check, FAIL→CAPEX gate (DEFERRED) | DEFERRED |

## Cross-cutting decisions (apply to every phase)

- **Schema application:** New tables → ORM models in `backend/app/models/` (created by `Base.metadata.create_all()` in `main.py`). Changes to **existing** tables → idempotent `ADD COLUMN IF NOT EXISTS` in `backend/app/core/runtime_migrations.py`. There is **no Alembic / no SQL migration runner.** New pg enums are created by SQLAlchemy `Enum(...)` on `create_all`; do **not** also hand-write `CREATE TYPE` (avoids double-create conflicts). `db/schema.sql` is a static baseline and is NOT the application path.
- **Money/rounding:** `Decimal` + `ROUND_HALF_UP`; money 2dp (`Decimal('0.01')`), pct 4dp (`Decimal('0.0001')`) — match `services/pricing_service.py`.
- **Two pricing models coexist:** legacy discount-off-list (`pricing_service`, `catalog_items` + `customer_pricing.default_discount_pct`) and new cost-plus-margin (`ComponentPricingService`, `products`/`product_components`). **Dispatch rule:** a quote line referencing `product_id`/`component_id` → margin engine; referencing `catalog_item_id` → discount engine.
- **Snapshot principle:** prices are recomputed live for previews but snapshotted onto quote/order lines at persist time so a quote is reproducible.
