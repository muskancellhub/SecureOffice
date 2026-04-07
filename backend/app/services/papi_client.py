import logging
import time

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_token_cache: dict = {"token": None, "expires_at": 0.0}

TOKEN_BUFFER_SECONDS = 60


class PapiAuthError(Exception):
    pass


class PapiRequestError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _get_bearer_token() -> str:
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"]:
        return _token_cache["token"]

    settings = get_settings()
    if not settings.papi_basic_auth_token:
        raise PapiAuthError("PAPI_BASIC_AUTH_TOKEN is not configured")

    url = f"{settings.papi_base_url}/v1/authenticate"
    headers = {
        "Authorization": f"Basic {settings.papi_basic_auth_token}",
        "Accept": "application/json",
    }

    resp = httpx.get(url, headers=headers, timeout=30)
    if resp.status_code != 200:
        body = resp.text[:500]
        raise PapiAuthError(f"PAPI auth failed ({resp.status_code}): {body}")

    data = resp.json()
    token = data.get("authToken")
    expires_in = int(data.get("ExpiresIn", 900))
    if not token:
        raise PapiAuthError("PAPI auth response missing authToken")

    _token_cache["token"] = token
    _token_cache["expires_at"] = now + expires_in - TOKEN_BUFFER_SECONDS
    logger.info("PAPI token acquired, expires in %ds", expires_in)
    return token


def invalidate_token():
    _token_cache["token"] = None
    _token_cache["expires_at"] = 0.0


def fetch_catalog_products(
    *,
    eip: bool = True,
    classic: bool = True,
    include_rate_plans: bool = False,
    sort_by: str = "price-high-low",
    page_size: int = 100,
    page_number: int = 1,
) -> dict:
    """Fetch a page of products from the PAPI catalog API."""
    settings = get_settings()
    token = _get_bearer_token()

    url = f"{settings.papi_base_url}/v1/catalog/products"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    payload = {
        "eip": eip,
        "classic": classic,
        "includeRatePlans": include_rate_plans,
        "sortBy": sort_by,
        "pageSize": page_size,
        "pageNumber": page_number,
    }

    resp = httpx.post(url, headers=headers, json=payload, timeout=60)

    if resp.status_code == 401:
        invalidate_token()
        token = _get_bearer_token()
        headers["Authorization"] = f"Bearer {token}"
        resp = httpx.post(url, headers=headers, json=payload, timeout=60)

    if resp.status_code != 200:
        body = resp.text[:500]
        raise PapiRequestError(
            f"PAPI catalog request failed ({resp.status_code}): {body}",
            status_code=resp.status_code,
        )

    return resp.json()


def fetch_all_products(
    *,
    eip: bool = True,
    classic: bool = True,
    page_size: int = 100,
    max_pages: int = 20,
) -> list[dict]:
    """Paginate through all PAPI products and return the merged Product list."""
    all_products: list[dict] = []
    for page in range(1, max_pages + 1):
        data = fetch_catalog_products(
            eip=eip,
            classic=classic,
            page_size=page_size,
            page_number=page,
        )
        products = data.get("Product") or data.get("product") or []
        all_products.extend(products)
        logger.info(
            "PAPI page %d: got %d products (total so far: %d)",
            page,
            len(products),
            len(all_products),
        )
        if data.get("endOfResult", True):
            break
    return all_products
