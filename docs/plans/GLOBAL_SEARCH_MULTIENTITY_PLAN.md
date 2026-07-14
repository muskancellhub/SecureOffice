# Plan — Global Search, Multi-Entity Expansion (Slices 6+)

Owner: usdev@enidususa.com · Status: **In progress — Slices 6-10 shipped (PR #7); 9 deferred, 11 optional** · Supersedes the "out of scope" note in `SLICE_2_FTS_SEARCH_HANDOFF.md`.

> **Progress:** ✅ 6 (foundation + orders/quotes) · ✅ 7 (designs) · ✅ 8 (invoices + subscriptions) · ⏸️ 9 (assets — deferred, no frontend page) · ✅ 10 (nav + managed services) · ⬜ 11 (cross-entity semantic — optional/advanced, not started).

> **Confirmed decision (locked):** Regular users search **their own records only** (`created_by`/owner); admins (`ADMIN`/`SUPER_ADMIN`) search the **whole tenant**. This mirrors the existing order/quote/design list pages exactly. See §1 layer 2 and §3.

## 0. Where we are

Slices 1–5 (merged / PR #6) built a strong search **engine** — Postgres FTS, `pg_trgm` typo tolerance, pgvector semantic + Reciprocal Rank Fusion, an action lane, LLM fallback, and click-log ranking — but it points at exactly one table: the global `products` catalog. Every lane in `backend/app/routes/search.py` is hardcoded `FROM products`, and every hit is `type='product'`.

The goal now: **one search box that returns everything a user can legitimately see** — their orders ("where is my order"), quotes, network designs, billing/invoices, subscriptions, contracts, assets, plus navigation into onboarding / managed services — each result deep-linking to the right page. Not an admin tool bolted on: the *same* box serves a regular customer (scoped to their own records) and an admin (scoped to the whole tenant).

## 1. The hard part is not more tables — it is scoping

`products` is a global catalog with **no `tenant_id`**, deliberately excluded from RLS. Every other entity is different, and getting this wrong leaks another tenant's or another user's data through the search box. Three scoping layers must stack on **every** non-product lane:

1. **Tenant isolation.** RLS (`_apply_tenant_guc` in `database.py`) filters tenant tables automatically — *but only when `ENABLE_RLS` is on*, and `design_leads` / `workflow_instances` are **not** in the RLS allowlist. → **The search query must apply an explicit `tenant_id = :tenant` predicate itself** (defense-in-depth; correct regardless of the flag and covers the non-RLS tables).
2. **User ownership.** RLS does **not** do per-user filtering. The REST services all use the same pattern — `_is_admin(role)` (`{ADMIN, SUPER_ADMIN}`) sees the whole tenant; a regular `USER` is filtered to their own rows via `created_by` / owner. → Search must replicate this: **non-admins get an ownership predicate** so "my orders" means *mine*.
3. **Permission gating.** Each entity is gated by a permission (below). → **A lane only runs if the user holds its permission.** An unauthorized entity is never queried, so it cannot appear — the billing lane simply doesn't execute for a user without `view_billing`.

This is the security spine of the plan. It is enforced centrally (one scoping helper), not per-entity, so it can't be forgotten.

## 2. What a regular customer can search (permission surface)

`USER` role default scope (`permissions.py`) = 7 permissions, which bound a customer's searchable universe:

| Permission | Unlocks search over |
|---|---|
| `view_catalog` | Products (done), managed-service catalog |
| `view_orders` | Orders |
| `view_quotes` | Quotes |
| `view_lifecycle` | Contracts, subscriptions, assets, workflow/order-tracking |
| `view_billing` | Invoices, payments |
| `manage_cart` | Cart (low value for search — skip) |
| `generate_quotes` | (action lane: "create a quote") |

Admins additionally search the whole tenant and admin-only surfaces. SUPER_ADMIN may target another tenant via `X-Tenant-Id` (already handled by `get_db`).

## 3. Entity catalog (from reconnaissance)

Columns are the human-meaningful, **non-encrypted** fields (encrypted columns — `assets.serial_number`/`location`, all `tenant_onboarding` PII — cannot be FTS/trigram-searched and are excluded).

| Entity | Table | Tenant col | User-scope (non-admin) | Searchable text | Gate | Deep-link |
|---|---|---|---|---|---|---|
| Order | `orders` (+`order_lines`) | `tenant_id` | `created_by` | `public_id` (OID0001), `status`, line `name/sku/vendor` | `view_orders` | `/shop/orders/:id` |
| Quote | `quotes` (+`quote_lines`) | `tenant_id` | `created_by` | `public_id` (QID0001), `status`, line `name/sku/vendor` | `view_quotes` | `/shop/quotes/:id` |
| Network design | `network_designs` | `tenant_id` (nullable) | `created_by` | `design_name`, `status` | authenticated + ownership | `/shop/designs/:id` |
| Invoice | `invoices` | `tenant_id` | via order/subscription `created_by` | `status`, `billing_month`, `amount`, `due_date` | `view_billing` | `/shop/billing` (list) |
| Payment | `payments` | `tenant_id` | via invoice | `external_reference`, `status`, `method` | `view_billing` | `/shop/billing` (list) |
| Contract | `contracts` | `tenant_id` | `created_by` | `status`, `sla_tier`, `term_months` | `view_lifecycle` | — (no detail route) |
| Subscription | `subscriptions` | `tenant_id` | via contract `created_by` | `name`, `sku`, `vendor`, `status`, `interval` | `view_lifecycle` | — (no detail route) |
| Asset / device | `assets` | `tenant_id` | **decision** (see §6) | `name`, `sku`, `vendor`, `asset_type`, `status` (NOT serial/location — encrypted) | `view_lifecycle` | — (no detail route) |
| Managed service | `product_components` (`component_type='MANAGED_SERVICE'`) | global | none | `label`, `vendor_component_sku` | `view_catalog` | `/shop/services` |
| Onboarding | `tenant_onboarding` | PK = `tenant_id` | tenant-level | `organization_name`, `legal_company_name`, status fields | tenant member | `/shop/onboarding` |

## 4. Architecture

### 4.1 Contract change (additive)
Add **`url: str | None`** to `SearchHit`. With many result types, the backend computes the deep-link and the frontend just navigates to `hit.url` — instead of the frontend hardcoding a route per `type`. Existing `type`/`title`/`subtitle` unchanged; `product`/`action` hits gain a populated `url`. Frontend `GlobalSearch.tsx` collapses its per-type routing into "navigate to `hit.url`" (falling back to the existing `ACTION_ROUTES` map for actions without a URL).

### 4.2 Per-entity providers
Refactor the products-specific lanes into a small **provider** shape (config + builder), one per entity:
```
SearchProvider = {
  type: str,                       # 'order' | 'quote' | 'design' | ...
  permission: str,                 # gate; lane skipped if user lacks it
  table, tenant_col, owner_col,    # scoping inputs
  fts_columns / trgm_column,       # lexical config
  to_hit(row) -> SearchHit(url=…), # mapper incl. deep-link + status subtitle
}
```
The orchestrator: filter providers to those the user is authorized for → run each provider's lexical lanes (reusing the existing `_build_tsquery`, RRF, `word_similarity`) under the **central scoping predicate** → collect per-entity ranked hits.

### 4.3 Central scoping helper (the security spine)
One function builds the `WHERE` fragment + bound params for any provider:
```
scope(provider, current_user) ->
  "tenant_id = :tenant"                          # always (defense in depth)
  + (" AND {owner_col} = :uid" if not _is_admin) # non-admins: own rows only
```
Bound params only. Products passes an empty scope (global). This is unit-tested in isolation so the tenant/owner predicate can never silently drop.

### 4.4 Cross-entity ranking
Each provider yields its top-N with internal RRF scores. Merge across entities with:
- **RRF across the per-entity ranked lists** (consistent with the intra-entity fusion we already use), plus
- **a recency boost** for transactional entities (orders/quotes/invoices) so "where is my order" surfaces the newest, and
- **a per-type cap** (e.g. ≤ N per type) so one entity can't crowd out the dropdown.
Action/nav hits stay pinned on top (as today).

### 4.5 "Where is my order" & nav intents
- Order/quote/invoice results put **status** in the subtitle ("Order OID0007 · Shipped") so a status question is answered in the dropdown without a click.
- Extend the Slice-4 action lane into a small **navigation registry**: "onboarding", "billing", "my designs", "managed services" → nav hits routing to the page (not a record). Cheap, keyword-driven, no DB.

### 4.6 Semantic (later)
FTS + trigram land first per entity (fast, no embedding cost). Semantic per-entity (embedding column + backfill, like products) is a **later slice** — most transactional lookups are lexical/ID-based; embeddings add the most value for designs and catalog.

## 5. Slice breakdown (each = its own PR)

- **Slice 6 — Foundation + Orders & Quotes.** Provider abstraction, `SearchHit.url` + frontend `navigate(hit.url)`, central scoping helper (+ tests), permission-gated orchestration, cross-entity merge. Ship with the two highest-value transactional entities. Delivers "where is my order/quote" end to end.
- **Slice 7 — Network designs.** `design_name`/`status`, user-scoped, deep-link `/shop/designs/:id`. Natural home for per-entity semantic later.
- **Slice 8 — Billing & lifecycle.** Invoices/payments (`view_billing`), contracts/subscriptions (`view_lifecycle`). Decision inside this slice: deep-link to list pages **or** add missing detail routes (see §6).
- **Slice 9 — Assets/devices.** Resolve the ownership-column mismatch (§6); exclude encrypted columns; `view_lifecycle`.
- **Slice 10 — Nav/onboarding/managed-services lane.** Navigation registry + managed-service catalog search. Rounds out "search everything," including non-record destinations.
- **Slice 11 — Cross-entity semantic + LLM query router (optional/advanced).** Per-entity embeddings where they pay off, a light LLM router to bias entity weighting for natural-language queries, cross-entity RRF tuning.

## 6. Open decisions (resolve before / during the relevant slice)

1. **Missing detail routes.** Contracts, subscriptions, and assets have **no single-record frontend page** (`AppRouter.tsx` has no `/shop/lifecycle/*`). Options: (a) deep-link results to the list page for now (fast), or (b) add detail routes as part of Slice 8/9 (better UX, more work). *Default: (a) now, (b) as a fast-follow.*
2. **Asset ownership column.** The model has `owner_user_id`, but `LifecycleService.list_assets` scopes non-admins via `Contract.created_by` (a join), not `owner_user_id`. Search must match the list view's semantics — **pick one deliberately** to avoid a user seeing assets in search they can't see in the list. *Recommend: mirror `LifecycleService` exactly.*
3. **Cart.** Low search value (one active cart). *Default: skip.*
4. **Non-admin billing/subscription scoping.** These scope through joins (invoice→order/subscription→contract.`created_by`). Confirm the join path per entity so a non-admin sees only their own invoices. *Mirror `BillingService`/`LifecycleService`.*

## 7. Guardrails (unchanged from Slice 2 discipline)

- Bound parameters only; permission check first; the central scoping predicate on every non-product lane.
- Contract stays `list[SearchHit]` (now with optional `url`); additive only.
- Idempotent runtime migrations (only if a slice adds columns/indexes — e.g. per-entity `search_vector`); guard optional infra like pgvector as we did in Slice 3.
- Each slice ships behind the same graceful-degradation posture: a lane that errors or lacks permission is skipped, never fatal.

## 8. Verification per slice

- **Scoping (critical):** as user A, confirm search returns A's records and **never** user B's or another tenant's — for every entity in the slice. Automated where possible, plus a live two-user check.
- Permission: a user lacking `view_billing` gets zero billing hits even with an exact match.
- Relevance: entity-appropriate queries (public IDs, status words, names) return the right record top-ranked; "where is my order" returns newest with status.
- Regression: existing product search + full `pytest` suite green.
