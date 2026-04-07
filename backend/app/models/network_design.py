import enum
import uuid
from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class NetworkDesignStatus(str, enum.Enum):
    DRAFT = 'draft'
    REVIEWED = 'reviewed'
    SUBMITTED = 'submitted'
    IN_REVIEW = 'in_review'
    BOM_FINALIZED = 'bom_finalized'
    PROPOSAL_READY = 'proposal_ready'
    APPROVED = 'approved'
    ORDER_DECOMPOSED = 'order_decomposed'
    FULFILLMENT_IN_PROGRESS = 'fulfillment_in_progress'
    INSTALLATION_SCHEDULED = 'installation_scheduled'
    INSTALLED = 'installed'
    COMPLETED = 'completed'


class DesignLead(Base):
    __tablename__ = 'design_leads'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('tenants.id', ondelete='SET NULL'),
        nullable=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column('metadata', JSONB, nullable=False, default=dict)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    designs = relationship('NetworkDesign', back_populates='lead')


class NetworkDesign(Base):
    __tablename__ = 'network_designs'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('tenants.id', ondelete='SET NULL'),
        nullable=True,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        'created_by',
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('design_leads.id', ondelete='SET NULL'),
        nullable=True,
    )
    design_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[NetworkDesignStatus] = mapped_column(
        Enum(NetworkDesignStatus, name='network_design_status_v1', native_enum=False),
        nullable=False,
        default=NetworkDesignStatus.DRAFT,
    )
    calculator_input_json: Mapped[dict] = mapped_column('calculator_input', JSONB, nullable=False, default=dict)
    calculator_result_json: Mapped[dict] = mapped_column('calculator_result', JSONB, nullable=False, default=dict)
    bom_json: Mapped[dict] = mapped_column('bom', JSONB, nullable=False, default=dict)
    topology_json: Mapped[dict] = mapped_column('topology', JSONB, nullable=False, default=dict)
    drawio_xml: Mapped[str | None] = mapped_column(Text, nullable=True)
    assumptions_json: Mapped[list] = mapped_column('assumptions', JSONB, nullable=False, default=list)
    estimate_capex: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    ap_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    switch_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    session_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    submitted_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status_updated_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status_history_json: Mapped[list] = mapped_column('status_history', JSONB, nullable=False, default=list)
    milestones_json: Mapped[dict] = mapped_column('milestones', JSONB, nullable=False, default=dict)
    updates_json: Mapped[list] = mapped_column('updates', JSONB, nullable=False, default=list)
    install_assistance_json: Mapped[dict] = mapped_column('install_assistance', JSONB, nullable=False, default=dict)
    decomposition_json: Mapped[dict] = mapped_column('decomposition', JSONB, nullable=False, default=dict)
    metadata_json: Mapped[dict] = mapped_column('metadata', JSONB, nullable=False, default=dict)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    lead = relationship('DesignLead', back_populates='designs', lazy='joined')
