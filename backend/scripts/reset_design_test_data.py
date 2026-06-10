"""Reset the tenant + design data to a clean two-company test fixture.

What it does (idempotent):
  1. Keeps the CellHub master tenant (home of the SUPER_ADMIN operator) and
     ensures the two test COMPANY tenants exist:
        company1  ->  muskan.d@enidususa.com
        company2  ->  dhingramuskan4@gmail.com
  2. Removes EVERY other tenant and all of its dependent rows (users, carts,
     quotes, orders, designs, …) so the environment only contains the three
     tenants above.
  3. Wipes ALL network_designs + design_leads (clean slate for testing).
  4. Seeds 3 designs per company with names in the canonical format
        design{N}-{INITIALS}-{company}-{YYYY-MM-DD}
     (design1 = reviewed/draft-stage, design2 + design3 = submitted so the
     admin design-ops queue has something to show).

Run:  cd backend && .venv/bin/python -m scripts.reset_design_test_data
WARNING: destructive. Point DATABASE_URL at a dev/test database.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

import app.models  # noqa: F401  (register all models)
from app.core.database import SessionLocal, Base, engine
from app.core.permissions import default_permissions_for_role
from app.core.runtime_migrations import apply_runtime_migrations
from app.core.security import hash_value
from app.core.tenancy import CELLHUB_MASTER_TENANT_ID
from app.models.catalog import CatalogItem, CatalogItemType
from app.models.network_design import DesignLead, NetworkDesign, NetworkDesignStatus
from app.models.onboarding import TenantOnboarding
from app.models.tenant import Tenant, TenantType
from app.models.user import AuthProvider, User, UserRole, UserType
from app.services.network_topology_service import NetworkTopologyService
from sqlalchemy import bindparam, func, select, text

PASSWORD = 'Password123!'

# company-slug -> spec. The slug is also the tenant name, so generated design
# names read e.g. "design1-MD-company1-2026-06-09".
COMPANIES = [
    {'slug': 'company1', 'email': 'muskan.d@enidususa.com', 'admin_name': 'Muskan Dhingra'},
    {'slug': 'company2', 'email': 'dhingramuskan4@gmail.com', 'admin_name': 'Muskan Dhingra'},
]

# The global operator (super admin). Homed in the CellHub master tenant so it
# survives the purge (its current home tenant is deleted) and matches the
# documented tenancy model. A password is set so it is login-testable even when
# OTP email delivery is unavailable.
SUPER_ADMIN = {'email': 'muskan.d@cellhubms.com', 'name': 'CellHub Operator'}

# Per-company seed designs: (sequence-status). Names are generated.
SEED_STATUSES = [
    NetworkDesignStatus.REVIEWED,   # design1 — draft-stage, exercises auto-save / "order this design"
    NetworkDesignStatus.SUBMITTED,  # design2 — appears in the admin ops queue
    NetworkDesignStatus.SUBMITTED,  # design3 — appears in the admin ops queue
]


# ──────────────────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────────────────
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _initials(name: str) -> str:
    parts = [p for p in re.split(r'[\s._\-]+', name or '') if p]
    return (''.join(p[0] for p in parts[:2]).upper() or 'XX')


def _design_name(seq: int, name: str, slug: str) -> str:
    return f'design{seq}-{_initials(name)}-{slug}-{_now().strftime("%Y-%m-%d")}'


def _try_exec(db, sql: str, ids: list) -> bool:
    """Execute a DELETE inside a SAVEPOINT so an FK-ordering failure doesn't
    poison the surrounding transaction; returns False if it failed."""
    sp = db.begin_nested()
    try:
        stmt = text(sql).bindparams(bindparam('ids', expanding=True))
        db.execute(stmt, {'ids': ids})
        sp.commit()
        return True
    except Exception:
        sp.rollback()
        return False


def _purge_removed_tenants(db, removed_ids: list[uuid.UUID]) -> None:
    if not removed_ids:
        return

    # 1. child tables that hang off a tenant-scoped parent (no tenant_id of their own)
    child_via_parent = [
        ('cart_lines', 'cart_id', 'carts'),
        ('quote_lines', 'quote_id', 'quotes'),
        ('order_lines', 'order_id', 'orders'),
        ('workflow_steps', 'workflow_instance_id', 'workflow_instances'),
    ]
    for child, fk, parent in child_via_parent:
        _try_exec(
            db,
            f'DELETE FROM {child} WHERE {fk} IN (SELECT id FROM {parent} WHERE tenant_id IN :ids)',
            removed_ids,
        )

    # 2. user-scoped child tables (otps, refresh sessions)
    for child, fk in [('otps', 'user_id'), ('refresh_sessions', 'user_id')]:
        _try_exec(
            db,
            f'DELETE FROM {child} WHERE {fk} IN (SELECT id FROM users WHERE tenant_id IN :ids)',
            removed_ids,
        )

    # 3. every table that carries a tenant_id column — retry to absorb arbitrary
    #    FK ordering between them (e.g. workflow_instances -> orders).
    tenant_tables = [
        r[0]
        for r in db.execute(
            text(
                "SELECT table_name FROM information_schema.columns "
                "WHERE column_name = 'tenant_id' AND table_schema = 'public'"
            )
        )
    ]
    remaining = {t for t in tenant_tables if t not in {'tenants'}}
    for _ in range(12):
        if not remaining:
            break
        progressed = False
        for table in list(remaining):
            if _try_exec(db, f'DELETE FROM {table} WHERE tenant_id IN :ids', removed_ids):
                remaining.discard(table)
                progressed = True
        if not progressed:
            break
    if remaining:
        print(f'  ! could not clear tenant rows from: {sorted(remaining)} (left in place)')

    # 4. finally the users + the tenants themselves
    _try_exec(db, 'DELETE FROM users WHERE tenant_id IN :ids', removed_ids)
    _try_exec(db, 'DELETE FROM tenants WHERE id IN :ids', removed_ids)


def _get_or_create_tenant(db, slug: str) -> Tenant:
    t = db.scalar(select(Tenant).where(func.lower(Tenant.name) == slug.lower()))
    if t is None:
        t = Tenant(id=uuid.uuid4(), name=slug, tenant_type=TenantType.COMPANY)
        db.add(t)
    t.name = slug
    t.tenant_type = TenantType.COMPANY
    db.flush()
    return t


def _get_or_create_user(db, email: str, name: str, tenant_id) -> User:
    u = db.scalar(select(User).where(func.lower(User.email) == email.lower()))
    if u is None:
        u = User(id=uuid.uuid4(), email=email.lower(), name=name, tenant_id=tenant_id)
        db.add(u)
    u.name = name
    u.tenant_id = tenant_id
    u.password_hash = hash_value(PASSWORD)
    u.provider = AuthProvider.LOCAL
    u.provider_id = None  # LOCAL accounts must have a null provider_id (CHECK constraint)
    u.is_verified = True
    u.role = UserRole.USER
    u.user_type = UserType.COMPANY
    u.permissions = default_permissions_for_role(UserRole.USER)
    db.flush()
    return u


def _ensure_super_admin(db, tenant_id) -> User:
    """Ensure the global operator exists in the CellHub master tenant with the
    SUPER_ADMIN role and a usable password. The startup bootstrap only
    *promotes* an existing user, so if the operator's current home tenant is
    purged the account would vanish — this recreates/relocates it safely."""
    email = SUPER_ADMIN['email']
    u = db.scalar(select(User).where(func.lower(User.email) == email.lower()))
    if u is None:
        u = User(id=uuid.uuid4(), email=email.lower(), name=SUPER_ADMIN['name'], tenant_id=tenant_id)
        db.add(u)
    u.name = SUPER_ADMIN['name']
    u.tenant_id = tenant_id
    u.password_hash = hash_value(PASSWORD)
    u.provider = AuthProvider.LOCAL
    u.provider_id = None  # LOCAL accounts must have a null provider_id (CHECK constraint)
    u.is_verified = True
    u.role = UserRole.SUPER_ADMIN
    u.user_type = UserType.CELLHUB
    u.permissions = default_permissions_for_role(UserRole.SUPER_ADMIN)
    db.flush()
    return u


def _ensure_onboarding(db, tenant_id, name: str, email: str) -> None:
    ob = db.get(TenantOnboarding, tenant_id)
    if ob is None:
        ob = TenantOnboarding(tenant_id=tenant_id)
        db.add(ob)
    ob.organization_name = name
    ob.admin_name = email.split('@', 1)[0]
    ob.admin_email = email
    ob.tax_id = f'TAX-{name}'
    ob.credit_validation_status = 'VERIFIED'
    ob.tax_validation_status = 'VERIFIED'
    ob.company_setup_completed = True
    ob.payment_validation_status = 'VERIFIED'
    ob.onboarding_completed = True
    db.flush()


def _pick_devices(db) -> list[CatalogItem]:
    """A small, category-diverse set of real catalog devices so the seeded BOM
    is orderable ('Order this design') and the per-line Edit deep-links resolve
    to real catalog categories."""
    rows = list(
        db.scalars(
            select(CatalogItem)
            .where(CatalogItem.type == CatalogItemType.DEVICE, CatalogItem.is_active.is_(True))
            .limit(80)
        ).all()
    )
    wanted = ['router', 'switch', 'wifi_ap', 'firewall']
    picked: list[CatalogItem] = []
    used: set[str] = set()
    for cat in wanted:
        for r in rows:
            if str((r.attributes or {}).get('category') or '').lower() == cat and str(r.id) not in used:
                picked.append(r)
                used.add(str(r.id))
                break
    # top up to at least 3 lines with any remaining devices
    for r in rows:
        if len(picked) >= 4:
            break
        if str(r.id) not in used:
            picked.append(r)
            used.add(str(r.id))
    return picked[:4]


def _build_bom(devices: list[CatalogItem]) -> tuple[dict, float, int, int]:
    line_items = []
    grand_total = 0.0
    ap_count = 0
    switch_count = 0
    for idx, dev in enumerate(devices):
        category = str((dev.attributes or {}).get('category') or 'router').lower()
        qty = 2 if category in {'wifi_ap', 'switch'} else 1
        unit = float(dev.price or 0)
        total = round(unit * qty, 2)
        grand_total += total
        if category == 'wifi_ap':
            ap_count += qty
        if category == 'switch':
            switch_count += qty
        line_items.append({
            'line_id': f'seed-line-{idx}-{uuid.uuid4().hex[:8]}',
            'item_id': str(dev.id),
            'name': dev.name,
            'sku': dev.sku,
            'vendor': dev.vendor or 'CellHub',
            'category': category,
            'quantity': qty,
            'unit_price': unit,
            'line_total': total,
            'source_type': 'catalog',
            'connectivity': 'wired',
        })
    bom = {
        'line_items': line_items,
        'grand_total': round(grand_total, 2),
        'summary': 'Seeded test bill of materials.',
        'assumptions': ['Seed data for tenant-isolation testing.'],
    }
    return bom, round(grand_total, 2), ap_count, switch_count


def _seed_design(db, *, tenant, user, seq: int, status: NetworkDesignStatus, devices) -> NetworkDesign:
    bom, capex, ap_count, switch_count = _build_bom(devices)
    name = _design_name(seq, user.name, tenant.name)
    now = _now()
    submitted = status not in {NetworkDesignStatus.DRAFT, NetworkDesignStatus.REVIEWED}
    # Generate a real network topology + draw.io diagram from the BOM, the same
    # way the live builder does, so seeded designs render a diagram on the detail
    # page instead of the "No diagram generated yet" empty state.
    artifact = NetworkTopologyService().generate_topology_artifact_from_bom(bom, design_id=None)
    topology = artifact.get('topology') or {}
    drawio_xml = artifact.get('drawioXml')
    design = NetworkDesign(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        created_by_user_id=user.id,
        design_name=name,
        status=status,
        calculator_input_json={'seedScenario': seq},
        calculator_result_json={'summary': {'estimatedCapEx': capex,
                                            'recommendedIndoorAPs': ap_count,
                                            'recommendedSwitches': switch_count}},
        bom_json=bom,
        topology_json=topology,
        drawio_xml=drawio_xml,
        assumptions_json=bom['assumptions'],
        estimate_capex=capex,
        ap_count=ap_count,
        switch_count=switch_count,
        status_updated_at=now,
        submitted_at=now if submitted else None,
        status_history_json=[{
            'status': status.value,
            'changedAt': now.isoformat(),
            'changedBy': user.email,
            'note': None,
        }],
        milestones_json={},
        updates_json=[],
        install_assistance_json={},
        decomposition_json={},
        metadata_json={'source': 'reset_design_test_data'},
    )
    db.add(design)
    db.flush()
    return design


# ──────────────────────────────────────────────────────────────────────────
def main() -> None:
    apply_runtime_migrations()
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        master_id = uuid.UUID(CELLHUB_MASTER_TENANT_ID)
        keep_ids: list[uuid.UUID] = [master_id]

        # 0. ensure the global operator (super admin) is homed in the CellHub
        #    master tenant BEFORE the purge — its current home tenant may be one
        #    of the tenants we are about to delete.
        super_admin = _ensure_super_admin(db, master_id)
        db.flush()

        # 1. ensure the two company tenants + their users
        companies = []
        for spec in COMPANIES:
            tenant = _get_or_create_tenant(db, spec['slug'])
            user = _get_or_create_user(db, spec['email'], spec['admin_name'], tenant.id)
            _ensure_onboarding(db, tenant.id, spec['slug'], spec['email'])
            keep_ids.append(tenant.id)
            companies.append((tenant, user))
        db.flush()

        # 2. remove every other tenant + dependents
        removed_ids = [
            r[0] for r in db.execute(
                text('SELECT id FROM tenants WHERE id NOT IN :ids').bindparams(
                    bindparam('ids', expanding=True)
                ),
                {'ids': keep_ids},
            )
        ]
        if removed_ids:
            print(f'Removing {len(removed_ids)} non-test tenant(s) and their data…')
            _purge_removed_tenants(db, removed_ids)

        # 3. wipe ALL designs / leads (clean slate)
        db.execute(text('DELETE FROM network_designs'))
        db.execute(text('DELETE FROM design_leads'))
        db.flush()

        # 4. seed 3 designs per company
        devices = _pick_devices(db)
        if not devices:
            print('  ! No catalog devices found — seeded BOMs will be empty. '
                  'Run the app once (or scripts.seed_test_tenants) to populate the catalog first.')
        created = []
        for tenant, user in companies:
            for i, status in enumerate(SEED_STATUSES, start=1):
                d = _seed_design(db, tenant=tenant, user=user, seq=i, status=status, devices=devices)
                created.append((tenant.name, d.design_name, status.value))

        db.commit()

        print('\n================  TEST FIXTURE READY  ================')
        print(f'Kept tenants: CellHub (super-admin home) + company1 + company2')
        print(f'Login password (all accounts): {PASSWORD}')
        print(f'  super admin: {super_admin.email}   tenant_id={super_admin.tenant_id} (CellHub master)')
        for spec, (tenant, _user) in zip(COMPANIES, companies):
            print(f'  {tenant.name}: {spec["email"]}   tenant_id={tenant.id}')
        print('\nSeeded designs:')
        for tname, dname, status in created:
            print(f'  [{tname}] {dname}  ({status})')


if __name__ == '__main__':
    main()
