import uuid

from fastapi import Request
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from app.core.config import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _effective_tenant_id(request: Request | None) -> str | None:
    """Tenant whose rows this request may touch, for the RLS GUC (Phase 4).

    Mirrors ``tenant_context.resolve_tenant_context``'s *effective* output, but
    without a DB lookup: a SUPER_ADMIN may target the ``X-Tenant-Id`` header;
    everyone else is pinned to their JWT tenant. ``None`` for unauthenticated
    requests (and for non-request system paths), which leaves the GUC unset →
    the isolation policy allows all rows (app-layer auth still applies).
    """
    user = getattr(request.state, 'user', None) if request is not None else None
    if not user:
        return None
    actor_tenant = user.get('tenant_id')
    header = request.headers.get('X-Tenant-Id')
    if header and header != actor_tenant and user.get('role') == 'SUPER_ADMIN':
        return header
    return actor_tenant


@event.listens_for(Session, 'after_begin')
def _apply_tenant_guc(session, transaction, connection):
    """Set ``app.current_tenant_id`` at the start of every transaction.

    Re-applying per-transaction is what makes RLS survive the multiple
    ``db.commit()`` calls a single request makes (a one-shot ``SET LOCAL`` would
    be discarded after the first commit). No-op unless RLS is enabled and the
    session carries a tenant — system/seed/migration paths set neither, so they
    run with the GUC unset (policy allows all).
    """
    if not settings.enable_rls:
        return
    tenant_id = session.info.get('tenant_id')
    if not tenant_id:
        return
    try:
        uuid.UUID(str(tenant_id))
    except (ValueError, TypeError):
        return
    # set_config(name, value, is_local=true) == SET LOCAL, but parameterised, so
    # the tenant id can never be SQL-injected.
    connection.execute(
        text("SELECT set_config('app.current_tenant_id', :t, true)"),
        {'t': str(tenant_id)},
    )


def get_db(request: Request = None):
    db = SessionLocal()
    # Stash the request's effective tenant on the session so the after_begin
    # listener can apply it to each transaction. Routes already depend on get_db,
    # so this is set for every request without per-route wiring.
    db.info['tenant_id'] = _effective_tenant_id(request)
    try:
        yield db
    finally:
        db.close()
