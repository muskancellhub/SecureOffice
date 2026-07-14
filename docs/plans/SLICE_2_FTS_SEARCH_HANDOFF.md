# Handoff Plan — Global Search Slice 2: Postgres Full-Text + Fuzzy Matching

**Audience:** Claude Code
**Owner:** usdev@enidususa.com
**Status:** Ready to implement. Slice 1 is already merged.

---

## 1. Context

We are building a global search feature for SecureOffice2 in incremental vertical
slices. **Slice 1 is complete, committed, and pushed to `main`** (commit
`6a2a127`, "Add global search with centered header search box"). It provides:

- Backend: `GET /search` in `backend/app/routes/search.py`, returning a uniform
  `SearchHit` shape `{ id, type, title, subtitle }`. It currently does naive
  `ILIKE '%q%'` substring matching over the `products` table.
- Frontend: `frontend/src/components/GlobalSearch.tsx` (debounced, AbortController
  + sequence-guarded dropdown), `frontend/src/api/searchApi.ts`, mounted in
  `frontend/src/components/shop/ShopShell.tsx` topbar.

**Slice 2 replaces the `ILIKE` matching with real search:** ranked Postgres
full-text search (FTS) plus trigram (`pg_trgm`) typo tolerance. The HTTP contract
does not change, so **no frontend changes are required.**

### Confirmed environment facts (do not re-litigate)

- Dev + prod DB is **PostgreSQL** (`DATABASE_URL=postgresql+psycopg2://…:5432/secureoffice2`).
  FTS, `tsvector`, and `pg_trgm` are all available. (The `backend/secureoffice2.db`
  SQLite file is a stale leftover — ignore it.)
- The `products` table is a **global catalog with no `tenant_id`** — it is not
  tenant-scoped, so no RLS/tenant predicate is needed for product search.
- Relevant `products` columns: `id` (uuid), `name`, `vendor`, `sku`,
  `description` (nullable), `is_active` (bool).
- Auth/permission pattern: routes call
  `AuthorizationService(db).require(current_user, PERM_VIEW_CATALOG)`.
- Session + tenant RLS wiring is provided automatically by `get_db`
  (`backend/app/core/database.py`) — nothing to add.
- Schema migrations are applied at startup by `apply_runtime_migrations()` in
  `backend/app/core/runtime_migrations.py`. Every statement there is **idempotent**
  (`IF NOT EXISTS` / `IF EXISTS`). There is **no Alembic** — follow this pattern.

---

## 2. Goal & acceptance criteria

Implement Slice 2 so that `GET /search?q=…` behaves as follows:

- [ ] **Ranked results.** A term matching a product `name` ranks above a term
      matching only its `description` (field-weighted ranking).
- [ ] **Prefix / as-you-type.** `q=wif` matches "WiFi 6 AP" (mid-word prefix),
      not only complete words.
- [ ] **Typo tolerance.** `q=netwrok` and `q=cisko` still return the relevant
      network / Cisco products.
- [ ] **Exact-before-fuzzy.** Full-text matches always appear above fuzzy-only
      matches, with no duplicate rows.
- [ ] **Contract unchanged.** Response is still `list[SearchHit]`
      (`{ id, type, title, subtitle }`). Frontend is untouched.
- [ ] **Safe.** All user input is passed as bound parameters (`:tsq`, `:q`);
      no string interpolation into SQL. Permission check remains first.
- [ ] Backend boots cleanly (migration runs at startup with no error) and
      existing tests still pass.

---

## 3. Guardrails / constraints

- **Do not change the frontend.** If you think you need to, stop — the contract
  is stable by design.
- **Do not introduce Alembic or a new migration framework.** Append to
  `apply_runtime_migrations()`.
- **Keep every DB statement idempotent** (`IF NOT EXISTS`) — it runs on every boot.
- **Use bound parameters only.** Never format user text into SQL strings.
- **Use the two-argument `to_tsvector('english', …)` form** in the generated
  column — it is IMMUTABLE, which generated columns require.
- Keep the change scoped to `products`. Other entity types (designs, orders) and
  semantic/vector search are later slices — do not add them here.

---

## 4. Precondition — clean the git state first

The working tree currently has a stale lock and a dead worktree pointer that make
`git status` fail. Clear them before starting:

```bash
cd ~/SecureOffice2
rm -f .git/index.lock
git worktree prune
git status   # must succeed before proceeding
```

Work on a feature branch, e.g. `git checkout -b feature/search-slice2-fts`.

---

## 5. Task 1 — Database migration

**File:** `backend/app/core/runtime_migrations.py`
**Location:** at the end of `apply_runtime_migrations()`, **immediately before the
`_apply_rls_policies(conn)` call (~line 1416)**. Use **8-space indentation** so the
statements are inside the `with engine.begin() as conn:` block (that block defines
`conn`).

```python
        # ── Slice 2: global-search full-text + fuzzy indexes on products ─────
        # pg_trgm provides trigram similarity (typo tolerance).
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))

        # GENERATED tsvector column — Postgres keeps it in sync automatically on
        # every insert/update. Two-arg to_tsvector('english', ...) is IMMUTABLE
        # (required for generated columns). setweight tags field importance
        # A > B > C, so a name match ranks above a description match.
        conn.execute(text("""
            ALTER TABLE products ADD COLUMN IF NOT EXISTS search_vector tsvector
            GENERATED ALWAYS AS (
                setweight(to_tsvector('english', coalesce(name, '')),        'A') ||
                setweight(to_tsvector('english', coalesce(vendor, '')),      'B') ||
                setweight(to_tsvector('english', coalesce(sku, '')),         'B') ||
                setweight(to_tsvector('english', coalesce(description, '')), 'C')
            ) STORED
        """))

        # GIN index for full-text lookups.
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_products_search_vector "
            "ON products USING gin (search_vector)"
        ))

        # GIN trigram index on name for fuzzy matching at scale.
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_products_name_trgm "
            "ON products USING gin (name gin_trgm_ops)"
        ))
```

