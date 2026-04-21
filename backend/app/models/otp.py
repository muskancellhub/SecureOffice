from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class OTP(Base):
    __tablename__ = 'otps'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Remaining verification attempts before this OTP is invalidated. When this
    # reaches 0, get_latest_active_for_user stops returning it and the user must
    # request a new OTP — blocks brute-force on the 6-digit code space.
    attempts_remaining: Mapped[int] = mapped_column(Integer, nullable=False, default=5)

    user = relationship('User', back_populates='otps')
