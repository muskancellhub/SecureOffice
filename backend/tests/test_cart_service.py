"""CartService on the component model (Phase 7 WS4) — DB integration.

Covers the WS4 acceptance criteria:
  * a configured 90X1 (2 voice lines + SIM) lands as a DEVICE parent line plus
    child component lines at the tenant's prices;
  * a standalone voice line ("add one more line", D10) attaches to a device in
    the cart or to an already-ordered device, and is blocked when it would
    exceed the device's FXS capacity;
  * cart → quote totals match the component engine.

Skips without Postgres.
"""
import uuid
from decimal import Decimal

import pytest

PFX = 'CARTSVC-'


@pytest.fixture(scope='module')
def cart_db():
    from sqlalchemy import text
    from app.core.database import engine, SessionLocal, Base
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
    except Exception as exc:  # pragma: no cover
        pytest.skip(f'No reachable database: {exc}')

    import app.models  # noqa: F401
    from app.core.runtime_migrations import apply_runtime_migrations
    from app.models.onboarding import TenantOnboarding
    from app.models.pricing import CustomerPricing
    from app.models.tenant import Tenant
    from app.models.user import User, UserRole
    from app.services.catalog_service import CatalogService
    Base.metadata.create_all(bind=engine)
    apply_runtime_migrations()

    tid, uid = uuid.uuid4(), uuid.uuid4()
    with SessionLocal() as db:
        CatalogService(db).seed_mix_products()
        db.add(Tenant(id=tid, name=f'{PFX}Tenant'))
        db.flush()
        db.add(User(id=uid, email=f'cartsvc-{uid}@test.local', name='Cart Tester',
                    tenant_id=tid, role=UserRole.USER, is_verified=True, password_hash='x'))
        # 20% tenant — keeps the worked-example numbers (660 / 13.80 / $30 SIM).
        db.add(CustomerPricing(tenant_id=tid, opex_eligible=True, default_margin_pct=Decimal('0.20')))
        db.add(TenantOnboarding(
            tenant_id=tid, organization_name=f'{PFX}Org', admin_name='Admin',
            admin_email='admin@test.local', tax_id='TAX-CART',
            credit_validation_status='VERIFIED', tax_validation_status='VERIFIED',
            company_setup_completed=True, payment_validation_status='VERIFIED',
            operations_address={'line1': '1 Main St', 'city': 'Austin', 'state': 'TX', 'postal_code': '78701'},
            billing_same_as_operations=True,
        ))
        db.commit()

    cu = {'user_id': str(uid), 'tenant_id': str(tid), 'role': 'USER'}
    yield SessionLocal, cu, tid

    from sqlalchemy import select
    from app.models.order import Order
    from app.models.quote import Quote
    with SessionLocal() as db:
        for o in db.scalars(select(Order).where(Order.tenant_id == tid)):
            db.delete(o)
        for q in db.scalars(select(Quote).where(Quote.tenant_id == tid)):
            db.delete(q)
        db.commit()
        db.execute(text('DELETE FROM cart_lines WHERE cart_id IN (SELECT id FROM carts WHERE tenant_id = :t)'), {'t': str(tid)})
        db.execute(text('DELETE FROM carts WHERE tenant_id = :t'), {'t': str(tid)})
        for tbl in ('deal_pricing',):
            pass  # deal_pricing rows cascade with quotes
        for tbl in ('customer_pricing', 'tenant_onboarding', 'users'):
            db.execute(text(f'DELETE FROM {tbl} WHERE tenant_id = :t'), {'t': str(tid)})
        db.execute(text('DELETE FROM tenants WHERE id = :t'), {'t': str(tid)})
        db.commit()


@pytest.fixture()
def fresh_cart(cart_db):
    """Empty the user's cart lines before each test that wants a clean slate."""
    SessionLocal, cu, tid = cart_db
    from sqlalchemy import text
    with SessionLocal() as db:
        db.execute(text('DELETE FROM cart_lines WHERE cart_id IN (SELECT id FROM carts WHERE tenant_id = :t)'), {'t': cu['tenant_id']})
        db.commit()
    return cart_db


