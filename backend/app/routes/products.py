"""Admin catalog CRUD routes (Secure Office, Phase 4)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import PERM_MANAGE_PRODUCTS, PERM_VIEW_CATALOG
from app.middleware.dependencies import get_current_user
from app.schemas.products import (
    ComponentResponse,
    CreateComponentRequest,
    CreateProductRequest,
    CreateProductWithComponentsRequest,
    ProductResponse,
    UpdateComponentRequest,
    UpdateProductRequest,
)
from app.services.authorization_service import AuthorizationService
from app.services.product_admin_service import ProductAdminService

router = APIRouter(prefix='/products', tags=['Products'])


def _enum_value(value):
    return value.value if hasattr(value, 'value') else value


def _serialize_component(c) -> ComponentResponse:
    return ComponentResponse(
        id=str(c.id),
        product_id=str(c.product_id),
        component_type=_enum_value(c.component_type),
        financial_model=_enum_value(c.financial_model),
        label=c.label,
        vendor_component_sku=c.vendor_component_sku,
        vendor_cost=float(c.vendor_cost),
        msrp=float(c.msrp) if c.msrp is not None else None,
        uom=_enum_value(c.uom),
        billing=c.billing,
        interval=c.interval,
        margin_pct=float(c.margin_pct) if c.margin_pct is not None else None,
        leasing_pct=float(c.leasing_pct) if c.leasing_pct is not None else None,
        default_qty=c.default_qty,
        is_required=c.is_required,
        is_active=c.is_active,
        attributes=c.attributes or {},
    )


def _serialize_product(p) -> ProductResponse:
    return ProductResponse(
        id=str(p.id),
        vendor=p.vendor,
        technology=p.technology,
        sku=p.sku,
        vendor_sku=p.vendor_sku,
        name=p.name,
        description=p.description,
        default_financial_model=_enum_value(p.default_financial_model),
        margin_pct=float(p.margin_pct) if p.margin_pct is not None else None,
        leasing_pct=float(p.leasing_pct) if p.leasing_pct is not None else None,
        is_active=p.is_active,
        attributes=p.attributes or {},
        components=[_serialize_component(c) for c in sorted(p.components, key=lambda c: _enum_value(c.component_type))],
    )


@router.get('', response_model=list[ProductResponse])
def list_products(
    vendor: str | None = None,
    technology: str | None = None,
    financial_model: str | None = None,
    is_active: bool | None = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    AuthorizationService(db).require(current_user, PERM_VIEW_CATALOG)
    products = ProductAdminService(db).list_products(
        vendor=vendor, technology=technology, financial_model=financial_model, is_active=is_active)
    return [_serialize_product(p) for p in products]


@router.get('/{product_id}', response_model=ProductResponse)
def get_product(product_id: str, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    AuthorizationService(db).require(current_user, PERM_VIEW_CATALOG)
    return _serialize_product(ProductAdminService(db).get_product(product_id))


@router.post('', response_model=ProductResponse)
def create_product(payload: CreateProductRequest, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    AuthorizationService(db).require(current_user, PERM_MANAGE_PRODUCTS)
    return _serialize_product(ProductAdminService(db).create_product(payload.model_dump(exclude_unset=True)))


@router.post('/with-components', response_model=ProductResponse)
def create_product_with_components(
    payload: CreateProductWithComponentsRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """BUG-PRODUCT-DATA-004: create a product and its components atomically."""
    AuthorizationService(db).require(current_user, PERM_MANAGE_PRODUCTS)
    data = payload.model_dump(exclude_unset=True)
    components = data.pop('components', [])
    return _serialize_product(
        ProductAdminService(db).create_product_with_components(data, components))


@router.patch('/{product_id}', response_model=ProductResponse)
def update_product(product_id: str, payload: UpdateProductRequest, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    AuthorizationService(db).require(current_user, PERM_MANAGE_PRODUCTS)
    return _serialize_product(ProductAdminService(db).update_product(product_id, payload.model_dump(exclude_unset=True)))


@router.post('/{product_id}/components', response_model=ComponentResponse)
def add_component(product_id: str, payload: CreateComponentRequest, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    AuthorizationService(db).require(current_user, PERM_MANAGE_PRODUCTS)
    return _serialize_component(ProductAdminService(db).add_component(product_id, payload.model_dump(exclude_unset=True)))


@router.patch('/components/{component_id}', response_model=ComponentResponse)
def update_component(component_id: str, payload: UpdateComponentRequest, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    AuthorizationService(db).require(current_user, PERM_MANAGE_PRODUCTS)
    return _serialize_component(ProductAdminService(db).update_component(component_id, payload.model_dump(exclude_unset=True)))
