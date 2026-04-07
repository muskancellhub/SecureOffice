from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.middleware.dependencies import get_current_user
from app.schemas.cart import AddCartLineRequest, CartLineResponse, CartResponse, UpdateCartLineRequest
from app.services.cart_service import CartService

router = APIRouter(prefix='/cart', tags=['Cart'])


def _serialize_cart(cart) -> CartResponse:
    lines_by_id = {str(line.id): line for line in cart.lines}
    lines = []
    one_time_subtotal = 0.0
    monthly_subtotal = 0.0

    for line in cart.lines:
        snapshot = line.price_snapshot or {}
        applies_to_name = None
        if line.applies_to_line_id:
            parent = lines_by_id.get(str(line.applies_to_line_id))
            if parent:
                applies_to_name = (parent.price_snapshot or {}).get('name')

        line_total = float(line.unit_price) * line.quantity
        billing_cycle = snapshot.get('billing_cycle')
        if billing_cycle == 'MONTHLY':
            monthly_subtotal += line_total
        else:
            one_time_subtotal += line_total

        lines.append(
            CartLineResponse(
                id=str(line.id),
                catalog_item_id=str(line.catalog_item_id),
                item_name=snapshot.get('name', ''),
                item_type=snapshot.get('type', ''),
                category=snapshot.get('category'),
                billing_cycle=billing_cycle,
                quantity=line.quantity,
                unit_price=float(line.unit_price),
                currency=line.currency,
                line_total=line_total,
                applies_to_line_id=str(line.applies_to_line_id) if line.applies_to_line_id else None,
                applies_to_item_name=applies_to_name,
                created_at=line.created_at,
            )
        )

    currency = lines[0].currency if lines else 'USD'
    estimated_12_month_total = one_time_subtotal + (monthly_subtotal * 12)
    return CartResponse(
        id=str(cart.id),
        status=cart.status.value,
        lines=lines,
        one_time_subtotal=one_time_subtotal,
        monthly_subtotal=monthly_subtotal,
        estimated_12_month_total=estimated_12_month_total,
        currency=currency,
    )


@router.get('', response_model=CartResponse)
def get_cart(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    cart = CartService(db).get_active_cart(current_user)
    return _serialize_cart(cart)


@router.post('/lines', response_model=CartResponse)
def add_cart_line(payload: AddCartLineRequest, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    cart = CartService(db).add_line(
        current_user,
        catalog_item_id=payload.catalog_item_id,
        quantity=payload.quantity,
        applies_to_line_id=payload.applies_to_line_id,
    )
    return _serialize_cart(cart)


@router.patch('/lines/{line_id}', response_model=CartResponse)
def update_cart_line(
    line_id: str,
    payload: UpdateCartLineRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cart = CartService(db).update_line(
        current_user,
        line_id,
        quantity=payload.quantity,
        catalog_item_id=payload.catalog_item_id,
    )
    return _serialize_cart(cart)


@router.delete('/lines/{line_id}', response_model=CartResponse)
def remove_cart_line(line_id: str, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    cart = CartService(db).remove_line(current_user, line_id)
    return _serialize_cart(cart)