def _svc(db):
    from app.services.cart_service import CartService
    return CartService(db)


def _x1(db):
    from sqlalchemy import select
    from app.models.product import Product, ProductComponent
    p = db.scalar(select(Product).where(Product.sku == '90X1'))
    comps = {c.vendor_component_sku: c for c in db.scalars(
        select(ProductComponent).where(ProductComponent.product_id == p.id))}
    return p, comps


def test_get_active_cart_creates_once(fresh_cart):
    SessionLocal, cu, _ = fresh_cart
    with SessionLocal() as db:
        c1 = _svc(db).get_active_cart(cu)
        c2 = _svc(db).get_active_cart(cu)
        assert str(c1.id) == str(c2.id)
        assert c1.lines == []


def test_unknown_user_unauthorized(cart_db):
    from app.core.exceptions import UnauthorizedError
    SessionLocal, cu, _ = cart_db
    with SessionLocal() as db:
        with pytest.raises(UnauthorizedError):
            _svc(db).get_active_cart({'user_id': str(uuid.uuid4()), 'tenant_id': cu['tenant_id']})


def test_clear_cart_removes_all_lines(fresh_cart):
    # BUG-CART-002: one call empties the cart (incl. attached children).
    SessionLocal, cu, _ = fresh_cart
    with SessionLocal() as db:
        p, comps = _x1(db)
        sel = {str(comps['SERV1970'].id): 2, str(comps['PAPI-SIM'].id): 1}
        cart = _svc(db).add_line(cu, product_id=str(p.id), selections=sel)
        assert len(cart.lines) >= 2
        cleared = _svc(db).clear_cart(cu)
        assert cleared.lines == []


def test_add_product_builds_parent_child_tree(fresh_cart):
    SessionLocal, cu, _ = fresh_cart
    with SessionLocal() as db:
        p, comps = _x1(db)
        sel = {str(comps['SERV1970'].id): 2, str(comps['PAPI-SIM'].id): 1}
        cart = _svc(db).add_line(cu, product_id=str(p.id), selections=sel)

        by_type = {}
        for line in cart.lines:
            by_type[(line.price_snapshot or {}).get('component_type')] = line
        device = by_type['DEVICE']
        voice = by_type['LINE_CHARGE']
        sim = by_type['SIM']
        assert device.applies_to_line_id is None and (device.price_snapshot or {}).get('is_parent')
        assert str(voice.applies_to_line_id) == str(device.id)
        assert str(sim.applies_to_line_id) == str(device.id)
        # 20% tenant prices: device 660 one-time (CAPEX), voice 13.80/mo ×2, SIM 30.
        assert float(device.unit_price) == 660.00
        assert float(voice.unit_price) == 13.80 and voice.quantity == 2
        assert float(sim.unit_price) == 30.00
        assert device.product_id == p.id and device.component_id is not None
        assert device.catalog_item_id is None  # legacy column stays NULL


def test_add_product_audits_item_name_and_price(fresh_cart):
    # BUG-AUD-005: cart_item_added must carry the human-readable name and the
    # unit price, not just the SKU.
    import logging
    from app.core.logging_config import SD_ID_AUDIT

    records = []
    handler = logging.Handler()
    handler.emit = records.append
    audit_logger = logging.getLogger('secureoffice.audit')
    audit_logger.addHandler(handler)
    audit_logger.setLevel(logging.INFO)
    try:
        SessionLocal, cu, _ = fresh_cart
        with SessionLocal() as db:
            p, comps = _x1(db)
            _svc(db).add_line(cu, product_id=str(p.id), selections={str(comps['SERV1970'].id): 2})
    finally:
        audit_logger.removeHandler(handler)

    added = [r for r in records if getattr(r, 'msgid', None) == 'cart_item_added']
    assert added, 'expected a cart_item_added audit event'
    fields = added[0].sd[SD_ID_AUDIT]
    assert fields['item_name'] == p.name
    assert float(fields['unit_price']) == 660.00


