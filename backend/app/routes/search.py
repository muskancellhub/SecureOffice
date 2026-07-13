"""Global search — multi-entity, lexical + semantic, fused across entities.

Products (global catalog) use the full engine — full-text + fuzzy + pgvector
semantic, fused with Reciprocal Rank Fusion, plus click-popularity and an LLM
fallback (Slices 2-5). Tenant/user-scoped entities (orders, quotes, … — Slice 6+)
run a scoped lexical lane each; every entity's ranked hits are then fused across
types via RRF.

Security spine (`_scope_sql`): every non-product lane is scoped by THREE layers —
  1. tenant   — explicit predicate on the request's EFFECTIVE tenant (db.info),
                so it holds even if RLS is off and covers non-RLS tables.
  2. ownership — a non-admin only sees their own rows (created_by/owner).
  3. permission — a lane only runs if the user holds its gating permission, so an
                  unauthorized entity is never queried and cannot leak.

Contract: list[SearchHit] {id, type, title, subtitle, url}. `url` is the deep-link
the frontend navigates to. All user input is passed as bound parameters; table and
column names come only from fixed provider configs, never from user input.
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass

import httpx
from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.permissions import (
    PERM_VIEW_BILLING,
    PERM_VIEW_CATALOG,
    PERM_VIEW_LIFECYCLE,
    PERM_VIEW_ORDERS,
    PERM_VIEW_QUOTES,
)
from app.middleware.dependencies import get_current_user
from app.services.authorization_service import AuthorizationService
from app.services.search_embedding_service import embed_query, to_pgvector_literal

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/search", tags=["search"])

# RRF constant — the standard k=60 from the original RRF paper. Larger k flattens
# the contribution of top ranks; 60 is a well-tested default.
_RRF_K = 60

# Max cosine distance (0=identical, 2=opposite) for a semantic hit to count.
# Calibrated on text-embedding-3-small over this catalog: real matches land
# ~0.43-0.56, off-topic/gibberish ~0.75+. Without this cutoff the nearest-
# neighbour scan would return products for ANY query (even nonsense) and the
# LLM fallback could never trigger.
_SEMANTIC_MAX_DISTANCE = 0.65

_ADMIN_ROLES = {'ADMIN', 'SUPER_ADMIN'}


class SearchHit(BaseModel):
    id: str
    type: str
    title: str
    subtitle: str | None = None
    url: str | None = None  # deep-link the frontend navigates to (Slice 6)


class SearchClickIn(BaseModel):
    query: str
    hit_id: str
    hit_type: str
    position: int | None = None


# ── generic helpers ──────────────────────────────────────────────────────────

def _build_tsquery(q: str, op: str = '&') -> str:
    """Raw user text -> a SAFE prefix full-text query string.

    Appends ':*' to each term for PREFIX matching and strips everything except
    letters/digits so to_tsquery() can never error or be injected. ``op`` joins
    terms with '&' (all terms, default) or '|' (any term, for LLM expansion).
    """
    terms = re.findall(r'[A-Za-z0-9]+', q)
    return f' {op} '.join(f'{t}:*' for t in terms)


def _rrf(lanes: list[list[str]], k: int = _RRF_K) -> dict[str, float]:
    """Reciprocal Rank Fusion: score(id) = Σ_lanes 1 / (k + rank)."""
    scores: dict[str, float] = {}
    for lane in lanes:
        for rank, hit_id in enumerate(lane, start=1):
            scores[hit_id] = scores.get(hit_id, 0.0) + 1.0 / (k + rank)
    return scores


def _is_admin(current_user: dict) -> bool:
    return str(current_user.get('role') or '').upper() in _ADMIN_ROLES


# ── the security spine ───────────────────────────────────────────────────────

def _scope_sql(db: Session, alias: str, provider: 'EntityProvider',
               current_user: dict) -> tuple[str, dict]:
    """Build the tenant + ownership WHERE fragment for a scoped entity lane.

    Uses the request's EFFECTIVE tenant (the one get_db applied to RLS), so
    SUPER_ADMIN cross-tenant targeting via X-Tenant-Id keeps working. Non-admins
    are additionally pinned to their own rows. Values are bound params.
    """
    clauses: list[str] = []
    params: dict = {}
    tenant = db.info.get('tenant_id')
    if tenant:
        clauses.append(f'{alias}.{provider.tenant_col} = :s_tenant')
        params['s_tenant'] = str(tenant)
    if not _is_admin(current_user):
        # Entities whose owner is reached through a join (invoices,
        # subscriptions) supply an explicit predicate; it is written to HIDE
        # rather than leak when a link is missing. Others use a direct column.
        clauses.append(provider.owner_predicate
                       or f'{alias}.{provider.owner_col} = :s_uid')
        params['s_uid'] = current_user.get('user_id')
    return (' AND '.join(clauses) or 'true'), params


# ── entity providers (Slice 6+) ──────────────────────────────────────────────

def _humanize(value: str | None) -> str:
    return (value or '').replace('_', ' ').strip().title()


def _order_hit(r) -> SearchHit:
    return SearchHit(id=str(r.id), type='order', title=f'Order {r.public_id}',
                     subtitle=_humanize(r.status) or None,
                     url=f'/shop/orders/{r.id}')


def _quote_hit(r) -> SearchHit:
    return SearchHit(id=str(r.id), type='quote', title=f'Quote {r.public_id}',
                     subtitle=_humanize(r.status) or None,
                     url=f'/shop/quotes/{r.id}')


def _design_hit(r) -> SearchHit:
    return SearchHit(id=str(r.id), type='design',
                     title=r.design_name or 'Untitled design',
                     subtitle=_humanize(r.status) or 'Design',
                     url=f'/shop/designs/{r.id}')


def _subscription_hit(r) -> SearchHit:
    return SearchHit(id=str(r.id), type='subscription',
                     title=r.name or 'Subscription',
                     subtitle=_humanize(r.status) or 'Subscription',
                     url='/shop/billing')


def _invoice_hit(r) -> SearchHit:
    parts = [p for p in (_humanize(r.status), str(r.billing_month or '')) if p]
    return SearchHit(id=str(r.id), type='invoice',
                     title=f'Invoice INV-{str(r.id)[:8].upper()}',
                     subtitle=' · '.join(parts) or None,
                     url='/shop/billing')


# Ownership reached through joins — written to HIDE, not leak, on missing links.
_SUB_OWNER = ('e.contract_id IN '
              '(SELECT c.id FROM contracts c WHERE c.created_by = :s_uid)')
_INVOICE_OWNER = ('e.subscription_id IN '
                  '(SELECT s.id FROM subscriptions s '
                  'JOIN contracts c ON c.id = s.contract_id '
                  'WHERE c.created_by = :s_uid)')


@dataclass(frozen=True)
class EntityProvider:
    """Config for one tenant/user-scoped searchable entity.

    All structural fields are developer constants (never user input) so they are
    safe to interpolate into SQL; user text/ids are always bound parameters.
    ``permission=None`` means any authenticated user may search it (still scoped
    to their own rows); otherwise the lane runs only if the user holds it.
    """
    type: str
    permission: str | None
    table: str
    select: str                     # SELECT column list, aliased for to_hit
    match_cols: tuple[str, ...]     # main-table columns matched via ILIKE
    to_hit: Callable[[object], SearchHit]
    tenant_col: str = 'tenant_id'
    owner_col: str = 'created_by'
    owner_predicate: str | None = None  # join-based ownership (else owner_col)
    line_table: str | None = None   # optional line-item table to also match
    line_fk: str | None = None
    prefer_col: str | None = None   # exact-match-first ordering (e.g. public_id)
    order_tail: str = 'e.created_at DESC'


PROVIDERS: list[EntityProvider] = [
    EntityProvider(
        type='order', permission=PERM_VIEW_ORDERS, table='orders',
        select='e.id, e.public_id, e.status::text AS status',
        match_cols=('public_id', 'status'),
        line_table='order_lines', line_fk='order_id',
        prefer_col='public_id', to_hit=_order_hit),
    EntityProvider(
        type='quote', permission=PERM_VIEW_QUOTES, table='quotes',
        select='e.id, e.public_id, e.status::text AS status',
        match_cols=('public_id', 'status'),
        line_table='quote_lines', line_fk='quote_id',
        prefer_col='public_id', to_hit=_quote_hit),
    EntityProvider(
        type='design', permission=None, table='network_designs',
        select='e.id, e.design_name, e.status::text AS status',
        match_cols=('design_name', 'status'),
        prefer_col='design_name', to_hit=_design_hit),
    EntityProvider(
        type='subscription', permission=PERM_VIEW_LIFECYCLE, table='subscriptions',
        select='e.id, e.name, e.status::text AS status',
        match_cols=('name', 'sku', 'vendor', 'status'),
        owner_predicate=_SUB_OWNER, prefer_col='name', to_hit=_subscription_hit),
    EntityProvider(
        type='invoice', permission=PERM_VIEW_BILLING, table='invoices',
        select='e.id, e.status::text AS status, e.billing_month',
        match_cols=('status', 'billing_month', 'amount'),
        owner_predicate=_INVOICE_OWNER, to_hit=_invoice_hit),
]


def _run_entity(db: Session, q: str, limit: int, provider: EntityProvider,
                current_user: dict) -> list[SearchHit]:
    """Scoped lexical lane for one entity: matches its text columns (and line
    text if any); ranks exact/name matches first, then recency."""
    scope_sql, params = _scope_sql(db, 'e', provider, current_user)
    params['like'] = f'%{q}%'
    params['lim'] = limit

    match = [f'e.{c}::text ILIKE :like' for c in provider.match_cols]
    if provider.line_table:
        match.append(
            f'EXISTS (SELECT 1 FROM {provider.line_table} l '
            f'WHERE l.{provider.line_fk} = e.id '
            f'AND (l.name ILIKE :like OR l.sku ILIKE :like '
            f'OR l.vendor ILIKE :like))'
        )
    prefix = f'(e.{provider.prefer_col}::text ILIKE :like) DESC, ' if provider.prefer_col else ''
    sql = f"""
        SELECT {provider.select}
        FROM {provider.table} e
        WHERE ({scope_sql}) AND ({' OR '.join(match)})
        ORDER BY {prefix}{provider.order_tail}
        LIMIT :lim
    """
    rows = db.execute(text(sql), params).all()
    return [provider.to_hit(r) for r in rows]


# ── product lanes (Slices 2-5) ───────────────────────────────────────────────

def _product_to_hit(r) -> SearchHit:
    return SearchHit(
        id=str(r.id),
        type='product',
        title=r.name,
        subtitle=f'{r.vendor} · {r.sku}',
        url=f'/shop/routers/{r.id}',
    )


def _run_fts(db: Session, tsq: str, limit: int, pdata: dict) -> list[str]:
    """Full-text lane. Returns product ids in rank order; fills pdata[id]=row."""
    if not tsq:
        return []
    rows = db.execute(
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
    ids = []
    for r in rows:
        rid = str(r.id)
        pdata.setdefault(rid, r)
        ids.append(rid)
    return ids


def _run_fuzzy(db: Session, q: str, limit: int, pdata: dict) -> list[str]:
    """Trigram typo-tolerance lane. word_similarity scores against the best-
    matching word inside the name, so a short misspelling still matches a long
    multi-word product name (plain similarity() would score far too low)."""
    rows = db.execute(
        text("""
            SELECT id, name, vendor, sku, word_similarity(:q, name) AS sim
            FROM products
            WHERE is_active = true
              AND word_similarity(:q, name) > 0.4
            ORDER BY sim DESC
            LIMIT :limit
        """),
        {'q': q, 'limit': limit},
    ).all()
    ids = []
    for r in rows:
        rid = str(r.id)
        pdata.setdefault(rid, r)
        ids.append(rid)
    return ids


_semantic_column: bool | None = None  # cached: does products.embedding exist?


def _semantic_available(db: Session) -> bool:
    global _semantic_column
    if not settings.search_semantic_enabled:
        return False
    if _semantic_column is None:
        _semantic_column = bool(db.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='products' AND column_name='embedding'"
        )).scalar())
    return _semantic_column


def _run_semantic(db: Session, q: str, limit: int, pdata: dict) -> list[str]:
    """Vector cosine lane. Skips cleanly if pgvector or the query embedding is
    unavailable."""
    if not _semantic_available(db):
        return []
    qvec = embed_query(q)
    if qvec is None:
        return []
    rows = db.execute(
        text("""
            SELECT id, name, vendor, sku
            FROM products
            WHERE is_active = true AND embedding IS NOT NULL
              AND embedding <=> CAST(:qvec AS vector) < :maxdist
            ORDER BY embedding <=> CAST(:qvec AS vector)
            LIMIT :limit
        """),
        {'qvec': to_pgvector_literal(qvec), 'limit': limit,
         'maxdist': _SEMANTIC_MAX_DISTANCE},
    ).all()
    ids = []
    for r in rows:
        rid = str(r.id)
        pdata.setdefault(rid, r)
        ids.append(rid)
    return ids


def _run_popularity(db: Session, candidate_ids: list[str]) -> list[str]:
    """Rank the already-found candidates by historical click count. Pure re-
    ranking signal — never introduces products the other lanes didn't surface."""
    if not candidate_ids:
        return []
    rows = db.execute(
        text("""
            SELECT hit_id, count(*) AS clicks
            FROM search_click_log
            WHERE hit_type = 'product' AND hit_id = ANY(:ids)
            GROUP BY hit_id
            ORDER BY clicks DESC
        """),
        {'ids': candidate_ids},
    ).all()
    return [str(r.hit_id) for r in rows]


