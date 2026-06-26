"""Per-tenant PII encryption — crypto unit tests + DB integration (docs/PII_ENCRYPTION.md §12).

The DB tests skip without Postgres. They assert the three things that matter:
  * PII is ciphertext *at rest* (raw SQL sees ``v1:...``) but plaintext through
    the repositories/services that read it.
  * Tenant isolation: a value encrypted for tenant A cannot be decrypted in
    tenant B's context (wrong DEK and/or wrong AAD).
  * The backfill is idempotent.
"""
import uuid

import pytest

from app.core import crypto
from app.core.config import Settings, get_settings

settings = get_settings()

PFX = 'PIIENC-'
RUN = uuid.uuid4().hex[:8]


# ── Pure crypto (no DB) ─────────────────────────────────────────────────────

def test_field_roundtrip():
    dek = crypto.generate_dek()
    blob = crypto.encrypt_field('Jane Q. Public', dek, 'tenant-a')
    assert blob.startswith('v1:') and blob.count(':') == 3
    assert crypto.decrypt_field(blob, dek, 'tenant-a') == 'Jane Q. Public'


def test_wrong_tenant_aad_raises():
    dek = crypto.generate_dek()
    blob = crypto.encrypt_field('555-0100', dek, 'tenant-a')
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt_field(blob, dek, 'tenant-b')


def test_wrong_key_raises():
    blob = crypto.encrypt_field('secret', crypto.generate_dek(), 'tenant-a')
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt_field(blob, crypto.generate_dek(), 'tenant-a')


def test_tamper_detected():
    dek = crypto.generate_dek()
    blob = crypto.encrypt_field('do-not-modify', dek, 'tenant-a')
    # Flip the last base64 char of the ciphertext segment.
    flipped = blob[:-1] + ('A' if blob[-1] != 'A' else 'B')
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt_field(flipped, dek, 'tenant-a')


def test_unique_iv_per_encryption():
    dek = crypto.generate_dek()
    a = crypto.encrypt_field('same', dek, 't')
    b = crypto.encrypt_field('same', dek, 't')
    assert a != b  # fresh IV each time -> different ciphertext for identical input


def test_dek_wrap_roundtrip():
    kek = crypto.generate_dek()  # any 32 bytes
    dek = crypto.generate_dek()
    assert crypto.unwrap_dek(crypto.wrap_dek(dek, kek), kek) == dek


def test_is_encrypted():
    assert crypto.is_encrypted('v1:a:b:c')
    assert not crypto.is_encrypted('plaintext')
    assert not crypto.is_encrypted(None)


def test_malformed_blob_raises():
    dek = crypto.generate_dek()
    for bad in ('', 'not-a-blob', 'v2:a:b:c', 'v1:only:three'):
        with pytest.raises(crypto.CryptoError):
            crypto.decrypt_field(bad, dek, 't')


def test_fail_fast_missing_master_key():
    s = Settings(MASTER_ENCRYPTION_KEY='')
    with pytest.raises(RuntimeError):
        s.master_encryption_key_bytes()


def test_fail_fast_wrong_length_master_key():
    import base64
    short = base64.b64encode(b'too-short').decode()
    with pytest.raises(RuntimeError):
        Settings(MASTER_ENCRYPTION_KEY=short).master_encryption_key_bytes()


# ── DB integration ──────────────────────────────────────────────────────────

@pytest.fixture(scope='module')
def db_factory():
    from sqlalchemy import text
    from app.core.database import engine, SessionLocal, Base
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
    except Exception as exc:  # pragma: no cover
        pytest.skip(f'No reachable database: {exc}')

    import app.models  # noqa: F401 — registers models + before_flush listener
    from app.core.runtime_migrations import apply_runtime_migrations
    Base.metadata.create_all(bind=engine)
    apply_runtime_migrations()

    yield SessionLocal

    with SessionLocal() as db:
        rows = db.execute(
            text("SELECT id FROM tenants WHERE name LIKE :p"), {'p': f'{PFX}%'}
        ).fetchall()
        for r in rows:
            t = str(r.id)
            db.execute(text("DELETE FROM payments WHERE tenant_id = :t"), {'t': t})
            db.execute(text("DELETE FROM invoices WHERE tenant_id = :t"), {'t': t})
            db.execute(text("DELETE FROM assets WHERE tenant_id = :t"), {'t': t})
            db.execute(text("DELETE FROM users WHERE tenant_id = :t"), {'t': t})
            db.execute(text("DELETE FROM vendors WHERE tenant_id = :t"), {'t': t})
            db.execute(text("DELETE FROM tenant_onboarding WHERE tenant_id = :t"), {'t': t})
            # tenant_keys cascade-deletes with the tenant.
            db.execute(text("DELETE FROM tenants WHERE id = :t"), {'t': t})
        db.commit()


