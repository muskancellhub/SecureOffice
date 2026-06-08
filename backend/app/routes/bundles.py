"""Bundle admin CRUD routes (Secure Office, Phase 5)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import PERM_MANAGE_PRODUCTS, PERM_VIEW_CATALOG
from app.middleware.dependencies import get_current_user
from app.schemas.products import (
    AddBundleItemRequest,
    BundleItemResponse,
    BundleResponse,
    CreateBundleRequest,
)
from app.services.authorization_service import AuthorizationService
from app.services.product_admin_service import ProductAdminService

router = APIRouter(prefix='/bundles', tags=['Bundles'])


def _serialize_item(i) -> BundleItemResponse:
    return BundleItemResponse(
        id=str(i.id), bundle_id=str(i.bundle_id), product_id=str(i.product_id),
        default_qty=i.default_qty, is_optional=i.is_optional, is_removable=i.is_removable,
        sort_order=i.sort_order,
    )


def _serialize_bundle(b) -> BundleResponse:
    return BundleResponse(
        id=str(b.id), sku=b.sku, name=b.name, vendor=b.vendor, technology=b.technology,
        description=b.description, is_active=b.is_active, attributes=b.attributes or {},
        items=[_serialize_item(i) for i in sorted(b.items, key=lambda x: x.sort_order)],
    )


@router.get('', response_model=list[BundleResponse])
def list_bundles(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    AuthorizationService(db).require(current_user, PERM_VIEW_CATALOG)
    return [_serialize_bundle(b) for b in ProductAdminService(db).list_bundles()]


@router.get('/{bundle_id}', response_model=BundleResponse)
def get_bundle(bundle_id: str, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    AuthorizationService(db).require(current_user, PERM_VIEW_CATALOG)
    return _serialize_bundle(ProductAdminService(db).get_bundle(bundle_id))


@router.post('', response_model=BundleResponse)
def create_bundle(payload: CreateBundleRequest, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    AuthorizationService(db).require(current_user, PERM_MANAGE_PRODUCTS)
    return _serialize_bundle(ProductAdminService(db).create_bundle(payload.model_dump(exclude_unset=True)))


@router.post('/{bundle_id}/items', response_model=BundleItemResponse)
def add_bundle_item(bundle_id: str, payload: AddBundleItemRequest, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    AuthorizationService(db).require(current_user, PERM_MANAGE_PRODUCTS)
    return _serialize_item(ProductAdminService(db).add_bundle_item(bundle_id, payload.model_dump(exclude_unset=True)))
