from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError

settings = get_settings()


class TokenService:
    @staticmethod
    def create_access_token(*, user_id: str, email: str, role: str, tenant_id: str) -> str:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
        payload = {
            'user_id': user_id,
            'email': email,
            'role': role,
            'tenant_id': tenant_id,
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
