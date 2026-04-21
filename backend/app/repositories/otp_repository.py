from datetime import datetime, timezone
from sqlalchemy import desc, select
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.models import OTP


class OTPRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, user_id, code_hash: str, expires_at: datetime) -> OTP:
        settings = get_settings()
        otp = OTP(
            user_id=user_id,
            code_hash=code_hash,
            expires_at=expires_at,
            used=False,
            attempts_remaining=settings.otp_max_attempts,
        )
        self.db.add(otp)
        self.db.flush()
        return otp

    def get_latest_active_for_user(self, user_id) -> OTP | None:
        """Return the most recent OTP that is unused, unexpired, and still has attempts left."""
        return self.db.scalar(
            select(OTP)
            .where(
                OTP.user_id == user_id,
                OTP.used.is_(False),
                OTP.expires_at > datetime.now(timezone.utc),
                OTP.attempts_remaining > 0,
            )
            .order_by(desc(OTP.id))
        )

    def mark_used(self, otp: OTP) -> None:
        otp.used = True
        self.db.flush()

    def decrement_attempts(self, otp: OTP) -> int:
        """Decrement attempts_remaining. Returns the new value. Caller commits."""
        otp.attempts_remaining = max(0, (otp.attempts_remaining or 0) - 1)
        self.db.flush()
        return otp.attempts_remaining
