import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.encryption import EncryptionService
from app.models.onboarding import TenantOnboarding


class OnboardingRepository:
    def __init__(self, db: Session):
        self.db = db
        # Decrypt encrypted PII (admin_name/email/phone, tax_id, duns_number) on
        # read (docs/PII_ENCRYPTION.md §7). NOTE: callers that subsequently call
        # ``db.refresh(profile)`` reload the ciphertext and must re-decrypt — see
        # OnboardingService.
        self._enc = EncryptionService(db)

    def get_by_tenant_id(self, tenant_id: str | uuid.UUID) -> TenantOnboarding | None:
        tenant_uuid = tenant_id if isinstance(tenant_id, uuid.UUID) else uuid.UUID(tenant_id)
        profile = self.db.scalar(select(TenantOnboarding).where(TenantOnboarding.tenant_id == tenant_uuid))
        if profile is not None:
            self._enc.decrypt_instance(profile)
        return profile

    def get_or_create(self, tenant_id: str | uuid.UUID) -> TenantOnboarding:
        tenant_uuid = tenant_id if isinstance(tenant_id, uuid.UUID) else uuid.UUID(tenant_id)
        profile = self.get_by_tenant_id(tenant_uuid)
        if profile:
            return profile
        profile = TenantOnboarding(tenant_id=tenant_uuid)
        self.db.add(profile)
        self.db.flush()
        return profile
