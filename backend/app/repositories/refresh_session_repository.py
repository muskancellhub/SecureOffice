from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import RefreshSession


class RefreshSessionRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_placeholder(self, user_id, expires_at) -> RefreshSession:
        session = RefreshSession(
            user_id=user_id,
            refresh_token_hash='',
            expires_at=expires_at,
            revoked=False,
        )
        self.db.add(session)
        self.db.flush()
        return session

    def get_active_by_id(self, session_id: int) -> RefreshSession | None:
        return self.db.scalar(
            select(RefreshSession).where(
                RefreshSession.id == session_id,
                RefreshSession.revoked.is_(False),
                RefreshSession.expires_at > datetime.now(timezone.utc),
            )
        )

    def revoke(self, session: RefreshSession) -> None:
        session.revoked = True
        self.db.flush()
