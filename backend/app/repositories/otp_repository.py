from datetime import datetime, timezone
from sqlalchemy import desc, func, select
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

    def count_since(self, user_id, since: datetime) -> int:
        """Count OTPs issued to a user at or after `since` (for request throttling)."""
        return self.db.scalar(
            select(func.count())
            .select_from(OTP)
            .where(OTP.user_id == user_id, OTP.created_at >= since)
        ) or 0

    def earliest_created_since(self, user_id, since: datetime) -> datetime | None:
        """Issuance time of the oldest OTP still inside the window — used to tell
        the user when the throttle will free up."""
        return self.db.scalar(
            select(func.min(OTP.created_at))
            .where(OTP.user_id == user_id, OTP.created_at >= since)
        )

    def latest_created_at(self, user_id) -> datetime | None:
        """Issuance time of the most recent OTP — used to enforce the resend cooldown."""
        return self.db.scalar(
            select(func.max(OTP.created_at)).where(OTP.user_id == user_id)
        )

    def mark_used(self, otp: OTP) -> None:
        otp.used = True
        self.db.flush()

    def decrement_attempts(self, otp: OTP) -> int:
        """Decrement attempts_remaining. Returns the new value. Caller commits."""
        otp.attempts_remaining = max(0, (otp.attempts_remaining or 0) - 1)
        self.db.flush()
        return otp.attempts_remaining
