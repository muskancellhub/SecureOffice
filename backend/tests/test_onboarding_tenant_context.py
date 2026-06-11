"""Onboarding service honours the effective tenant (SUPER_ADMIN X-Tenant-Id).

DB integration (skips without Postgres). Route-level authz (non-super 403,
missing tenant 404) is covered by test_tenant_context.py — the onboarding
routes share the same get_tenant_context dependency.
"""
import uuid

import pytest

PFX = 'ONBTC-'

COMPLETE_PAYLOAD = {
    'organization_name': f'{PFX}Org B',
    'admin_name': 'B Admin',
    'admin_email': 'b-admin@test.local',
    'tax_id': 'TAX-ONBTC-B',
    'credit_validation_status': 'VERIFIED',
    'tax_validation_status': 'VERIFIED',
    'company_setup_completed': True,
    'operations_address': {
        'line1': '1 B Street', 'city': 'Bee', 'state': 'CA', 'postal_code': '90001',
    },
}


@pytest.fixture(scope='module')
def onb_db():
    from sqlalchemy import text
    from app.core.database import engine, SessionLocal, Base
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
    except Exception as exc:  # pragma: no cover
        pytest.skip(f'No reachable database: {exc}')

    import app.models  # noqa: F401
    from app.core.runtime_migrations import apply_runtime_migrations
    from app.models.tenant import Tenant
    from app.models.user import User, UserRole
    apply_runtime_migrations()
    Base.metadata.create_all(bind=engine)

    a, b = uuid.uuid4(), uuid.uuid4()
    uid = uuid.uuid4()
    with SessionLocal() as db:
        db.add(Tenant(id=a, name=f'{PFX}A'))
        db.add(Tenant(id=b, name=f'{PFX}B'))
        db.flush()  # tenants must exist before FK-dependent rows
        db.add(User(id=uid, email=f'onbtc-{uid}@test.local', name='ONBTC Super',
                    tenant_id=a, role=UserRole.SUPER_ADMIN, is_verified=True,
                    password_hash='x'))
        db.commit()

    current_user = {'user_id': str(uid), 'tenant_id': str(a), 'role': UserRole.SUPER_ADMIN.value}
    yield SessionLocal, a, b, current_user

    with SessionLocal() as db:
        db.execute(text('DELETE FROM users WHERE id = :u'), {'u': str(uid)})
        for t in (a, b):
            db.execute(text('DELETE FROM tenant_onboarding WHERE tenant_id = :t'), {'t': str(t)})
            db.execute(text('DELETE FROM tenants WHERE id = :t'), {'t': str(t)})
        db.commit()


def _service(db):
    from app.services.onboarding_service import OnboardingService
    return OnboardingService(db)


def _delete_profiles(SessionLocal, *tenant_ids):
    from sqlalchemy import text
    with SessionLocal() as db:
        for t in tenant_ids:
            db.execute(text('DELETE FROM tenant_onboarding WHERE tenant_id = :t'), {'t': str(t)})
        db.commit()


def test_get_profile_targets_effective_tenant(onb_db):
    SessionLocal, a, b, current_user = onb_db
    _delete_profiles(SessionLocal, a, b)
    with SessionLocal() as db:
        profile = _service(db).get_profile(current_user, effective_tenant_id=str(b))
        assert profile.tenant_id == b
        from app.repositories.onboarding_repository import OnboardingRepository
        # The actor's home tenant gained no row.
        assert OnboardingRepository(db).get_by_tenant_id(a) is None


def test_get_profile_falls_back_to_home_tenant(onb_db):
    SessionLocal, a, b, current_user = onb_db
    _delete_profiles(SessionLocal, a, b)
    with SessionLocal() as db:
        profile = _service(db).get_profile(current_user)
        assert profile.tenant_id == a


def test_update_profile_writes_target_and_leaves_home_untouched(onb_db):
    SessionLocal, a, b, current_user = onb_db
    _delete_profiles(SessionLocal, a, b)
    with SessionLocal() as db:
        svc = _service(db)
        svc.update_profile(current_user, {'organization_name': f'{PFX}Org A'})
        svc.update_profile(current_user, {'organization_name': f'{PFX}Org B'},
                           effective_tenant_id=str(b))
        from app.repositories.onboarding_repository import OnboardingRepository
        repo = OnboardingRepository(db)
        assert repo.get_by_tenant_id(a).organization_name == f'{PFX}Org A'
        assert repo.get_by_tenant_id(b).organization_name == f'{PFX}Org B'


def test_validate_payment_method_targets_effective_tenant(onb_db):
    SessionLocal, a, b, current_user = onb_db
    _delete_profiles(SessionLocal, a, b)
    with SessionLocal() as db:
        _service(db).validate_payment_method(
            current_user,
            payment_method_type='CARD',
            last4='4242',
            external_reference=None,
            effective_tenant_id=str(b),
        )
        from app.repositories.onboarding_repository import OnboardingRepository
        repo = OnboardingRepository(db)
        row = repo.get_by_tenant_id(b)
        assert row.payment_method_setup is True
        assert row.payment_validation_status == 'VERIFIED'
        assert row.payment_method_last4 == '4242'
        assert repo.get_by_tenant_id(a) is None


def test_cross_tenant_update_completes_target_onboarding(onb_db):
    SessionLocal, a, b, current_user = onb_db
    _delete_profiles(SessionLocal, a, b)
    with SessionLocal() as db:
        svc = _service(db)
        assert svc.is_onboarding_complete(str(b)) is False
        svc.update_profile(current_user, dict(COMPLETE_PAYLOAD), effective_tenant_id=str(b))
        # is_onboarding_complete(B) is the /users/me data path for a
        # super-admin with the switcher set to B.
        assert svc.is_onboarding_complete(str(b)) is True
        assert svc.is_onboarding_complete(str(a)) is False
