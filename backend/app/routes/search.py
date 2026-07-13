"""Global search — lexical + semantic, fused with Reciprocal Rank Fusion.

Lanes (each produces a ranked list of product ids; RRF fuses them):
  1. Full-text  — field-weighted tsvector, prefix-aware  (Slice 2)
  2. Fuzzy      — pg_trgm word_similarity, typo tolerant  (Slice 2)
  3. Semantic   — pgvector cosine over OpenAI embeddings   (Slice 3)
  4. Popularity — historical click counts per product      (Slice 5)

On top of product results:
  - Action lane — command intents like "make a new network design" (Slice 4)
  - LLM fallback — when every lane is empty, expand the query and retry (Slice 5)

The HTTP contract is still list[SearchHit] {id, type, title, subtitle}. Semantic
and LLM lanes degrade gracefully (skip) when pgvector or an OpenAI key is absent.
All user input is passed as bound parameters.
"""
from __future__ import annotations

import json
import logging
import re

import httpx
from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.permissions import PERM_VIEW_CATALOG
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


class SearchHit(BaseModel):
    id: str
    type: str
    title: str
    subtitle: str | None = None


class SearchClickIn(BaseModel):
    query: str
    hit_id: str
    hit_type: str
    position: int | None = None


# ── helpers ──────────────────────────────────────────────────────────────────

def _build_tsquery(q: str, op: str = '&') -> str:
    """Raw user text -> a SAFE prefix full-text query string.

    Appends ':*' to each term for PREFIX matching and strips everything except
    letters/digits so to_tsquery() can never error or be injected. ``op`` joins
    terms with '&' (all terms, default) or '|' (any term, for LLM expansion).
    """
    terms = re.findall(r'[A-Za-z0-9]+', q)
    return f' {op} '.join(f'{t}:*' for t in terms)


def _row_to_hit(r) -> SearchHit:
    return SearchHit(
        id=str(r.id),
        type='product',
        title=r.name,
        subtitle=f'{r.vendor} · {r.sku}',
    )


def _rrf(lanes: list[list[str]], k: int = _RRF_K) -> dict[str, float]:
    """Reciprocal Rank Fusion: score(id) = Σ_lanes 1 / (k + rank)."""
    scores: dict[str, float] = {}
    for lane in lanes:
        for rank, hit_id in enumerate(lane, start=1):
            scores[hit_id] = scores.get(hit_id, 0.0) + 1.0 / (k + rank)
    return scores


# ── Slice 4: action / command lane ───────────────────────────────────────────

_CREATE_VERB = r'(?:create|make|new|build|start|add|generate|set\s*up|setup)'
# A create-verb anywhere near "design", OR the explicit "new network" phrase.
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
        ))
    return actions


# ── lexical lanes ────────────────────────────────────────────────────────────

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


# ── Slice 3: semantic lane ───────────────────────────────────────────────────

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


# ── Slice 5: popularity lane + LLM fallback ──────────────────────────────────

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
        # Tolerate code-fenced or bare JSON.
        content = re.sub(r'^```(?:json)?|```$', '', content, flags=re.MULTILINE).strip()
        terms = json.loads(content)
        return [str(t) for t in terms if isinstance(t, (str, int, float))][:6]
    except Exception as exc:  # noqa: BLE001
        logger.warning('LLM query expansion failed: %s', exc)
        return []


# ── endpoints ────────────────────────────────────────────────────────────────

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

    # Slice 4: command intents surface as action hits above product results.
    action_hits = _detect_actions(q)

    # Fetch a few extra per lane so RRF has material to fuse, then trim.
    fetch_k = max(limit * 2, 20)
    pdata: dict = {}

    fts_ids = _run_fts(db, _build_tsquery(q), fetch_k, pdata)
    fuzzy_ids = _run_fuzzy(db, q, fetch_k, pdata)
    semantic_ids = _run_semantic(db, q, fetch_k, pdata)

    candidate_ids = list(pdata.keys())
    popularity_ids = _run_popularity(db, candidate_ids)

    fused = _rrf([fts_ids, fuzzy_ids, semantic_ids, popularity_ids])
    ordered = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)

    product_slots = max(limit - len(action_hits), 0)
    product_hits = [_row_to_hit(pdata[hid]) for hid, _ in ordered[:product_slots]]

    # Slice 5: nothing lexical/semantic matched — expand the query and retry FTS.
    if not product_hits and product_slots:
        for term in _llm_expand_query(q):
            tsq = _build_tsquery(term, op='|')
            expand_pdata: dict = {}
            for hid in _run_fts(db, tsq, product_slots, expand_pdata):
                product_hits.append(_row_to_hit(expand_pdata[hid]))
                if len(product_hits) >= product_slots:
                    break
            if len(product_hits) >= product_slots:
                break

    return action_hits + product_hits


@router.post('/click', status_code=status.HTTP_204_NO_CONTENT)
def record_click(
    payload: SearchClickIn,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Record a result click — a learning-to-rank signal for the popularity lane."""
    AuthorizationService(db).require(current_user, PERM_VIEW_CATALOG)
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
