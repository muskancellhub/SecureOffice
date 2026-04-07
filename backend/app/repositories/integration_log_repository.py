from datetime import datetime, timezone
from sqlalchemy import desc, select
from sqlalchemy.orm import Session
from app.models.integration_log import IntegrationSyncLog, SyncStatus


class IntegrationLogRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_log(self, *, integration_name: str, scope: str) -> IntegrationSyncLog:
        log = IntegrationSyncLog(integration_name=integration_name, scope=scope, status=SyncStatus.FAILED)
        self.db.add(log)
        self.db.flush()
        return log

    def complete_log(
        self,
        log: IntegrationSyncLog,
        *,
        status: SyncStatus,
        synced_count: int,
        created_count: int,
        updated_count: int,
        error_excerpt: str | None,
    ) -> None:
        log.status = status
        log.synced_count = synced_count
        log.created_count = created_count
        log.updated_count = updated_count
        log.error_excerpt = error_excerpt
        log.finished_at = datetime.now(timezone.utc)
        self.db.flush()

    def get_last(self, integration_name: str, scope: str) -> IntegrationSyncLog | None:
        return self.db.scalar(
            select(IntegrationSyncLog)
            .where(IntegrationSyncLog.integration_name == integration_name, IntegrationSyncLog.scope == scope)
            .order_by(desc(IntegrationSyncLog.created_at))
        )
