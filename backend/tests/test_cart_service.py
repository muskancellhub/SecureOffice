"""CartService — DB integration (skips without Postgres)."""
import uuid

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
    from app.models.catalog import BillingCycle, CatalogItem, CatalogItemType
    from app.models.tenant import Tenant
    from app.models.user import User, UserRole
    apply_runtime_migrations()
    Base.metadata.create_all(bind=engine)

    tid, uid = uuid.uuid4(), uuid.uuid4()
    device_id, service_id, bad_service_id, inactive_id = (uuid.uuid4() for _ in range(4))
    with SessionLocal() as db:
        db.add(Tenant(id=tid, name=f'{PFX}Tenant'))
        db.flush()
        db.add(User(id=uid, email=f'cartsvc-{uid}@test.local', name='Cart Tester',
                    tenant_id=tid, role=UserRole.USER, is_verified=True, password_hash='x'))
        db.add(CatalogItem(id=device_id, type=CatalogItemType.DEVICE, name=f'{PFX}Router',
                           sku=f'{PFX}RTR-1', price=499.0, billing_cycle=BillingCycle.ONE_TIME,
                           attributes={'category': 'router'}))
        db.add(CatalogItem(id=service_id, type=CatalogItemType.SERVICE, name=f'{PFX}Managed Router',
                           sku=f'{PFX}SVC-1', price=29.0, billing_cycle=BillingCycle.MONTHLY,
                           attributes={'category': 'managed', 'applies_to_categories': ['router']}))
        db.add(CatalogItem(id=bad_service_id, type=CatalogItemType.SERVICE, name=f'{PFX}Managed Camera',
                           sku=f'{PFX}SVC-2', price=19.0, billing_cycle=BillingCycle.MONTHLY,
                           attributes={'category': 'managed', 'applies_to_categories': ['camera']}))
        db.add(CatalogItem(id=inactive_id, type=CatalogItemType.DEVICE, name=f'{PFX}Old Switch',
                           sku=f'{PFX}OLD-1', price=99.0, is_active=False,
                           attributes={'category': 'switch'}))
        db.commit()

    cu = {'user_id': str(uid), 'tenant_id': str(tid), 'role': 'USER'}
    ids = {'device': device_id, 'service': service_id, 'bad_service': bad_service_id,
           'inactive': inactive_id}
    yield SessionLocal, cu, ids

    with SessionLocal() as db:
        db.execute(text('DELETE FROM cart_lines WHERE cart_id IN (SELECT id FROM carts WHERE tenant_id = :t)'), {'t': str(tid)})
        db.execute(text('DELETE FROM carts WHERE tenant_id = :t'), {'t': str(tid)})
        db.execute(text("DELETE FROM catalog_items WHERE sku LIKE :p"), {'p': f'{PFX}%'})
        db.execute(text('DELETE FROM users WHERE id = :u'), {'u': str(uid)})
        db.execute(text('DELETE FROM tenants WHERE id = :t'), {'t': str(tid)})
        db.commit()


@pytest.fixture()
def fresh_cart(cart_db):
    """Empty the user's cart lines before each test that wants a clean slate."""
    SessionLocal, cu, ids = cart_db
    from sqlalchemy import text
    with SessionLocal() as db:
        db.execute(text('DELETE FROM cart_lines WHERE cart_id IN (SELECT id FROM carts WHERE tenant_id = :t)'), {'t': cu['tenant_id']})
        db.commit()
    return cart_db


def _svc(db):
    from app.services.cart_service import CartService
    return CartService(db)


def test_get_active_cart_creates_once(fresh_cart):
    SessionLocal, cu, ids = fresh_cart
    with SessionLocal() as db:
        cart1 = _svc(db).get_active_cart(cu)
        cart2 = _svc(db).get_active_cart(cu)
        assert cart1.id == cart2.id
        assert cart1.lines == []


