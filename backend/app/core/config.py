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
    cookie_secure: bool = False
    cookie_samesite: str = 'lax'
    cookie_domain: str | None = None

    otp_expire_minutes: int = 5

    smtp_host: str = ''
    smtp_port: int = 587
    smtp_username: str = ''
    smtp_password: str = ''
    smtp_from_email: str = ''
    smtp_from_name: str = 'SecureOffice2'
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    design_handoff_email: str = Field(default='', alias='DESIGN_HANDOFF_EMAIL')
    sendgrid_api_key: str = Field(default='', alias='SENDGRID_API_KEY')
    sendgrid_from_email: str = Field(default='', alias='SENDGRID_FROM_EMAIL')
    sendgrid_from_name: str = Field(default='SecureOffice2', alias='SENDGRID_FROM_NAME')

    default_tenant_id: str | None = None
    bootstrap_super_admin_email: str = 'muskan.d@cellhubms.com'

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
