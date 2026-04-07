from authlib.integrations.starlette_client import OAuth
from app.core.config import get_settings

settings = get_settings()

oauth = OAuth()


def register_oauth_clients() -> None:
    if settings.google_client_id and settings.google_client_secret:
        oauth.register(
            name='google',
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
            client_kwargs={'scope': 'openid email profile'},
        )

    if settings.microsoft_client_id and settings.microsoft_client_secret:
        metadata = f"https://login.microsoftonline.com/{settings.microsoft_tenant_id}/v2.0/.well-known/openid-configuration"
        oauth.register(
            name='microsoft',
            client_id=settings.microsoft_client_id,
            client_secret=settings.microsoft_client_secret,
            server_metadata_url=metadata,
            client_kwargs={'scope': 'openid email profile User.Read'},
        )
