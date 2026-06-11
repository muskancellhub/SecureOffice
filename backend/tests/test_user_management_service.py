"""UserManagementService — DB integration (skips without Postgres)."""
import uuid

import pytest

PFX = 'UMSVC-'


@pytest.fixture(scope='module')
def um_db():
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

    ta, tb = uuid.uuid4(), uuid.uuid4()
    super_id, admin_id, user_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with SessionLocal() as db:
        db.add(Tenant(id=ta, name=f'{PFX}A'))
        db.add(Tenant(id=tb, name=f'{PFX}B'))
        db.flush()
        db.add(User(id=super_id, email=f'umsvc-super-{ta}@test.local', name='UM Super',
                    tenant_id=ta, role=UserRole.SUPER_ADMIN, is_verified=True, password_hash='x'))
        db.add(User(id=admin_id, email=f'umsvc-admin-{ta}@test.local', name='UM Admin',
                    tenant_id=ta, role=UserRole.ADMIN, is_verified=True, password_hash='x'))
        db.add(User(id=user_id, email=f'umsvc-user-{ta}@test.local', name='UM User',
                    tenant_id=ta, role=UserRole.USER, is_verified=True, password_hash='x'))
        db.commit()

    actors = {
        'super': {'user_id': str(super_id), 'tenant_id': str(ta), 'role': 'SUPER_ADMIN'},
        'admin': {'user_id': str(admin_id), 'tenant_id': str(ta), 'role': 'ADMIN'},
        'user': {'user_id': str(user_id), 'tenant_id': str(ta), 'role': 'USER'},
    }
    yield SessionLocal, actors, ta, tb, user_id

    with SessionLocal() as db:
        for t in (ta, tb):
            db.execute(text('DELETE FROM users WHERE tenant_id = :t'), {'t': str(t)})
            db.execute(text('DELETE FROM tenants WHERE id = :t'), {'t': str(t)})
        db.commit()


def _svc(db):
    from app.services.user_management_service import UserManagementService
    return UserManagementService(db)


def _create_req(email, role='USER', tenant_id=None, password='Password123!'):
    from app.models.user import UserRole
    from app.schemas.users import CreateUserRequest
    return CreateUserRequest(email=email, name='Created User', password=password,
                             role=UserRole(role), tenant_id=tenant_id)


def test_permission_catalog_requires_manage_permissions(um_db):
    from app.core.exceptions import ForbiddenError
    SessionLocal, actors, ta, tb, _ = um_db
    with SessionLocal() as db:
        catalog = _svc(db).list_permission_catalog(actors['super'])
        assert {'code', 'description'} <= set(catalog[0])
        with pytest.raises(ForbiddenError):
            _svc(db).list_permission_catalog(actors['user'])


def test_create_user_happy_and_duplicate(um_db):
    from app.core.exceptions import AppError
    SessionLocal, actors, ta, tb, _ = um_db
    email = f'umsvc-new-{uuid.uuid4().hex[:8]}@corp.example'
    with SessionLocal() as db:
        svc = _svc(db)
        user = svc.create_user(actors['admin'], _create_req(email))
        assert user.email == email
        assert str(user.tenant_id) == str(ta)
        assert user.is_verified is True
        with pytest.raises(AppError) as exc:
            svc.create_user(actors['admin'], _create_req(email))
        assert exc.value.status_code == 409


def test_create_user_role_matrix(um_db):
    from app.core.exceptions import ForbiddenError
    SessionLocal, actors, ta, tb, _ = um_db
    with SessionLocal() as db:
        svc = _svc(db)
        # ADMIN cannot create ADMIN
        with pytest.raises(ForbiddenError):
            svc.create_user(actors['admin'], _create_req('x1@corp.example', role='ADMIN'))
        # nobody creates SUPER_ADMIN
        with pytest.raises(ForbiddenError):
            svc.create_user(actors['super'], _create_req('x2@corp.example', role='SUPER_ADMIN'))
        # plain USER cannot manage at all
        with pytest.raises(ForbiddenError):
            svc.create_user(actors['user'], _create_req('x3@corp.example'))
        # SUPER_ADMIN with default perms can create ADMIN (manage_admins is default)
        email = f'umsvc-admin2-{uuid.uuid4().hex[:8]}@corp.example'
        created = svc.create_user(actors['super'], _create_req(email, role='ADMIN'))
        assert created.role.value == 'ADMIN'


def test_create_user_tenant_resolution(um_db):
    from app.core.exceptions import AppError, ForbiddenError, NotFoundError
    SessionLocal, actors, ta, tb, _ = um_db
    with SessionLocal() as db:
        svc = _svc(db)
        # super-admin targets tenant B
        email = f'umsvc-b-{uuid.uuid4().hex[:8]}@corp.example'
        user = svc.create_user(actors['super'], _create_req(email, tenant_id=str(tb)))
        assert str(user.tenant_id) == str(tb)
        # unknown tenant
        with pytest.raises(NotFoundError):
            svc.create_user(actors['super'], _create_req('y1@corp.example', tenant_id=str(uuid.uuid4())))
        # malformed tenant id
        with pytest.raises(AppError) as exc:
            svc.create_user(actors['super'], _create_req('y2@corp.example', tenant_id='garbage'))
        assert exc.value.status_code == 400
        # ADMIN cannot target another tenant
        with pytest.raises(ForbiddenError):
            svc.create_user(actors['admin'], _create_req('y3@corp.example', tenant_id=str(tb)))


