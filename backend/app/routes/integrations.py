from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import PERM_MANAGE_CATALOG_SYNC
from app.middleware.dependencies import get_current_user
from app.models.integration_log import SyncStatus
from app.repositories.integration_log_repository import IntegrationLogRepository
from app.schemas.catalog import CatalogItemResponse, CatalogSyncResponse
from app.schemas.integrations import (
    DesignXSuggestBOMRequest,
    DesignXSuggestBOMResponse,
    DesignXSuggestedLineResponse,
    GenerateNetworkBomRequest,
    GenerateNetworkBomResponse,
    IntegrationSyncLogResponse,
    NetworkBomLineResponse,
    SyncNetworkVendorCatalogRequest,
    SyncPapiDevicesRequest,
    SyncRoutersRequest,
)
from app.schemas.topology import (
    GenerateNetworkTopologyRequest,
    GenerateNetworkTopologyResponse,
    NetworkTopologyResponse,
    NetworkTopologySummaryResponse,
)
from app.services.authorization_service import AuthorizationService
from app.services.catalog_service import CatalogService
from app.services.cdw_agent_service import CDWAgentService
from app.services.designx_service import DesignXService
from app.services.network_bom_service import NetworkBomService
from app.services.network_topology_service import NetworkTopologyService
from app.services.papi_client import fetch_all_products

router = APIRouter(prefix='/integrations', tags=['Integrations'])


def _catalog_response(service: CatalogService, item) -> CatalogItemResponse:
    return CatalogItemResponse(**service.to_catalog_response_dict(item))


