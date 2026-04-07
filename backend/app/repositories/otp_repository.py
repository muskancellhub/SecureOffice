from datetime import datetime, timezone
from sqlalchemy import desc, select
from sqlalchemy.orm import Session
from app.models import OTP


class OTPRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, user_id, code_hash: str, expires_at: datetime) -> OTP:
        otp = OTP(user_id=user_id, code_hash=code_hash, expires_at=expires_at, used=False)
        self.db.add(otp)
        self.db.flush()
        return otp

    def get_latest_active_for_user(self, user_id) -> OTP | None:
        return self.db.scalar(
            select(OTP)
            .where(OTP.user_id == user_id, OTP.used.is_(False), OTP.expires_at > datetime.now(timezone.utc))
            .order_by(desc(OTP.id))
        )

    def mark_used(self, otp: OTP) -> None:
        otp.used = True
        self.db.flush()
