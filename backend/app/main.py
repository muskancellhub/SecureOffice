from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware
from app.core.config import get_settings
from app.core.database import Base, SessionLocal, engine
from app.core.exceptions import AppError
from app.core.permissions import default_permissions_for_role
from app.core.runtime_migrations import apply_runtime_migrations
from app.middleware.auth_middleware import AuthContextMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.models import User, UserRole, UserType
from app.models.tenant import Tenant, TenantType
from app.models.vendor import Vendor
from app.routes.auth import router as auth_router
from app.routes.billing import router as billing_router
from app.routes.chatbot import router as chatbot_router
from app.routes.designs import router as designs_router
from app.routes.cart import router as cart_router
from app.routes.catalog import router as catalog_router
from app.routes.integrations import router as integrations_router
from app.routes.lifecycle import router as lifecycle_router
from app.routes.onboarding import router as onboarding_router
from app.routes.orders import router as orders_router
from app.routes.pricing import router as pricing_router
from app.routes.quotes import router as quotes_router
from app.routes.users import router as users_router
from app.services.catalog_service import CatalogService
from app.services.oauth_service import register_oauth_clients
from app import models  # noqa: F401

settings = get_settings()
app = FastAPI(title=settings.app_name, debug=settings.app_debug)


@app.on_event('startup')
def startup() -> None:
    import logging
    logger = logging.getLogger(__name__)

    apply_runtime_migrations()
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        CatalogService(db).seed_managed_services()
        CatalogService(db).seed_partner_devices()
        try:
            result = CatalogService(db).upsert_network_vendor_catalog()
            logger.info(
                'Network vendor Excel sync: %d synced, %d created, %d updated, %d errors',
                result['synced_count'],
                result['created_count'],
                result['updated_count'],
                len(result['errors']),
            )
        except Exception as exc:
            logger.warning('Network vendor Excel sync failed on startup: %s', exc)

        if settings.papi_basic_auth_token:
            try:
                from app.services.papi_client import fetch_all_products
                raw_products = fetch_all_products(page_size=100, max_pages=5)
                result = CatalogService(db).upsert_papi_products(raw_products)
                logger.info(
                    'PAPI startup sync: %d synced, %d created, %d updated, %d errors',
                    result['synced_count'], result['created_count'],
                    result['updated_count'], len(result['errors']),
                )
            except Exception as exc:
                logger.warning('PAPI startup sync failed (using seed data): %s', exc)
    if settings.bootstrap_super_admin_email:
        with SessionLocal() as db:
            bootstrap_user = db.scalar(
                select(User).where(User.email == settings.bootstrap_super_admin_email.lower().strip())
            )
            if bootstrap_user and bootstrap_user.role != UserRole.SUPER_ADMIN:
                bootstrap_user.role = UserRole.SUPER_ADMIN
                bootstrap_user.permissions = default_permissions_for_role(UserRole.SUPER_ADMIN)
                bootstrap_user.is_verified = True
                db.commit()

    with SessionLocal() as db:
        vendor_email = 'vendor@gmail.com'
        existing_vendor_user = db.scalar(select(User).where(User.email == vendor_email))
        if not existing_vendor_user:
            from app.core.security import hash_value
            vendor_tenant = Tenant(name='Demo Vendor Inc.', tenant_type=TenantType.VENDOR)
            db.add(vendor_tenant)
            db.flush()
            vendor_profile = Vendor(
                tenant_id=vendor_tenant.id,
                company_name='Demo Vendor Inc.',
                address_street='123 Commerce St',
                address_city='Austin',
                address_state='TX',
                address_zip='73301',
                company_website='https://demovendor.com',
                company_email='info@demovendor.com',
                federal_tax_id='12-3456789',
                bbb_good_standing=True,
                sos_good_standing=True,
                corporate_liable_sales=True,
                is_approved=True,
            )
            db.add(vendor_profile)
            db.flush()
            vendor_user = User(
                email=vendor_email,
                name='Demo Vendor',
                password_hash=hash_value('vendor123'),
                provider='LOCAL',
                is_verified=True,
                role=UserRole.ADMIN,
                user_type=UserType.VENDOR,
                permissions=default_permissions_for_role(UserRole.ADMIN),
                tenant_id=vendor_tenant.id,
            )
            db.add(vendor_user)
            db.commit()
            logger.info('Seeded demo vendor: vendor@gmail.com / vendor123')

    register_oauth_clients()


# NOTE: Middleware order matters. Starlette's `add_middleware` inserts at
# position 0, so the LAST middleware added becomes the OUTERMOST wrapper.
# CORSMiddleware must be outermost so that responses generated directly by
# inner middleware (e.g. 429 from RateLimitMiddleware, 401 from auth failures)
# still get `Access-Control-Allow-Origin` headers attached on the way out.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.oauth_session_secret or settings.jwt_secret_key,
    same_site=settings.cookie_samesite,
    https_only=settings.cookie_secure,
)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(AuthContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.backend_cors_origins.split(',') if origin.strip()],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content={'detail': exc.message})


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(_: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code, content={'detail': exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={'detail': exc.errors()})


@app.exception_handler(Exception)
async def unhandled_error_handler(_: Request, exc: Exception):
    if settings.app_debug:
        return JSONResponse(status_code=500, content={'detail': str(exc)})
    return JSONResponse(status_code=500, content={'detail': 'Internal server error'})


@app.get('/health')
def health_check():
    return {'status': 'ok'}


app.include_router(auth_router)
app.include_router(users_router)
app.include_router(onboarding_router)
app.include_router(integrations_router)
app.include_router(catalog_router)
app.include_router(designs_router)
app.include_router(cart_router)
app.include_router(quotes_router)
app.include_router(orders_router)
app.include_router(pricing_router)
app.include_router(lifecycle_router)
app.include_router(billing_router)
app.include_router(chatbot_router)

from app.routes.anam import router as anam_router
app.include_router(anam_router)

from app.routes.zabbix import router as zabbix_router
app.include_router(zabbix_router)

from app.routes.intake_chat import router as intake_chat_router
app.include_router(intake_chat_router)
