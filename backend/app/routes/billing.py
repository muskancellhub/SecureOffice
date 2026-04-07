from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.permissions import PERM_MANAGE_BILLING, PERM_VIEW_BILLING
from app.middleware.dependencies import get_current_user
from app.schemas.billing import (
    BillingMonthPointResponse,
    BillingOverviewResponse,
    BillingTotalsResponse,
    InvoiceResponse,
    PaymentResponse,
    RecordPaymentRequest,
    RunInvoicingRequest,
)
from app.services.billing_service import BillingService
from app.services.authorization_service import AuthorizationService

router = APIRouter(prefix='/billing', tags=['Billing'])


def _serialize_payment(payment) -> PaymentResponse:
    return PaymentResponse(
        id=str(payment.id),
        tenant_id=str(payment.tenant_id),
        invoice_id=str(payment.invoice_id),
        amount=float(payment.amount),
        currency=payment.currency,
        status=payment.status.value if hasattr(payment.status, 'value') else str(payment.status),
        method=payment.method.value if hasattr(payment.method, 'value') else str(payment.method),
        external_reference=payment.external_reference,
        paid_at=payment.paid_at,
        metadata=payment.metadata_json or {},
        created_at=payment.created_at,
    )


def _serialize_invoice(invoice) -> InvoiceResponse:
    return InvoiceResponse(
        id=str(invoice.id),
        tenant_id=str(invoice.tenant_id),
        subscription_id=str(invoice.subscription_id) if invoice.subscription_id else None,
        billing_month=invoice.billing_month,
        amount=float(invoice.amount),
        currency=invoice.currency,
        status=invoice.status.value if hasattr(invoice.status, 'value') else str(invoice.status),
        due_date=invoice.due_date,
        issued_at=invoice.issued_at,
        paid_at=invoice.paid_at,
        metadata=invoice.metadata_json or {},
        created_at=invoice.created_at,
        updated_at=invoice.updated_at,
        payments=[_serialize_payment(payment) for payment in invoice.payments or []],
    )


@router.get('/overview', response_model=BillingOverviewResponse)
def get_billing_overview(
    months_back: int = 12,
    months_forward: int = 12,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    AuthorizationService(db).require(current_user, PERM_VIEW_BILLING)
    data = BillingService(db).get_billing_overview(current_user, months_back=months_back, months_forward=months_forward)
    return BillingOverviewResponse(
        past_months=[
            BillingMonthPointResponse(
                month=row['month'],
                one_time_total=float(row['one_time_total']),
                recurring_total=float(row['recurring_total']),
                total=float(row['total']),
            )
            for row in data['past_months']
        ],
        projected_months=[
            BillingMonthPointResponse(
                month=row['month'],
                one_time_total=float(row['one_time_total']),
                recurring_total=float(row['recurring_total']),
                total=float(row['total']),
            )
            for row in data['projected_months']
        ],
        totals=BillingTotalsResponse(
            one_time_last_12_months=float(data['totals']['one_time_last_12_months']),
            recurring_last_12_months=float(data['totals']['recurring_last_12_months']),
            projected_next_12_months=float(data['totals']['projected_next_12_months']),
            current_monthly_recurring=float(data['totals']['current_monthly_recurring']),
        ),
    )


@router.get('/invoices', response_model=list[InvoiceResponse])
def list_invoices(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    AuthorizationService(db).require(current_user, PERM_VIEW_BILLING)
    rows = BillingService(db).list_invoices(current_user)
    return [_serialize_invoice(row) for row in rows]


@router.post('/invoices/run', response_model=list[InvoiceResponse])
def run_invoicing(
    payload: RunInvoicingRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    AuthorizationService(db).require(current_user, PERM_MANAGE_BILLING)
    rows = BillingService(db).run_monthly_invoicing(current_user, billing_month=payload.billing_month)
    return [_serialize_invoice(row) for row in rows]


@router.post('/invoices/{invoice_id}/payments', response_model=PaymentResponse)
def record_payment(
    invoice_id: str,
    payload: RecordPaymentRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    AuthorizationService(db).require(current_user, PERM_MANAGE_BILLING)
    _, payment = BillingService(db).record_payment(
        current_user,
        invoice_id,
        amount=payload.amount,
        method=payload.method,
        external_reference=payload.external_reference,
    )
    return _serialize_payment(payment)
