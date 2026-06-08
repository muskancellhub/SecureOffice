# Phase 6 — Credit Layer (DEFERRED)

**Status:** DEFERRED (out of scope per §3a #7 — manager confirmed do not build yet)
**Depends on:** Phases 1–5.
**Parent spec sections:** §7, §4.7, §11 (Phase 6)
**Goal (future):** Automated business-credit check feeding OPEX eligibility, replacing the manual `opex_eligible` flag from Phase 3.

---

## Scope (when picked up)
- Automated business-credit check consuming `tenant_onboarding` fields: EIN / Tax ID / DUNS / legal name / business credit bureau (collected in Phase 1, unused until now). No customer credit card (§19).
- Write `customer_pricing.credit_status` (PENDING/PASS/FAIL), `credit_limit`, `credit_checked_at`, `credit_bureau_ref`; `tenant_onboarding.credit_check_result` JSONB.
- Gate: **FAIL → CAPEX only** (OPEX not offered). Replaces the manual flag — `opex_eligible` becomes derived.
- `POST /onboarding/{tenant_id}/credit-check`.

## Open questions to resolve before building (spec §12)
- Failed-OPEX UI: hidden vs. visible-but-disabled? (#2)
- Credit-limit semantics: caps financed principal, monthly MRC, or full contract value? (#3)
- Annual rate: replace ×12 with a rate card if MIX offers one? (#4)

## Handover IN
*(fill from Phase 5 Handover OUT when this phase begins.)*

## Handover OUT
*(n/a until built.)*
