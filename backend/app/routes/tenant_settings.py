"""Tenant settings API (multi-tenant Phase 3).

Reads/writes the active tenant's JSONB soft settings. Tenant resolution goes
through ``get_tenant_context`` (so a SUPER_ADMIN with X-Tenant-Id edits another
tenant's toggles; everyone else is pinned to their own). Admin-gated.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import ForbiddenError
from app.middleware.dependencies import get_current_user
from app.middleware.tenant_context import TenantContext, get_tenant_context
from app.repositories.tenant_settings_repository import TenantSettingsRepository
from app.schemas.tenant_settings import (
    AdminServicesSettings,
    DesignOpsSettings,
    TenantSettingsResponse,
    UpdateTenantSettingsRequest,
)

router = APIRouter(prefix='/tenant-settings', tags=['Tenant Settings'])

_ADMIN_ROLES = {'ADMIN', 'SUPER_ADMIN'}


def _require_admin(current_user: dict) -> None:
    if current_user.get('role') not in _ADMIN_ROLES:
        raise ForbiddenError('Admin access required')


def _serialize(row) -> TenantSettingsResponse:
    return TenantSettingsResponse(
        tenant_id=str(row.tenant_id),
        design_ops=DesignOpsSettings(**(row.design_ops or {})),
        admin_services=AdminServicesSettings(**(row.admin_services or {})),
        feature_flags=dict(row.feature_flags or {}),
        updated_at=row.updated_at,
    )


@router.get('', response_model=TenantSettingsResponse)
def get_tenant_settings(
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    row = TenantSettingsRepository(db).get_or_create(ctx.effective_tenant_id)
    db.commit()
    db.refresh(row)
    return _serialize(row)


@router.put('', response_model=TenantSettingsResponse)
def update_tenant_settings(
    payload: UpdateTenantSettingsRequest,
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    # Only sections present in the request are replaced; each is stored complete
    # (Pydantic fills sub-model defaults) so a section never persists half-set.
    provided = payload.model_dump(exclude_unset=True).keys()
    dumped = payload.model_dump()
    patch = {section: dumped[section] for section in provided}
    row = TenantSettingsRepository(db).update(ctx.effective_tenant_id, patch)
    db.commit()
    db.refresh(row)
    return _serialize(row)
