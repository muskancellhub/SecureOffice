import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware
from app.core.config import get_settings
from app.core.database import Base, SessionLocal, engine
from app.core.exceptions import AppError, ForbiddenError
from app.core.logging_config import configure_logging
from app.core.permissions import default_permissions_for_role
from app.core.request_context import reset_request_context, set_request_context
from app.core.runtime_migrations import apply_runtime_migrations
from app.middleware.auth_middleware import AuthContextMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_context import RequestContextMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.services.audit_logger import audit
from app.models import User, UserRole, UserType
from app.models.tenant import Tenant, TenantType
from app.models.vendor import Vendor
from app.routes.audit_logs import router as audit_logs_router
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
from app.routes.products import router as products_router
from app.routes.bundles import router as bundles_router
from app.routes.quotes import router as quotes_router
from app.routes.tenants import router as tenants_router
from app.routes.tenant_settings import router as tenant_settings_router
from app.routes.users import router as users_router
from app.routes.search import router as search_router
from app.services.catalog_service import CatalogService
from app.services.oauth_service import register_oauth_clients
from app import models  # noqa: F401

settings = get_settings()

configure_logging(
    app_env=settings.app_env,
    log_sink=settings.log_sink,
    log_dir=settings.log_dir,
    log_level=settings.log_level,
)
logger = logging.getLogger(__name__)

# In production, hide the auto-generated API docs. They leak the full endpoint
# shape + request/response schemas to anyone who can reach the backend, which
# is an easy reconnaissance win for attackers.
_is_prod = settings.app_env == 'production'
app = FastAPI(
    title=settings.app_name,
    debug=settings.app_debug,
    docs_url=None if _is_prod else '/docs',
    redoc_url=None if _is_prod else '/redoc',
    openapi_url=None if _is_prod else '/openapi.json',
)


def _custom_openapi():
    """Declare a global HTTP Bearer scheme so Swagger UI shows an 'Authorize'
    button. Auth is enforced by AuthContextMiddleware (it reads the
    `Authorization: Bearer <access_token>` header), not per-route security
    dependencies — so we inject the scheme into the schema here rather than
    adding Security() to every endpoint."""
    if app.openapi_schema:
        return app.openapi_schema
    from fastapi.openapi.utils import get_openapi

    schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
        description=app.description,
    )
    schema.setdefault('components', {}).setdefault('securitySchemes', {})['bearerAuth'] = {
        'type': 'http',
        'scheme': 'bearer',
        'bearerFormat': 'JWT',
    }
    # Apply as a default so every operation shows the lock icon; endpoints that
    # don't check auth simply ignore the header.
    schema['security'] = [{'bearerAuth': []}]
    app.openapi_schema = schema
    return schema


app.openapi = _custom_openapi


def _assert_production_hardening(settings) -> None:
    """Refuse to start in production with insecure defaults.

    Catches common "forgot to set the env var in prod" mistakes before
    the app accepts any traffic.
    """
    if settings.app_env != 'production':
        return
    errors = []
    if not settings.cookie_secure:
        errors.append('COOKIE_SECURE must be true in production (refresh cookie leaks over HTTP otherwise)')
    if not settings.oauth_session_secret:
        errors.append('OAUTH_SESSION_SECRET must be set in production (do not share with JWT_SECRET_KEY)')
    if settings.oauth_session_secret and settings.oauth_session_secret == settings.jwt_secret_key:
        errors.append('OAUTH_SESSION_SECRET must differ from JWT_SECRET_KEY (avoid cross-purpose key reuse)')
    if settings.app_debug:
        errors.append('APP_DEBUG must be false in production (leaks stack traces)')
    if errors:
        raise RuntimeError('Refusing to start — production security preconditions failed:\n  - ' + '\n  - '.join(errors))


def _assert_encryption_ready(settings) -> None:
    """Fail fast (all environments) if the PII-encryption master key is missing
    or malformed (docs/PII_ENCRYPTION.md §5). Booting without a valid KEK would
    let the first PII write fail mid-request, or — worse — invite a fallback to
    plaintext; refusing to start makes the misconfiguration loud and immediate.
    """
    settings.master_encryption_key_bytes()  # raises RuntimeError if absent/not 32 bytes


_assert_production_hardening(settings)
_assert_encryption_ready(settings)


