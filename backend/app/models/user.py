import enum
import uuid
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class AuthProvider(str, enum.Enum):
    LOCAL = 'LOCAL'
    GOOGLE = 'GOOGLE'
    MICROSOFT = 'MICROSOFT'


class UserRole(str, enum.Enum):
    SUPER_ADMIN = 'SUPER_ADMIN'
    ADMIN = 'ADMIN'
    USER = 'USER'


class UserType(str, enum.Enum):
    CELLHUB = 'CELLHUB'
    VENDOR = 'VENDOR'
    COMPANY = 'COMPANY'


class User(Base):
    __tablename__ = 'users'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    mobile: Mapped[str | None] = mapped_column(String(32), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider: Mapped[AuthProvider] = mapped_column(Enum(AuthProvider, name='auth_provider'), nullable=False, default=AuthProvider.LOCAL)
    provider_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name='user_role'), nullable=False, default=UserRole.USER)
    user_type: Mapped[UserType] = mapped_column(
        Enum(UserType, name='user_type_enum'), nullable=False, default=UserType.CELLHUB,
    )
    permissions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('tenants.id', ondelete='RESTRICT'), nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    tenant = relationship('Tenant', back_populates='users')
    otps = relationship('OTP', back_populates='user', cascade='all, delete-orphan')
    refresh_sessions = relationship('RefreshSession', back_populates='user', cascade='all, delete-orphan')
