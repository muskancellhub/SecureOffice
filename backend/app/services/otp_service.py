import secrets
from datetime import datetime, timedelta, timezone
from app.core.config import get_settings
from app.core.security import hash_value, verify_value

settings = get_settings()


class OTPService:
    @staticmethod
    def generate_otp() -> str:
        return f"{secrets.randbelow(1_000_000):06d}"

    @staticmethod
    def hash_otp(otp: str) -> str:
        return hash_value(otp)

    @staticmethod
    def verify_otp(otp: str, otp_hash: str) -> bool:
        return verify_value(otp, otp_hash)

    @staticmethod
    def otp_expiry() -> datetime:
        return datetime.now(timezone.utc) + timedelta(minutes=settings.otp_expire_minutes)
