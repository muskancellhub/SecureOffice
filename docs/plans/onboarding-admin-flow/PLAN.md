# Plan — Company-First Onboarding, Admin Model, EULA & Design Review Routing

**Source:** product conversation (2026-06-09).
**Status:** draft for review. Decisions marked `❓DECISION` need sign-off before build.

This turns the conversation into a buildable plan. Each section states the
**requirement** (what was said), the **current state** (what the code does today),
and the **work** (the gap to close).

---

## 0. Governing principle

> "We are not having individual users. Everyone signs up with a **company email**
> and enters a **company name** → that becomes the tenant."

The tenant is the company. There is no standalone individual account. Every user
belongs to exactly one company-tenant. This reframes signup, roles, billing, and
design review around the **company** as the unit of identity and responsibility.

---

## 1. Company-first signup → tenant creation

**Requirement**
- Signup requires a **company email** and a **company name**.
- The company name becomes a **tenant** (`tenant_type = COMPANY`).
- The person who signs up (the **paying / primary user**) becomes the company's
  first **ADMIN**.

**Current state**
- `SignupPage` collects only Full Name + Email + password.
- `auth_service.signup` always assigns `role=USER`, `user_type=CELLHUB`, and drops
  the user into the **default/first tenant** (`_resolve_tenant_id`). No company
  name, no per-company tenant. (This is why the old "Default Tenant" accumulated
  ~20 unrelated users.)

**Locked decisions:** the **company is keyed on its email domain**. Free-provider
domains (gmail/outlook/yahoo/…) are **blocked** at signup. If a tenant already
exists for the domain, the new user **auto-joins it as a USER, pending admin
approval** (ties into the EULA "users come to you for approval" term, §4.2).

**STATUS (2026-06-09): items 1–4 below are BUILT & verified.** Remaining: item 5
(pending-approval queue + enforcement) and the OAuth/SSO path (see note). Built:
- `backend/app/core/email_domains.py` (free-provider blocklist + domain helpers)
- `tenants.email_domain` (unique), `users.status` (ACTIVE/PENDING), `users.is_billing_owner`
  (model + `runtime_migrations`)
- `auth_service.signup` rewritten: blocks free providers, resolves tenant by domain,
  creates COMPANY tenant + founding ADMIN (ACTIVE, billing owner) or auto-joins as
  USER/PENDING, seeds the onboarding row
- `SignupRequest.company_name`; `SignupPage` adds Company Name + "Company Email" + a
  client-side free-provider hint
- Verified: free provider→400, first signup→ADMIN/ACTIVE/billing-owner + COMPANY tenant,
  second same-domain→USER/PENDING same tenant, duplicate→409.

> **OAuth/SSO gap:** Google/Microsoft signup still uses the old `_resolve_tenant_id`
> (default/first tenant, `user_type=CELLHUB`). It does NOT yet follow company-first
> rules (no company-name capture in the SSO flow). Follow-up.

**Work**
1. Add **Company name** (required) to the signup form + payload.
2. **Block free-provider email domains** at signup (maintain a blocklist; reject
   with a clear "use your company email" message).
3. **Domain → tenant resolution** in `signup`:
   - Derive `domain` from the email. Store it on the tenant (new `tenants.email_domain`,
     unique) so it's the canonical company key.
   - **No tenant for this domain** → provision a **new COMPANY tenant** (name = company
     name, `email_domain` = domain), `user_type=COMPANY`, and make the signup user the
     first **ADMIN** + **billing owner** (the "paying/primary user").
   - **Tenant exists for this domain** → **auto-join as USER** with `status=PENDING`
     (new user status); the tenant's admin must approve before the user is active.
4. Seed the `TenantOnboarding` row for newly-created tenants (`organization_name` = company).
5. **Pending-approval surface**: admins get a queue of pending joiners to approve/reject
   (this is the "authorization/approval" the admin EULA makes them liable for).

