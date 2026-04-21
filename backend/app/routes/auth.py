from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import AppError, UnauthorizedError
from app.models import AuthProvider
from app.schemas.auth import (
    LoginOtpRequest,
    LoginOtpVerifyRequest,
    LoginRequest,
    MessageResponse,
    SignupRequest,
    TokenResponse,
    VendorSignupRequest,
    VerifyOtpRequest,
)
from app.services.auth_service import AuthService
from app.services.oauth_service import oauth

settings = get_settings()
router = APIRouter(prefix='/auth', tags=['Auth'])


def set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        domain=settings.cookie_domain,
        path='/',
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        domain=settings.cookie_domain,
        path='/',
    )


@router.post('/signup', response_model=MessageResponse)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    AuthService(db).signup(
        email=payload.email,
        password=payload.password,
        mobile=payload.mobile,
        name=payload.name,
        tenant_id=payload.tenant_id,
    )
    return MessageResponse(message='Signup successful. OTP sent.')


@router.post('/vendor/signup', response_model=MessageResponse)
def vendor_signup(payload: VendorSignupRequest, db: Session = Depends(get_db)):
    AuthService(db).vendor_signup(
        contact_name=payload.contact_name,
        contact_email=payload.contact_email,
        contact_phone=payload.contact_phone,
        password=payload.password,
        company_name=payload.company_name,
        address_street=payload.address_street,
        address_city=payload.address_city,
        address_state=payload.address_state,
        address_zip=payload.address_zip,
        company_website=payload.company_website,
        company_email=payload.company_email,
        federal_tax_id=payload.federal_tax_id,
        bbb_good_standing=payload.bbb_good_standing,
        sos_good_standing=payload.sos_good_standing,
        corporate_liable_sales=payload.corporate_liable_sales,
    )
    return MessageResponse(message='Vendor application submitted successfully. You can now log in.')


@router.post('/verify-otp', response_model=TokenResponse)
def verify_otp(payload: VerifyOtpRequest, response: Response, db: Session = Depends(get_db)):
    tokens = AuthService(db).verify_otp(email=payload.email, otp=payload.otp)
    set_refresh_cookie(response, tokens['refresh_token'])
    return TokenResponse(access_token=tokens['access_token'], expires_in=tokens['expires_in'])


@router.post('/login', response_model=TokenResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    tokens = AuthService(db).login(email=payload.email, password=payload.password)
    set_refresh_cookie(response, tokens['refresh_token'])
    return TokenResponse(access_token=tokens['access_token'], expires_in=tokens['expires_in'])


@router.post('/login/otp/request', response_model=MessageResponse)
def request_login_otp(payload: LoginOtpRequest, db: Session = Depends(get_db)):
    AuthService(db).request_login_otp(email=payload.email)
    return MessageResponse(message='If the account exists, OTP has been sent to email.')


@router.post('/login/otp/verify', response_model=TokenResponse)
def verify_login_otp(payload: LoginOtpVerifyRequest, response: Response, db: Session = Depends(get_db)):
    tokens = AuthService(db).login_with_otp(email=payload.email, otp=payload.otp)
    set_refresh_cookie(response, tokens['refresh_token'])
    return TokenResponse(access_token=tokens['access_token'], expires_in=tokens['expires_in'])


@router.post('/refresh', response_model=TokenResponse)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    refresh_token = request.cookies.get(settings.refresh_cookie_name)
    if not refresh_token:
        raise UnauthorizedError('Missing refresh token')

    tokens = AuthService(db).refresh(refresh_token)
    set_refresh_cookie(response, tokens['refresh_token'])
    return TokenResponse(access_token=tokens['access_token'], expires_in=tokens['expires_in'])


@router.post('/logout', response_model=MessageResponse)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    refresh_token = request.cookies.get(settings.refresh_cookie_name)
    if refresh_token:
        AuthService(db).logout(refresh_token)
    clear_refresh_cookie(response)
    return MessageResponse(message='Logged out')


@router.get('/google/login')
async def google_login(request: Request):
    if not hasattr(oauth, 'google'):
        raise AppError('Google OAuth is not configured', 500)
    return await oauth.google.authorize_redirect(request, settings.google_redirect_uri)


@router.get('/google/callback')
async def google_callback(request: Request, db: Session = Depends(get_db)):
    if not hasattr(oauth, 'google'):
        raise AppError('Google OAuth is not configured', 500)

    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get('userinfo')
    if not userinfo:
        userinfo = await oauth.google.parse_id_token(request, token)

    email = userinfo.get('email')
    sub = userinfo.get('sub')
    name = userinfo.get('name') or email
    if not email or not sub:
        raise UnauthorizedError('Invalid Google identity payload')

    tokens = AuthService(db).oauth_login_or_register(provider=AuthProvider.GOOGLE, email=email, name=name, provider_id=sub)
    redirect = RedirectResponse(url=f"{settings.frontend_url}/oauth/success")
    set_refresh_cookie(redirect, tokens['refresh_token'])
    return redirect


@router.get('/microsoft/login')
async def microsoft_login(request: Request):
    if not hasattr(oauth, 'microsoft'):
        raise AppError('Microsoft OAuth is not configured', 500)
    return await oauth.microsoft.authorize_redirect(request, settings.microsoft_redirect_uri)


@router.get('/microsoft/callback')
async def microsoft_callback(request: Request, db: Session = Depends(get_db)):
    if not hasattr(oauth, 'microsoft'):
        raise AppError('Microsoft OAuth is not configured', 500)

    # Microsoft `common`/`organizations` authorities can emit tenant-specific `iss`.
    # Pass explicit claims_options to avoid strict issuer equality against metadata issuer.
    token = await oauth.microsoft.authorize_access_token(request, claims_options={})
    userinfo = token.get('userinfo')
    if not userinfo:
        userinfo = await oauth.microsoft.parse_id_token(token, nonce=None, claims_options={})

    email = userinfo.get('email') or userinfo.get('preferred_username')
    sub = userinfo.get('sub') or userinfo.get('oid')
    name = userinfo.get('name') or email
    if not email or not sub:
        raise UnauthorizedError('Invalid Microsoft identity payload')

    tokens = AuthService(db).oauth_login_or_register(provider=AuthProvider.MICROSOFT, email=email, name=name, provider_id=sub)
    redirect = RedirectResponse(url=f"{settings.frontend_url}/oauth/success")
    set_refresh_cookie(redirect, tokens['refresh_token'])
    return redirect
