from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.permissions import PERM_VIEW_VENDOR_ORDERS
from app.middleware.dependencies import get_current_user
from app.models.tenant import Tenant
from app.schemas.vendor_orders import (
    VendorOrderDetailResponse,
    VendorOrderLineResponse,
    VendorOrderSummaryResponse,
)
from app.services.authorization_service import AuthorizationService
from app.services.vendor_service import VendorService

router = APIRouter(prefix='/vendor', tags=['Vendor'])


def _serialize_line(line) -> VendorOrderLineResponse:
    # NOTE: intentionally omits all price/margin fields — see schema docstring.
    return VendorOrderLineResponse(
        id=str(line.id),
        name=line.name_snapshot,
        sku=line.sku_snapshot,
        qty=line.qty,
        line_type=line.line_type.value if hasattr(line.line_type, 'value') else str(line.line_type),
        component_type=line.component_type,
        billing=line.billing_type.value if hasattr(line.billing_type, 'value') else str(line.billing_type),
        interval=line.interval.value if line.interval else None,
        created_at=line.created_at,
    )


def _serialize_summary(order, vendor_lines, buyer_company) -> VendorOrderSummaryResponse:
    return VendorOrderSummaryResponse(
        id=str(order.id),
        public_id=order.public_id,
        status=order.status.value if hasattr(order.status, 'value') else str(order.status),
        buyer_company=buyer_company,
        estimated_delivery_date=order.estimated_delivery_date,
        confirmed_delivery_date=order.confirmed_delivery_date,
        line_count=len(vendor_lines),
        total_qty=sum(line.qty for line in vendor_lines),
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


def _buyer_names(db: Session, orders) -> dict:
    """Buyer org name per order in one query — for fulfillment context only."""
    tenant_ids = {order.tenant_id for order in orders}
    if not tenant_ids:
        return {}
    rows = db.query(Tenant.id, Tenant.name).filter(Tenant.id.in_(tenant_ids)).all()
    return {str(tid): name for tid, name in rows}


@router.get('/orders', response_model=list[VendorOrderSummaryResponse])
def list_vendor_orders(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    AuthorizationService(db).require(current_user, PERM_VIEW_VENDOR_ORDERS)
    vendor_tenant_id = current_user['tenant_id']
    orders = VendorService(db).list_orders(current_user)
    buyer_names = _buyer_names(db, orders)
    return [
        _serialize_summary(
            order,
            VendorService.vendor_lines(order, vendor_tenant_id),
            buyer_names.get(str(order.tenant_id)),
        )
        for order in orders
    ]


@router.get('/orders/{order_id}', response_model=VendorOrderDetailResponse)
def get_vendor_order(order_id: str, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    AuthorizationService(db).require(current_user, PERM_VIEW_VENDOR_ORDERS)
    vendor_tenant_id = current_user['tenant_id']
    order = VendorService(db).get_order(current_user, order_id)
    vendor_lines = VendorService.vendor_lines(order, vendor_tenant_id)
    buyer_names = _buyer_names(db, [order])
    summary = _serialize_summary(order, vendor_lines, buyer_names.get(str(order.tenant_id)))
    return VendorOrderDetailResponse(
        **summary.model_dump(),
        lines=[_serialize_line(line) for line in vendor_lines],
    )
