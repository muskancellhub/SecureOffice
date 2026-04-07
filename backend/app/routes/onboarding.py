from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.middleware.dependencies import get_current_user
from app.schemas.onboarding import (
    OnboardingProfileResponse,
    UpdateOnboardingProfileRequest,
    ValidatePaymentMethodRequest,
)
from app.services.onboarding_service import OnboardingService

router = APIRouter(prefix='/onboarding', tags=['Onboarding'])


def _serialize_profile(service: OnboardingService, profile) -> OnboardingProfileResponse:
    return OnboardingProfileResponse(
        tenant_id=str(profile.tenant_id),
        organization_name=profile.organization_name,
        admin_name=profile.admin_name,
        admin_email=profile.admin_email,
        admin_phone=profile.admin_phone,
        credit_validation_status=profile.credit_validation_status,
        tax_validation_status=profile.tax_validation_status,
        duns_number=profile.duns_number,
        tax_id=profile.tax_id,
        company_setup_completed=profile.company_setup_completed,
        payment_method_setup=profile.payment_method_setup,
        payment_validation_status=profile.payment_validation_status,
        payment_method_type=profile.payment_method_type,
        payment_method_last4=profile.payment_method_last4,
        onboarding_completed=profile.onboarding_completed,
        metadata=profile.metadata_json or {},
        missing_requirements=service.missing_requirements(profile),
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.get('/profile', response_model=OnboardingProfileResponse)
def get_onboarding_profile(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    service = OnboardingService(db)
    profile = service.get_profile(current_user)
    return _serialize_profile(service, profile)


@router.put('/profile', response_model=OnboardingProfileResponse)
def update_onboarding_profile(
    payload: UpdateOnboardingProfileRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = OnboardingService(db)
    profile = service.update_profile(current_user, payload.model_dump(exclude_unset=True))
    return _serialize_profile(service, profile)


@router.post('/payment/validate', response_model=OnboardingProfileResponse)
def validate_payment_method(
    payload: ValidatePaymentMethodRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = OnboardingService(db)
    profile = service.validate_payment_method(
        current_user,
        payment_method_type=payload.payment_method_type,
        last4=payload.last4,
        external_reference=payload.external_reference,
    )
    return _serialize_profile(service, profile)