def test_invite_user_email_success_and_failure(um_db, monkeypatch):
    from app.models.user import UserRole
    from app.schemas.users import InviteUserRequest
    from app.services.email_service import EmailService
    SessionLocal, actors, ta, tb, _ = um_db
    captured = {}

    def fake_invite(*, to_email, org_name, invited_by, login_url):
        captured.update(to_email=to_email, org_name=org_name,
                        invited_by=invited_by, login_url=login_url)
    monkeypatch.setattr(EmailService, 'send_invite_email', staticmethod(fake_invite))
    with SessionLocal() as db:
        svc = _svc(db)
        email = f'umsvc-invite-{uuid.uuid4().hex[:8]}@corp.example'
        user, sent, err = svc.invite_user(
            actors['admin'], InviteUserRequest(email=email, role=UserRole.USER))
        assert sent is True and err is None
        assert captured['to_email'] == email
        assert captured['org_name'] == f'{PFX}A'
        assert captured['login_url'].endswith('/login')

    def failing_invite(**kwargs):
        raise RuntimeError('resend quota exhausted')
    monkeypatch.setattr(EmailService, 'send_invite_email', staticmethod(failing_invite))
    with SessionLocal() as db:
        svc = _svc(db)
        email = f'umsvc-invite-{uuid.uuid4().hex[:8]}@corp.example'
        user, sent, err = svc.invite_user(
            actors['admin'], InviteUserRequest(email=email, role=UserRole.USER))
        assert sent is False
        assert 'resend quota exhausted' in err
        # account survived the email failure
        assert svc.user_repo.get_by_email(email) is not None


def test_list_users_scoping(um_db):
    from app.core.exceptions import ForbiddenError
    SessionLocal, actors, ta, tb, _ = um_db
    with SessionLocal() as db:
        svc = _svc(db)
        all_users = svc.list_users(actors['super'])
        assert len(all_users) >= 3
        b_users = svc.list_users(actors['super'], tenant_id=str(tb))
        assert all(str(u.tenant_id) == str(tb) for u in b_users)
        admin_view = svc.list_users(actors['admin'])
        assert all(str(u.tenant_id) == str(ta) for u in admin_view)
        with pytest.raises(ForbiddenError):
            svc.list_users(actors['admin'], tenant_id=str(tb))


def test_update_user_role_matrix(um_db):
    from app.core.exceptions import ForbiddenError
    from app.models.user import UserRole
    SessionLocal, actors, ta, tb, target_user_id = um_db
    with SessionLocal() as db:
        svc = _svc(db)
        # super-admin promotes USER -> ADMIN; permissions reset to role defaults
        from app.core.permissions import default_permissions_for_role
        promoted = svc.update_user_role(actors['super'], str(target_user_id), UserRole.ADMIN)
        assert promoted.role == UserRole.ADMIN
        assert promoted.permissions == default_permissions_for_role(UserRole.ADMIN)
        # ADMIN cannot touch a non-USER account
        with pytest.raises(ForbiddenError):
            svc.update_user_role(actors['admin'], str(target_user_id), UserRole.USER)
        # nobody assigns SUPER_ADMIN
        with pytest.raises(ForbiddenError):
            svc.update_user_role(actors['super'], str(target_user_id), UserRole.SUPER_ADMIN)
        # restore for other tests
        svc.update_user_role(actors['super'], str(target_user_id), UserRole.USER)
        # super-admin account itself is untouchable
        with pytest.raises(ForbiddenError):
            svc.update_user_role(actors['super'], actors['super']['user_id'], UserRole.USER)


def test_update_user_permissions_validation(um_db):
    from app.core.exceptions import AppError, ForbiddenError
    from app.core.permissions import PERM_VIEW_CATALOG, PERM_MANAGE_USERS
    SessionLocal, actors, ta, tb, target_user_id = um_db
    with SessionLocal() as db:
        svc = _svc(db)
        # unknown code rejected outright (BUG-USER-001 guard)
        with pytest.raises(AppError) as exc:
            svc.update_user_permissions(actors['super'], str(target_user_id), ['not_a_permission'])
        assert exc.value.status_code == 400
        # valid subset for a USER persists
        updated = svc.update_user_permissions(actors['super'], str(target_user_id), [PERM_VIEW_CATALOG])
        assert updated.permissions == [PERM_VIEW_CATALOG]
        # a code outside the USER role's allowed set → 400
        with pytest.raises(AppError) as exc:
            svc.update_user_permissions(actors['super'], str(target_user_id), [PERM_MANAGE_USERS])
        assert exc.value.status_code == 400
        # plain USER actor cannot manage permissions
        with pytest.raises(ForbiddenError):
            svc.update_user_permissions(actors['user'], str(target_user_id), [PERM_VIEW_CATALOG])


def test_create_user_integrity_race_maps_to_409(um_db, monkeypatch):
    from sqlalchemy.exc import IntegrityError
    from app.core.exceptions import AppError
    SessionLocal, actors, ta, tb, _ = um_db
    with SessionLocal() as db:
        svc = _svc(db)

        def racing_create(**kwargs):
            raise IntegrityError('stmt', {}, Exception('duplicate key'))
        monkeypatch.setattr(svc.user_repo, 'create', racing_create)
        with pytest.raises(AppError) as exc:
            svc.create_user(actors['admin'], _create_req('race@corp.example'))
        assert exc.value.status_code == 409
