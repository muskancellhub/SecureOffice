from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.middleware.dependencies import get_current_user
from app.middleware.tenant_context import TenantContext, get_tenant_context
from app.schemas.cart import AddCartLineRequest, CartLineResponse, CartResponse, UpdateCartLineRequest
from app.services.cart_service import CartService

router = APIRouter(prefix='/cart', tags=['Cart'])

# Per-line total above which the cart returns a (non-blocking) review advisory.
_HIGH_VALUE_LINE_TOTAL = 50_000


def _effective_user(current_user: dict, ctx: TenantContext) -> dict:
    """BUG-TENANT-003: the cart (and its tenant pricing) follows the effective
    tenant, so a SUPER_ADMIN sees a per-tenant cart when the switcher is active.
    For non-admins the effective tenant is always their own, so this is a no-op."""
    return {**current_user, 'tenant_id': ctx.effective_tenant_id}


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
        recurring = snapshot.get('billing') == 'RECURRING' or snapshot.get('billing_cycle') == 'MONTHLY'
        if recurring:
            monthly_subtotal += line_total
        else:
            one_time_subtotal += line_total

        lines.append(
            CartLineResponse(
                id=str(line.id),
                product_id=str(line.product_id) if line.product_id else None,
                component_id=str(line.component_id) if line.component_id else None,
                component_type=snapshot.get('component_type'),
                item_name=snapshot.get('name', ''),
                item_type=snapshot.get('type', ''),
                category=snapshot.get('category'),
                billing_cycle=snapshot.get('billing_cycle'),
                financial_model=snapshot.get('financial_model'),
                financed=bool(snapshot.get('financed')),
                standalone=bool(snapshot.get('standalone')),
                is_parent=bool(snapshot.get('is_parent')),
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

    # BUG-CART-003: flag unusually large lines so the UI can prompt a review,
    # without hard-capping (legitimate bulk orders must still go through).
    warnings: list[str] = []
    high_value = [ln for ln in lines if ln.line_total > _HIGH_VALUE_LINE_TOTAL]
    if high_value:
        warnings.append(
            f'{len(high_value)} line(s) exceed ${_HIGH_VALUE_LINE_TOTAL:,.0f}. '
            'Please review the quantities before checkout.'
        )

    # BUG-BOM-CART-PRICE-001: lines added from a design carry a `price_changed`
    # flag set at add-time when the cart's current price differed from the BOM
    # estimate. Surface a single, non-blocking notice so the change isn't silent.
    repriced = sum(1 for line in cart.lines if (line.price_snapshot or {}).get('price_changed'))
    if repriced:
        warnings.append(
            f'{repriced} item(s) were repriced from your design estimate to current '
            'catalog rates. Review the updated prices before checkout.'
        )

    # BUG-CART-SETUP-001: setup & deployment is bundled with managed services, so
    # it's only "included" when the cart actually contains a recurring service —
    # derived from cart contents, not hard-coded.
    setup_included = monthly_subtotal > 0

    return CartResponse(
        id=str(cart.id),
        status=cart.status.value,
        lines=lines,
        one_time_subtotal=round(one_time_subtotal, 2),
        monthly_subtotal=round(monthly_subtotal, 2),
        estimated_12_month_total=round(estimated_12_month_total, 2),
        currency=currency,
        warnings=warnings,
        setup_included=setup_included,
    )


@router.get('', response_model=CartResponse)
def get_cart(
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    cart = CartService(db).get_active_cart(_effective_user(current_user, ctx))
    return _serialize_cart(cart)


@router.post('/lines', response_model=CartResponse)
def add_cart_line(
    payload: AddCartLineRequest,
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    cart = CartService(db).add_line(
        _effective_user(current_user, ctx),
        product_id=payload.product_id,
        component_id=payload.component_id,
        selections=payload.selections,
        quantity=payload.quantity,
        financial_model=payload.financial_model,
        interval=payload.interval,
        applies_to_line_id=payload.applies_to_line_id,
        source_unit_price=payload.source_unit_price,
    )
    return _serialize_cart(cart)


@router.patch('/lines/{line_id}', response_model=CartResponse)
def update_cart_line(
    line_id: str,
    payload: UpdateCartLineRequest,
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    cart = CartService(db).update_line(
        _effective_user(current_user, ctx),
        line_id,
        quantity=payload.quantity,
    )
    return _serialize_cart(cart)


@router.delete('/lines/{line_id}', response_model=CartResponse)
def remove_cart_line(
    line_id: str,
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    cart = CartService(db).remove_line(_effective_user(current_user, ctx), line_id)
    return _serialize_cart(cart)


@router.delete('', response_model=CartResponse)
def clear_cart(
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """BUG-CART-002: empty the active cart in a single call."""
    cart = CartService(db).clear_cart(_effective_user(current_user, ctx))
    return _serialize_cart(cart)