def _llm_expand_query(q: str) -> list[str]:
    """Ask the model for alternative search keywords. Best-effort; [] on failure."""
    api_key = settings.openai_api_key.strip()
    if not (settings.search_llm_fallback_enabled and api_key):
        return []
    try:
        resp = httpx.post(
            'https://api.openai.com/v1/chat/completions',
            headers={'Authorization': f'Bearer {api_key}',
                     'Content-Type': 'application/json'},
            json={
                'model': settings.search_llm_fallback_model,
                'messages': [
                    {'role': 'system', 'content':
                        'You expand a product-catalog search query into alternative '
                        'keywords (synonyms, canonical brand/category names, '
                        'corrected spelling). Reply ONLY with a JSON array of 3-6 '
                        'short lowercase keyword strings. No prose.'},
                    {'role': 'user', 'content': q},
                ],
                'temperature': 0,
                'max_tokens': 100,
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        content = resp.json()['choices'][0]['message']['content'].strip()
        content = re.sub(r'^```(?:json)?|```$', '', content, flags=re.MULTILINE).strip()
        terms = json.loads(content)
        return [str(t) for t in terms if isinstance(t, (str, int, float))][:6]
    except Exception as exc:  # noqa: BLE001
        logger.warning('LLM query expansion failed: %s', exc)
        return []


def _product_hits(db: Session, q: str, limit: int) -> list[SearchHit]:
    """The product pipeline (Slices 2-5, minus the LLM fallback) as a ranked list.

    The fallback is deliberately NOT here — it must fire only when the WHOLE
    cross-entity search is empty (see global_search), otherwise an order-id query
    that matched an order would still trigger a noisy product expansion."""
    fetch_k = max(limit * 2, 20)
    pdata: dict = {}

    fts_ids = _run_fts(db, _build_tsquery(q), fetch_k, pdata)
    fuzzy_ids = _run_fuzzy(db, q, fetch_k, pdata)
    semantic_ids = _run_semantic(db, q, fetch_k, pdata)

    popularity_ids = _run_popularity(db, list(pdata.keys()))
    fused = _rrf([fts_ids, fuzzy_ids, semantic_ids, popularity_ids])
    ordered = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
    return [_product_to_hit(pdata[hid]) for hid, _ in ordered[:limit]]


def _product_llm_fallback(db: Session, q: str, limit: int) -> list[SearchHit]:
    """Last resort when the entire search is empty: expand the query via the LLM
    and retry product full-text with the alternative keywords."""
    hits: list[SearchHit] = []
    for term in _llm_expand_query(q):
        expand_pdata: dict = {}
        for hid in _run_fts(db, _build_tsquery(term, op='|'), limit, expand_pdata):
            hits.append(_product_to_hit(expand_pdata[hid]))
            if len(hits) >= limit:
                return hits
    return hits


# ── Slice 4: action / command lane ───────────────────────────────────────────

_CREATE_VERB = r'(?:create|make|new|build|start|add|generate|set\s*up|setup)'
_CREATE_DESIGN_RE = re.compile(
    rf'\b{_CREATE_VERB}\b.*\bdesign\b|\bnew\s+network\b', re.IGNORECASE
)


def _detect_actions(q: str) -> list[SearchHit]:
    """Map command-style queries to actionable hits the frontend can route."""
    actions: list[SearchHit] = []
    if _CREATE_DESIGN_RE.search(q):
        actions.append(SearchHit(
            id='action:create-design',
            type='action',
            title='Create a new network design',
            subtitle='Open the design builder',
            url='/shop/designs/new',
        ))
    return actions


# ── cross-entity fusion ──────────────────────────────────────────────────────

def _merge_cross_entity(lists: list[list[SearchHit]], limit: int) -> list[SearchHit]:
    """Fuse per-entity ranked lists into one, via RRF over each hit's rank in
    its own list. Dedups by (type, id)."""
    scores: dict[tuple[str, str], float] = {}
    hit_by_key: dict[tuple[str, str], SearchHit] = {}
    for lst in lists:
        for rank, hit in enumerate(lst, start=1):
            key = (hit.type, hit.id)
            scores[key] = scores.get(key, 0.0) + 1.0 / (_RRF_K + rank)
            hit_by_key.setdefault(key, hit)
    ordered = sorted(scores, key=lambda kk: scores[kk], reverse=True)
    return [hit_by_key[kk] for kk in ordered[:limit]]


# ── endpoints ────────────────────────────────────────────────────────────────

@router.get('', response_model=list[SearchHit])
def global_search(
    q: str = Query('', min_length=0, max_length=200),
    limit: int = Query(10, ge=1, le=25),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SearchHit]:
    q = q.strip()
    if len(q) < 2:
        return []

    # Command intents surface as action hits pinned above everything.
    action_hits = _detect_actions(q)

    # Permission-gated fan-out: only lanes the user is authorized for run at all.
    perms = AuthorizationService(db).effective_permissions(current_user)

    lists: list[list[SearchHit]] = []
    if PERM_VIEW_CATALOG in perms:
        lists.append(_product_hits(db, q, limit))
    for provider in PROVIDERS:
        if provider.permission is None or provider.permission in perms:
            lists.append(_run_entity(db, q, limit, provider, current_user))

    product_slots = max(limit - len(action_hits), 0)
    merged = _merge_cross_entity(lists, product_slots)

    # LLM fallback fires only when the WHOLE search came up empty.
    if not merged and product_slots and PERM_VIEW_CATALOG in perms:
        merged = _product_llm_fallback(db, q, product_slots)

    return action_hits + merged


@router.post('/click', status_code=status.HTTP_204_NO_CONTENT)
def record_click(
    payload: SearchClickIn,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Record a result click — a learning-to-rank signal for the popularity lane.
    Any authenticated user may log a click (search itself is permission-gated)."""
    db.execute(
        text("""
            INSERT INTO search_click_log (user_id, query, hit_id, hit_type, position)
            VALUES (:uid, :q, :hid, :htype, :pos)
        """),
        {
            'uid': current_user.get('user_id'),
            'q': payload.query[:200],
            'hid': payload.hit_id,
            'htype': payload.hit_type,
            'pos': payload.position,
        },
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
