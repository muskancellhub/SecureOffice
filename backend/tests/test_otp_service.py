"""OTPService — pure crypto unit tests."""
import re
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.services.otp_service import OTPService

settings = get_settings()


def test_generate_otp_is_six_zero_padded_digits():
    for _ in range(50):
        assert re.fullmatch(r'\d{6}', OTPService.generate_otp())


def test_hash_and_verify_roundtrip():
    otp = '042137'
    hashed = OTPService.hash_otp(otp)
    assert hashed != otp
    assert OTPService.verify_otp(otp, hashed) is True


def test_verify_wrong_code_fails():
    hashed = OTPService.hash_otp('111111')
    assert OTPService.verify_otp('222222', hashed) is False


def test_otp_expiry_uses_configured_minutes(monkeypatch):
    monkeypatch.setattr(settings, 'otp_expire_minutes', 7)
    expiry = OTPService.otp_expiry()
    assert expiry.tzinfo is not None
    expected = datetime.now(timezone.utc) + timedelta(minutes=7)
    assert abs((expiry - expected).total_seconds()) < 5
