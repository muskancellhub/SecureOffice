from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.permissions import PERM_MANAGE_LIFECYCLE
from app.middleware.dependencies import get_current_user
from app.schemas.order_notifications import (
    OrderNotificationRecipientsResponse,
    UpdateOrderNotificationRecipientsRequest,
)
from app.schemas.orders import OrderDetailResponse, OrderLineResponse, OrderSummaryResponse, UpdateOrderRequest
from app.services.authorization_service import AuthorizationService
from app.services.order_notification_service import OrderNotificationService
from app.services.order_service import OrderService

router = APIRouter(prefix='/orders', tags=['Orders'])


def _serialize_order_line(line) -> OrderLineResponse:
    return OrderLineResponse(
        id=str(line.id),
        order_id=str(line.order_id),
        line_type=line.line_type.value if hasattr(line.line_type, 'value') else str(line.line_type),
        catalog_item_id=str(line.catalog_item_id) if line.catalog_item_id else None,
        name=line.name_snapshot,
        sku=line.sku_snapshot,
        vendor=line.vendor_snapshot,
        qty=line.qty,
        list_price_snapshot=float(line.list_price_snapshot),
        final_unit_price_snapshot=float(line.final_unit_price_snapshot),
        unit_price=float(line.final_unit_price_snapshot),
        billing_type=line.billing_type.value if hasattr(line.billing_type, 'value') else str(line.billing_type),
        billing=line.billing_type.value if hasattr(line.billing_type, 'value') else str(line.billing_type),
        interval=line.interval.value if line.interval else None,
        metadata=line.metadata_json or {},
        parent_line_id=str(line.parent_line_id) if line.parent_line_id else None,
        created_at=line.created_at,
    )


def _serialize_order(order) -> OrderDetailResponse:
    return OrderDetailResponse(
        id=str(order.id),
        public_id=order.public_id,
        tenant_id=str(order.tenant_id),
        created_by_user_id=str(order.created_by_user_id),
        created_by=str(order.created_by_user_id),
        quote_id=str(order.quote_id) if order.quote_id else None,
        quote_public_id=order.quote.public_id if getattr(order, 'quote', None) else None,
        status=order.status.value if hasattr(order.status, 'value') else str(order.status),
        estimated_delivery_date=order.estimated_delivery_date,
        confirmed_delivery_date=order.confirmed_delivery_date,
        created_at=order.created_at,
        updated_at=order.updated_at,
        lines=[_serialize_order_line(line) for line in order.lines],
    )


def _serialize_order_notification_settings(settings_row) -> OrderNotificationRecipientsResponse:
    return OrderNotificationRecipientsResponse(
        tenant_id=str(settings_row.tenant_id),
        recipients=list(settings_row.recipient_emails_json or []),
        updated_by_user_id=str(settings_row.updated_by_user_id) if settings_row.updated_by_user_id else None,
        updated_at=settings_row.updated_at,
    )


@router.get('', response_model=list[OrderSummaryResponse])
def list_orders(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    orders = OrderService(db).list_orders(current_user)
    return [
        OrderSummaryResponse(
            id=str(order.id),
            public_id=order.public_id,
            tenant_id=str(order.tenant_id),
            created_by_user_id=str(order.created_by_user_id),
            created_by=str(order.created_by_user_id),
            quote_id=str(order.quote_id) if order.quote_id else None,
            quote_public_id=order.quote.public_id if getattr(order, 'quote', None) else None,
            status=order.status.value if hasattr(order.status, 'value') else str(order.status),
            estimated_delivery_date=order.estimated_delivery_date,
            confirmed_delivery_date=order.confirmed_delivery_date,
            created_at=order.created_at,
            updated_at=order.updated_at,
        )
        for order in orders
    ]


@router.get('/notifications/recipients', response_model=OrderNotificationRecipientsResponse)
def get_order_notification_recipients(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    AuthorizationService(db).require(current_user, PERM_MANAGE_LIFECYCLE)
    settings_row = OrderNotificationService(db).get_recipient_settings(current_user)
    return _serialize_order_notification_settings(settings_row)


@router.put('/notifications/recipients', response_model=OrderNotificationRecipientsResponse)
def update_order_notification_recipients(
    payload: UpdateOrderNotificationRecipientsRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    AuthorizationService(db).require(current_user, PERM_MANAGE_LIFECYCLE)
    settings_row = OrderNotificationService(db).update_recipient_settings(current_user, [str(x) for x in payload.recipients])
    return _serialize_order_notification_settings(settings_row)


@router.get('/{order_id}', response_model=OrderDetailResponse)
def get_order(order_id: str, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    order = OrderService(db).get_order(current_user, order_id)
    return _serialize_order(order)


@router.patch('/{order_id}', response_model=OrderDetailResponse)
def update_order(
    order_id: str,
    payload: UpdateOrderRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    AuthorizationService(db).require(current_user, PERM_MANAGE_LIFECYCLE)
    updates = payload.model_dump(exclude_unset=True)
    order = OrderService(db).update_order(current_user, order_id, updates)
    return _serialize_order(order)
