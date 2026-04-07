from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import PERM_MANAGE_MANAGED_SERVICES
from app.middleware.dependencies import get_current_user
from app.models.catalog import CatalogItemType
from app.schemas.catalog import CatalogItemResponse, UpdateManagedServiceRequest
from app.services.authorization_service import AuthorizationService
from app.services.catalog_service import CatalogService

router = APIRouter(tags=['Catalog'])


@router.get('/catalog', response_model=list[CatalogItemResponse])
def list_catalog_items(
    type: CatalogItemType | None = Query(default=None),
    category: str | None = Query(default=None),
    service_kind: str | None = Query(default=None),
    search: str | None = Query(default=None),
    brand: str | None = Query(default=None),
    vendor: str | None = Query(default=None),
    product_type: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    source_name: str | None = Query(default=None),
    wifi_standard: str | None = Query(default=None),
    availability: str | None = Query(default=None),
    min_price: float | None = Query(default=None),
    max_price: float | None = Query(default=None),
    min_ports: int | None = Query(default=None),
    sort: str | None = Query(default='recommended'),
    page: int = Query(default=1, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=250),
    _: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = CatalogService(db)
    items = service.list_items(
        item_type=type,
        category=category,
        service_kind=service_kind,
        search=search,
        brand=brand,
        vendor=vendor,
        product_type=product_type,
        source_type=source_type,
        source_name=source_name,
        wifi_standard=wifi_standard,
        availability=availability,
        min_price=min_price,
        max_price=max_price,
        min_ports=min_ports,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return [CatalogItemResponse(**service.to_catalog_response_dict(item)) for item in items]


@router.get('/catalog/{item_id}', response_model=CatalogItemResponse)
def get_catalog_item(item_id: str, _: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    service = CatalogService(db)
    item = service.get_item_by_id(item_id)
    return CatalogItemResponse(**service.to_catalog_response_dict(item))


@router.patch('/catalog/services/{item_id}', response_model=CatalogItemResponse)
def update_managed_service(
    item_id: str,
    payload: UpdateManagedServiceRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    AuthorizationService(db).require(current_user, PERM_MANAGE_MANAGED_SERVICES)

    service = CatalogService(db)
    item = service.update_managed_service(
        current_user,
        item_id,
        price=payload.price,
        is_active=payload.is_active,
        features=payload.features,
    )
    return CatalogItemResponse(**service.to_catalog_response_dict(item))