def _make_tenant(db, label='Tenant'):
    from app.models.tenant import Tenant
    t = Tenant(id=uuid.uuid4(), name=f'{PFX}{label}-{uuid.uuid4().hex[:6]}')
    db.add(t)
    db.flush()
    return t.id


def _raw(db, sql, **params):
    from sqlalchemy import text
    return db.execute(text(sql), params).first()


def test_user_pii_encrypted_at_rest_and_plaintext_via_repo(db_factory):
    from app.models.user import User, UserRole
    from app.repositories.user_repository import UserRepository

    with db_factory() as db:
        tid = _make_tenant(db)
        u = User(id=uuid.uuid4(), email=f'enc-{uuid.uuid4().hex[:8]}@x.local',
                 name='Alice Encrypted', mobile='+1-555-0142',
                 tenant_id=tid, role=UserRole.USER, is_verified=True, password_hash='x')
        db.add(u)
        db.commit()
        uid = u.id

        # At rest: raw SQL must see ciphertext, never the plaintext.
        row = _raw(db, "SELECT name, mobile FROM users WHERE id = :i", i=str(uid))
        assert row.name.startswith('v1:') and row.mobile.startswith('v1:')
        assert 'Alice Encrypted' not in row.name

        # Through the repository: plaintext.
        fetched = UserRepository(db).get_by_id(str(uid))
        assert fetched.name == 'Alice Encrypted'
        assert fetched.mobile == '+1-555-0142'

        # A DEK was provisioned for the tenant, stored wrapped.
        key_row = _raw(db, "SELECT wrapped_dek FROM tenant_keys WHERE tenant_id = :t", t=str(tid))
        assert key_row is not None and key_row.wrapped_dek.startswith('v1:')


def test_null_pii_stays_null(db_factory):
    from app.models.user import User, UserRole
    with db_factory() as db:
        tid = _make_tenant(db)
        u = User(id=uuid.uuid4(), email=f'nul-{uuid.uuid4().hex[:8]}@x.local',
                 name='No Mobile', mobile=None,
                 tenant_id=tid, role=UserRole.USER, is_verified=True, password_hash='x')
        db.add(u)
        db.commit()
        row = _raw(db, "SELECT mobile FROM users WHERE id = :i", i=str(u.id))
        assert row.mobile is None


def test_onboarding_pii_roundtrip(db_factory):
    from app.models.onboarding import TenantOnboarding
    from app.repositories.onboarding_repository import OnboardingRepository

    with db_factory() as db:
        tid = _make_tenant(db)
        ob = TenantOnboarding(tenant_id=tid, admin_name='Bob Boss',
                              admin_email='bob@corp.local', admin_phone='555-0199',
                              tax_id='12-3456789', duns_number='987654321')
        db.add(ob)
        db.commit()

        row = _raw(db, "SELECT admin_name, tax_id, organization_name FROM tenant_onboarding "
                       "WHERE tenant_id = :t", t=str(tid))
        assert row.admin_name.startswith('v1:') and row.tax_id.startswith('v1:')

        fetched = OnboardingRepository(db).get_by_tenant_id(tid)
        assert fetched.admin_name == 'Bob Boss'
        assert fetched.tax_id == '12-3456789'
        assert fetched.duns_number == '987654321'


def test_asset_pii_roundtrip(db_factory):
    from app.models.lifecycle import Asset, AssetStatus
    from app.core.encryption import EncryptionService

    with db_factory() as db:
        tid = _make_tenant(db)
        a = Asset(id=uuid.uuid4(), tenant_id=tid, name='Router-1', asset_type='device',
                  status=AssetStatus.ACTIVE, serial_number='SN-AAA-111', location='Rack 4B')
        db.add(a)
        db.commit()
        aid = a.id

        row = _raw(db, "SELECT serial_number, location FROM assets WHERE id = :i", i=str(aid))
        assert row.serial_number.startswith('v1:') and row.location.startswith('v1:')

        db.expire(a)
        EncryptionService(db).decrypt_instance(a)
        assert a.serial_number == 'SN-AAA-111' and a.location == 'Rack 4B'


