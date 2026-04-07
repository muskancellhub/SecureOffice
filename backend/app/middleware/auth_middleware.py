from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.services.token_service import TokenService


class AuthContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.user = None
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ', 1)[1].strip()
            try:
                payload = TokenService.decode_token(token)
                if payload.get('type') == 'access':
                    request.state.user = payload
            except Exception:
                request.state.user = None
        return await call_next(request)
