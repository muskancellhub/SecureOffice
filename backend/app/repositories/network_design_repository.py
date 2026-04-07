import uuid
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload
from app.models.network_design import DesignLead, NetworkDesign, NetworkDesignStatus


class NetworkDesignRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_lead(self, **kwargs) -> DesignLead:
        row = DesignLead(**kwargs)
        self.db.add(row)
        self.db.flush()
        return row

    def get_lead_by_id(self, lead_id: str | uuid.UUID) -> DesignLead | None:
        lead_uuid = lead_id if isinstance(lead_id, uuid.UUID) else uuid.UUID(str(lead_id))
        return self.db.get(DesignLead, lead_uuid)

    def find_lead(
        self,
        *,
        email: str,
        company_name: str,
        tenant_id: str | uuid.UUID | None = None,
    ) -> DesignLead | None:
        stmt = select(DesignLead).where(
            func.lower(DesignLead.email) == email.strip().lower(),
            func.lower(DesignLead.company_name) == company_name.strip().lower(),
        )
        if tenant_id is None:
            stmt = stmt.where(DesignLead.tenant_id.is_(None))
        else:
            tenant_uuid = tenant_id if isinstance(tenant_id, uuid.UUID) else uuid.UUID(str(tenant_id))
            stmt = stmt.where(DesignLead.tenant_id == tenant_uuid)
        stmt = stmt.order_by(desc(DesignLead.updated_at))
        return self.db.scalar(stmt)

    def create_design(self, **kwargs) -> NetworkDesign:
        row = NetworkDesign(**kwargs)
        self.db.add(row)
        self.db.flush()
        return row

    def get_design_by_id(self, design_id: str) -> NetworkDesign | None:
        try:
            stmt = (
                select(NetworkDesign)
                .where(NetworkDesign.id == uuid.UUID(str(design_id)))
                .options(selectinload(NetworkDesign.lead))
            )
            return self.db.scalar(stmt)
        except (TypeError, ValueError):
            return None

    def list_for_user(
        self,
        *,
        user_id: str,
        submitted_only: bool = False,
    ) -> list[NetworkDesign]:
        stmt = (
            select(NetworkDesign)
            .where(NetworkDesign.created_by_user_id == uuid.UUID(str(user_id)))
            .options(selectinload(NetworkDesign.lead))
            .order_by(desc(NetworkDesign.updated_at))
        )
        if submitted_only:
            stmt = stmt.where(NetworkDesign.status.notin_([NetworkDesignStatus.DRAFT, NetworkDesignStatus.REVIEWED]))
        return list(self.db.scalars(stmt).all())

    def list_for_tenant(
        self,
        *,
        tenant_id: str,
        submitted_only: bool = False,
    ) -> list[NetworkDesign]:
        stmt = (
            select(NetworkDesign)
            .where(NetworkDesign.tenant_id == uuid.UUID(str(tenant_id)))
            .options(selectinload(NetworkDesign.lead))
            .order_by(desc(NetworkDesign.updated_at))
        )
        if submitted_only:
            stmt = stmt.where(NetworkDesign.status.notin_([NetworkDesignStatus.DRAFT, NetworkDesignStatus.REVIEWED]))
        return list(self.db.scalars(stmt).all())

    def list_ops_submissions(self, *, tenant_id: str) -> list[NetworkDesign]:
        submitted_like = [
            NetworkDesignStatus.SUBMITTED,
            NetworkDesignStatus.IN_REVIEW,
            NetworkDesignStatus.BOM_FINALIZED,
            NetworkDesignStatus.PROPOSAL_READY,
            NetworkDesignStatus.APPROVED,
            NetworkDesignStatus.ORDER_DECOMPOSED,
            NetworkDesignStatus.FULFILLMENT_IN_PROGRESS,
            NetworkDesignStatus.INSTALLATION_SCHEDULED,
            NetworkDesignStatus.INSTALLED,
            NetworkDesignStatus.COMPLETED,
        ]
        stmt = (
            select(NetworkDesign)
            .where(
                NetworkDesign.tenant_id == uuid.UUID(str(tenant_id)),
                NetworkDesign.status.in_(submitted_like),
            )
            .options(selectinload(NetworkDesign.lead))
            .order_by(desc(NetworkDesign.submitted_at), desc(NetworkDesign.updated_at))
        )
        return list(self.db.scalars(stmt).all())
