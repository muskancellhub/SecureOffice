import enum
import uuid
from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class TenantType(str, enum.Enum):
    CELLHUB = 'CELLHUB'
    VENDOR = 'VENDOR'
    COMPANY = 'COMPANY'


class Tenant(Base):
    __tablename__ = 'tenants'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Canonical company key for company-first signup: the email domain of the
    # founding admin (e.g. ``acme.com``). Unique across tenants; null for
    # non-company tenants (CellHub master, vendors, legacy). (PLAN.md §1.)
    email_domain: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    tenant_type: Mapped[TenantType] = mapped_column(
        Enum(TenantType, name='tenant_type'), nullable=False, default=TenantType.CELLHUB,
    )
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    users = relationship('User', back_populates='tenant')
    vendor_profile = relationship('Vendor', back_populates='tenant', uselist=False)
    company_profile = relationship('Company', back_populates='tenant', uselist=False)
