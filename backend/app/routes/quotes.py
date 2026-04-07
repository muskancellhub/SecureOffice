from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.middleware.dependencies import get_current_user
from app.schemas.orders import OrderDetailResponse, OrderLineResponse
from app.schemas.quotes import (
    CreateQuoteRequest,
    PreviewQuoteRequest,
    QuoteDetailResponse,
    QuoteIdResponse,
    QuoteLineResponse,
    QuotePricingPreviewResponse,
    QuoteSummaryResponse,
)
from app.services.pricing_service import PricingService
from app.services.quote_service import QuoteService

router = APIRouter(prefix='/quotes', tags=['Quotes'])


def _serialize_quote_line(line) -> QuoteLineResponse:
    billing_value = line.billing_type.value if hasattr(line.billing_type, 'value') else str(line.billing_type)
    return QuoteLineResponse(
        id=str(line.id),
        quote_id=str(line.quote_id),
        line_type=line.line_type.value if hasattr(line.line_type, 'value') else str(line.line_type),
        catalog_item_id=str(line.catalog_item_id) if line.catalog_item_id else None,
        name_snapshot=line.name_snapshot,
        sku_snapshot=line.sku_snapshot,
        vendor_snapshot=line.vendor_snapshot,
        qty=line.qty,
        list_price_snapshot=float(line.list_price_snapshot),
        final_unit_price_snapshot=float(line.final_unit_price_snapshot),
        unit_price=float(line.final_unit_price_snapshot),
        billing_type=billing_value,
        billing=billing_value,
        interval=line.interval.value if line.interval else None,
        metadata=line.metadata_json or {},
        parent_line_id=str(line.parent_line_id) if line.parent_line_id else None,
        created_at=line.created_at,
    )


def _serialize_quote(db: Session, quote) -> QuoteDetailResponse:
    customer_pricing = PricingService(db).get_or_create_customer_pricing(str(quote.tenant_id))
    default_discount_pct = float(customer_pricing.default_discount_pct)
    incremental_discount_pct = float(quote.deal_pricing.incremental_discount_pct) if quote.deal_pricing else 0.0

    return QuoteDetailResponse(
        id=str(quote.id),
        public_id=quote.public_id,
        tenant_id=str(quote.tenant_id),
        created_by_user_id=str(quote.created_by_user_id),
        created_by=str(quote.created_by_user_id),
        status=quote.status.value if hasattr(quote.status, 'value') else str(quote.status),
        one_time_total=float(quote.one_time_total),
        monthly_total=float(quote.monthly_total),
        projected_12_month_cost=float(quote.projected_12_month_cost),
        currency=quote.currency,
        default_discount_pct=default_discount_pct,
        incremental_discount_pct=incremental_discount_pct,
        created_at=quote.created_at,
        updated_at=quote.updated_at,
        lines=[_serialize_quote_line(line) for line in quote.lines],
    )


def _serialize_order(order) -> OrderDetailResponse:
    return OrderDetailResponse(
        id=str(order.id),
        public_id=order.public_id,
        tenant_id=str(order.tenant_id),
        created_by_user_id=str(order.created_by_user_id),
        created_by=str(order.created_by_user_id),
        quote_id=str(order.quote_id) if order.quote_id else None,
        quote_public_id=order.quote.public_id if getattr(order, 'quote', None) else None,
        status=order.status.value if hasattr(order.status, 'value') else str(order.status),
        estimated_delivery_date=order.estimated_delivery_date,
        confirmed_delivery_date=order.confirmed_delivery_date,
        created_at=order.created_at,
        updated_at=order.updated_at,
        lines=[
            OrderLineResponse(
                id=str(line.id),
                order_id=str(line.order_id),
                line_type=line.line_type.value if hasattr(line.line_type, 'value') else str(line.line_type),
                catalog_item_id=str(line.catalog_item_id) if line.catalog_item_id else None,
                name=line.name_snapshot,
                sku=line.sku_snapshot,
                vendor=line.vendor_snapshot,
                qty=line.qty,
                list_price_snapshot=float(line.list_price_snapshot),
                final_unit_price_snapshot=float(line.final_unit_price_snapshot),
                unit_price=float(line.final_unit_price_snapshot),
                billing_type=line.billing_type.value if hasattr(line.billing_type, 'value') else str(line.billing_type),
                billing=line.billing_type.value if hasattr(line.billing_type, 'value') else str(line.billing_type),
                interval=line.interval.value if line.interval else None,
                metadata=line.metadata_json or {},
                parent_line_id=str(line.parent_line_id) if line.parent_line_id else None,
                created_at=line.created_at,
            )
            for line in order.lines
        ],
    )


@router.post('/preview', response_model=QuotePricingPreviewResponse)
def preview_quote(
    payload: PreviewQuoteRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    preview = QuoteService(db).preview_quote(current_user, payload.draft_solution.model_dump())
    return QuotePricingPreviewResponse(**preview)


@router.post('', response_model=QuoteIdResponse)
def create_quote(
    payload: CreateQuoteRequest | None = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    quote = QuoteService(db).create_quote(current_user, payload.model_dump() if payload else None)
    return QuoteIdResponse(quote_id=str(quote.id), quote_public_id=quote.public_id)


@router.post('/generate', response_model=QuoteIdResponse)
def generate_quote_compat(
    payload: CreateQuoteRequest | None = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    quote = QuoteService(db).create_quote(current_user, payload.model_dump() if payload else None)
    return QuoteIdResponse(quote_id=str(quote.id), quote_public_id=quote.public_id)


@router.get('', response_model=list[QuoteSummaryResponse])
def list_quotes(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    quotes = QuoteService(db).list_quotes(current_user)
    customer_pricing = PricingService(db).get_or_create_customer_pricing(current_user['tenant_id'])
    default_discount_pct = float(customer_pricing.default_discount_pct)
    db.commit()

    return [
        QuoteSummaryResponse(
            id=str(quote.id),
            public_id=quote.public_id,
            tenant_id=str(quote.tenant_id),
            created_by_user_id=str(quote.created_by_user_id),
            created_by=str(quote.created_by_user_id),
            status=quote.status.value if hasattr(quote.status, 'value') else str(quote.status),
            one_time_total=float(quote.one_time_total),
            monthly_total=float(quote.monthly_total),
            projected_12_month_cost=float(quote.projected_12_month_cost),
            currency=quote.currency,
            default_discount_pct=default_discount_pct,
            incremental_discount_pct=float(quote.deal_pricing.incremental_discount_pct) if quote.deal_pricing else 0.0,
            created_at=quote.created_at,
            updated_at=quote.updated_at,
        )
        for quote in quotes
    ]


@router.get('/{quote_id}', response_model=QuoteDetailResponse)
def get_quote(quote_id: str, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    quote = QuoteService(db).get_quote(current_user, quote_id)
    return _serialize_quote(db, quote)


@router.post('/{quote_id}/send', response_model=QuoteDetailResponse)
def send_quote(quote_id: str, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    quote = QuoteService(db).send_quote(current_user, quote_id)
    return _serialize_quote(db, quote)


@router.post('/{quote_id}/accept', response_model=QuoteDetailResponse)
def accept_quote(quote_id: str, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    quote = QuoteService(db).accept_quote(current_user, quote_id)
    return _serialize_quote(db, quote)


@router.post('/{quote_id}/convert', response_model=OrderDetailResponse)
def convert_quote(quote_id: str, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    _, order = QuoteService(db).convert_quote(current_user, quote_id)
    return _serialize_order(order)