def test_unknown_user_unauthorized(cart_db):
    from app.core.exceptions import UnauthorizedError
    SessionLocal, cu, ids = cart_db
    with SessionLocal() as db:
        with pytest.raises(UnauthorizedError):
            _svc(db).get_active_cart({'user_id': str(uuid.uuid4()), 'tenant_id': cu['tenant_id']})


def test_add_device_line_snapshots(fresh_cart):
    SessionLocal, cu, ids = fresh_cart
    with SessionLocal() as db:
        cart = _svc(db).add_line(cu, catalog_item_id=str(ids['device']), quantity=3, applies_to_line_id=None)
        assert len(cart.lines) == 1
        line = cart.lines[0]
        assert line.quantity == 3
        snap = line.price_snapshot
        assert snap['sku'].endswith('RTR-1')
        assert snap['type'] == 'DEVICE'
        assert snap['category'] == 'router'
        assert snap['billing_cycle'] == 'ONE_TIME'


def test_add_inactive_or_missing_item_not_found(fresh_cart):
    from app.core.exceptions import NotFoundError
    SessionLocal, cu, ids = fresh_cart
    with SessionLocal() as db:
        with pytest.raises(NotFoundError):
            _svc(db).add_line(cu, catalog_item_id=str(ids['inactive']), quantity=1, applies_to_line_id=None)
        with pytest.raises(NotFoundError):
            _svc(db).add_line(cu, catalog_item_id=str(uuid.uuid4()), quantity=1, applies_to_line_id=None)


def test_re_add_same_item_replaces_quantity(fresh_cart):
    SessionLocal, cu, ids = fresh_cart
    with SessionLocal() as db:
        svc = _svc(db)
        svc.add_line(cu, catalog_item_id=str(ids['device']), quantity=2, applies_to_line_id=None)
        cart = svc.add_line(cu, catalog_item_id=str(ids['device']), quantity=5, applies_to_line_id=None)
        assert len(cart.lines) == 1
        assert cart.lines[0].quantity == 5


def test_attach_service_pins_quantity_to_device(fresh_cart):
    SessionLocal, cu, ids = fresh_cart
    with SessionLocal() as db:
        svc = _svc(db)
        cart = svc.add_line(cu, catalog_item_id=str(ids['device']), quantity=4, applies_to_line_id=None)
        device_line = cart.lines[0]
        cart = svc.add_line(cu, catalog_item_id=str(ids['service']), quantity=1,
                            applies_to_line_id=str(device_line.id))
        service_line = next(l for l in cart.lines if str(l.catalog_item_id) == str(ids['service']))
        assert service_line.quantity == 4  # follows the device, not the requested 1
        assert str(service_line.applies_to_line_id) == str(device_line.id)


def test_attach_non_service_rejected(fresh_cart):
    from app.core.exceptions import AppError
    SessionLocal, cu, ids = fresh_cart
    with SessionLocal() as db:
        svc = _svc(db)
        cart = svc.add_line(cu, catalog_item_id=str(ids['device']), quantity=1, applies_to_line_id=None)
        with pytest.raises(AppError) as exc:
            svc.add_line(cu, catalog_item_id=str(ids['device']), quantity=1,
                         applies_to_line_id=str(cart.lines[0].id))
        assert exc.value.status_code == 400


def test_attach_service_to_disallowed_category_forbidden(fresh_cart):
    from app.core.exceptions import ForbiddenError
    SessionLocal, cu, ids = fresh_cart
    with SessionLocal() as db:
        svc = _svc(db)
        cart = svc.add_line(cu, catalog_item_id=str(ids['device']), quantity=1, applies_to_line_id=None)
        with pytest.raises(ForbiddenError):
            svc.add_line(cu, catalog_item_id=str(ids['bad_service']), quantity=1,
                         applies_to_line_id=str(cart.lines[0].id))


