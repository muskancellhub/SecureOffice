# Handoff — Design Flow End-to-End (tenant isolation, auto-save, naming, cart, admin nav)

**Audience:** Claude Code (or any engineer) picking up this work.
**Repo:** `SecureOffice2` (monorepo: `backend/` FastAPI + `frontend/` React/TS/Vite).
**Date:** 2026-06-09.

This document is the complete context for a batch of changes to the **network
design flow**. Every file touched, why, the exact final code, how to run the DB
reset, what's verified, and the known open items are below. Nothing here depends
on reading the chat it came from.

---

## 0. TL;DR of what changed

| # | Area | Files | Summary |
|---|------|-------|---------|
| 1 | Tenant isolation (super-admin path) | `backend/app/services/network_design_service.py`, `backend/app/routes/designs.py` | Designs routes resolve effective tenant via `X-Tenant-Id`; `SUPER_ADMIN` may read any tenant's design; USER/ADMIN unchanged (still isolated). |
| 2 | Auto design naming | `backend/app/services/network_design_service.py`, `backend/app/repositories/network_design_repository.py` | New designs without a name get `design{N}-{INITIALS}-{company}-{YYYY-MM-DD}` (N = per-tenant count + 1). |
| 3 | Auto-save (no Save button) | `frontend/src/pages/NetworkDesignBuilderPage.tsx` | Save button + editable name input removed; debounced (~1.5s) auto-save; name shown read-only. |
| 4 | Submit button restyle | `frontend/src/pages/DesignDetailPage.tsx` | "Submit for review" now uses the "Order this design" button style. |
| 5 | BOM per-line Edit → catalog | `frontend/src/pages/DesignDetailPage.tsx` | Each BOM line has an Edit button deep-linking to `/shop/routers?category=<line.category>`. |
| 6 | Cart-not-updating bug | `frontend/src/pages/NetworkDesignBuilderPage.tsx`, `frontend/src/pages/DesignDetailPage.tsx` | "Order this design" now calls `ShopContext.refreshCart()` so the badge/steppers update without reload. |
| 7 | Admin → design navigation | `frontend/src/pages/AdminDesignSubmissionsPage.tsx` | Clicking a submission card navigates full-page to `/shop/designs/{id}`; the detail modal was removed. |
| 8 | DB reset/seed script | `backend/scripts/reset_design_test_data.py` (new) | Keeps CellHub + company1 + company2, deletes other tenants, wipes designs, seeds 3 designs/company. |
| 9 | Docs | `docs/design-flow-architecture.md`, `docs/design-flow-architecture.mermaid` | Storage + isolation write-up and ER diagram. |

---

## 1. Key architecture facts (read before editing)

- **Auth:** `AuthContextMiddleware` decodes the JWT into `request.state.user`
  (`user_id`, `tenant_id`, `role`, `email`, `permissions`). Designs routes use
  `get_current_user` (JWT), so the JWT's `tenant_id` is the actor's *home* tenant.
- **Tenant context:** `app/middleware/tenant_context.py` exposes
  `get_tenant_context` → `TenantContext(effective_tenant_id, is_cross_tenant)`.
  `resolve_tenant_context` returns the **home tenant** unless the caller is
  `SUPER_ADMIN` *and* sends an `X-Tenant-Id` header (the frontend tenant switcher
  sets this only for super admins via `frontend/src/api/activeTenant.ts`). This
  is behaviour-preserving for everyone else.
- **Super admin:** bootstrapped from `BOOTSTRAP_SUPER_ADMIN_EMAIL`
  (`muskan.d@cellhubms.com`) in the **CellHub master tenant**
  (`00000000-0000-0000-0000-0000000000c1`). It has no designs of its own — it
  views company designs by selecting a tenant in the switcher (→ `X-Tenant-Id`).
- **Design storage:** one row in `network_designs`; heavy artifacts are JSONB on
  that row (`bom`, `topology`, `status_history`, `milestones`, `updates`,
  `decomposition`, `managed_services`, `metadata`). `metadata_json` holds
  `quoteId/orderId/workflowInstanceId/assetId` links to the commerce tables.
- **Designs save path:** `POST /designs` → `NetworkDesignService.save_design`.
  No `design_id` = create; `design_id` present = update. `submit: true` or
  `POST /designs/{id}/submit` flips status to `submitted`.
