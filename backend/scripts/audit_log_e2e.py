"""Comprehensive logging-system test: static catalog coverage + live E2E + line validation.

Safety: no emails (no signup/invite/real-OTP/design-submit), no Stripe API calls
(signature-failure webhook only), no Anam calls, fixture designs untouched
(creates+deletes its own), throwaway DB rows named TEST-AUDIT-*.
"""
import datetime
import pathlib
import re
import sys
import time

BACKEND = pathlib.Path('/Users/muskan/SecureOffice2/backend')

# ── Part A: static coverage — every catalog event has an emit site ───────────
CATALOG = """
user_signup vendor_signup user_login user_logout otp_requested otp_verified token_refresh
oauth_login super_admin_setup_link_sent super_admin_credentials_changed user_login_failed
otp_verify_failed user_created user_invited user_role_changed user_permissions_changed
user_list_viewed permission_catalog_viewed billing_overview_viewed tenant_list_viewed
cart_item_added cart_item_updated cart_item_removed service_attached_to_device
quote_created quote_updated quote_sent quote_accepted quote_converted
order_placed order_status_changed order_delivery_date_set notification_recipients_changed
design_saved design_submitted design_status_changed design_note_added design_deleted
design_milestones_updated design_install_assistance_updated design_managed_services_updated
invoices_generated payment_recorded stripe_checkout_created stripe_webhook_received
customer_discount_changed deal_discount_applied service_price_updated bulk_price_update
financing_terms_created customer_commercial_changed price_override_created
product_created product_updated component_created component_updated bundle_created bundle_item_added
cdw_sync_triggered papi_sync_triggered excel_sync_triggered bom_generated topology_generated
designx_bom_suggested subscription_status_changed workflow_advanced onboarding_updated
payment_method_validated zabbix_credentials_updated access_denied rate_limit_exceeded server_error
""".split()

emitted_in_code = set()
for py in BACKEND.glob('app/**/*.py'):
    text = py.read_text()
    for first_arg in re.findall(r"audit\.log\(\s*([^,]+),", text, re.S):
        emitted_in_code.update(re.findall(r"'([a-z_]+)'", first_arg))

missing = [e for e in CATALOG if e not in emitted_in_code]
extra = sorted(e for e in emitted_in_code if e not in CATALOG)
print(f'=== STATIC COVERAGE: {len(CATALOG) - len(missing)}/{len(CATALOG)} catalog events have emit sites ===')
if missing:
    print('MISSING EMIT SITES:', missing)
if extra:
    print('emit sites not in catalog (should be none):', extra)

# ── Part B: live E2E ─────────────────────────────────────────────────────────
import os
os.chdir(BACKEND)
sys.path.insert(0, str(BACKEND))

from starlette.testclient import TestClient
import app.main as m
from app.models.product import ComponentType

# temp route to exercise the unhandled-exception hook safely
@m.app.get('/test-boom')
def boom():
    raise RuntimeError('intentional test explosion')

# fresh logs for this run
for f in ('logs/dev/app.log', 'logs/dev/audit.log'):
    open(f, 'w').close()

TS = str(int(time.time()))
FUTURE = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
SA_EMAIL, C1_EMAIL, PW = 'muskan.d@cellhubms.com', 'muskan.d@enidususa.com', 'Password123!'

sa = TestClient(m.app, raise_server_exceptions=False)
c1 = TestClient(m.app, raise_server_exceptions=False)

results = []  # (scenario, ok, note)

def run(name, fn):
    try:
        note = fn() or ''
        results.append((name, True, note))
    except Exception as exc:
        results.append((name, False, f'{type(exc).__name__}: {exc}'))

def login(client, email, pw):
    r = client.post('/auth/login', json={'email': email, 'password': pw})
    assert r.status_code == 200, f'login {email}: {r.status_code} {r.text[:120]}'
    return {'Authorization': f"Bearer {r.json()['access_token']}"}

def expect(r, code, what=''):
    assert r.status_code == code, f'{what}: got {r.status_code} {r.text[:150]}'
    return r

