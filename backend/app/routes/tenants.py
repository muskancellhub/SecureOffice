"""Tenant directory for the SUPER_ADMIN tenant switcher (multi-tenant Phase 0).

Populates the global active-tenant dropdown the frontend renders only for
super-admins. SUPER_ADMIN-gated: a non-super caller never sees other tenants.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import ForbiddenError
from app.middleware.dependencies import get_current_user
from app.repositories.tenant_repository import TenantRepository
from app.schemas.tenants import TenantSummary

router = APIRouter(prefix='/tenants', tags=['Tenants'])


@router.get('', response_model=list[TenantSummary])
def list_tenants(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.get('role') != 'SUPER_ADMIN':
        raise ForbiddenError('Only SUPER_ADMIN may list tenants')
    tenants = TenantRepository(db).list_all()
    return [
        TenantSummary(
            id=str(t.id),
            name=t.name,
            tenant_type=t.tenant_type.value if hasattr(t.tenant_type, 'value') else str(t.tenant_type),
        )
        for t in tenants
    ]
