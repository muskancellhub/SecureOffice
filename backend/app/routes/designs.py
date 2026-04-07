from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import PERM_MANAGE_LIFECYCLE
from app.middleware.dependencies import get_current_user
from app.schemas.designs import (
    AddNetworkDesignUpdateRequest,
    DesignLeadResponse,
    DesignMilestonesResponse,
    DesignUpdateResponse,
    DesignInstallAssistanceResponse,
    DesignStatusHistoryEntryResponse,
    NetworkDesignDetailResponse,
    NetworkDesignSummaryResponse,
    SaveNetworkDesignRequest,
    SubmitNetworkDesignRequest,
    UpdateNetworkDesignInstallationRequest,
    UpdateNetworkDesignMilestonesRequest,
    UpdateNetworkDesignStatusRequest,
)
from app.services.authorization_service import AuthorizationService
from app.services.network_design_service import NetworkDesignService

router = APIRouter(prefix='/designs', tags=['Designs'])


def _is_admin_actor(current_user: dict | None) -> bool:
    if not current_user:
        return False
    return str(current_user.get('role') or '').upper() in {'ADMIN', 'SUPER_ADMIN'}


def _serialize_lead(lead) -> DesignLeadResponse | None:
    if not lead:
        return None
    return DesignLeadResponse(
        id=str(lead.id),
        fullName=lead.full_name,
        email=lead.email,
        companyName=lead.company_name,
        phone=lead.phone,
        notes=lead.notes,
        createdAt=lead.created_at,
        updatedAt=lead.updated_at,
    )


def _serialize_updates(row, *, include_internal: bool) -> list[DesignUpdateResponse]:
    updates = NetworkDesignService.filter_updates(row.updates_json or [], include_internal=include_internal)
    design_id = str(row.id)
    serialized: list[DesignUpdateResponse] = []
    for update in updates:
        serialized.append(
            DesignUpdateResponse(
                id=str(update.get('id') or ''),
                requestId=design_id,
                createdAt=str(update.get('createdAt') or ''),
                author=update.get('author'),
                visibility='customer' if str(update.get('visibility') or '').lower() == 'customer' else 'internal',
                message=str(update.get('message') or ''),
            )
        )
    return serialized


def _serialize_status_history(row) -> list[DesignStatusHistoryEntryResponse]:
    status_aliases = {
        'quote_ready': 'proposal_ready',
        'fulfilled': 'completed',
    }
    status_history = list(row.status_history_json or [])
    serialized: list[DesignStatusHistoryEntryResponse] = []
    for entry in status_history:
        if not isinstance(entry, dict):
            continue
        status = str(entry.get('status') or '').strip()
        status = status_aliases.get(status, status)
        changed_at = str(entry.get('changedAt') or '')
        if not status or not changed_at:
            continue
        try:
            serialized.append(
                DesignStatusHistoryEntryResponse(
                    status=status,
                    changedAt=changed_at,
                    changedBy=entry.get('changedBy'),
                    note=entry.get('note'),
                )
            )
        except Exception:
            continue
    return serialized


def _serialize_summary(row, *, include_internal: bool) -> NetworkDesignSummaryResponse:
    metadata = row.metadata_json or {}
    status = row.status.value if hasattr(row.status, 'value') else str(row.status)
    if status == 'quote_ready':
        status = 'proposal_ready'
    if status == 'fulfilled':
        status = 'completed'
    visible_updates = _serialize_updates(row, include_internal=include_internal)
    return NetworkDesignSummaryResponse(
        id=str(row.id),
        quoteId=metadata.get('quoteId') or metadata.get('quote_id'),
        orderId=metadata.get('orderId') or metadata.get('order_id'),
        workflowInstanceId=metadata.get('workflowInstanceId') or metadata.get('workflow_instance_id'),
        designName=row.design_name,
        status=status,
        statusUpdatedAt=row.status_updated_at,
        estimatedCapex=float(row.estimate_capex or 0),
        apCount=int(row.ap_count or 0),
        switchCount=int(row.switch_count or 0),
        submittedAt=row.submitted_at,
        milestones=DesignMilestonesResponse(**(row.milestones_json or {})),
        latestUpdate=visible_updates[-1].message if visible_updates else None,
        nextMilestone=NetworkDesignService.next_milestone_label(row.milestones_json or {}),
        createdAt=row.created_at,
        updatedAt=row.updated_at,
        lead=_serialize_lead(row.lead),
    )


