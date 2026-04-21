import uuid
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Vendor(Base):
    __tablename__ = 'vendors'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('tenants.id', ondelete='CASCADE'), unique=True, nullable=False,
    )
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    address_street: Mapped[str] = mapped_column(String(500), nullable=False)
    address_city: Mapped[str] = mapped_column(String(255), nullable=False)
    address_state: Mapped[str] = mapped_column(String(100), nullable=False)
    address_zip: Mapped[str] = mapped_column(String(20), nullable=False)
    company_website: Mapped[str] = mapped_column(String(500), nullable=False)
    company_email: Mapped[str] = mapped_column(String(320), nullable=False)
    federal_tax_id: Mapped[str] = mapped_column(String(64), nullable=False)
    bbb_good_standing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sos_good_standing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    corporate_liable_sales: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    tenant = relationship('Tenant', back_populates='vendor_profile')
