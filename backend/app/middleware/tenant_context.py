"""Active-tenant resolution for the request (multi-tenant Phase 0).

A CellHub ``SUPER_ADMIN`` can act on behalf of any tenant by sending an
``X-Tenant-Id`` header (set by the frontend tenant switcher, Phase 2). Everyone
else is pinned to their own tenant. ``get_tenant_context`` is a FastAPI
dependency that resolves the *effective* tenant for the request and is the single
place cross-tenant access is authorised.

Phase 0 is behaviour-preserving: with no header (or a header equal to the
actor's own tenant) this resolves exactly to ``current_user['tenant_id']`` —
identical to today. RLS GUC wiring (``SET LOCAL app.current_tenant_id``) lands in
Phase 4; this module is the seam it will hang off.
"""
from dataclasses import dataclass

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import ForbiddenError, NotFoundError
from app.middleware.dependencies import get_current_user
from app.repositories.tenant_repository import TenantRepository

# Gate decision (locked): cross-tenant access requires role == SUPER_ADMIN only.
# (We deliberately do NOT also assert user_type == 'CELLHUB' — see
# docs/plans/multi-tenant/phase-0-tenant-context.md.)
SUPER_ADMIN = 'SUPER_ADMIN'


@dataclass(frozen=True)
class TenantContext:
    """The tenant a request should read/write, plus whether the actor crossed
    out of their own tenant to reach it."""

    effective_tenant_id: str
    is_cross_tenant: bool


def resolve_tenant_context(
    requested_tenant_id: str | None,
    current_user: dict,
    db: Session,
) -> TenantContext:
    """Pure resolver, independent of FastAPI, so it is unit-testable and reusable
    from services that already hold ``current_user``.

    - No requested tenant, or one equal to the actor's home tenant → home tenant.
    - A different tenant → allowed only for SUPER_ADMIN, and only if it exists.
    """
    actor_tenant = current_user.get('tenant_id')
    if not requested_tenant_id or requested_tenant_id == actor_tenant:
        return TenantContext(effective_tenant_id=actor_tenant, is_cross_tenant=False)

    if current_user.get('role') != SUPER_ADMIN:
        raise ForbiddenError('Cross-tenant access requires SUPER_ADMIN')

    if not TenantRepository(db).get_by_id(requested_tenant_id):
        raise NotFoundError('Tenant not found')

    return TenantContext(effective_tenant_id=requested_tenant_id, is_cross_tenant=True)


def get_tenant_context(
    x_tenant_id: str | None = Header(default=None, alias='X-Tenant-Id'),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TenantContext:
    """FastAPI dependency resolving the effective tenant from the
    ``X-Tenant-Id`` request header."""
    return resolve_tenant_context(x_tenant_id, current_user, db)


def assert_tenant_access(current_user: dict, tenant_id: str) -> None:
    """Authorise an explicit ``tenant_id`` path/body param against the actor.

    Closes the Phase-0 authz holes on endpoints that still take a raw tenant id
    (e.g. ``/pricing/customers/{tenant_id}/...``): a caller may only target their
    own tenant unless they are a SUPER_ADMIN.
    """
    if current_user.get('role') == SUPER_ADMIN:
        return
    if tenant_id != current_user.get('tenant_id'):
        raise ForbiddenError('Cross-tenant access requires SUPER_ADMIN')