def test_remove_line_audits_quantity_removed_and_name(fresh_cart):
    # BUG-AUD-006: cart_item_removed uses quantity_removed + item_name.
    import logging
    from app.core.logging_config import SD_ID_AUDIT

    records = []
    handler = logging.Handler()
    handler.emit = records.append
    audit_logger = logging.getLogger('secureoffice.audit')
    audit_logger.addHandler(handler)
    audit_logger.setLevel(logging.INFO)
    try:
        SessionLocal, cu, _ = fresh_cart
        with SessionLocal() as db:
            p, comps = _x1(db)
            svc = _svc(db)
            cart = svc.add_line(cu, product_id=str(p.id), selections={str(comps['SERV1970'].id): 1})
            device = next(l for l in cart.lines if (l.price_snapshot or {}).get('is_parent'))
            svc.remove_line(cu, str(device.id))
    finally:
        audit_logger.removeHandler(handler)

    removed = [r for r in records if getattr(r, 'msgid', None) == 'cart_item_removed']
    assert removed, 'expected a cart_item_removed audit event'
    f = removed[0].sd[SD_ID_AUDIT]
    assert 'quantity_removed' in f
    assert 'quantity' not in f          # old field name is gone
    assert 'item_name' in f


def test_add_missing_product_not_found(fresh_cart):
    from app.core.exceptions import NotFoundError
    SessionLocal, cu, _ = fresh_cart
    with SessionLocal() as db:
        with pytest.raises(NotFoundError):
            _svc(db).add_line(cu, product_id=str(uuid.uuid4()))


def test_product_xor_component_required(fresh_cart):
    from app.core.exceptions import AppError
    SessionLocal, cu, _ = fresh_cart
    with SessionLocal() as db:
        with pytest.raises(AppError):
            _svc(db).add_line(cu)


def test_standalone_line_requires_a_device_somewhere(fresh_cart):
    from app.core.exceptions import AppError
    SessionLocal, cu, _ = fresh_cart
    with SessionLocal() as db:
        _, comps = _x1(db)
        with pytest.raises(AppError):
            _svc(db).add_line(cu, component_id=str(comps['SERV1970'].id))


def test_standalone_line_attaches_to_cart_device_and_respects_capacity(fresh_cart):
    from app.core.exceptions import AppError
    SessionLocal, cu, _ = fresh_cart
    with SessionLocal() as db:
        p, comps = _x1(db)
        cart = _svc(db).add_line(cu, product_id=str(p.id), selections={str(comps['SERV1970'].id): 7})
        device = next(l for l in cart.lines if (l.price_snapshot or {}).get('component_type') == 'DEVICE')

        # 7 voice lines in cart + 1 specialty = 8 — at the FXS limit, allowed.
        cart = _svc(db).add_line(
            cu, component_id=str(comps['SERV1969'].id), quantity=1,
            applies_to_line_id=str(device.id),
        )
        specialty = next(l for l in cart.lines if l.component_id == comps['SERV1969'].id)
        assert str(specialty.applies_to_line_id) == str(device.id)
        assert float(specialty.unit_price) == 18.60  # 15.50 × 1.20 at the 20% tenant

        # Pushing to 9 consumed FXS ports on one 8-port device → blocked.
        with pytest.raises(AppError):
            _svc(db).add_line(
                cu, component_id=str(comps['SERV1969'].id), quantity=2,
                applies_to_line_id=str(device.id),
            )