def test_vendor_federal_tax_id_encrypted(db_factory):
    from app.models.vendor import Vendor
    with db_factory() as db:
        tid = _make_tenant(db, 'VendorTenant')
        v = Vendor(id=uuid.uuid4(), tenant_id=tid, company_name=f'{PFX}Vend',
                   address_street='1 St', address_city='C', address_state='ST',
                   address_zip='00000', company_website='https://x.local',
                   company_email='v@x.local', federal_tax_id='99-8887777')
        db.add(v)
        db.commit()
        row = _raw(db, "SELECT federal_tax_id FROM vendors WHERE id = :i", i=str(v.id))
        assert row.federal_tax_id.startswith('v1:')


def test_payment_external_reference_NOT_encrypted(db_factory):
    """external_reference is deliberately excluded from v1 — it's queried by exact
    match in the Stripe idempotency check, so it must stay plaintext (§4)."""
    from app.models.lifecycle import Invoice, InvoiceStatus, Payment, PaymentStatus, PaymentMethod
    from datetime import date
    with db_factory() as db:
        tid = _make_tenant(db, 'PayTenant')
        inv = Invoice(id=uuid.uuid4(), tenant_id=tid, billing_month=date.today(),
                      amount=10, due_date=date.today(), status=InvoiceStatus.PAID)
        db.add(inv)
        db.flush()
        p = Payment(id=uuid.uuid4(), tenant_id=tid, invoice_id=inv.id, amount=10,
                    status=PaymentStatus.SUCCEEDED, method=PaymentMethod.STRIPE,
                    external_reference='pi_test_12345')
        db.add(p)
        db.commit()
        row = _raw(db, "SELECT external_reference FROM payments WHERE id = :i", i=str(p.id))
        assert row.external_reference == 'pi_test_12345'  # plaintext, queryable


def test_cross_tenant_decrypt_fails(db_factory):
    """A user's ciphertext, reinterpreted under a different tenant, must not
    decrypt — the DEK and the AAD both differ."""
    from app.models.user import User, UserRole
    from app.core.encryption import EncryptionService
    with db_factory() as db:
        tid_a = _make_tenant(db, 'A')
        tid_b = _make_tenant(db, 'B')
        u = User(id=uuid.uuid4(), email=f'x-{uuid.uuid4().hex[:8]}@x.local',
                 name='Carol Cross', tenant_id=tid_a,
                 role=UserRole.USER, is_verified=True, password_hash='x')
        db.add(u)
        db.commit()
        # Pull the raw ciphertext, then attempt to decrypt it as if it belonged to B.
        row = _raw(db, "SELECT name FROM users WHERE id = :i", i=str(u.id))
        EncryptionService(db).provision_tenant(tid_b)  # ensure B has its own DEK
        u.name = row.name              # ciphertext from A
        u.tenant_id = tid_b            # pretend it's B's
        with pytest.raises(crypto.CryptoError):
            EncryptionService(db).decrypt_instance(u)


def test_backfill_idempotent(db_factory):
    from sqlalchemy import text
    from app.models.user import User, UserRole
    from app.core.encryption import EncryptionService
    from scripts.backfill_pii_encryption import backfill_tenant

    with db_factory() as db:
        tid = _make_tenant(db, 'Backfill')
        uid = uuid.uuid4()
        u = User(id=uid, email=f'bf-{uuid.uuid4().hex[:8]}@x.local', name='Temp',
                 tenant_id=tid, role=UserRole.USER, is_verified=True, password_hash='x')
        db.add(u)
        db.commit()
        # Simulate a legacy plaintext row by writing plaintext directly (bypassing ORM).
        db.execute(text("UPDATE users SET name = :n, mobile = :m WHERE id = :i"),
                   {'n': 'Legacy Plain', 'm': '555-0000', 'i': str(uid)})
        db.commit()

        enc = EncryptionService(db)
        counts1 = backfill_tenant(db, enc, tid, dry_run=False)
        db.commit()
        assert counts1.get('users', 0) == 2  # name + mobile encrypted

        row = _raw(db, "SELECT name FROM users WHERE id = :i", i=str(uid))
        assert row.name.startswith('v1:')

        # Second pass is a no-op (already v1:).
        counts2 = backfill_tenant(db, enc, tid, dry_run=False)
        db.commit()
        assert counts2.get('users', 0) == 0
