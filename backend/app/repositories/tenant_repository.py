import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Tenant


class TenantRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, tenant_id: str) -> Tenant | None:
        try:
            tid = uuid.UUID(str(tenant_id))
        except (ValueError, TypeError):
            return None
        return self.db.get(Tenant, tid)

    def get_first(self) -> Tenant | None:
        return self.db.scalar(select(Tenant).order_by(Tenant.created_at.asc()))

    def list_all(self) -> list[Tenant]:
        return list(self.db.scalars(select(Tenant).order_by(Tenant.name.asc())))
