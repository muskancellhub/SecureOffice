import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.order_notification import TenantOrderNotificationSettings


class OrderNotificationRepository:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _as_uuid(tenant_id: str | uuid.UUID) -> uuid.UUID:
        return tenant_id if isinstance(tenant_id, uuid.UUID) else uuid.UUID(str(tenant_id))

    def get_by_tenant_id(self, tenant_id: str | uuid.UUID) -> TenantOrderNotificationSettings | None:
        tenant_uuid = self._as_uuid(tenant_id)
        return self.db.scalar(
            select(TenantOrderNotificationSettings).where(TenantOrderNotificationSettings.tenant_id == tenant_uuid)
        )

    def get_or_create(self, tenant_id: str | uuid.UUID) -> TenantOrderNotificationSettings:
        tenant_uuid = self._as_uuid(tenant_id)
        row = self.get_by_tenant_id(tenant_uuid)
        if row:
            return row

        row = TenantOrderNotificationSettings(tenant_id=tenant_uuid, recipient_emails_json=[])
        self.db.add(row)
        self.db.flush()
        return row