# -- auth events --
run('user_login_failed (bad password)', lambda: expect(sa.post('/auth/login', json={'email': SA_EMAIL, 'password': 'WrongPass999!'}), 401).and_none if False else expect(sa.post('/auth/login', json={'email': SA_EMAIL, 'password': 'WrongPass999!'}), 401) and None)
run('user_login_failed (unknown user)', lambda: expect(sa.post('/auth/login', json={'email': 'ghost-test-audit@example.com', 'password': 'xxxxxxxxxx'}), 401) and None)
SA = {}
C1 = {}
run('user_login (super admin)', lambda: SA.update(login(sa, SA_EMAIL, PW)))
run('user_login (company1 admin)', lambda: C1.update(login(c1, C1_EMAIL, PW)))
run('otp_requested (unknown email, skipped path)', lambda: expect(sa.post('/auth/login/otp/request', json={'email': 'probe-test-audit@example.com'}), 200) and None)
run('token_refresh', lambda: expect(sa.post('/auth/refresh'), 200) and None)

# -- audited reads + access_denied --
run('tenant_list_viewed', lambda: expect(sa.get('/tenants', headers=SA), 200) and None)
run('access_denied (company1 admin hits /tenants)', lambda: expect(c1.get('/tenants', headers=C1), 403) and None)
run('user_list_viewed', lambda: expect(sa.get('/users', headers=SA), 200) and None)
run('permission_catalog_viewed', lambda: expect(sa.get('/users/permissions/catalog', headers=SA), 200) and None)
run('billing_overview_viewed', lambda: expect(c1.get('/billing/overview', headers=C1), 200) and None)

# -- user management --
STATE = {}
def create_user():
    r = expect(sa.post('/users', headers=SA, json={
        'email': f'test-audit-{TS}@example.com', 'name': 'Audit Test User',
        'password': 'Aud1t-Test-Pass!', 'role': 'USER'}), 200, 'create user')
    STATE['uid'] = r.json()['id']
run('user_created', create_user)
run('user_permissions_changed', lambda: expect(sa.patch(f"/users/{STATE['uid']}/permissions", headers=SA, json={'permissions': []}), 200) and None)
run('user_role_changed', lambda: expect(sa.patch(f"/users/{STATE['uid']}/role", headers=SA, json={'role': 'ADMIN'}), 200) and None)

# -- cart (company1) --
def cart_flow():
    items = expect(c1.get('/catalog', headers=C1), 200).json()
    device = next(i for i in items if i.get('type') == 'DEVICE' and i.get('is_active', True))
    STATE['device_id'] = device['id']
    r = expect(c1.post('/cart/lines', headers=C1, json={'catalog_item_id': device['id'], 'quantity': 1}), 200, 'add line')
    line = next(l for l in r.json()['lines'] if l['catalog_item_id'] == device['id'])
    expect(c1.patch(f"/cart/lines/{line['id']}", headers=C1, json={'quantity': 3}), 200, 'update line')
    expect(c1.delete(f"/cart/lines/{line['id']}", headers=C1), 200, 'remove line')
    return f"device={device['sku']}"
run('cart_item_added/updated/removed', cart_flow)

# -- designs (own throwaway design; fixture designs untouched) --
def design_flow():
    # clean up leftovers from prior aborted runs first
    for d in expect(c1.get('/designs', headers=C1), 200).json():
        name = d.get('design_name') or d.get('designName') or ''
        if name.startswith('TEST-AUDIT-'):
            c1.delete(f"/designs/{d['id']}", headers=C1)
    r = expect(c1.post('/designs', headers=C1, json={'designName': f'TEST-AUDIT-{TS}'}), 200, 'save design')
    did = r.json()['id']
    STATE['design_id'] = did
    # note/milestones/status need manage_lifecycle — super admin (cross-tenant by design)
    expect(sa.post(f'/designs/{did}/updates', headers=SA,
                   json={'update': {'message': 'audit e2e note', 'visibility': 'internal'}}), 200, 'note')
    expect(sa.patch(f'/designs/{did}/milestones', headers=SA,
                    json={'milestones': {'estimatedReviewDate': FUTURE}}), 200, 'milestones')
    expect(c1.patch(f'/designs/{did}/install-assistance', headers=C1,
                    json={'install_assistance': {'installMode': 'self_install'}}), 200, 'install')
    expect(c1.put(f'/designs/{did}/managed-services', headers=C1,
                  json={'enabled_categories': [], 'excluded_item_ids': []}), 200, 'managed services')
    expect(sa.patch(f'/designs/{did}/status', headers=SA, json={'status': 'reviewed'}), 200, 'status')
    expect(c1.delete(f'/designs/{did}', headers=C1), 204, 'delete')
