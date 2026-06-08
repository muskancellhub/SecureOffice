import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tenant_settings import TenantSettings

# Columns a PUT may replace. Partial updates replace a whole section (column),
# never deep-merge — the client sends the full section it edited.
SECTIONS = ('design_ops', 'admin_services', 'feature_flags')


class TenantSettingsRepository:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _as_uuid(tenant_id: str | uuid.UUID) -> uuid.UUID:
        return tenant_id if isinstance(tenant_id, uuid.UUID) else uuid.UUID(str(tenant_id))

    def get_by_tenant_id(self, tenant_id: str | uuid.UUID) -> TenantSettings | None:
        tid = self._as_uuid(tenant_id)
        return self.db.scalar(select(TenantSettings).where(TenantSettings.tenant_id == tid))

    def get_or_create(self, tenant_id: str | uuid.UUID) -> TenantSettings:
        tid = self._as_uuid(tenant_id)
        row = self.get_by_tenant_id(tid)
        if row:
            return row
        row = TenantSettings(tenant_id=tid)
        self.db.add(row)
        self.db.flush()
        return row

    def update(self, tenant_id: str | uuid.UUID, patch: dict) -> TenantSettings:
        """Replace only the sections present in ``patch`` (keys among SECTIONS);
        omitted sections are left untouched."""
        row = self.get_or_create(tenant_id)
        for section in SECTIONS:
            if section in patch and patch[section] is not None:
                setattr(row, section, patch[section])
        self.db.flush()
        return row
