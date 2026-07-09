from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import PERM_VIEW_CATALOG
from app.middleware.dependencies import get_current_user
from app.models.product import Product
from app.services.authorization_service import AuthorizationService

router = APIRouter(prefix="/search", tags=["search"])

class SearchHit(BaseModel):
    id: str
    type: str
    title: str
    subtitle: str | None = None


@router.get('',response_model=list[SearchHit])

def global_search(
    q: str = Query('', min_length=0, max_length=200),
    limit: int = Query(10,ge=1, le=25),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SearchHit]:
    AuthorizationService(db).require(current_user, PERM_VIEW_CATALOG)
    q= q.strip()
    if  len(q)<2:
        return []

    pattern = f"%{q}%"
    stmt = (
        select (Product)
        .where(Product.is_active.is_(True))  # never surface retired products
        .where(
            or_(  # match if the term appears in ANY of these columns
                Product.name.ilike(pattern),
                Product.sku.ilike(pattern),
                Product.vendor.ilike(pattern),
                Product.description.ilike(pattern),
            )
        )
        .limit(limit)  # hard cap; the dropdown never needs more
    )

    products=db.execute(stmt).scalars().all()

    return [
        SearchHit(
            id=str(p.id),
            type='product',
            title=p.name,
            subtitle=f'{p.vendor} · {p.sku}',
        )
        for p in products
    ]
