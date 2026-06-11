from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'SecureOffice2 API'
    app_env: str = 'development'
    app_debug: bool = False
    backend_cors_origins: str = 'http://localhost:5173'

    database_url: str = Field(..., alias='DATABASE_URL')

    jwt_secret_key: str = Field(..., alias='JWT_SECRET_KEY')
    oauth_session_secret: str = ''
    jwt_algorithm: str = 'HS256'
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    refresh_cookie_name: str = 'refresh_token'
    # Secure defaults: HTTPS-only cookies, SameSite=lax (compatible with OAuth redirects
    # and same-site frontend). Override via COOKIE_SECURE=false for local HTTP dev only.
    cookie_secure: bool = True
    cookie_samesite: str = 'lax'
    cookie_domain: str | None = None

    # Number of trusted reverse proxies in front of the app. When > 0, the rate limiter
    # resolves the real client IP from X-Forwarded-For instead of the socket peer.
    # Set to 1 if behind a single LB / nginx; 2 if LB -> nginx; etc. 0 means no proxy.
    trusted_proxy_count: int = 0

    # Logging (docs/LOGGING_PLAN.md §4.5). The sink is the only env-specific
    # piece: 'file' writes RFC 5424 lines to LOG_DIR (dev), 'syslog' sends to
    # rsyslog via /dev/log (prod). LOG_LEVEL empty → DEBUG in dev, INFO in prod.
    log_sink: str = Field(default='file', alias='LOG_SINK')
    log_dir: str = Field(default='./logs/dev', alias='LOG_DIR')
    log_level: str = Field(default='', alias='LOG_LEVEL')

    # OTP brute-force protection: number of verification attempts per issued OTP
    # before the OTP is invalidated and the user must request a new one.
    otp_max_attempts: int = 5

    otp_expire_minutes: int = 5

    # Per-email OTP request throttle: caps how many OTPs can be issued to a single
    # account within a rolling window. The IP-based RateLimitMiddleware stops a
    # single noisy IP, but a distributed attacker (botnet / rotating IPs) can still
    # email-bomb one victim and burn our email quota — this closes that gap.
    otp_request_max_per_window: int = 3
    otp_request_window_minutes: int = 10
    # Minimum gap between successive OTP sends to one account. Stops the
    # "5 wrong attempts -> instant resend -> 5 more" loop at machine speed and
    # cuts email cost, without punishing a legit user who simply mistyped.
    otp_resend_cooldown_seconds: int = 60

    design_handoff_email: str = Field(default='', alias='DESIGN_HANDOFF_EMAIL')
    resend_api_key: str = Field(default='', alias='RESEND_API_KEY')
    resend_from_email: str = Field(default='', alias='RESEND_FROM_EMAIL')
    resend_from_name: str = Field(default='SecureOffice2', alias='RESEND_FROM_NAME')

    default_tenant_id: str | None = None
    bootstrap_super_admin_email: str = 'muskan.d@cellhubms.com'
    # Additional super-admin emails (comma-separated), kept in env — NOT the DB.
    # This env list is the source of truth for *who* is a super admin; the user's
    # credential row is created only when they set a password via the secure setup
    # flow. e.g. SUPER_ADMIN_EMAILS=a@x.com,b@x.com
    super_admin_emails: str = Field(default='', alias='SUPER_ADMIN_EMAILS')

    @property
    def super_admin_email_set(self) -> set[str]:
        """Lowercased set of all super-admin emails: the bootstrap admin plus the
        comma-separated SUPER_ADMIN_EMAILS allowlist."""
        emails: set[str] = set()
        if self.bootstrap_super_admin_email:
            emails.add(self.bootstrap_super_admin_email.strip().lower())
        for raw in (self.super_admin_emails or '').split(','):
            e = raw.strip().lower()
            if e:
                emails.add(e)
        return emails

    def is_super_admin_email(self, email: str | None) -> bool:
        return bool(email) and email.strip().lower() in self.super_admin_email_set

    # Minutes a super-admin password-setup link stays valid (single-use + expiring).
    super_admin_setup_ttl_minutes: int = Field(default=60, alias='SUPER_ADMIN_SETUP_TTL_MINUTES')

    # Multi-tenant Phase 4: Postgres Row-Level Security hardening. OFF by default —
    # app-layer guards (Phases 0–3) already scope queries; RLS is defense-in-depth.
    # When True, runtime migrations ENABLE+FORCE RLS with a tenant-isolation policy
    # on every tenant-scoped table, and each request sets app.current_tenant_id.
    # When False, the migration reverts (drops policy + disables RLS) — a kill switch.
    # Requires the app's DB role to be a NON-superuser owner (superusers bypass RLS).
    enable_rls: bool = Field(default=False, alias='ENABLE_RLS')

    frontend_url: str = 'http://localhost:5173'

    google_client_id: str = ''
    google_client_secret: str = ''
    google_redirect_uri: str = 'http://localhost:8000/auth/google/callback'

    microsoft_client_id: str = ''
    microsoft_client_secret: str = ''
    microsoft_tenant_id: str = 'common'
    microsoft_redirect_uri: str = 'http://localhost:8000/auth/microsoft/callback'

    openai_api_key: str = Field(default='', alias='OPENAI_API_KEY')
    cdw_ingest_mode: str = Field(default='script', alias='CDW_INGEST_MODE')
    cdw_agent_command: str = Field(default='', alias='CDW_AGENT_COMMAND')
    cdw_agent_timeout_seconds: int = Field(default=60, alias='CDW_AGENT_TIMEOUT_SECONDS')
    cdw_openai_model: str = Field(default='gpt-4.1-mini', alias='CDW_OPENAI_MODEL')

    papi_base_url: str = Field(default='https://apipapi.cellhub.com', alias='PAPI_BASE_URL')
    papi_basic_auth_token: str = Field(default='', alias='PAPI_BASIC_AUTH_TOKEN')

    crewai_verbose: bool = Field(default=False, alias='CREWAI_VERBOSE')

    anam_api_key: str = Field(default='', alias='ANAM_API_KEY')

    zabbix_url: str = Field(default='', alias='ZABBIX_URL')
    zabbix_username: str = Field(default='', alias='ZABBIX_USERNAME')
    zabbix_password: str = Field(default='', alias='ZABBIX_PASSWORD')

    stripe_secret_key: str = Field(default='', alias='STRIPE_SECRET_KEY')
    stripe_publishable_key: str = Field(default='', alias='STRIPE_PUBLISHABLE_KEY')
    stripe_webhook_secret: str = Field(default='', alias='STRIPE_WEBHOOK_SECRET')
    stripe_success_url: str = Field(default='', alias='STRIPE_SUCCESS_URL')
    stripe_cancel_url: str = Field(default='', alias='STRIPE_CANCEL_URL')


@lru_cache
def get_settings() -> Settings:
    return Settings()
