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
    # word_similarity() scores the query against the best-matching WORD inside
    # the name, so a short misspelling ("cisko", "netwrok") still matches a long
    # multi-word product name — plain similarity() would compare against the
    # whole name and score far too low to clear any useful threshold here.
    if len(hits) < limit:
        fuzzy_rows = db.execute(
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
        for r in fuzzy_rows:
            rid = str(r.id)
            if rid not in seen and len(hits) < limit:
                hits.append(_row_to_hit(r))
                seen.add(rid)

    return hits
