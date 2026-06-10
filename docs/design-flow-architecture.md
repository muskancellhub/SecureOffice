# Design Flow & Tenant Isolation — Architecture

How tenants, users, network designs and their downstream connections (leads,
carts, quotes, orders, workflows) are stored and isolated in the database.

## 1. Tenancy model

Everything hangs off the `tenants` table. A tenant has a `tenant_type`:

| tenant_type | who                          | example                      |
|-------------|------------------------------|------------------------------|
| `CELLHUB`   | the operator (super admin)   | CellHub master `…0000c1`     |
| `COMPANY`   | a customer organisation      | company1, company2           |
| `VENDOR`    | a supplier                   | —                            |

- The **CellHub master tenant** (`00000000-0000-0000-0000-0000000000c1`) is the
  home of the `SUPER_ADMIN` operator (`muskan.d@cellhubms.com`).
- Each `users` row has a non-null `tenant_id` (`ON DELETE RESTRICT`) — a user
  always belongs to exactly one tenant.
- The two test companies:
  - `company1` → `muskan.d@enidususa.com`
  - `company2` → `dhingramuskan4@gmail.com`

## 2. How a design is stored

A design is one row in `network_designs`. Scalar columns hold the summary; the
heavy artifacts are JSONB blobs on the same row (no separate child tables):

```
network_designs
├─ id                     uuid (PK)
├─ tenant_id      ─────────────►  tenants.id     (owner; ON DELETE SET NULL)
├─ created_by     ─────────────►  users.id       (author; ON DELETE SET NULL)
├─ lead_id        ─────────────►  design_leads.id(contact; ON DELETE SET NULL)
├─ design_name           designN-INITIALS-company-YYYY-MM-DD
├─ status                draft│reviewed│submitted│in_review│…│completed
├─ estimate_capex, ap_count, switch_count, submitted_at, status_updated_at
└─ JSONB artifacts:
   ├─ calculator_input / calculator_result   the intake + sizing math
   ├─ bom            { line_items:[{item_id, name, category, qty, unit_price}], … }
   ├─ topology       node/edge graph   +   drawio_xml (the diagram)
   ├─ status_history [{status, changedAt, changedBy, note}]
   ├─ milestones     {estimatedReviewDate, …}
   ├─ updates        [{visibility:internal|customer, message}]
   ├─ install_assistance, decomposition, managed_services
   └─ metadata       {quoteId, orderId, workflowInstanceId, assetId}
```

`design_leads` is a lightweight contact captured at submit time
(`tenant_id`, `email`, `company_name`, …) and de-duplicated per tenant.

## 3. Downstream connections (design → commerce)

A design is the source of truth; submitting/advancing it **syncs** tenant-scoped
rows in the existing commerce tables. The links are kept in `metadata_json`:

- `bom.line_items` → **`quote_lines`** (a `quotes` row per design) → **`orders`**/`order_lines` → **`workflow_instances`**/`workflow_steps` → `assets`.
- **"Order this design"** is a separate, lighter path: each BOM `item_id` is added
  to the user's **`carts` / `cart_lines`** (active cart per `user_id` + `tenant_id`).

All of these — quotes, orders, workflows, carts — carry their own `tenant_id`,
so the tenant boundary is preserved end-to-end.

## 4. Tenant isolation — how it's enforced

Isolation is enforced at the repository + service layer (not just the UI):

| Actor            | What they can see / open                                            |
|------------------|--------------------------------------------------------------------|
| Regular `USER`   | only **their own** designs (`created_by = user_id`)                 |
| Tenant `ADMIN`   | only **their tenant's** designs (`tenant_id = jwt.tenant_id`)       |
| `SUPER_ADMIN`    | **any tenant** — scoped by the `X-Tenant-Id` header (tenant switcher)|

- Queries: `list_for_user` (by author), `list_for_tenant` / `list_ops_submissions`
  (by `tenant_id`).
- `get_design` runs `_assert_design_access`: a `USER` must be the author, an
  `ADMIN` must match the design's tenant, and a `SUPER_ADMIN` is allowed across
  tenants (this is what backs the admin ops queue and full-page navigation into
  `/shop/designs/{id}`).
- The designs routes now resolve the **effective tenant** via `X-Tenant-Id`
  (`get_tenant_context`). For non-super-admins this always resolves to their own
  tenant, so isolation is unchanged; a super admin sees the tenant selected in
  the switcher.

## 5. Auto-save & naming flow

```
Builder page  ──(debounced ~1.5s on any BOM/topology/calculator change)──►  POST /designs
                                                                              │
                       no design_id + no name  ──►  _generate_design_name()   │
                       = design{N}-{INITIALS}-{company}-{YYYY-MM-DD}          │
                       (N = count_for_tenant + 1)                             ▼
                                                              network_designs row (status=reviewed)
```

No Save button: the builder writes automatically. Submitting (`/designs/{id}/submit`)
flips status to `submitted`, where it appears in the admin **Design Ops Queue**
(`/shop/admin/design-submissions`).

See `design-flow-architecture.mermaid` for the entity-relationship diagram.