def test_standalone_line_attaches_to_existing_ordered_device(fresh_cart):
    """WS4 AC: one extra line on an existing 90X1 contract — no new device —
    and blocked past the device's FXS capacity."""
    from app.core.exceptions import AppError
    from app.models.order import Order, OrderLine, OrderStatus
    from app.models.quote import BillingType, QuoteLineType
    SessionLocal, cu, tid = fresh_cart
    with SessionLocal() as db:
        p, comps = _x1(db)
        order = Order(tenant_id=tid, created_by_user_id=uuid.UUID(cu['user_id']), status=OrderStatus.ACTIVE)
        db.add(order)
        db.flush()
        db.add(OrderLine(
            order_id=order.id, line_type=QuoteLineType.DEVICE, name_snapshot='90X1',
            sku_snapshot='PROD7901', qty=1, final_unit_price_snapshot=660,
            billing_type=BillingType.ONE_TIME, component_type='DEVICE',
            product_id=p.id, component_id=comps['PROD7901'].id,
        ))
        db.add(OrderLine(
            order_id=order.id, line_type=QuoteLineType.SERVICE, name_snapshot='Voice line',
            sku_snapshot='SERV1970', qty=7, final_unit_price_snapshot=13.80,
            billing_type=BillingType.RECURRING, component_type='LINE_CHARGE',
            product_id=p.id, component_id=comps['SERV1970'].id,
        ))
        db.commit()

        # 7 lines on the contract + 1 new = 8 → fits, no new device line.
        cart = _svc(db).add_line(cu, component_id=str(comps['SERV1970'].id), quantity=1)
        standalone = next(l for l in cart.lines if l.component_id == comps['SERV1970'].id)
        assert standalone.applies_to_line_id is None
        assert (standalone.price_snapshot or {}).get('standalone') is True
        assert float(standalone.unit_price) == 13.80
        assert all((l.price_snapshot or {}).get('component_type') != 'DEVICE' for l in cart.lines)

        # 2 more would make 9 on an 8-FXS device → blocked.
        with pytest.raises(AppError):
            _svc(db).add_line(cu, component_id=str(comps['SERV1969'].id), quantity=2)


def test_remove_device_cascades_children(fresh_cart):
    SessionLocal, cu, _ = fresh_cart
    with SessionLocal() as db:
        p, comps = _x1(db)
        cart = _svc(db).add_line(cu, product_id=str(p.id), selections={str(comps['SERV1970'].id): 1})
        device = next(l for l in cart.lines if (l.price_snapshot or {}).get('component_type') == 'DEVICE')
        cart = _svc(db).remove_line(cu, str(device.id))
        assert cart.lines == []


def test_update_device_quantity_scales_children(fresh_cart):
    SessionLocal, cu, _ = fresh_cart
    with SessionLocal() as db:
        p, comps = _x1(db)
        cart = _svc(db).add_line(cu, product_id=str(p.id), selections={str(comps['SERV1970'].id): 2})
        device = next(l for l in cart.lines if (l.price_snapshot or {}).get('component_type') == 'DEVICE')
        cart = _svc(db).update_line(cu, str(device.id), quantity=3)
        device = next(l for l in cart.lines if (l.price_snapshot or {}).get('component_type') == 'DEVICE')
        voice = next(l for l in cart.lines if (l.price_snapshot or {}).get('component_type') == 'LINE_CHARGE')
        assert device.quantity == 3 and voice.quantity == 6


def test_cart_quote_matches_component_preview(fresh_cart):
    """WS8: cart → quote totals match the engine's component-preview."""
    from app.services.component_pricing_service import ComponentPricingService
    from app.services.quote_service import QuoteService
    SessionLocal, cu, _ = fresh_cart
    with SessionLocal() as db:
        p, comps = _x1(db)
        sel = {str(comps['SERV1970'].id): 2, str(comps['PAPI-SIM'].id): 1}
        _svc(db).add_line(cu, product_id=str(p.id), selections=sel)

        preview = ComponentPricingService(db).price_product(
            p.id, financial_model='CAPEX', interval='MONTH',
            selections=sel, tenant_id=cu['tenant_id'],
        )
        quote = QuoteService(db).create_quote(cu)
        assert Decimal(quote.one_time_total) == preview['one_time_total']
        assert Decimal(quote.monthly_total) == preview['monthly_total']
        device = next(l for l in quote.lines if l.component_type == 'DEVICE')
        children = [l for l in quote.lines if l.parent_line_id == device.id]
        assert len(children) >= 2  # voice line + SIM under the device
