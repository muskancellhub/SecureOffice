import uuid
from app.core.exceptions import AppError, UnauthorizedError
from app.repositories.onboarding_repository import OnboardingRepository
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.services.audit_logger import audit

VALIDATION_STATUSES = {'PENDING', 'VERIFIED', 'FAILED'}


class OnboardingService:
    def __init__(self, db):
        self.db = db
        self.user_repo = UserRepository(db)
        self.tenant_repo = TenantRepository(db)
        self.onboarding_repo = OnboardingRepository(db)

    @staticmethod
    def _parse_uuid(value: str, *, field_name: str) -> uuid.UUID:
        try:
            return uuid.UUID(value)
        except (TypeError, ValueError):
            raise AppError(f'Invalid {field_name}', 400)

    def _assert_user_exists(self, current_user: dict) -> None:
        if not self.user_repo.get_by_id(current_user['user_id']):
            raise UnauthorizedError('User not found')

    def _assert_tenant_exists(self, tenant_id: str) -> uuid.UUID:
        tenant_uuid = self._parse_uuid(tenant_id, field_name='tenant_id')
        tenant = self.tenant_repo.get_by_id(str(tenant_uuid))
        if not tenant:
            raise AppError('Tenant not found', 404)
        return tenant_uuid

    @staticmethod
    def _normalize_validation_status(value: str | None) -> str | None:
        if value is None:
            return None
        status = value.strip().upper()
        if status not in VALIDATION_STATUSES:
            raise AppError('Validation status must be one of PENDING, VERIFIED, FAILED', 422)
        return status

    @staticmethod
    def _has_address(addr: dict | None) -> bool:
        """True when an address dict has the core fields filled."""
        a = addr or {}
        return all(str(a.get(k) or '').strip() for k in ('line1', 'city', 'state', 'postal_code'))

    @staticmethod
    def _clean_address(addr: dict | None) -> dict:
        """Normalize a validated address dict for storage. A blank address (no
        core fields) collapses to ``{}`` (i.e. 'not set')."""
        a = addr or {}
        keys = ('line1', 'line2', 'city', 'state', 'postal_code', 'country')
        cleaned = {k: str(a.get(k) or '').strip() for k in keys}
        if not any(cleaned[k] for k in ('line1', 'city', 'state', 'postal_code')):
            return {}
        return {k: v for k, v in cleaned.items() if v}

    @classmethod
    def _compute_onboarding_completed(cls, profile) -> bool:
        has_org = bool((profile.organization_name or '').strip())
        has_admin = bool((profile.admin_name or '').strip()) and bool((profile.admin_email or '').strip())
        has_identifier = bool((profile.duns_number or '').strip()) or bool((profile.tax_id or '').strip())
        credit_verified = (profile.credit_validation_status or '').upper() == 'VERIFIED'
        tax_verified = (profile.tax_validation_status or '').upper() == 'VERIFIED'
        has_address = cls._has_address(profile.operations_address)
        billing_ok = bool(profile.billing_same_as_operations) or cls._has_address(profile.billing_address)
        return all([
            has_org, has_admin, has_identifier, credit_verified, tax_verified,
            bool(profile.company_setup_completed), has_address, billing_ok,
        ])

    @classmethod
    def _missing_requirements(cls, profile) -> list[str]:
        missing: list[str] = []
        if not (profile.organization_name or '').strip():
            missing.append('Organization name')
        if not (profile.admin_name or '').strip():
            missing.append('Admin name')
        if not (profile.admin_email or '').strip():
            missing.append('Admin email')
        if not ((profile.duns_number or '').strip() or (profile.tax_id or '').strip()):
            missing.append('DUNS or Tax ID')
        if (profile.credit_validation_status or '').upper() != 'VERIFIED':
            missing.append('Credit validation')
        if (profile.tax_validation_status or '').upper() != 'VERIFIED':
            missing.append('DUNS/Tax validation')
        if not profile.company_setup_completed:
            missing.append('Basic company setup')
        if not cls._has_address(profile.operations_address):
            missing.append('Operations address')
        if not profile.billing_same_as_operations and not cls._has_address(profile.billing_address):
            missing.append('Billing address')
        return missing

    def missing_requirements(self, profile) -> list[str]:
        return self._missing_requirements(profile)

    def _get_or_create_profile(self, tenant_id: str):
        tenant_uuid = self._assert_tenant_exists(tenant_id)
        return self.onboarding_repo.get_or_create(tenant_uuid)

    def get_profile(self, current_user: dict, *, effective_tenant_id: str | None = None):
        self._assert_user_exists(current_user)
        # Effective tenant: the actor's own tenant unless a SUPER_ADMIN has
        # selected another via X-Tenant-Id (resolved upstream in get_tenant_context).
        tenant_id = effective_tenant_id or current_user['tenant_id']
        profile = self._get_or_create_profile(tenant_id)
        profile.onboarding_completed = self._compute_onboarding_completed(profile)
        self.db.commit()
        self.db.refresh(profile)
        return profile

    def update_profile(self, current_user: dict, payload: dict, *, effective_tenant_id: str | None = None):
        self._assert_user_exists(current_user)
        # Effective tenant: the actor's own tenant unless a SUPER_ADMIN has
        # selected another via X-Tenant-Id (resolved upstream in get_tenant_context).
        tenant_id = effective_tenant_id or current_user['tenant_id']
        profile = self._get_or_create_profile(tenant_id)

        if 'organization_name' in payload:
            profile.organization_name = (payload.get('organization_name') or '').strip() or None
        if 'admin_name' in payload:
            profile.admin_name = (payload.get('admin_name') or '').strip() or None
        if 'admin_email' in payload:
            profile.admin_email = (payload.get('admin_email') or '').strip().lower() or None
        if 'admin_phone' in payload:
            profile.admin_phone = (payload.get('admin_phone') or '').strip() or None

        credit_status = self._normalize_validation_status(payload.get('credit_validation_status'))
        if credit_status is not None:
            profile.credit_validation_status = credit_status

        tax_status = self._normalize_validation_status(payload.get('tax_validation_status'))
        if tax_status is not None:
            profile.tax_validation_status = tax_status

        if 'duns_number' in payload:
            profile.duns_number = (payload.get('duns_number') or '').strip() or None
        if 'tax_id' in payload:
            profile.tax_id = (payload.get('tax_id') or '').strip() or None
        if 'company_setup_completed' in payload and payload.get('company_setup_completed') is not None:
            profile.company_setup_completed = bool(payload.get('company_setup_completed'))
        if 'payment_method_setup' in payload and payload.get('payment_method_setup') is not None:
            profile.payment_method_setup = bool(payload.get('payment_method_setup'))

        # Addresses (PLAN.md §5). The request schema (AddressInput) has already
        # enforced shape/format; here we persist and reconcile the billing copy.
        if 'operations_address' in payload:
            profile.operations_address = self._clean_address(payload.get('operations_address'))
        if 'billing_same_as_operations' in payload and payload.get('billing_same_as_operations') is not None:
            profile.billing_same_as_operations = bool(payload.get('billing_same_as_operations'))
        if 'billing_address' in payload:
            profile.billing_address = self._clean_address(payload.get('billing_address'))
        if profile.billing_same_as_operations:
            # Billing mirrors operations — keep a concrete copy so downstream
            # billing always has an address regardless of the toggle.
            profile.billing_address = dict(profile.operations_address or {})
        elif not self._has_address(profile.billing_address):
            raise AppError('A billing address is required when it differs from the operations address.', 422)

        metadata_patch = payload.get('metadata')
        if isinstance(metadata_patch, dict):
            profile.metadata_json = {**(profile.metadata_json or {}), **metadata_patch}

        profile.onboarding_completed = self._compute_onboarding_completed(profile)
        self.db.commit()
        self.db.refresh(profile)
        audit.log('onboarding_updated', fields_changed=sorted(payload.keys()),
                  onboarding_completed=profile.onboarding_completed,
                  target_tenant_id=tenant_id)
        return profile

    def validate_payment_method(
        self,
        current_user: dict,
        *,
        payment_method_type: str,
        last4: str | None,
        external_reference: str | None,
        effective_tenant_id: str | None = None,
    ):
        self._assert_user_exists(current_user)
        # Effective tenant: the actor's own tenant unless a SUPER_ADMIN has
        # selected another via X-Tenant-Id (resolved upstream in get_tenant_context).
        tenant_id = effective_tenant_id or current_user['tenant_id']
        profile = self._get_or_create_profile(tenant_id)

        method = (payment_method_type or '').strip().upper()
        if method not in {'CARD', 'BANK_TRANSFER', 'MANUAL'}:
            raise AppError('payment_method_type must be CARD, BANK_TRANSFER, or MANUAL', 422)

        masked_last4 = None
        if last4:
            digits = ''.join(ch for ch in str(last4) if ch.isdigit())
            if len(digits) != 4:
                raise AppError('last4 must contain exactly 4 digits', 422)
            masked_last4 = digits

        profile.payment_method_setup = True
        profile.payment_validation_status = 'VERIFIED'
        profile.payment_method_type = method
        profile.payment_method_last4 = masked_last4
        profile.metadata_json = {
            **(profile.metadata_json or {}),
            'payment_reference': (external_reference or '').strip() or None,
        }
        profile.onboarding_completed = self._compute_onboarding_completed(profile)
        self.db.commit()
        self.db.refresh(profile)
        # last4 only — full card data never reaches this service (plan §6).
        audit.log('payment_method_validated', payment_method_type=method, last4=masked_last4,
                  target_tenant_id=tenant_id)
        return profile

    def is_onboarding_complete(self, tenant_id: str) -> bool:
        tenant_uuid = self._assert_tenant_exists(tenant_id)
        profile = self.onboarding_repo.get_by_tenant_id(tenant_uuid)
        if not profile:
            return False
        return self._compute_onboarding_completed(profile)

    def is_payment_validated(self, tenant_id: str) -> bool:
        tenant_uuid = self._assert_tenant_exists(tenant_id)
        profile = self.onboarding_repo.get_by_tenant_id(tenant_uuid)
        if not profile:
            return False
        return (profile.payment_validation_status or '').upper() == 'VERIFIED'