run('design_saved/note/milestones/install/managed/status/deleted', design_flow)

# -- product admin / pricing (super admin; throwaway TEST-AUDIT rows) --
def product_flow():
    r = expect(sa.post('/products', headers=SA, json={
        'vendor': 'TESTV', 'technology': 'TESTTECH', 'sku': f'TEST-AUDIT-{TS}',
        'name': 'Audit Test Product'}), 200, 'create product')
    pid = r.json()['id']
    STATE['pid'] = pid
    expect(sa.patch(f'/products/{pid}', headers=SA, json={'description': 'updated by audit e2e'}), 200, 'update product')
    ctype = list(ComponentType)[0].value
    r2 = expect(sa.post(f'/products/{pid}/components', headers=SA, json={
        'component_type': ctype, 'label': 'Audit Test Component', 'vendor_cost': 10}), 200, 'add component')
    cid = r2.json()['id']
    expect(sa.patch(f'/products/components/{cid}', headers=SA, json={'label': 'Audit Test Component v2'}), 200, 'update component')
run('product/component created+updated', product_flow)

def bundle_flow():
    r = expect(sa.post('/bundles', headers=SA, json={'sku': f'TEST-AUDIT-B-{TS}', 'name': 'Audit Bundle'}), 200, 'create bundle')
    expect(sa.post(f"/bundles/{r.json()['id']}/items", headers=SA, json={'product_id': STATE['pid']}), 200, 'add item')
run('bundle_created + bundle_item_added', bundle_flow)

C1_TENANT = '7f959d6b'  # prefix; resolve full id from /users/me
def pricing_flow():
    me = expect(c1.get('/users/me', headers=C1), 200).json()
    tid = me.get('tenant_id') or me.get('user', {}).get('tenant_id')
    expect(sa.put('/pricing/customer', headers=SA, json={'default_discount_pct': 0.25}), 200, 'customer discount')
    expect(sa.post('/pricing/financing-terms', headers=SA, json={'name': f'TEST-AUDIT-{TS}'}), 200, 'financing terms')
    expect(sa.patch(f'/pricing/customers/{tid}/commercial', headers=SA, json={'opex_eligible': True}), 200, 'commercial')
    expect(sa.post(f'/pricing/customers/{tid}/price-overrides', headers=SA,
                   json={'product_id': STATE['pid'], 'override_unit_price': 9.99}), 200, 'override')
run('customer_discount/financing/commercial/price_override', pricing_flow)

# -- catalog managed-service pricing --
def price_flow():
    expect(sa.patch(f"/catalog/devices/{STATE['device_id']}/managed-service-price", headers=SA,
                    json={'managed_service_price': 7.5}), 200, 'single price')
    expect(sa.put('/catalog/devices/managed-service-prices', headers=SA,
                  json={'updates': [{'item_id': STATE['device_id'], 'managed_service_price': 7.5}]}), 200, 'bulk price')
run('service_price_updated + bulk_price_update', price_flow)

# -- billing + orders --
run('invoices_generated', lambda: expect(sa.post('/billing/invoices/run', headers=SA, json={}), 200) and None)
run('notification_recipients_changed', lambda: expect(sa.put('/orders/notifications/recipients', headers=SA,
    json={'recipients': ['ops-test-audit@example.com']}), 200) and None)

# -- security hooks --
run('zabbix_credentials_updated (validation failure, password must not log)',
    lambda: expect(sa.post('/zabbix/config', headers=SA, json={
        'url': 'http://127.0.0.1:9/api_jsonrpc.php', 'username': 'audituser',
        'password': 'SuperSecretZabbix123'}), 400) and None)
run('stripe_webhook_received (bad signature)',
    lambda: expect(sa.post('/billing/stripe/webhook', content=b'{}',
                           headers={'stripe-signature': 't=1,v1=bad'}), 400) and None)