@router.post('/cdw/sync-routers', response_model=CatalogSyncResponse)
def sync_cdw_routers(payload: SyncRoutersRequest, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    AuthorizationService(db).require(current_user, PERM_MANAGE_CATALOG_SYNC)

    log_repo = IntegrationLogRepository(db)
    log = log_repo.create_log(integration_name='cdw', scope='routers')

    try:
        raw_items = CDWAgentService.fetch_routers(payload.query, payload.limit)
        service = CatalogService(db)
        result = service.upsert_router_items(raw_items)

        status = SyncStatus.SUCCESS if not result['errors'] else SyncStatus.PARTIAL
        log_repo.complete_log(
            log,
            status=status,
            synced_count=result['synced_count'],
            created_count=result['created_count'],
            updated_count=result['updated_count'],
            error_excerpt='; '.join(result['errors'][:3]) if result['errors'] else None,
        )
        db.commit()

        return CatalogSyncResponse(
            synced_count=result['synced_count'],
            created_count=result['created_count'],
            updated_count=result['updated_count'],
            errors=result['errors'],
            items=[_catalog_response(service, item) for item in result['items']],
        )
    except Exception as exc:
        log_repo.complete_log(
            log,
            status=SyncStatus.FAILED,
            synced_count=0,
            created_count=0,
            updated_count=0,
            error_excerpt=str(exc)[:1500],
        )
        db.commit()
        raise


@router.get('/cdw/last-sync', response_model=IntegrationSyncLogResponse | None)
def get_cdw_last_sync(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    AuthorizationService(db).require(current_user, PERM_MANAGE_CATALOG_SYNC)
    log = IntegrationLogRepository(db).get_last('cdw', 'routers')
    if not log:
        return None

    return IntegrationSyncLogResponse(
        integration_name=log.integration_name,
        scope=log.scope,
        status=log.status.value,
        synced_count=log.synced_count,
        created_count=log.created_count,
        updated_count=log.updated_count,
        error_excerpt=log.error_excerpt,
        started_at=log.started_at,
        finished_at=log.finished_at,
        created_at=log.created_at,
    )


@router.post('/papi/sync-devices', response_model=CatalogSyncResponse)
def sync_papi_devices(
    payload: SyncPapiDevicesRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    AuthorizationService(db).require(current_user, PERM_MANAGE_CATALOG_SYNC)

    log_repo = IntegrationLogRepository(db)
    log = log_repo.create_log(integration_name='papi', scope='devices')

    try:
        raw_products = fetch_all_products(
            eip=payload.eip,
            classic=payload.classic,
            page_size=payload.page_size,
            max_pages=payload.max_pages,
        )
        service = CatalogService(db)
        result = service.upsert_papi_products(raw_products)

        status = SyncStatus.SUCCESS if not result['errors'] else SyncStatus.PARTIAL
        log_repo.complete_log(
            log,
            status=status,
            synced_count=result['synced_count'],
            created_count=result['created_count'],
            updated_count=result['updated_count'],
            error_excerpt='; '.join(result['errors'][:3]) if result['errors'] else None,
        )
        db.commit()

        return CatalogSyncResponse(
            synced_count=result['synced_count'],
            created_count=result['created_count'],
            updated_count=result['updated_count'],
            errors=result['errors'],
            items=[_catalog_response(service, item) for item in result['items']],
        )
    except Exception as exc:
        log_repo.complete_log(
            log,
            status=SyncStatus.FAILED,
            synced_count=0,
            created_count=0,
            updated_count=0,
            error_excerpt=str(exc)[:1500],
        )
        db.commit()
        raise


@router.get('/papi/last-sync', response_model=IntegrationSyncLogResponse | None)
def get_papi_last_sync(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    AuthorizationService(db).require(current_user, PERM_MANAGE_CATALOG_SYNC)
    log = IntegrationLogRepository(db).get_last('papi', 'devices')
    if not log:
        return None

    return IntegrationSyncLogResponse(
        integration_name=log.integration_name,
        scope=log.scope,
        status=log.status.value,
        synced_count=log.synced_count,
        created_count=log.created_count,
        updated_count=log.updated_count,
        error_excerpt=log.error_excerpt,
        started_at=log.started_at,
        finished_at=log.finished_at,
        created_at=log.created_at,
    )


@router.post('/network/sync-vendor-catalog', response_model=CatalogSyncResponse)
def sync_network_vendor_catalog(
    payload: SyncNetworkVendorCatalogRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    AuthorizationService(db).require(current_user, PERM_MANAGE_CATALOG_SYNC)

    log_repo = IntegrationLogRepository(db)
    log = log_repo.create_log(integration_name='excel_network_vendor', scope='devices')

    try:
        service = CatalogService(db)
        result = service.upsert_network_vendor_catalog(payload.file_path)

        status = SyncStatus.SUCCESS if not result['errors'] else SyncStatus.PARTIAL
        log_repo.complete_log(
            log,
            status=status,
            synced_count=result['synced_count'],
            created_count=result['created_count'],
            updated_count=result['updated_count'],
            error_excerpt='; '.join(result['errors'][:3]) if result['errors'] else None,
        )
        db.commit()

        return CatalogSyncResponse(
            synced_count=result['synced_count'],
            created_count=result['created_count'],
            updated_count=result['updated_count'],
            errors=result['errors'],
            items=[_catalog_response(service, item) for item in result['items']],
        )
    except Exception as exc:
        log_repo.complete_log(
            log,
            status=SyncStatus.FAILED,
            synced_count=0,
            created_count=0,
            updated_count=0,
            error_excerpt=str(exc)[:1500],
        )
        db.commit()
        raise


@router.get('/network/last-sync', response_model=IntegrationSyncLogResponse | None)
def get_network_vendor_last_sync(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    AuthorizationService(db).require(current_user, PERM_MANAGE_CATALOG_SYNC)
    log = IntegrationLogRepository(db).get_last('excel_network_vendor', 'devices')
    if not log:
        return None

    return IntegrationSyncLogResponse(
        integration_name=log.integration_name,
        scope=log.scope,
        status=log.status.value,
        synced_count=log.synced_count,
        created_count=log.created_count,
        updated_count=log.updated_count,
        error_excerpt=log.error_excerpt,
        started_at=log.started_at,
        finished_at=log.finished_at,
        created_at=log.created_at,
    )


@router.post('/designx/suggest-bom', response_model=DesignXSuggestBOMResponse)
def suggest_designx_bom(
    payload: DesignXSuggestBOMRequest,
    _: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = DesignXService(db).suggest_bom(
        requirement=payload.requirement,
        employee_count=payload.employee_count,
        site_count=payload.site_count,
        existing_customer=payload.existing_customer,
    )
    return DesignXSuggestBOMResponse(
        summary=result['summary'],
        suggestions=[DesignXSuggestedLineResponse(**row) for row in result['suggestions']],
        unavailable_categories=result['unavailable_categories'],
    )


@router.post('/network/generate-bom', response_model=GenerateNetworkBomResponse)
def generate_network_bom(
    payload: GenerateNetworkBomRequest,
    _: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = NetworkBomService(CatalogService(db)).generate_bom_from_estimate(
        calculator_result=payload.calculator_result,
        business_context=payload.business_context,
        preferences=payload.preferences.model_dump(exclude_none=True),
    )

    return GenerateNetworkBomResponse(
        line_items=[NetworkBomLineResponse(**line) for line in result['line_items']],
        subtotal=result['subtotal'],
        tax=result['tax'],
        grand_total=result['grand_total'],
        summary=result['summary'],
        assumptions=result['assumptions'],
    )


@router.post('/network/generate-topology', response_model=GenerateNetworkTopologyResponse)
def generate_network_topology(
    payload: GenerateNetworkTopologyRequest,
    _: dict = Depends(get_current_user),
):
    result = NetworkTopologyService().generate_topology_artifact_from_bom(
        bom=payload.bom,
        design_id=payload.design_id,
        business_context=payload.business_context,
    )

    return GenerateNetworkTopologyResponse(
        topology=NetworkTopologyResponse.model_validate(result['topology']),
        drawio_xml=result['drawioXml'],
        summary=NetworkTopologySummaryResponse.model_validate(result['summary']),
    )