---

## 2. Roles within a company

**Requirement**
- The **primary/paying user = ADMIN** by default ("whoever is the paying user is
  the admin").
- The primary admin can **assign others as ADMIN**, or they stay **USER**.
  ("I assign Vijay as admin, rest are users only.")
- **Minimum one admin** per company; **multiple admins allowed** (no hard max).
- (Future / SMB-with-consumer) a finer split of **Commercial admin** vs **IT admin**
  — commercial admin can remove the IT admin; if the commercial admin leaves they
  lose data/page visibility but can still do add/delete. → **deferred**, §9.

**Current state**
- `UserRole` = SUPER_ADMIN / ADMIN / USER (per-user, independent of tenant) ✓.
- `user_management_service.create_user` already gates who can create which role
  (ADMIN can create USERs in own tenant; SUPER_ADMIN any). ✓ partial.
- `AdminUserManagementPage` exists.
- **Gap:** no "promote existing user to ADMIN" path, no "min 1 admin" invariant.

**Work**
1. Add **promote/demote role** within a tenant (ADMIN↔USER) to user-management
   (service + route + page), gated so an ADMIN can manage only their own tenant.
2. Enforce the **invariant: a COMPANY tenant must always have ≥1 ADMIN** (block
   demoting/removing the last admin).
3. Mark the signup/primary admin as the **billing owner** (so we know "the paying
   user"). Add a flag or derive from "first admin" — `❓DECISION 3`.

---

## 3. Admin elevation flow + EULA acceptance gate

**Requirement**
- When the primary admin promotes someone to ADMIN:
  1. That person gets an **email**: "you've been promoted to admin," with a **login
     link** ("you've been elevated to admin — login here").
  2. On login, before they can act as admin, they must **accept a multi-part EULA**
     (not one document — **3–4 separate terms**, see §4).
- Acceptance is an **approval**, recorded against that admin (this is what shifts
  responsibility to them — see §4).

**Current state**
- No invite/elevation email. No terms acceptance anywhere (`grep` found none).
- Email infra exists (Resend, `EmailService`), used for OTP.

**Work**
1. **Elevation email**: on promote-to-admin, send a Resend email with a signed,
   expiring link to an **"Accept admin terms"** page.
2. **EULA acceptance page** (frontend): renders the 3–4 agreements (§4) as separate,
   individually-checked sections; all required to proceed.
3. **Persistence**: new table `admin_terms_acceptances` (or JSONB on the user) —
   record `user_id`, `tenant_id`, `eula_version`, each agreement key, `accepted_at`,
   IP/user-agent. **Locked:** until acceptance, the promoted user **acts as USER**
   for authorization (no lockout); admin powers unlock only after all terms are accepted.
4. **Versioning**: store an `eula_version`; re-prompt on version bump (EULAs change
   — the conversation stressed this).
5. **Locked:** canonical EULA text lives as **versioned Markdown in the repo**
   (e.g. `docs/legal/eula/<version>/*.md`), edited by engineers via PR; the acceptance
   page renders these and records the version accepted.

---

## 4. The EULA — four agreements

The conversation specified the **content/intent** of the terms an admin accepts.
These become the sections of the acceptance gate (§3). Legal copy is for the
business/lawyer; we model the structure and store acceptance per section.

1. **Platform Terms of Use** — you won't dispute/abuse the platform; standard
   platform rules.
2. **Responsibility for your company's users** — the admin (not the platform) is
   responsible for the users they authorize/approve. Onboarding a user is an
   **approval**, not a platform intrusion; misuse by a company user (theft, leaving,
   etc.) is the admin's/company's liability.
3. **Equipment & services / preferential pricing confidentiality** — pricing shown
   is the company's **preferential pricing**; disclosing it to third parties is
   grounds for **service termination**.
4. **Billing terms** — pay within **30 days**; non-payment lets the platform
   **terminate service, repossess equipment, and pursue legal action** (jurisdiction:
   New York / New Jersey).

**Work:** content authored as versioned documents (Markdown/CMS), each rendered as
a checkbox section; acceptance stored per §3. `❓DECISION 5`: where does the canonical
EULA text live (repo Markdown vs DB/CMS so non-engineers can edit)?

---

## 5. Billing & card configuration

**Requirement**
- Admin can **configure card / subscribe** (the paying user owns billing).
- Ask whether the **card/billing address == operations address** (often differ).
- Small business (1 shop) → simple/local billing. Multi-shop (e.g. 4 shops) →
  **central billing location**.

**Current state**
- `TenantOnboarding` has payment fields (`payment_method_*`, `payment_validation_status`)
  and a payment validate endpoint. No billing-vs-operations-address question, no
  multi-location model.

**STATUS (2026-06-09): address capture + validation BUILT & verified.**
- `tenant_onboarding.operations_address`, `.billing_address` (JSONB),
  `.billing_same_as_operations` (model + migration).
- `AddressInput` schema: US-only, blank allowed but any partial input must be
  complete + valid (required line1/city/state, 2-letter US state, ZIP `\d{5}(-\d{4})?`).
  Enforced backend (422) AND client-side in `OnboardingPage`.
- Onboarding completion now requires a valid operations address (+ a billing
  address when it differs). Billing mirrors operations when "same" is checked.
- New "Business address" card on the onboarding page (street/unit/city/state
  dropdown/ZIP) + "billing same as operations" toggle.
- Verified live: valid→stored (state normalized), partial/bad-state/bad-ZIP→422,
  billing mirrors when same, stored separately when different.

**Remaining**
1. Gate **billing/card config to ADMIN** (the paying user), not all users. *(open)*
2. (Later) multi-location / central-billing model for chains — `❓DECISION 6`, likely
   deferred.

---

## 6. Design review routing (engineer reviewer, escalation, disclaimer)

**Requirement**
- During **onboarding**, the company chooses a review posture:
  - **"I have an engineer"** → designate an internal **reviewer/architect**; submitted
    designs go to **that person's review** first.
  - **Escalate ("sell-up review")** → after internal review, it comes to **CellHub
    (us)** for review.
  - **"No review"** → the company is responsible; we show a **disclaimer**.
- After a design is built, a company user can either:
  - **Submit for review** → routes per the posture above, or
  - **Order directly** → skip review, enter card, order. The platform stays out of
    the middle (no obligation).
- **Pricing/markup negotiation** ("give me less price") is handled by a **separate
  call**, set up out-of-band — NOT in the in-app flow.

**Current state**
- `DesignDetailPage` already has **Submit for review** and **Order this design**.
- `/shop/admin/design-submissions` shows **submitted** designs to SUPER_ADMIN.
- **Gap:** no reviewer/architect concept, no per-company review posture, no internal→
  CellHub escalation, no disclaimer on the no-review path.

**Work**
1. Onboarding: capture **review posture** (`has_internal_reviewer`, reviewer
   user/email; or `no_review`).
2. Design submit: route to **internal reviewer** → optional **escalate to CellHub**;
   or, if `no_review`, show **disclaimer** and allow direct order.
3. **Order-directly** path: ensure card-on-file/checkout, no review required.
4. Keep pricing negotiation **out of the app** (maybe a "Request pricing call" CTA
   that just notifies — `❓DECISION 7`).

---

## 7. Catalog constraint on designs

**Requirement**
- A design may contain **only items in our catalog** (things we can fulfill). The
  customer **cannot add arbitrary items**. ("square peg / round hole" — we can ship
  catalog items; we're not obligated to fix unsuitable designs, but can reasonably help.)

**Current state**
- The builder generates BOM/topology from the catalog already, so designs are
  largely catalog-derived. No explicit **validation** that every BOM line maps to a
  live catalog item.

**Work**
1. **Validate on save/submit/order**: every BOM `item_id` must resolve to an active
   `catalog_items` row; reject/flag otherwise.
2. UI: prevent adding non-catalog items; surface a clear message.

---

## 8. Admin visibility of ALL designs (not just submitted)

**Requirement**
- **Every design a user submits is shown on the admin page** — even ones we don't
  have to review. Admins see "this person built X."

**Current state**
- `/shop/admin/design-submissions` ops queue shows **submitted-only**
  (`list_ops_submissions`). Company admins don't have a company-wide design view.

**Work**
1. Give **company ADMINs** a view of **all designs in their tenant** (any status),
   reusing `list_for_tenant`. (Tenant-scoped; SUPER_ADMIN already sees via switcher.)
2. Decide whether CellHub's queue should also show non-submitted designs read-only
   — `❓DECISION 8`.

---

## 8b. Design flow SIMPLIFIED (2026-06-09 decision — supersedes parts of §6/§8)

The review pipeline was dropped to keep the flow simple:
- **No "Submit for review"** — users **order a design directly** (or add items to cart)
  and do other things with it. The submit button + handler were removed from
  `DesignDetailPage`; the "next action" copy now says "Ready to order".
- **No admin "Design Ops Queue"** — `/shop/admin/design-submissions` route, the
  sidebar nav item, and `AdminDesignSubmissionsPage.tsx` were removed.
- Backend `/designs/{id}/submit` and `/designs/ops/submissions` still exist but are
  now **unused by the UI** (left in place; remove later if desired). Seed still
  creates some `submitted` designs — harmless, but could be simplified.
- This **supersedes** the review-routing parts of §6 (engineer reviewer / escalate
  to CellHub) and the ops-queue part of §8.
- **No design statuses surfaced** — removed all lifecycle status UI (status chips
  on builder/detail/history, the "Progress"/status-track + milestones + status
  timeline + team-updates section, the next-action callout, and the status filter
  tabs on the history page). The backend `network_designs.status` column still
  exists (auto-save writes `reviewed`) but is no longer shown to users.
- **"Order this design" is now shown for super admin too** (removed the
  `!isSuperAdmin` gate on the detail-page order button).

## 9. Deferred (explicitly "later" / "tomorrow")

- **Commercial admin vs IT admin** split (§2) — finer role model for SMB-with-consumer.
- **Avatar** (v1, two versions) — to discuss separately.
- **Multi-location / chain billing** (§5).

---

## 10. Suggested build order

| Phase | Scope | Why first |
|------|-------|-----------|
| **P1** | Company-first signup → tenant + first user = ADMIN (§1) | Foundation; everything else assumes company-tenants |
| **P2** | Role management + ≥1-admin invariant (§2) | Needed before elevation |
| **P3** | Admin elevation email + EULA acceptance gate (§3, §4) | Core legal/responsibility model |
| **P4** | Onboarding: billing-vs-ops address + review posture (§5, §6) | Feeds billing + review routing |
| **P5** | Design review routing + order-direct + disclaimer (§6) | Builds on posture |
| **P6** | Catalog validation (§7) + admin all-designs view (§8) | Hardening + visibility |

---

## 11. Decisions

**Resolved (2026-06-09):**
1. ✅ **Company email** — **block free-provider domains** at signup.
2. ✅ **Existing company** — **auto-join as USER (pending admin approval)**; company
   keyed on **email domain**.
3. ✅ **"Paying user"** — the first/signup admin **is** the billing owner.
4. ✅ **Admin-before-acceptance** — promoted admin **acts as USER** until EULA accepted.
5. ✅ **EULA storage** — **versioned Markdown in the repo**.

**Still open:**
6. **Multi-location billing** — in scope now or deferred? (assume deferred, §9)
7. **Pricing negotiation** — just a "request a call" notification, or a tracked request?
8. **CellHub queue** — should it show non-submitted designs (read-only) too?