run('server_error (unhandled exception route)', lambda: expect(sa.get('/test-boom'), 500) and None)

# -- logout, then rate-limit flood LAST (poisons the /auth/login bucket) --
run('user_logout', lambda: expect(c1.post('/auth/logout'), 200) and None)
def flood():
    for i in range(14):
        r = sa.post('/auth/login', json={'email': 'flood-test-audit@example.com', 'password': 'x'})
        if r.status_code == 429:
            return f'429 at attempt {i + 1}'
    raise AssertionError('never hit 429')
run('rate_limit_exceeded', flood)

# ── Part C: validate every emitted line ──────────────────────────────────────
LINE_RE = re.compile(
    r'^<(\d{1,3})>1 \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z \S+ secureoffice2 \d+ (\S+) (-|\[.+\]) .*$')
SECRETS = ['Password123!', 'WrongPass999!', 'Aud1t-Test-Pass!', 'SuperSecretZabbix123']

audit_lines = open('logs/dev/audit.log').read().splitlines()
app_lines = open('logs/dev/app.log').read().splitlines()

bad_audit = [l for l in audit_lines if not LINE_RE.match(l)]
bad_pri = [l for l in audit_lines if LINE_RE.match(l) and int(LINE_RE.match(l).group(1)) not in (139, 140, 141, 142)]
bad_app = [l for l in app_lines if not LINE_RE.match(l)]
bad_app_pri = [l for l in app_lines if LINE_RE.match(l) and not (128 <= int(LINE_RE.match(l).group(1)) <= 135)]
leaks = [(s, f) for s in SECRETS for f, lines in (('audit', audit_lines), ('app', app_lines)) for l in lines if s in l]

seen = {}
for l in audit_lines:
    mt = LINE_RE.match(l)
    if mt:
        seen[mt.group(2)] = seen.get(mt.group(2), 0) + 1

print('\n=== E2E SCENARIOS ===')
for name, ok, note in results:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f'  [{note}]' if note else ''))

print(f'\n=== LINE VALIDATION ===')
print(f'  audit.log: {len(audit_lines)} lines, {len(bad_audit)} malformed, {len(bad_pri)} bad PRI')
print(f'  app.log:   {len(app_lines)} lines, {len(bad_app)} malformed, {len(bad_app_pri)} bad PRI')
print(f'  secret leak scan: {"CLEAN" if not leaks else leaks}')
for l in (bad_audit + bad_pri)[:5]:
    print('  BAD:', l[:160])

EXPECTED_LIVE = """user_login user_login_failed otp_requested token_refresh user_logout tenant_list_viewed
access_denied user_list_viewed permission_catalog_viewed billing_overview_viewed user_created
user_permissions_changed user_role_changed cart_item_added cart_item_updated cart_item_removed
design_saved design_note_added design_milestones_updated design_install_assistance_updated
design_managed_services_updated design_status_changed design_deleted product_created product_updated
component_created component_updated bundle_created bundle_item_added customer_discount_changed
financing_terms_created customer_commercial_changed price_override_created service_price_updated
bulk_price_update invoices_generated notification_recipients_changed zabbix_credentials_updated
stripe_webhook_received server_error rate_limit_exceeded http_request""".split()
EXPECTED_LIVE.remove('http_request')

print('\n=== LIVE EVENT COVERAGE (msgid -> count in audit.log) ===')
missed = []
for e in EXPECTED_LIVE:
    n = seen.get(e, 0)
    if n == 0:
        missed.append(e)
    print(f"  {'OK  ' if n else 'MISS'}  {e}: {n}")
unexpected = sorted(k for k in seen if k not in EXPECTED_LIVE)
print('  (other msgids seen:', unexpected or 'none', ')')

live_ok = not missed and not bad_audit and not bad_pri and not bad_app and not bad_app_pri and not leaks
fails = [r for r in results if not r[1]]
print(f'\n=== SUMMARY: static {len(CATALOG)-len(missing)}/{len(CATALOG)} | live events {len(EXPECTED_LIVE)-len(missed)}/{len(EXPECTED_LIVE)} | scenarios {len(results)-len(fails)}/{len(results)} | validation {"PASS" if live_ok else "FAIL"} ===')