def test_attach_to_unknown_line_not_found(fresh_cart):
    from app.core.exceptions import NotFoundError
    SessionLocal, cu, ids = fresh_cart
    with SessionLocal() as db:
        with pytest.raises(NotFoundError):
            _svc(db).add_line(cu, catalog_item_id=str(ids['service']), quantity=1,
                              applies_to_line_id=str(uuid.uuid4()))


def test_remove_device_cascades_attached_services(fresh_cart):
    SessionLocal, cu, ids = fresh_cart
    with SessionLocal() as db:
        svc = _svc(db)
        cart = svc.add_line(cu, catalog_item_id=str(ids['device']), quantity=2, applies_to_line_id=None)
        device_line = cart.lines[0]
        svc.add_line(cu, catalog_item_id=str(ids['service']), quantity=1,
                     applies_to_line_id=str(device_line.id))
        cart = svc.remove_line(cu, str(device_line.id))
        assert cart.lines == []


def test_update_device_quantity_propagates_to_services(fresh_cart):
    SessionLocal, cu, ids = fresh_cart
    with SessionLocal() as db:
        svc = _svc(db)
        cart = svc.add_line(cu, catalog_item_id=str(ids['device']), quantity=2, applies_to_line_id=None)
        device_line = cart.lines[0]
        svc.add_line(cu, catalog_item_id=str(ids['service']), quantity=1,
                     applies_to_line_id=str(device_line.id))
        cart = svc.update_line(cu, str(device_line.id), quantity=7, catalog_item_id=None)
        for line in cart.lines:
            assert line.quantity == 7


def test_update_service_quantity_pinned_to_parent(fresh_cart):
    SessionLocal, cu, ids = fresh_cart
    with SessionLocal() as db:
        svc = _svc(db)
        cart = svc.add_line(cu, catalog_item_id=str(ids['device']), quantity=3, applies_to_line_id=None)
        device_line = cart.lines[0]
        cart = svc.add_line(cu, catalog_item_id=str(ids['service']), quantity=1,
                            applies_to_line_id=str(device_line.id))
        service_line = next(l for l in cart.lines if str(l.catalog_item_id) == str(ids['service']))
        cart = svc.update_line(cu, str(service_line.id), quantity=99, catalog_item_id=None)
        updated = next(l for l in cart.lines if str(l.catalog_item_id) == str(ids['service']))
        assert updated.quantity == 3  # parent wins


def test_replace_non_service_line_rejected(fresh_cart):
    from app.core.exceptions import AppError
    SessionLocal, cu, ids = fresh_cart
    with SessionLocal() as db:
        svc = _svc(db)
        cart = svc.add_line(cu, catalog_item_id=str(ids['device']), quantity=1, applies_to_line_id=None)
        with pytest.raises(AppError) as exc:
            svc.update_line(cu, str(cart.lines[0].id), quantity=None,
                            catalog_item_id=str(ids['service']))
        assert exc.value.status_code == 400


def test_service_tier_swap_validates_target_category(fresh_cart):
    from app.core.exceptions import ForbiddenError, NotFoundError
    SessionLocal, cu, ids = fresh_cart
    with SessionLocal() as db:
        svc = _svc(db)
        cart = svc.add_line(cu, catalog_item_id=str(ids['device']), quantity=1, applies_to_line_id=None)
        device_line = cart.lines[0]
        cart = svc.add_line(cu, catalog_item_id=str(ids['service']), quantity=1,
                            applies_to_line_id=str(device_line.id))
        service_line = next(l for l in cart.lines if str(l.catalog_item_id) == str(ids['service']))
        # bad_service does not allow 'router' targets
        with pytest.raises(ForbiddenError):
            svc.update_line(cu, str(service_line.id), quantity=None,
                            catalog_item_id=str(ids['bad_service']))
        # missing replacement item
        with pytest.raises(NotFoundError):
            svc.update_line(cu, str(service_line.id), quantity=None,
                            catalog_item_id=str(uuid.uuid4()))
