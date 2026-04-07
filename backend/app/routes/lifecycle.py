from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.permissions import PERM_MANAGE_LIFECYCLE, PERM_VIEW_LIFECYCLE
from app.middleware.dependencies import get_current_user
from app.models.lifecycle import SubscriptionStatus
from app.schemas.lifecycle import (
    AssetResponse,
    ContractResponse,
    SubscriptionResponse,
    UpdateSubscriptionStatusRequest,
    WorkflowInstanceResponse,
    WorkflowStepResponse,
)
from app.services.lifecycle_service import LifecycleService
from app.services.authorization_service import AuthorizationService

router = APIRouter(prefix='/lifecycle', tags=['Lifecycle'])


def _serialize_contract(contract) -> ContractResponse:
    return ContractResponse(
        id=str(contract.id),
        tenant_id=str(contract.tenant_id),
        order_id=str(contract.order_id),
        created_by=str(contract.created_by),
        status=contract.status.value if hasattr(contract.status, 'value') else str(contract.status),
        term_months=contract.term_months,
        sla_tier=contract.sla_tier,
        entitlements=contract.entitlements or {},
        start_date=contract.start_date,
        end_date=contract.end_date,
        created_at=contract.created_at,
        updated_at=contract.updated_at,
    )


def _serialize_subscription(subscription) -> SubscriptionResponse:
    return SubscriptionResponse(
        id=str(subscription.id),
        tenant_id=str(subscription.tenant_id),
        contract_id=str(subscription.contract_id),
        order_line_id=str(subscription.order_line_id) if subscription.order_line_id else None,
        name=subscription.name,
        sku=subscription.sku,
        vendor=subscription.vendor,
        qty=subscription.qty,
        unit_price=float(subscription.unit_price),
        currency=subscription.currency,
        interval=subscription.interval.value if hasattr(subscription.interval, 'value') else str(subscription.interval),
        status=subscription.status.value if hasattr(subscription.status, 'value') else str(subscription.status),
        start_date=subscription.start_date,
        end_date=subscription.end_date,
        next_billing_date=subscription.next_billing_date,
        metadata=subscription.metadata_json or {},
        created_at=subscription.created_at,
        updated_at=subscription.updated_at,
    )


def _serialize_asset(asset) -> AssetResponse:
    return AssetResponse(
        id=str(asset.id),
        tenant_id=str(asset.tenant_id),
        contract_id=str(asset.contract_id) if asset.contract_id else None,
        order_line_id=str(asset.order_line_id) if asset.order_line_id else None,
        name=asset.name,
        sku=asset.sku,
        vendor=asset.vendor,
        asset_type=asset.asset_type,
        status=asset.status.value if hasattr(asset.status, 'value') else str(asset.status),
        owner_user_id=str(asset.owner_user_id) if asset.owner_user_id else None,
        location=asset.location,
        serial_number=asset.serial_number,
        metadata=asset.metadata_json or {},
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


def _serialize_workflow(workflow) -> WorkflowInstanceResponse:
    steps = sorted(workflow.steps or [], key=lambda row: row.sequence)
    return WorkflowInstanceResponse(
        id=str(workflow.id),
        tenant_id=str(workflow.tenant_id),
        order_id=str(workflow.order_id),
        template_key=workflow.template_key,
        status=workflow.status.value if hasattr(workflow.status, 'value') else str(workflow.status),
        current_stage=workflow.current_stage,
        created_at=workflow.created_at,
        updated_at=workflow.updated_at,
        steps=[
            WorkflowStepResponse(
                id=str(step.id),
                workflow_instance_id=str(step.workflow_instance_id),
                stage_key=step.stage_key,
                display_name=step.display_name,
                sequence=step.sequence,
                status=step.status.value if hasattr(step.status, 'value') else str(step.status),
                retries=step.retries,
                started_at=step.started_at,
                completed_at=step.completed_at,
                metadata=step.metadata_json or {},
                created_at=step.created_at,
            )
            for step in steps
        ],
    )


@router.get('/contracts', response_model=list[ContractResponse])
def list_contracts(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    AuthorizationService(db).require(current_user, PERM_VIEW_LIFECYCLE)
    rows = LifecycleService(db).list_contracts(current_user)
    return [_serialize_contract(row) for row in rows]


@router.get('/subscriptions', response_model=list[SubscriptionResponse])
def list_subscriptions(
    status: SubscriptionStatus | None = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    AuthorizationService(db).require(current_user, PERM_VIEW_LIFECYCLE)
    rows = LifecycleService(db).list_subscriptions(current_user, status=status)
    return [_serialize_subscription(row) for row in rows]


@router.patch('/subscriptions/{subscription_id}/status', response_model=SubscriptionResponse)
def update_subscription_status(
    subscription_id: str,
    payload: UpdateSubscriptionStatusRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    AuthorizationService(db).require(current_user, PERM_MANAGE_LIFECYCLE)
    updated = LifecycleService(db).update_subscription_status(current_user, subscription_id, payload.status)
    return _serialize_subscription(updated)


@router.get('/assets', response_model=list[AssetResponse])
def list_assets(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    AuthorizationService(db).require(current_user, PERM_VIEW_LIFECYCLE)
    rows = LifecycleService(db).list_assets(current_user)
    return [_serialize_asset(row) for row in rows]


@router.get('/orders/{order_id}/workflow', response_model=WorkflowInstanceResponse)
def get_order_workflow(order_id: str, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    AuthorizationService(db).require(current_user, PERM_VIEW_LIFECYCLE)
    workflow = LifecycleService(db).get_order_workflow(current_user, order_id)
    return _serialize_workflow(workflow)


@router.post('/orders/{order_id}/workflow/advance', response_model=WorkflowInstanceResponse)
def advance_order_workflow(order_id: str, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    AuthorizationService(db).require(current_user, PERM_MANAGE_LIFECYCLE)
    workflow = LifecycleService(db).advance_order_workflow(current_user, order_id)
    return _serialize_workflow(workflow)
