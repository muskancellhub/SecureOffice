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

    # ── Global search (Slices 3–5) ───────────────────────────────────────────
    # Semantic lane: embeds the query + products and fuses vector hits with the
    # lexical lanes via Reciprocal Rank Fusion. Degrades gracefully to lexical-
    # only when pgvector isn't installed or no OpenAI key is set.
    search_semantic_enabled: bool = Field(default=True, alias='SEARCH_SEMANTIC_ENABLED')
    search_embedding_model: str = Field(
        default='text-embedding-3-small', alias='SEARCH_EMBEDDING_MODEL'
    )
    search_embedding_dim: int = Field(default=1536, alias='SEARCH_EMBEDDING_DIM')
    # LLM fallback: when every lexical/semantic lane comes up empty, ask the
    # model to expand the query into alternative keywords and retry full-text.
    search_llm_fallback_enabled: bool = Field(
        default=True, alias='SEARCH_LLM_FALLBACK_ENABLED'
    )
    search_llm_fallback_model: str = Field(
        default='gpt-4.1-mini', alias='SEARCH_LLM_FALLBACK_MODEL'
    )

    # RAG guardrails 2.1 — secondary model-based injection classifier. Off by
    # default: it adds an OpenAI call (cost + latency) and only runs on
    # borderline inputs the deterministic filter didn't already block.
    llm_guardrail_classifier_enabled: bool = Field(
        default=False, alias='LLM_GUARDRAIL_CLASSIFIER_ENABLED'
    )
    llm_guardrail_classifier_model: str = Field(
        default='gpt-4.1-mini', alias='LLM_GUARDRAIL_CLASSIFIER_MODEL'
    )

    anam_api_key: str = Field(default='', alias='ANAM_API_KEY')

    zabbix_url: str = Field(default='', alias='ZABBIX_URL')
    zabbix_username: str = Field(default='', alias='ZABBIX_USERNAME')
    zabbix_password: str = Field(default='', alias='ZABBIX_PASSWORD')

    # Square is the sole payment provider (Stripe fully removed). Sandbox first —
    # docs/SQUARE_MIGRATION_PLAN.md §5. Host defaults to
    # the sandbox; production cutover is config-only (connect.squareup.com). The
    # access token is a backend-only secret; app id + location id are publishable.
    square_env: str = Field(default='sandbox', alias='SQUARE_ENV')
    square_api_base: str = Field(default='https://connect.squareupsandbox.com', alias='SQUARE_API_BASE')
    square_version: str = Field(default='2025-01-23', alias='SQUARE_VERSION')
    square_access_token: str = Field(default='', alias='SQUARE_ACCESS_TOKEN')
    square_location_id: str = Field(default='', alias='SQUARE_LOCATION_ID')
    square_webhook_signature_key: str = Field(default='', alias='SQUARE_WEBHOOK_SIGNATURE_KEY')
    # Square signs each webhook over (notification_url + raw body). Behind a tunnel
    # the inbound request.url often differs from the URL registered in the Console
    # (scheme/host rewrites), which breaks verification — pin the exact registered
    # URL here so the HMAC matches. Empty → fall back to the request URL.
    square_webhook_notification_url: str = Field(default='', alias='SQUARE_WEBHOOK_NOTIFICATION_URL')
    square_success_url: str = Field(default='', alias='SQUARE_SUCCESS_URL')
    square_cancel_url: str = Field(default='', alias='SQUARE_CANCEL_URL')

    # Per-tenant PII encryption master key (KEK) — base64 of exactly 32 random
    # bytes (docs/PII_ENCRYPTION.md §5). Wraps every per-tenant DEK; never stored
    # in the DB. Generate with:
    #   python -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())"
    # In v1 this is the only encryption secret; Phase 2 moves it into KMS/Key Vault
    # behind the same KeyProvider interface. The app fails fast at startup if it is
    # missing or not 32 bytes after decoding (see master_encryption_key_bytes).
    master_encryption_key: str = Field(default='', alias='MASTER_ENCRYPTION_KEY')

    def master_encryption_key_bytes(self) -> bytes:
        """Decode and validate the master KEK, returning the raw 32 bytes.

        Raises ``RuntimeError`` (fail fast) if the key is absent, not valid
        base64, or not exactly 32 bytes — an undersized/typo'd key must never
        silently downgrade encryption strength.
        """
        import base64
        import binascii

        raw = (self.master_encryption_key or '').strip()
        if not raw:
            raise RuntimeError(
                'MASTER_ENCRYPTION_KEY is not set. PII encryption requires a '
                'base64-encoded 32-byte master key. Generate one with: '
                'python -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())"'
            )
        try:
            key = base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise RuntimeError(f'MASTER_ENCRYPTION_KEY is not valid base64: {exc}') from exc
        if len(key) != 32:
            raise RuntimeError(
                f'MASTER_ENCRYPTION_KEY must decode to exactly 32 bytes, got {len(key)}.'
            )
        return key


@lru_cache
def get_settings() -> Settings:
    return Settings()