- **Repos:** `list_for_user` (by `created_by`), `list_for_tenant` /
  `list_ops_submissions` (by `tenant_id`), `get_design_by_id`.
- **Frontend cart state:** `frontend/src/context/ShopContext.tsx` owns `cart` and
  exposes `refreshCart()`. The cart badge in `components/shop/ShopShell.tsx`
  reads `cart?.lines?.length`. The builder/detail pages previously called
  `commerceApi.addCartLine` **directly**, bypassing this context — that was the
  "cart doesn't update until reload" bug.
- **Catalog deep-link:** `frontend/src/pages/RoutersCatalogPage.tsx` reads
  `?category=` and selects the matching tab (`router`/`switch`/`wifi_ap`/`firewall`
  → "Routers & switches"; `phone` → "Phones"; `laptop`/`tablet` → "Tablets &
  laptops"; `hotspot`/`cellular_gateway` → "Hotspots & gateways").
- **Routes (frontend):** `/shop/designs/new` = builder, `/shop/designs/:designId`
  = detail, `/shop/admin/design-submissions` = admin ops queue (super-admin only).

---

## 2. Backend changes

### 2.1 `backend/app/repositories/network_design_repository.py`

Added a per-tenant count used by the name generator. Inserted before
`delete_design`:

```python
def count_for_tenant(self, *, tenant_id: str | uuid.UUID) -> int:
    """Number of designs already owned by a tenant — used to derive the
    next sequential index for an auto-generated design name."""
    tenant_uuid = tenant_id if isinstance(tenant_id, uuid.UUID) else uuid.UUID(str(tenant_id))
    stmt = select(func.count(NetworkDesign.id)).where(NetworkDesign.tenant_id == tenant_uuid)
    return int(self.db.scalar(stmt) or 0)
```

(`func` and `select` were already imported.)

### 2.2 `backend/app/services/network_design_service.py`

**(a) Import:** added `import re` at the top (after `from __future__`).

**(b) `_assert_design_access` — super-admin bypass + explicit isolation.**
Replaced the method so `SUPER_ADMIN` may access any tenant's design while
`ADMIN` stays tenant-pinned and `USER` stays owner-pinned:

```python
def _assert_design_access(self, current_user: dict, design: NetworkDesign) -> None:
    role = current_user.get('role')
    # The global CellHub operator (SUPER_ADMIN) may read/manage any tenant's
    # design — this is what backs the admin design-ops queue and the
    # full-page navigation into /shop/designs/{id} across tenants.
    if role == UserRole.SUPER_ADMIN.value:
        return
    if self._is_admin(role):
        # A tenant ADMIN is pinned to their own tenant — cross-tenant designs
        # are invisible to them (tenant isolation).
        if design.tenant_id and str(design.tenant_id) != current_user['tenant_id']:
            raise ForbiddenError('Design not found in your tenant')
        return
    if not design.created_by_user_id or str(design.created_by_user_id) != current_user['user_id']:
        raise ForbiddenError('Design not found for current user')
```

**(c) Name generator helpers.** Added immediately after `_assert_design_access`:

```python
@staticmethod
def _user_initials(current_user: dict | None) -> str:
    """Two-letter initials from the actor's name, falling back to the email
    local-part (e.g. ``muskan.d@…`` → ``MD``)."""
    if not current_user:
        return 'XX'
    name = str(current_user.get('name') or '').strip()
    if not name:
        email = str(current_user.get('email') or '').strip()
        name = email.split('@', 1)[0] if email else ''
    parts = [p for p in re.split(r'[\s._\-]+', name) if p]
    if not parts:
        return 'XX'
    initials = ''.join(p[0] for p in parts[:2]).upper()
    return initials or 'XX'

@staticmethod
def _slugify_company(name: str | None) -> str:
    slug = re.sub(r'[^a-zA-Z0-9]+', '', str(name or '')).lower()
    return slug or 'company'

def _generate_design_name(self, current_user: dict | None) -> str | None:
    """Auto-generated design name in the format
    ``design{N}-{INITIALS}-{company}-{YYYY-MM-DD}`` where N is the next
    sequential index within the tenant. Used when a design is created
    without an explicit name (auto-save flow)."""
    if not current_user:
        return None
    tenant_id = current_user.get('tenant_id')
    seq = 1
    company = 'company'
    if tenant_id:
        try:
            seq = self.repo.count_for_tenant(tenant_id=tenant_id) + 1
        except Exception:
            seq = 1
        try:
            tenant = self.db.get(Tenant, self._parse_uuid(tenant_id, field_name='tenant_id'))
            if tenant and tenant.name:
                company = self._slugify_company(tenant.name)
        except Exception:
            company = 'company'
    initials = self._user_initials(current_user)
    date_str = self._now().strftime('%Y-%m-%d')
    return f'design{seq}-{initials}-{company}-{date_str}'
```

**(d) Wire the generator into `save_design`.** The old company-name fallback was
replaced. The block now reads:

```python
design_name = self._clean_text(payload.get('design_name') or payload.get('designName'))
design_id = payload.get('design_id') or payload.get('designId')
# On first create with no explicit name, auto-generate the formatted name
# (design{N}-INITIALS-company-YYYY-MM-DD). Existing designs keep their name.
if not design_name and not design_id:
    design_name = self._generate_design_name(current_user)
if design_id:
    design = self.repo.get_design_by_id(str(design_id))
    ...
```

> Note: `design_id` is now computed once here (the previously-duplicate
> assignment lower down was removed). Downstream, `if design_name is not None:
> design.design_name = design_name` still means **updates without a name keep the
> existing name** — the generator only fires on create.

**(e) `list_designs` — accept an effective tenant.** Signature + body:

```python
def list_designs(
    self,
    current_user: dict,
    *,
    submitted_only: bool = False,
    ops_view: bool = False,
    effective_tenant_id: str | None = None,
) -> list[NetworkDesign]:
    self._assert_user_exists(current_user)
    # The effective tenant is the actor's own tenant unless a SUPER_ADMIN
    # has selected another via X-Tenant-Id (resolved upstream). It is always
    # the actor's own tenant for non-super-admins, preserving isolation.
    tenant_id = effective_tenant_id or current_user['tenant_id']
    if ops_view:
        if not self._is_admin(current_user.get('role')):
            raise ForbiddenError('Ops view is available to ADMIN or SUPER_ADMIN only')
        return self.repo.list_ops_submissions(tenant_id=tenant_id)
    if self._is_admin(current_user.get('role')):
        return self.repo.list_for_tenant(tenant_id=tenant_id, submitted_only=submitted_only)
    return self.repo.list_for_user(user_id=current_user['user_id'], submitted_only=submitted_only)
```

### 2.3 `backend/app/routes/designs.py`

**Import:** `from app.middleware.tenant_context import TenantContext, get_tenant_context`.

**`GET /designs` and `GET /designs/ops/submissions`** now depend on
`get_tenant_context` and pass `effective_tenant_id=ctx.effective_tenant_id`:

```python
@router.get('', response_model=list[NetworkDesignSummaryResponse])
def list_designs(
    submitted_only: bool = False,
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    include_internal = _is_admin_actor(current_user)
    rows = NetworkDesignService(db).list_designs(
        current_user,
        submitted_only=submitted_only,
        effective_tenant_id=ctx.effective_tenant_id,
    )
    return [_serialize_summary(row, include_internal=include_internal) for row in rows]


@router.get('/ops/submissions', response_model=list[NetworkDesignSummaryResponse])
def list_ops_submissions(
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    AuthorizationService(db).require(current_user, PERM_MANAGE_LIFECYCLE)
    rows = NetworkDesignService(db).list_designs(
        current_user,
        ops_view=True,
        effective_tenant_id=ctx.effective_tenant_id,
    )
    return [_serialize_summary(row, include_internal=True) for row in rows]
```

`GET /designs/{id}` was **not** changed — `get_design` → `_assert_design_access`
already lets `SUPER_ADMIN` open any design, so the admin full-page navigation
works regardless of header. (If you later want strict scoping, gate it on
`ctx.effective_tenant_id` too.)

---

## 3. Frontend changes

### 3.1 `frontend/src/pages/NetworkDesignBuilderPage.tsx` (auto-save + cart fix)

- **Icon import:** removed `Save` from the `lucide-react` import.
- **Hooks:** destructure `refreshCart` from `useShop()`:
  `const { cart, updateLineQuantity, removeLine, refreshCart } = useShop();`
- **State:** removed `designName` state. Added auto-save plumbing:

  ```tsx
  const savedDesignRef = useRef<NetworkDesignDetail | null>(null);
  const lastSavedHashRef = useRef<string>('');
  const saveTimerRef = useRef<number | undefined>(undefined);
  const displayName = savedDesign?.designName || 'New design — auto-named on first save';
  ```

- **Removed** the onboarding-driven name-default `useEffect`; replaced with
  `useEffect(() => { savedDesignRef.current = savedDesign; }, [savedDesign]);`
- **Replaced** `onSaveDesign` with `autoSave` (does **not** send a name, so the
  backend names it on create) + a debounced effect:

  ```tsx
  const autoSave = useCallback(async (hash: string) => {
    if (!accessToken || !calculatorResult || !bom || !topologyArtifact) return;
    setSaving(true);
    setError('');
    try {
      const saved = await commerceApi.saveNetworkDesign(accessToken, {
        designId: savedDesignRef.current?.id,
        calculatorInput: calculatorInput || {},
        calculatorResult,
        bom,
        topology: topologyArtifact.topology || {},
        drawioXml: topologyArtifact.drawioXml,
        assumptions: topologyArtifact.summary?.assumptions || bom.assumptions || [],
        status: 'reviewed',
        submit: false,
      });
      setSavedDesign(saved);
      savedDesignRef.current = saved;
      lastSavedHashRef.current = hash;
      loadManagedServices(saved.id);
      setNotice('Saved automatically.');
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to auto-save design'));
    } finally {
      setSaving(false);
    }
  }, [accessToken, calculatorResult, bom, topologyArtifact, calculatorInput, loadManagedServices]);

  useEffect(() => {
    if (!accessToken || !calculatorResult || !bom || !topologyArtifact) return;
    const hash = JSON.stringify({
      calc: calculatorResult,
      lines: (bom.line_items || []).map((l) => [l.item_id, l.quantity, l.unit_price]),
      nodes: topologyArtifact.summary?.nodeCount,
      edges: topologyArtifact.summary?.edgeCount,
    });
    if (hash === lastSavedHashRef.current) return;
    if (saveTimerRef.current) window.clearTimeout(saveTimerRef.current);
    saveTimerRef.current = window.setTimeout(() => { void autoSave(hash); }, 1500);
    return () => { if (saveTimerRef.current) window.clearTimeout(saveTimerRef.current); };
  }, [accessToken, calculatorResult, bom, topologyArtifact, autoSave]);
  ```

  The `hash` guard prevents re-saving when nothing meaningful changed (so the
  `setSavedDesign` that follows a save doesn't loop).

- **Header:** replaced the editable `<input className="dnb-name-input">` with a
  read-only heading + an auto-save status line:

  ```tsx
  <h1 className="dnb-name-display">{displayName}</h1>
  <p className="apx-subtitle">Generated bill of materials and network topology from your intake. Changes save automatically.</p>
  <div className="apx-scope">
    <span className={`dnb-status-chip ${savedDesign ? 'reviewed' : 'draft'}`}>{savedDesign ? 'Reviewed' : 'Draft'}</span>
    <span className="apx-scope-meta">{saving ? 'Saving…' : savedDesign ? 'All changes saved' : 'Not saved yet'}</span>
    <span className="apx-scope-meta">{bom?.line_items?.length || 0} BOM lines · {eligibleCatalogLines.length} orderable</span>
  </div>
  ```

- **Toolbar:** removed the `<button … onClick={onSaveDesign}>Save</button>`.
- **Diagram title:** `title={`${savedDesign?.designName || 'SMB Network Design'} Diagram Preview`}`.
- **Cart fix:** after a successful add in `onAddLineToCart` and `onAddAllToCart`,
  call `await refreshCart();` before navigating to `/shop/cart`.

> ⚠️ There is a `dnb-name-display` class referenced that may not exist in CSS.
> It renders fine as an `<h1>` but you may want to add styling. See §6.

### 3.2 `frontend/src/pages/DesignDetailPage.tsx`

- **Imports:** added `Pencil` to the `lucide-react` import; added
  `import { useShop } from '../context/ShopContext';`.
- **Hook:** `const { refreshCart } = useShop();` (page is rendered inside
  `ShopProvider`, so this is safe).
- **Helper** (added above `formatDate`):

  ```tsx
  // Deep-link a BOM line to the catalog page pre-filtered to its category.
  const catalogLinkForLine = (line: NetworkBomLine): string => {
    const cat = String(line.category || '').toLowerCase();
    return cat ? `/shop/routers?category=${encodeURIComponent(cat)}` : '/shop/routers';
  };
  ```

- **Cart fix:** in `onAddAllToCart`, `if (ok > 0) await refreshCart();` before
  `setAddingAllToCart(false)` / navigate.
- **Submit button restyle:** the "Submit for review" button class changed from
  `dnb-tool-btn` to `apx-add-btn dnb-order-btn` and icon size 15→18 (matches the
  "Order this design" button).
- **BOM Edit column:** added `<th />` to the table head, an Edit cell per row, and
  a trailing `<td />` in the managed-services `tfoot` row (table is now 7 cols):

  ```tsx
  <td className="dnb-bom-action">
    <button
      type="button"
      className="dnb-add-line"
      title={`Edit ${line.category || 'item'} in catalog`}
      onClick={() => navigate(catalogLinkForLine(line))}
    >
      <Pencil size={14} /> Edit
    </button>
  </td>
  ```

### 3.3 `frontend/src/pages/AdminDesignSubmissionsPage.tsx` (navigate, remove modal)

- **Imports:** added `import { useNavigate } from 'react-router-dom';`. Trimmed
  the `lucide-react` import to `{ Globe, Save, Settings2, ShieldCheck }` (removed
  `ArrowRight` and `X`, which were only used by the now-deleted modal).
- **Hook:** `const navigate = useNavigate();` at the top of the component.
- **Card click:** `onClick={() => navigate(`/shop/designs/${row.id}`)}`
  (was `setActiveDesignId(row.id)`).
- **Removed** the entire `{activeDesign && ( …modal… )}` block at the bottom of
  the JSX.

> Behaviour change: the in-modal admin controls (post update / milestones /
> install assistance / order-decomposition view) are **gone**. Status still
> advances via **drag-and-drop** between board columns (`onDropToColumn` →
> `onAdvance`, unchanged). The detail/note/milestone handlers and their state
> (`activeDesign`, `loadActiveDesign`, `onAddUpdate`, `onSaveMilestones`,
> `onSaveInstallAssistance`, `milestones`, `installAssistance`, `noteMessage`,
> `noteVisibility`, `decompositionSections`, etc.) are now **dead code** but
> left in place. `noUnusedLocals` is **not** enabled, so the build passes. See
> §6 for the recommended follow-up (fold these controls into the design detail
> page, or delete the dead code).

---

## 4. DB reset / seed — `backend/scripts/reset_design_test_data.py` (new)

Destructive dev helper. **Cannot be run from a remote sandbox** — `DATABASE_URL`
points at `localhost:5432`, so run it on the machine with the DB.

```bash
cd backend && .venv/bin/python -m scripts.reset_design_test_data
```

What it does (idempotent, wrapped in one transaction with per-statement
SAVEPOINTs so FK ordering can't poison the run):

1. Ensures the two **COMPANY** tenants exist (tenant name == slug, so generated
   design names read `…-company1-…`):
   - `company1` → `muskan.d@enidususa.com`
   - `company2` → `dhingramuskan4@gmail.com`
   - Users: password `Password123!`, role `USER`, verified, onboarding complete.
2. Keeps **CellHub** (`00000000-0000-0000-0000-0000000000c1`, super-admin home)
   + the two companies; **deletes every other tenant** and its dependent rows.
   Removal is resilient: it deletes child tables that hang off a tenant-scoped
   parent (`cart_lines`, `quote_lines`, `order_lines`, `workflow_steps`),
   user-scoped children (`otps`, `refresh_sessions`), then loops over **every
   table with a `tenant_id` column** retrying deletes to absorb arbitrary FK
   ordering, then `users`, then `tenants`.
3. **Wipes ALL `network_designs` + `design_leads`** (clean slate).
4. Seeds **3 designs per company** named via the same format
   (`design{N}-{INITIALS}-{company}-{YYYY-MM-DD}`):
   - `design1` = `reviewed` (draft-stage; exercises auto-save / "Order this design")
   - `design2`, `design3` = `submitted` (so the admin ops queue is populated)
   - BOMs use real `catalog_items` (categories router/switch/wifi_ap/firewall when
     present) so "Order this design" and the per-line Edit deep-links resolve.
   - Prints credentials + tenant ids + seeded design names at the end.

> If the catalog is empty, seeded BOMs are empty — run the app once (or
> `scripts.seed_test_tenants`) to populate `catalog_items` first.

---

## 5. Verification status

- **Frontend:** `cd frontend && npx tsc -b --noEmit` → **clean (exit 0)**.
- **Backend:** `python -m py_compile` on all four changed files → OK.
- **New logic unit-checked** (standalone, no DB):
  - `_user_initials({'email':'muskan.d@enidususa.com'})` → `MD`.
  - `_generate_design_name(...)` → `design3-MD-company1-2026-06-09` (matches
    `^design\d+-[A-Z]{2}-company1-\d{4}-\d{2}-\d{2}$`).
  - `_assert_design_access`: SUPER_ADMIN cross-tenant **allowed**; ADMIN
    cross-tenant **blocked**; USER non-owner **blocked**.
- **Pre-existing failures (NOT from this work):**
  `backend/tests/test_network_design_service.py` has 11 failures, all
  `AttributeError: 'Profile' object has no attribute 'duns_number'`. The test's
  `FakeProfile` is stale vs. `_sync_onboarding_contact` (untouched HEAD code at
  `network_design_service.py:364`). Fix the fakes separately; unrelated to these
  changes.
- Running backend tests in a fresh env needs:
  `pip install pytest sqlalchemy fastapi pydantic pydantic-settings psycopg2-binary resend stripe "passlib[bcrypt]" python-jose email-validator`
  and env `DATABASE_URL`, `JWT_SECRET_KEY`, `OAUTH_SESSION_SECRET`.

---

## 6. Open items / follow-ups

1. **Admin controls lost with the modal.** Decide whether to (a) port post-update
   / milestones / install-assistance into `DesignDetailPage` (gated on
   `manage_lifecycle`), or (b) delete the now-dead handlers/state in
   `AdminDesignSubmissionsPage.tsx`. Currently they're dead code (build passes
   because `noUnusedLocals` is off).
2. **`get_design` strict scoping (optional).** It currently allows SUPER_ADMIN
   across tenants unconditionally. If you want it scoped to the switcher
   selection, add `get_tenant_context` and compare `design.tenant_id ==
   ctx.effective_tenant_id` for super admins.
3. **CSS for `dnb-name-display`.** New class on the builder header `<h1>`; add a
   rule (or reuse an existing heading class) for polish.
4. **`design_name` length.** Column is `String(255)`; the generated format is far
   shorter, fine. Explicit user names should still be validated client-side.
5. **Auto-save chattiness.** Debounce is 1.5s on a content hash. If write volume
   matters, consider also gating on `document.visibilitychange`/unmount flush.
6. **Git housekeeping (environment):** a stale worktree pointer exists —
   `.git/worktrees/dreamy-yonath-bebe4a/gitdir` points to a missing
   `.claude/worktrees/dreamy-yonath-bebe4a/.git`, which makes `git diff` error
   with *"not a git repository"*. Run `git worktree prune` (or remove that
   worktrees dir) to restore normal git. All edits are unstaged on disk and
   unaffected.

---

## 7. Files touched (quick index)

```
backend/app/services/network_design_service.py     (isolation, naming, list_designs)
backend/app/routes/designs.py                       (tenant-context on list endpoints)
backend/app/repositories/network_design_repository.py (count_for_tenant)
backend/scripts/reset_design_test_data.py           (NEW — reset/seed)
frontend/src/pages/NetworkDesignBuilderPage.tsx     (auto-save, no Save btn, cart fix)
frontend/src/pages/DesignDetailPage.tsx             (submit restyle, BOM Edit, cart fix)
frontend/src/pages/AdminDesignSubmissionsPage.tsx   (navigate to design, modal removed)
docs/design-flow-architecture.md                    (NEW — storage + isolation)
docs/design-flow-architecture.mermaid               (NEW — ER diagram)
docs/HANDOFF-design-flow.md                          (NEW — this file)
```
