import enum
import uuid
from datetime import date
from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.quote import BillingInterval


class ContractStatus(str, enum.Enum):
    ACTIVE = 'ACTIVE'
    PAUSED = 'PAUSED'
    CANCELLED = 'CANCELLED'
    EXPIRED = 'EXPIRED'


class SubscriptionStatus(str, enum.Enum):
    ACTIVE = 'ACTIVE'
    PAUSED = 'PAUSED'
    CANCELLED = 'CANCELLED'


class WorkflowStatus(str, enum.Enum):
    ACTIVE = 'ACTIVE'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'


class WorkflowStepStatus(str, enum.Enum):
    PENDING = 'PENDING'
    IN_PROGRESS = 'IN_PROGRESS'
    DONE = 'DONE'
    FAILED = 'FAILED'


class AssetStatus(str, enum.Enum):
    PROVISIONING = 'PROVISIONING'
    ACTIVE = 'ACTIVE'
    RETIRED = 'RETIRED'


class InvoiceStatus(str, enum.Enum):
    DUE = 'DUE'
    PAID = 'PAID'
    VOID = 'VOID'


class PaymentStatus(str, enum.Enum):
    SUCCEEDED = 'SUCCEEDED'
    FAILED = 'FAILED'


class PaymentMethod(str, enum.Enum):
    MANUAL = 'MANUAL'
    CARD = 'CARD'
    BANK_TRANSFER = 'BANK_TRANSFER'


class Contract(Base):
    __tablename__ = 'contracts'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('tenants.id', ondelete='RESTRICT'), nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('orders.id', ondelete='CASCADE'), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    status: Mapped[ContractStatus] = mapped_column(
        Enum(ContractStatus, name='contract_status_v1', native_enum=False),
        nullable=False,
        default=ContractStatus.ACTIVE,
    )
    term_months: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    sla_tier: Mapped[str] = mapped_column(String(64), nullable=False, default='STANDARD')
    entitlements: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    start_date: Mapped[date] = mapped_column(Date, nullable=False, server_default=func.current_date())
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    subscriptions = relationship('Subscription', back_populates='contract', cascade='all, delete-orphan')
    assets = relationship('Asset', back_populates='contract')


class Subscription(Base):
    __tablename__ = 'subscriptions'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('tenants.id', ondelete='RESTRICT'), nullable=False)
    contract_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('contracts.id', ondelete='CASCADE'), nullable=False)
    order_line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('order_lines.id', ondelete='SET NULL'),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(128), nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    qty: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default='USD')
    interval: Mapped[BillingInterval] = mapped_column(
        Enum(BillingInterval, name='subscription_billing_interval_v1', native_enum=False),
        nullable=False,
        default=BillingInterval.MONTH,
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name='subscription_status_v1', native_enum=False),
        nullable=False,
        default=SubscriptionStatus.ACTIVE,
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False, server_default=func.current_date())
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_billing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    metadata_json: Mapped[dict] = mapped_column('metadata', JSONB, nullable=False, default=dict)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    contract = relationship('Contract', back_populates='subscriptions')
    invoices = relationship('Invoice', back_populates='subscription')


class WorkflowInstance(Base):
    __tablename__ = 'workflow_instances'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('tenants.id', ondelete='RESTRICT'), nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, unique=True)
    template_key: Mapped[str] = mapped_column(String(64), nullable=False, default='order_fulfillment')
    status: Mapped[WorkflowStatus] = mapped_column(
        Enum(WorkflowStatus, name='workflow_status_v1', native_enum=False),
        nullable=False,
        default=WorkflowStatus.ACTIVE,
    )
    current_stage: Mapped[str] = mapped_column(String(64), nullable=False, default='ordered')
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    steps = relationship('WorkflowStep', back_populates='workflow_instance', cascade='all, delete-orphan')


class WorkflowStep(Base):
    __tablename__ = 'workflow_steps'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('workflow_instances.id', ondelete='CASCADE'),
        nullable=False,
    )
    stage_key: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[WorkflowStepStatus] = mapped_column(
        Enum(WorkflowStepStatus, name='workflow_step_status_v1', native_enum=False),
        nullable=False,
        default=WorkflowStepStatus.PENDING,
    )
    retries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column('metadata', JSONB, nullable=False, default=dict)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    workflow_instance = relationship('WorkflowInstance', back_populates='steps')


class Asset(Base):
    __tablename__ = 'assets'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('tenants.id', ondelete='RESTRICT'), nullable=False)
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('contracts.id', ondelete='SET NULL'),
        nullable=True,
    )
    order_line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('order_lines.id', ondelete='SET NULL'),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(128), nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    asset_type: Mapped[str] = mapped_column(String(64), nullable=False, default='device')
    status: Mapped[AssetStatus] = mapped_column(
        Enum(AssetStatus, name='asset_status_v1', native_enum=False),
        nullable=False,
        default=AssetStatus.ACTIVE,
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
    )
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict] = mapped_column('metadata', JSONB, nullable=False, default=dict)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    contract = relationship('Contract', back_populates='assets')


class Invoice(Base):
    __tablename__ = 'invoices'
    __table_args__ = (
        UniqueConstraint('subscription_id', 'billing_month', name='uq_invoices_subscription_billing_month'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('tenants.id', ondelete='RESTRICT'), nullable=False)
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('subscriptions.id', ondelete='SET NULL'),
        nullable=True,
    )
    billing_month: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default='USD')
    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus, name='invoice_status_v1', native_enum=False),
        nullable=False,
        default=InvoiceStatus.DUE,
    )
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    issued_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    paid_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column('metadata', JSONB, nullable=False, default=dict)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    subscription = relationship('Subscription', back_populates='invoices')
    payments = relationship('Payment', back_populates='invoice', cascade='all, delete-orphan')


class Payment(Base):
    __tablename__ = 'payments'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('tenants.id', ondelete='RESTRICT'), nullable=False)
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('invoices.id', ondelete='CASCADE'), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default='USD')
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name='payment_status_v1', native_enum=False),
        nullable=False,
        default=PaymentStatus.SUCCEEDED,
    )
    method: Mapped[PaymentMethod] = mapped_column(
        Enum(PaymentMethod, name='payment_method_v1', native_enum=False),
        nullable=False,
        default=PaymentMethod.MANUAL,
    )
    external_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    paid_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    metadata_json: Mapped[dict] = mapped_column('metadata', JSONB, nullable=False, default=dict)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    invoice = relationship('Invoice', back_populates='payments')