def _serialize_detail(row, *, include_internal: bool) -> NetworkDesignDetailResponse:
    summary = _serialize_summary(row, include_internal=include_internal)
    return NetworkDesignDetailResponse(
        **summary.model_dump(by_alias=True),
        calculatorInput=row.calculator_input_json or {},
        calculatorResult=row.calculator_result_json or {},
        bom=row.bom_json or {},
        topology=row.topology_json or {},
        drawioXml=row.drawio_xml,
        assumptions=list(row.assumptions_json or []),
        statusHistory=_serialize_status_history(row),
        updates=_serialize_updates(row, include_internal=include_internal),
        installAssistance=DesignInstallAssistanceResponse(**(row.install_assistance_json or {})),
        decomposition=row.decomposition_json or {},
        metadata=row.metadata_json or {},
    )


@router.post('', response_model=NetworkDesignDetailResponse)
def save_design(
    payload: SaveNetworkDesignRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    current_user = getattr(request.state, 'user', None)
    include_internal = _is_admin_actor(current_user)
    design = NetworkDesignService(db).save_design(
        current_user=current_user,
        payload=payload.model_dump(by_alias=False, exclude_none=True),
    )
    return _serialize_detail(design, include_internal=include_internal)


@router.get('', response_model=list[NetworkDesignSummaryResponse])
def list_designs(
    submitted_only: bool = False,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    include_internal = _is_admin_actor(current_user)
    rows = NetworkDesignService(db).list_designs(current_user, submitted_only=submitted_only)
    return [_serialize_summary(row, include_internal=include_internal) for row in rows]


@router.get('/ops/submissions', response_model=list[NetworkDesignSummaryResponse])
def list_ops_submissions(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    AuthorizationService(db).require(current_user, PERM_MANAGE_LIFECYCLE)
    rows = NetworkDesignService(db).list_designs(current_user, ops_view=True)
    return [_serialize_summary(row, include_internal=True) for row in rows]


@router.get('/{design_id}', response_model=NetworkDesignDetailResponse)
def get_design(design_id: str, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    row = NetworkDesignService(db).get_design(current_user, design_id)
    return _serialize_detail(row, include_internal=_is_admin_actor(current_user))


@router.post('/{design_id}/submit', response_model=NetworkDesignDetailResponse)
def submit_design(
    design_id: str,
    payload: SubmitNetworkDesignRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = NetworkDesignService(db).submit_design(
        current_user,
        design_id=design_id,
        payload=payload.model_dump(by_alias=False, exclude_none=True),
    )
    return _serialize_detail(row, include_internal=_is_admin_actor(current_user))


@router.patch('/{design_id}/status', response_model=NetworkDesignDetailResponse)
def update_design_status(
    design_id: str,
    payload: UpdateNetworkDesignStatusRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    AuthorizationService(db).require(current_user, PERM_MANAGE_LIFECYCLE)
    row = NetworkDesignService(db).update_status(
        current_user,
        design_id,
        payload.status,
        note=payload.note,
        note_visibility=payload.note_visibility,
    )
    return _serialize_detail(row, include_internal=True)


@router.patch('/{design_id}/milestones', response_model=NetworkDesignDetailResponse)
def update_design_milestones(
    design_id: str,
    payload: UpdateNetworkDesignMilestonesRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    AuthorizationService(db).require(current_user, PERM_MANAGE_LIFECYCLE)
    row = NetworkDesignService(db).update_milestones(
        current_user,
        design_id,
        payload.milestones.model_dump(by_alias=False, exclude_none=True),
    )
    return _serialize_detail(row, include_internal=True)


@router.patch('/{design_id}/install-assistance', response_model=NetworkDesignDetailResponse)
def update_design_install_assistance(
    design_id: str,
    payload: UpdateNetworkDesignInstallationRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = NetworkDesignService(db).update_install_assistance(
        current_user,
        design_id,
        payload.install_assistance.model_dump(by_alias=False, exclude_none=True),
    )
    return _serialize_detail(row, include_internal=_is_admin_actor(current_user))


@router.post('/{design_id}/updates', response_model=NetworkDesignDetailResponse)
def add_design_update(
    design_id: str,
    payload: AddNetworkDesignUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    AuthorizationService(db).require(current_user, PERM_MANAGE_LIFECYCLE)
    row = NetworkDesignService(db).add_update_note(
        current_user=current_user,
        design_id=design_id,
        payload=payload.update.model_dump(by_alias=False, exclude_none=True),
    )
    return _serialize_detail(row, include_internal=True)
