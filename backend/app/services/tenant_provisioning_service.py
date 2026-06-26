"""Clone-on-onboard: seed a new tenant's isolated config (multi-tenant Phase 1).

When a tenant is created it gets its own copy of the per-tenant config that the
CellHub master tenant holds, so editing one tenant never touches another. With
the shared-catalog decision this is intentionally small: financing terms +
a default customer_pricing row. (Products/catalog/bundles are global and are NOT
cloned. tenant_settings is added here once Phase 3 lands.)

Centralised so every tenant-creation path calls the same seeding — no path can
silently create a config-less tenant. Operates within the caller's transaction
(uses flush, never commits) so it composes with signup/registration flows.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenancy import CELLHUB_MASTER_TENANT_ID
from app.models.financing import FinancingTerms
from app.repositories.tenant_settings_repository import TenantSettingsRepository
from app.services.pricing_service import PricingService


class TenantProvisioningService:
    def __init__(self, db: Session):
        self.db = db

    def provision(self, tenant_id) -> None:
        """Seed config for a freshly created tenant. Idempotent and a no-op for
        the master tenant itself (it is the clone *source*)."""
        tid = tenant_id if isinstance(tenant_id, uuid.UUID) else uuid.UUID(str(tenant_id))
        master = uuid.UUID(CELLHUB_MASTER_TENANT_ID)
        if tid == master:
            return

        # Provision the tenant's PII-encryption DEK up front (docs/PII_ENCRYPTION.md
        # §7). Idempotent; encryption also provisions lazily on first PII write, so
        # this is the explicit onboarding hook rather than a correctness gate.
        from app.core.encryption import EncryptionService
        EncryptionService(self.db).provision_tenant(tid)

        self._clone_financing_terms(tid, master)
        # Default customer_pricing tier (also creates it lazily on first edit, but
        # seeding now means a new tenant has a complete config set immediately).
        PricingService(self.db).get_or_create_customer_pricing(tid)
        # Default tenant_settings row (Phase 3 soft toggles).
        TenantSettingsRepository(self.db).get_or_create(tid)

    def _clone_financing_terms(self, tid: uuid.UUID, master: uuid.UUID) -> None:
        existing = self.db.scalars(
            select(FinancingTerms).where(FinancingTerms.tenant_id == tid)
        ).all()
        existing_names = {row.name for row in existing}
        # Respect the per-tenant single-default index: never clone a second default
        # onto a tenant that already has one.
        has_default = any(row.is_default for row in existing)
        source_rows = self.db.scalars(
            select(FinancingTerms).where(FinancingTerms.tenant_id == master)
        ).all()
        for src in source_rows:
            if src.name in existing_names:
                continue
            clone_default = src.is_default and not has_default
            if clone_default:
                has_default = True
            self.db.add(FinancingTerms(
                tenant_id=tid,
                name=src.name,
                term_months=src.term_months,
                annual_rate_pct=src.annual_rate_pct,
                subscription_interval=src.subscription_interval,
                is_default=clone_default,
                is_active=src.is_active,
            ))
        self.db.flush()
