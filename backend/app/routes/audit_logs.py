"""Read-only audit-log query API (BUG-AUD-001).

Restricted to SUPER_ADMIN — the global CellHub operator — who can query across
all tenants. The table is append-only (DB triggers), so this endpoint never
mutates. Reads are themselves audited for accountability.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import ForbiddenError
from app.middleware.dependencies import get_current_user
from app.models.audit_log import AuditLog
from app.models.user import UserRole
from app.services.audit_logger import audit

router = APIRouter(prefix='/audit-logs', tags=['Audit Logs'])


class AuditLogResponse(BaseModel):
    id: str
    action: str
    userId: str | None
    tenantId: str | None
    ip: str | None
    endpoint: str | None
    status: str
    metadata: dict
    createdAt: datetime


def _require_super_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get('role') != UserRole.SUPER_ADMIN.value:
        raise ForbiddenError('Audit logs are restricted to SUPER_ADMIN')
    return current_user


@router.get('', response_model=list[AuditLogResponse])
def list_audit_logs(
    action: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    tenant_id: str | None = Query(default=None),
    start: datetime | None = Query(default=None, description='created_at >= start'),
    end: datetime | None = Query(default=None, description='created_at <= end'),
    limit: int = Query(default=100, ge=1, le=1000),
    _admin: dict = Depends(_require_super_admin),
    db: Session = Depends(get_db),
):
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if tenant_id:
        stmt = stmt.where(AuditLog.tenant_id == tenant_id)
    if start:
        stmt = stmt.where(AuditLog.created_at >= start)
    if end:
        stmt = stmt.where(AuditLog.created_at <= end)
    stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit)

    rows = db.scalars(stmt).all()
    audit.log('audit_logs_read', count=len(rows))
    return [
        AuditLogResponse(
            id=str(r.id),
            action=r.action,
            userId=r.user_id,
            tenantId=r.tenant_id,
            ip=r.ip,
            endpoint=r.endpoint,
            status=r.status,
            metadata=r.audit_metadata or {},
            createdAt=r.created_at,
        )
        for r in rows
    ]