@app.on_event('startup')
def startup() -> None:
    # Bootstrap ordering matters on a fresh database (mirrors the CI
    # "Bootstrap schema" step): the orders/quotes public_id server defaults
    # reference these sequences, so they must exist before create_all, and
    # the runtime migrations ALTER tables that create_all has to create first.
    from sqlalchemy import text as _text
    with engine.begin() as conn:
        conn.execute(_text('CREATE SEQUENCE IF NOT EXISTS quote_public_id_seq'))
        conn.execute(_text('CREATE SEQUENCE IF NOT EXISTS order_public_id_seq'))
    Base.metadata.create_all(bind=engine)
    apply_runtime_migrations()
    # Phase 7 — one catalog: backfill any legacy catalog_items rows into
    # products, then drop the legacy tables (locked decision — not in
    # production, no archive window). Both steps are idempotent no-ops once
    # the table is gone.
    from app.services.catalog_unification import (
        drop_legacy_catalog_tables,
        migrate_catalog_items_to_products,
    )
    with SessionLocal() as db:
        result = migrate_catalog_items_to_products(db)
        if not result.get('skipped'):
            logger.info('Catalog unification: migrated %d legacy catalog_items rows', result['migrated'])
    drop_legacy_catalog_tables()
    with SessionLocal() as db:
        CatalogService(db).seed_managed_services()
        CatalogService(db).seed_partner_devices()
        CatalogService(db).seed_mix_products()
        CatalogService(db).seed_discounted_items()
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
    # Promote every existing user whose email is in the env super-admin allowlist
    # (bootstrap admin + SUPER_ADMIN_EMAILS). Accounts that don't exist yet are
    # promoted lazily on first auth (or created via the secure password-setup flow).
    super_admin_emails = settings.super_admin_email_set
    if super_admin_emails:
        from sqlalchemy import func as _func
        with SessionLocal() as db:
            rows = db.scalars(
                select(User).where(_func.lower(User.email).in_(super_admin_emails))
            ).all()
            changed = False
            for u in rows:
                if u.role != UserRole.SUPER_ADMIN:
                    u.role = UserRole.SUPER_ADMIN
                    u.permissions = default_permissions_for_role(UserRole.SUPER_ADMIN)
                    u.is_verified = True
                    changed = True
            if changed:
                db.commit()

    # Demo vendor seed: DEV ONLY. Never run in production — this creates a
    # well-known admin account with a publicly-documented password.
    if settings.app_env != 'production':
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
                from app.services.tenant_provisioning_service import TenantProvisioningService
                TenantProvisioningService(db).provision(vendor_tenant.id)
                db.commit()
                logger.info('[dev] seeded demo vendor: vendor@gmail.com / vendor123 (APP_ENV=%s)', settings.app_env)

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
app.add_middleware(RateLimitMiddleware, trusted_proxy_count=settings.trusted_proxy_count)
app.add_middleware(SecurityHeadersMiddleware, app_env=settings.app_env)
app.add_middleware(AuthContextMiddleware)
# Just inside CORS so every downstream middleware/route runs with request
# context set, and the access line sees auth identity (docs/LOGGING_PLAN.md §4.1).
app.add_middleware(RequestContextMiddleware, trusted_proxy_count=settings.trusted_proxy_count)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.backend_cors_origins.split(',') if origin.strip()],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    # Central security hooks (docs/LOGGING_PLAN.md §4.3) — no per-route work.
    if isinstance(exc, ForbiddenError):
        audit.log(
            'access_denied',
            status='denied',
            level=logging.WARNING,
            endpoint_attempted=f'{request.method} {request.url.path}',
            required_permission=exc.required_permission,
            reason=exc.message,
        )
    elif exc.status_code >= 500:
        audit.log(
            'server_error',
            status='failure',
            level=logging.ERROR,
            error_code=exc.status_code,
            reason=exc.message,
        )
    return JSONResponse(status_code=exc.status_code, content={'detail': exc.message})


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(_: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code, content={'detail': exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError):
    safe_errors = [
        {k: v for k, v in e.items() if k != 'ctx'}
        for e in exc.errors()
    ]
    # jsonable_encoder coerces non-serializable values (e.g. the raw request
    # body bytes that FastAPI stores in `input` for non-JSON Content-Types)
    # into JSON-safe types. Without it, json.dumps raises on bytes and the
    # 422 handler itself fails with an unhandled 500 (BUG-CART-003).
    return JSONResponse(status_code=422, content={'detail': jsonable_encoder(safe_errors)})


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    # Bad Unicode in JSON body → Postgres rejects it → SQLAlchemy DataError.
    # Classify these as client input errors (400), not server errors (500).
    # Prevents a trivial DoS where any authenticated user can force 500s by
    # sending lone surrogates like "\uD812" in JSON fields that hit JSONB.
    try:
        from sqlalchemy.exc import DataError
    except ImportError:
        DataError = ()  # type: ignore[assignment]
    if isinstance(exc, UnicodeError) or (DataError and isinstance(exc, DataError) and 'surrogate' in str(exc).lower()):
        return JSONResponse(
            status_code=400,
            content={'detail': 'Request body contains invalid Unicode (lone surrogates or non-UTF-8 sequences).'},
        )
    # Stack trace to the app log (local0) only; the audit stream gets the
    # event without internals (docs/LOGGING_PLAN.md §4.3).
    logger.error(
        'Unhandled exception on %s %s', request.method, request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    # BUG-AUD-015: this handler runs in the outer ServerErrorMiddleware, after
    # RequestContextMiddleware has already reset the context var — so re-attach
    # the stashed context for the audit emit (otherwise request_id/endpoint/ip/ua
    # log as nil). Also include error_code=500 to match the spec.
    ctx = getattr(request.state, 'log_context', None)
    token = set_request_context(ctx) if ctx is not None else None
    try:
        audit.log(
            'server_error',
            status='failure',
            level=logging.ERROR,
            error_code=500,
            error_type=type(exc).__name__,
        )
    finally:
        if token is not None:
            reset_request_context(token)
    if settings.app_debug:
        return JSONResponse(status_code=500, content={'detail': str(exc)})
    return JSONResponse(status_code=500, content={'detail': 'Internal server error'})


@app.get('/health')
def health_check():
    return {'status': 'ok'}


app.include_router(auth_router)
app.include_router(audit_logs_router)
app.include_router(users_router)
app.include_router(tenants_router)
app.include_router(tenant_settings_router)
app.include_router(onboarding_router)
app.include_router(integrations_router)
app.include_router(catalog_router)
app.include_router(designs_router)
app.include_router(cart_router)
app.include_router(quotes_router)
app.include_router(orders_router)
app.include_router(pricing_router)
app.include_router(products_router)
app.include_router(bundles_router)
app.include_router(lifecycle_router)
app.include_router(billing_router)

from app.routes.square import router as square_router
app.include_router(square_router)

app.include_router(chatbot_router)

from app.routes.anam import router as anam_router
app.include_router(anam_router)

from app.routes.zabbix import router as zabbix_router
app.include_router(zabbix_router)

from app.routes.intake_chat import router as intake_chat_router
app.include_router(intake_chat_router)
app.include_router(search_router)
