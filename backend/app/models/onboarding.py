import uuid
from sqlalchemy import Boolean, DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class TenantOnboarding(Base):
    __tablename__ = 'tenant_onboarding'

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('tenants.id', ondelete='CASCADE'),
        primary_key=True,
    )
    organization_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    admin_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    admin_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    admin_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    credit_validation_status: Mapped[str] = mapped_column(String(16), nullable=False, default='PENDING', server_default='PENDING')
    tax_validation_status: Mapped[str] = mapped_column(String(16), nullable=False, default='PENDING', server_default='PENDING')
    duns_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    company_setup_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text('FALSE'))
    payment_method_setup: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text('FALSE'))
    payment_validation_status: Mapped[str] = mapped_column(String(16), nullable=False, default='PENDING', server_default='PENDING')
    payment_method_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payment_method_last4: Mapped[str | None] = mapped_column(String(8), nullable=True)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text('FALSE'))
    metadata_json: Mapped[dict] = mapped_column('metadata', JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
