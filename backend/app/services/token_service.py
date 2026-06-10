from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError

settings = get_settings()


class TokenService:
    @staticmethod
    def create_access_token(
        *, user_id: str, email: str, role: str, user_type: str = 'CELLHUB',
        tenant_id: str, tenant_type: str = 'CELLHUB',
    ) -> str:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
        payload = {
            'user_id': user_id,
            'email': email,
            'role': role,
            'user_type': user_type,
            'tenant_id': tenant_id,
            'tenant_type': tenant_type,
            'type': 'access',
            'exp': expire,
        }
        return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    @staticmethod
    def create_refresh_token(*, user_id: str, session_id: int) -> str:
        expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
        payload = {
            'user_id': user_id,
            'sid': session_id,
            'type': 'refresh',
            'exp': expire,
        }
        return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    @staticmethod
    def decode_token(token: str) -> dict:
        try:
            return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        except JWTError as exc:
            raise UnauthorizedError('Invalid token') from exc

    SUPER_ADMIN_SETUP_TYPE = 'super_admin_pwd_setup'

    @staticmethod
    def create_super_admin_setup_token(*, email: str, state: str) -> str:
        """Single-use, short-TTL token for the super-admin password-setup link.
        `state` binds the token to the account's current password state so it can
        only be redeemed once (it stops matching after the password is set)."""
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.super_admin_setup_ttl_minutes)
        payload = {
            'email': email.strip().lower(),
            'state': state,
            'type': TokenService.SUPER_ADMIN_SETUP_TYPE,
            'exp': expire,
        }
        return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    @staticmethod
    def decode_super_admin_setup_token(token: str) -> dict:
        payload = TokenService.decode_token(token)
        if payload.get('type') != TokenService.SUPER_ADMIN_SETUP_TYPE:
            raise UnauthorizedError('Invalid setup token')
        return payload