`text` is already imported at the top of this file. Adding a generated column to a
populated table triggers a one-time table rewrite (fine at catalog size).

---

## 6. Task 2 — Rewrite the search query

**File:** `backend/app/routes/search.py`
**Action:** replace the whole file with the following. This switches from the ORM
to raw SQL via `text()` because FTS functions (`ts_rank_cd`, `to_tsquery`) are not
first-class in the ORM. The `Product` model / `select` / `or_` imports are dropped;
`re` and `text` are added.

```python
import re

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import PERM_VIEW_CATALOG
from app.middleware.dependencies import get_current_user
from app.services.authorization_service import AuthorizationService

router = APIRouter(prefix="/search", tags=["search"])


class SearchHit(BaseModel):
    id: str
    type: str
    title: str
    subtitle: str | None = None


def _build_prefix_tsquery(q: str) -> str:
    """Raw user text -> a SAFE prefix full-text query string.

    Appends ':*' to each term for PREFIX matching (so "wif" matches "wifi"), and
    strips everything except letters/digits so to_tsquery() can never error on
    punctuation or be injected. Example: "cisco wif" -> "cisco:* & wif:*".
    """
    terms = re.findall(r'[A-Za-z0-9]+', q)
    return ' & '.join(f'{t}:*' for t in terms)


def _row_to_hit(r) -> SearchHit:
    return SearchHit(
        id=str(r.id),
        type='product',
        title=r.name,
        subtitle=f'{r.vendor} · {r.sku}',
    )


@router.get('', response_model=list[SearchHit])
def global_search(
    q: str = Query('', min_length=0, max_length=200),
    limit: int = Query(10, ge=1, le=25),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SearchHit]:
    AuthorizationService(db).require(current_user, PERM_VIEW_CATALOG)

    q = q.strip()
    if len(q) < 2:
        return []

    hits: list[SearchHit] = []
    seen: set[str] = set()

    # Lane 1: full-text search, ranked (name > vendor/sku > description).
    tsq = _build_prefix_tsquery(q)
    if tsq:
        fts_rows = db.execute(
            text("""
                SELECT id, name, vendor, sku,
                       ts_rank_cd(search_vector, to_tsquery('english', :tsq)) AS rank
                FROM products
                WHERE is_active = true
                  AND search_vector @@ to_tsquery('english', :tsq)
                ORDER BY rank DESC
                LIMIT :limit
            """),
            {'tsq': tsq, 'limit': limit},
        ).all()
        for r in fts_rows:
            hits.append(_row_to_hit(r))
            seen.add(str(r.id))

    # Lane 2: fuzzy/typo tolerance, only to fill remaining slots.
    if len(hits) < limit:
        fuzzy_rows = db.execute(
            text("""
                SELECT id, name, vendor, sku, similarity(name, :q) AS sim
                FROM products
                WHERE is_active = true
                  AND similarity(name, :q) > 0.3
                ORDER BY sim DESC
                LIMIT :limit
            """),
            {'q': q, 'limit': limit},
        ).all()
        for r in fuzzy_rows:
            rid = str(r.id)
            if rid not in seen and len(hits) < limit:
                hits.append(_row_to_hit(r))
                seen.add(rid)

    return hits
```

---

## 7. Task 3 — Frontend

**No changes.** The response contract is unchanged. Confirm by reading
`frontend/src/api/searchApi.ts` (`SearchHit` fields must still match) — do not edit.

---

## 8. Verification

Run and confirm all of these before opening a PR.

1. **Boot:** start the backend (`cd backend && uvicorn app.main:app --reload
   --port 8000`) and confirm the migration runs with no error in the terminal.
2. **Schema applied** (from a psql shell on the dev DB):
   ```sql
   \d products                              -- shows search_vector + the two indexes
   SELECT extname FROM pg_extension WHERE extname = 'pg_trgm';  -- 1 row
   ```
3. **Prefix:** `GET /search?q=wif` returns WiFi products (via /docs or curl with a
   bearer token).
4. **Typo:** `GET /search?q=netwrok` and `q=cisko` still return relevant products.
5. **Ranking:** pick a term present in one product's `name` and another's
   `description`; the name match must appear first.
6. **No duplicates:** a term that matches both lanes returns each product once.
7. **Regression:** run the backend test suite (`pytest` in `backend/`) — it must
   still pass.

---

## 9. Rollback

Purely additive and reversible:

```sql
DROP INDEX IF EXISTS ix_products_search_vector;
DROP INDEX IF EXISTS ix_products_name_trgm;
ALTER TABLE products DROP COLUMN IF EXISTS search_vector;
-- pg_trgm extension can be left installed; it is harmless.
```

Revert `search.py` to the Slice 1 version from commit `6a2a127`.

---

## 10. Commit & PR

- Commit the two changed files together with a message like:
  `feat(search): Slice 2 — Postgres full-text ranking + pg_trgm typo tolerance`
- PR description should note: no frontend/contract change; migration is idempotent
  and additive; verification checklist above completed.
- Do **not** merge Slice 3 (pgvector/semantic) work into this PR — it is a separate
  slice.

---

## Out of scope (later slices)

- Slice 3: pgvector semantic search + Reciprocal Rank Fusion.
- Slice 4: action/command lane ("make a new network design").
- Slice 5: LLM fallback + click-log ranking.
- Extending search beyond `products` to tenant-scoped entities (will require the
  RLS/tenant predicate that products don't need).
