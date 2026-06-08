"""Seed two sample customer tenants for manual / pricing testing.

Creates tenant1 + tenant2, each with a verified user (email + password),
completed onboarding, and a customer_pricing row. Gives tenant1 a per-tenant
price override on the MIX 90X1 so the two tenants see DIFFERENT prices for the
same product. Prints login credentials + a fresh OTP per user.

Run:  cd backend && .venv/bin/python -m scripts.seed_test_tenants
Idempotent: re-running reuses the same tenants/users and re-issues OTPs.

This is a DEV helper — it writes to whatever DATABASE_URL points at.
"""
from __future__ import annotations

import uuid

import app.models  # noqa: F401  (register models)
from app.core.database import SessionLocal, Base, engine
from app.core.permissions import default_permissions_for_role
from app.core.runtime_migrations import apply_runtime_migrations
from app.core.security import hash_value
from app.models.onboarding import TenantOnboarding
from app.models.otp import OTP
from app.models.pricing import CustomerPricing
from app.models.product import Product
from app.models.tenant import Tenant, TenantType
from app.models.user import AuthProvider, User, UserRole, UserType
from app.services.catalog_service import CatalogService
from app.services.component_pricing_service import ComponentPricingService
from app.services.otp_service import OTPService
from app.services.product_admin_service import ProductAdminService
from sqlalchemy import select

PASSWORD = 'Password123!'

# Customer companies (NOT CellHub — CellHub is the operator tenant, VENDOR = suppliers).
TENANTS = [
    {'name': 'Company1', 'email': 'company1@example.com', 'override_margin': 0.40},
    {'name': 'Company2', 'email': 'company2@example.com', 'override_margin': None},
]


def _get_or_create_tenant(db, name):
    t = db.scalar(select(Tenant).where(Tenant.name == name))
    if t is None:
        t = Tenant(id=uuid.uuid4(), name=name, tenant_type=TenantType.COMPANY)
        db.add(t)
    t.tenant_type = TenantType.COMPANY
    db.flush()
    return t


def _get_or_create_user(db, email, name, tenant_id):
    u = db.scalar(select(User).where(User.email == email))
    if u is None:
        u = User(id=uuid.uuid4(), email=email, name=name, tenant_id=tenant_id)
        db.add(u)
    u.password_hash = hash_value(PASSWORD)
    u.provider = AuthProvider.LOCAL
    u.is_verified = True
    u.role = UserRole.USER
    u.user_type = UserType.COMPANY
    u.permissions = default_permissions_for_role(UserRole.USER)
    db.flush()
    return u


def _ensure_onboarding(db, tenant_id, name, email):
    ob = db.get(TenantOnboarding, tenant_id)
    if ob is None:
        ob = TenantOnboarding(tenant_id=tenant_id)
        db.add(ob)
    ob.organization_name = name
    ob.admin_name = name
    ob.admin_email = email
    ob.tax_id = f'TAX-{name.replace(" ", "")}'
    ob.credit_validation_status = 'VERIFIED'
    ob.tax_validation_status = 'VERIFIED'
    ob.company_setup_completed = True
    ob.payment_validation_status = 'VERIFIED'
    ob.onboarding_completed = True
    db.flush()


def _ensure_pricing(db, tenant_id):
    cp = db.get(CustomerPricing, tenant_id)
    if cp is None:
        cp = CustomerPricing(tenant_id=tenant_id)
        db.add(cp)
    cp.opex_eligible = True
    db.flush()


def _issue_otp(db, user_id) -> str:
    code = OTPService.generate_otp()
    db.add(OTP(
        user_id=user_id, code_hash=OTPService.hash_otp(code),
        expires_at=OTPService.otp_expiry(), used=False, attempts_remaining=5,
    ))
    db.flush()
    return code


def main():
    apply_runtime_migrations()
    Base.metadata.create_all(bind=engine)

    creds = []
    with SessionLocal() as db:
        CatalogService(db).seed_mix_products()
        x1 = db.scalar(select(Product).where(Product.sku == '90X1'))
        admin = ProductAdminService(db)

        for spec in TENANTS:
            t = _get_or_create_tenant(db, spec['name'])
            u = _get_or_create_user(db, spec['email'], spec['name'], t.id)
            _ensure_onboarding(db, t.id, spec['name'], spec['email'])
            _ensure_pricing(db, t.id)
            if spec['override_margin'] is not None:
                admin.upsert_price_override(t.id, {
                    'product_id': str(x1.id), 'override_margin_pct': spec['override_margin'],
                })
            otp = _issue_otp(db, u.id)
            creds.append((spec['name'], spec['email'], str(t.id), otp))
        db.commit()

        # Demonstrate per-tenant differentiation on the same product (90X1 CAPEX).
        print('\n================  LOGIN CREDENTIALS  ================')
        print(f'Password (both): {PASSWORD}')
        for name, email, tid, otp in creds:
            print(f'  {name}: {email}   tenant_id={tid}   OTP={otp} (valid 5 min)')

        print('\n================  PER-TENANT PRICE TEST (90X1, CAPEX)  ================')
        cps = ComponentPricingService(db)
        for name, email, tid, _ in creds:
            r = cps.price_product(x1.id, financial_model='CAPEX', interval='MONTH', tenant_id=tid)
            device = next(l for l in r['lines'] if l['component_type'] == 'DEVICE')
            print(f'  {name}: 90X1 device = ${device["unit_price"]}  '
                  f'(margin {device["margin_pct"]} via {device["margin_source"]})  '
                  f'| one-time total ${r["one_time_total"]}')


if __name__ == '__main__':
    main()
