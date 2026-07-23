import { Building2, CheckCircle2, CreditCard, FileCheck2, MapPin, ShieldCheck, Users } from 'lucide-react';
import { FormEvent, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import * as commerceApi from '../api/commerceApi';
import { useAuth } from '../context/AuthContext';
import type { Address, OnboardingProfile, ValidationStatus } from '../types/commerce';
import { extractApiError, isValidEmail } from '../utils/extractApiError';

const validationOptions: ValidationStatus[] = ['PENDING', 'VERIFIED', 'FAILED'];

const prettyVal = (s: string): string => s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();

// "2026-07-22T14:03:00Z" → "Jul 22, 2026, 2:03 PM" (locale-aware); '' if unparseable.
const formatUpdated = (iso?: string | null): string => {
  if (!iso) return '';
  const d = new Date(iso);
  return isNaN(d.getTime()) ? '' : d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
};

const US_STATES = [
  'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA', 'HI', 'ID', 'IL', 'IN', 'IA',
  'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
  'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT',
  'VA', 'WA', 'WV', 'WI', 'WY', 'DC', 'PR', 'VI', 'GU', 'AS', 'MP',
];

const EMPTY_ADDRESS: Address = { line1: '', line2: '', city: '', state: '', postal_code: '', country: 'US' };

// Mirror of the backend AddressInput rules: a blank address is allowed (onboarding
// stays incomplete), but any partially-filled address must be complete + valid.
const validateAddress = (a: Address, label: string): string => {
  const filled = [a.line1, a.line2, a.city, a.state, a.postal_code].some((v) => (v || '').trim());
  if (!filled) return '';
  const missing: string[] = [];
  if (!(a.line1 || '').trim()) missing.push('street address');
  if (!(a.city || '').trim()) missing.push('city');
  if (!(a.state || '').trim()) missing.push('state');
  if (!(a.postal_code || '').trim()) missing.push('ZIP code');
  if (missing.length) return `${label} is incomplete — please provide: ${missing.join(', ')}`;
  if (!US_STATES.includes((a.state || '').toUpperCase())) return `${label}: state must be a valid 2-letter US state code`;
  if (!/^\d{5}(-\d{4})?$/.test((a.postal_code || '').trim())) return `${label}: ZIP code must be 5 digits or ZIP+4 (e.g. 07030 or 07030-1234)`;
  return '';
};

export const OnboardingPage = () => {
  const navigate = useNavigate();
  const { accessToken, refreshMe } = useAuth();
  const [profile, setProfile] = useState<OnboardingProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [validatingPayment, setValidatingPayment] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const [organizationName, setOrganizationName] = useState('');
  const [adminName, setAdminName] = useState('');
  const [adminEmail, setAdminEmail] = useState('');
  const [adminPhone, setAdminPhone] = useState('');
  const [creditStatus, setCreditStatus] = useState<ValidationStatus>('PENDING');
  const [taxStatus, setTaxStatus] = useState<ValidationStatus>('PENDING');
  const [dunsNumber, setDunsNumber] = useState('');
  const [taxId, setTaxId] = useState('');
  const [companySetupCompleted, setCompanySetupCompleted] = useState(false);
  const [paymentMethodSetup, setPaymentMethodSetup] = useState(false);
  const [paymentMethodType, setPaymentMethodType] = useState<'CARD' | 'BANK_TRANSFER' | 'MANUAL'>('CARD');
  const [paymentLast4, setPaymentLast4] = useState('');
  const [opsAddress, setOpsAddress] = useState<Address>({ ...EMPTY_ADDRESS });
  const [billingSame, setBillingSame] = useState(true);
  const [billingAddress, setBillingAddress] = useState<Address>({ ...EMPTY_ADDRESS });
  const missingCount = profile?.missing_requirements?.length || 0;
  const TOTAL_REQUIREMENTS = 8;
  const completionPct = Math.max(0, Math.min(100, Math.round(((TOTAL_REQUIREMENTS - Math.min(TOTAL_REQUIREMENTS, missingCount)) / TOTAL_REQUIREMENTS) * 100)));

  const loadProfile = async () => {
    if (!accessToken) return;
    setLoading(true);
    setError('');
    try {
      const data = await commerceApi.getOnboardingProfile(accessToken);
      setProfile(data);
      setOrganizationName(data.organization_name || '');
      setAdminName(data.admin_name || '');
      setAdminEmail(data.admin_email || '');
      setAdminPhone(data.admin_phone || '');
      setCreditStatus(data.credit_validation_status);
      setTaxStatus(data.tax_validation_status);
      setDunsNumber(data.duns_number || '');
      setTaxId(data.tax_id || '');
      setCompanySetupCompleted(Boolean(data.company_setup_completed));
      setPaymentMethodSetup(Boolean(data.payment_method_setup));
      setPaymentMethodType((data.payment_method_type as any) || 'CARD');
      setPaymentLast4(data.payment_method_last4 || '');
      setOpsAddress({ ...EMPTY_ADDRESS, ...(data.operations_address || {}) });
      setBillingSame(data.billing_same_as_operations ?? true);
      setBillingAddress({ ...EMPTY_ADDRESS, ...(data.billing_address || {}) });
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to load onboarding profile'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProfile();
  }, [accessToken]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(''), 2000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const onSave = async (e: FormEvent) => {
    e.preventDefault();
    if (!accessToken) return;
    if (adminEmail && !isValidEmail(adminEmail)) { setError('Please enter a valid admin email address'); return; }
    const opsErr = validateAddress(opsAddress, 'Operations address');
    if (opsErr) { setError(opsErr); return; }
    if (!billingSame) {
      const billErr = validateAddress(billingAddress, 'Billing address');
      if (billErr) { setError(billErr); return; }
    }
    setSaving(true);
    setError('');
    setNotice('');
    try {
      const updated = await commerceApi.updateOnboardingProfile(accessToken, {
        organization_name: organizationName,
        admin_name: adminName,
        admin_email: adminEmail || undefined,
        admin_phone: adminPhone || undefined,
        credit_validation_status: creditStatus,
        tax_validation_status: taxStatus,
        duns_number: dunsNumber || undefined,
        tax_id: taxId || undefined,
        company_setup_completed: companySetupCompleted,
        payment_method_setup: paymentMethodSetup,
        operations_address: opsAddress,
        billing_same_as_operations: billingSame,
        billing_address: billingSame ? undefined : billingAddress,
      });
      setProfile(updated);
      await refreshMe();
      setNotice(updated.onboarding_completed ? 'Onboarding completed. Dashboard unlocked.' : 'Onboarding saved.');
      if (updated.onboarding_completed) {
        navigate('/shop/dashboard', { replace: true });
      }
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to save onboarding'));
    } finally {
      setSaving(false);
    }
  };

  const onValidatePayment = async () => {
    if (!accessToken) return;
    setValidatingPayment(true);
    setError('');
    setNotice('');
    try {
      const updated = await commerceApi.validatePaymentMethod(accessToken, {
        payment_method_type: paymentMethodType,
        last4: paymentLast4 || undefined,
        external_reference: `onboarding-${Date.now()}`,
      });
      setProfile(updated);
      setPaymentMethodSetup(true);
      setNotice('Payment method validated. Checkout can proceed.');
    } catch (err: any) {
      setError(extractApiError(err, 'Payment validation failed'));
    } finally {
      setValidatingPayment(false);
    }
  };

  const renderAddressFields = (addr: Address, setAddr: React.Dispatch<React.SetStateAction<Address>>) => (
    <div className="onb-fields">
      <label className="apx-field"><span>Street address</span>
        <input value={addr.line1 || ''} onChange={(e) => setAddr((p) => ({ ...p, line1: e.target.value }))} placeholder="123 Main St" /></label>
      <label className="apx-field"><span>Suite / unit (optional)</span>
        <input value={addr.line2 || ''} onChange={(e) => setAddr((p) => ({ ...p, line2: e.target.value }))} placeholder="Suite 200" /></label>
      <label className="apx-field"><span>City</span>
        <input value={addr.city || ''} onChange={(e) => setAddr((p) => ({ ...p, city: e.target.value }))} placeholder="Newark" /></label>
      <label className="apx-field"><span>State</span>
        <select value={(addr.state || '').toUpperCase()} onChange={(e) => setAddr((p) => ({ ...p, state: e.target.value }))}>
          <option value="">Select…</option>
          {US_STATES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select></label>
      <label className="apx-field"><span>ZIP code</span>
        <input value={addr.postal_code || ''} onChange={(e) => setAddr((p) => ({ ...p, postal_code: e.target.value.replace(/[^\d-]/g, '').slice(0, 10) }))} placeholder="07102" inputMode="numeric" /></label>
    </div>
  );

  return (
    <section className="content-wrap fade-in onb-page">
      <header className="apx-header">
        <div className="apx-header-text">
          <span className="apx-eyebrow"><ShieldCheck size={15} /> Workspace setup</span>
          <h1>Organization onboarding</h1>
          <p className="apx-subtitle">Configure compliance, billing, and admin ownership before procurement goes live.</p>
        </div>
      </header>

      {loading && <div className="onboarding-alert info">Loading onboarding data…</div>}
      {error && <div className="onboarding-alert error">{error}</div>}
      {notice && <div className="onboarding-alert success">{notice}</div>}

      {!loading && (
        <>
          {/* BUG-ONB-007: onboarding is tenant-scoped, so pre-filled values are
              SHARED company data (saved by a teammate or earlier session) — not
              something the current design generated. Say so explicitly and show
              when it was last touched, so it can't be mistaken for fresh output. */}
          <div className="onb-shared-note">
            <Users size={16} />
            <div>
              <strong>Shared company information.</strong> This onboarding profile is saved at the
              organization level — everyone in {organizationName || 'your company'} sees and edits the
              same data, so anything already filled in was entered by a teammate or a previous session.
              Saving here updates the shared values for the whole company.
              {formatUpdated(profile?.updated_at) && (
                <span className="onb-updated"> Last updated {formatUpdated(profile?.updated_at)}.</span>
              )}
            </div>
          </div>

          <div className="apx-stats onb-stats">
            <article className="apx-stat">
              <div className="apx-stat-head"><span>Completion</span><span className="apx-stat-icon green"><CheckCircle2 size={16} /></span></div>
              <div className="apx-stat-value">{completionPct}%</div>
            </article>
            <article className="apx-stat">
              <div className="apx-stat-head"><span>Missing checks</span><span className="apx-stat-icon amber"><FileCheck2 size={16} /></span></div>
              <div className="apx-stat-value">{missingCount}</div>
            </article>
            <article className="apx-stat">
              <div className="apx-stat-head"><span>Status</span><span className="apx-stat-icon blue"><ShieldCheck size={16} /></span></div>
              <div className="apx-stat-value apx-stat-text">{profile?.onboarding_completed ? 'Ready' : 'Pending'}</div>
            </article>
          </div>

          <form className="onb-grid" onSubmit={onSave}>
            <article className="apx-table-card onb-card">
              <div className="onb-card-head">
                <h3><Building2 size={17} /> Company setup</h3>
                <span className="onb-step">Step 1</span>
              </div>
              <div className="onb-fields">
                <label className="apx-field"><span>Organization name</span>
                  <input value={organizationName} onChange={(e) => setOrganizationName(e.target.value)} placeholder="Secure AI Office LLC" required /></label>
                <label className="apx-field"><span>Admin name</span>
                  <input value={adminName} onChange={(e) => setAdminName(e.target.value)} placeholder="Primary admin contact" required /></label>
                <label className="apx-field"><span>Admin email</span>
                  <input type="email" value={adminEmail} onChange={(e) => setAdminEmail(e.target.value)} placeholder="admin@company.com" required /></label>
                <label className="apx-field"><span>Admin phone</span>
                  <input value={adminPhone} onChange={(e) => setAdminPhone(e.target.value)} placeholder="+1…" /></label>
              </div>
              <label className="onb-toggle">
                <input type="checkbox" checked={companySetupCompleted} onChange={(e) => setCompanySetupCompleted(e.target.checked)} />
                <span>Basic company setup completed</span>
              </label>
            </article>

            <article className="apx-table-card onb-card">
              <div className="onb-card-head">
                <h3><MapPin size={17} /> Business address</h3>
                <span className="onb-step">Step 2</span>
              </div>
              <p className="apx-modal-sub" style={{ marginTop: 0 }}>Where your business operates — used for fulfillment and billing.</p>
              {renderAddressFields(opsAddress, setOpsAddress)}
              <label className="onb-toggle">
                <input type="checkbox" checked={billingSame} onChange={(e) => setBillingSame(e.target.checked)} />
                <span>Billing address is the same as the operations address</span>
              </label>
              {!billingSame && (
                <>
                  <p className="apx-modal-sub" style={{ marginTop: 0 }}>Billing address</p>
                  {renderAddressFields(billingAddress, setBillingAddress)}
                </>
              )}
            </article>

            <article className="apx-table-card onb-card">
              <div className="onb-card-head">
                <h3><FileCheck2 size={17} /> Compliance validation</h3>
                <span className="onb-step">Step 3</span>
              </div>
              <div className="onb-fields">
                <label className="apx-field"><span>DUNS number</span>
                  <input value={dunsNumber} onChange={(e) => setDunsNumber(e.target.value)} placeholder="Optional if Tax ID exists" /></label>
                <label className="apx-field"><span>Tax ID</span>
                  <input value={taxId} onChange={(e) => setTaxId(e.target.value)} placeholder="Optional if DUNS exists" /></label>
                <label className="apx-field"><span>Credit validation</span>
                  <select value={creditStatus} onChange={(e) => setCreditStatus(e.target.value as ValidationStatus)}>
                    {validationOptions.map((s) => <option key={s} value={s}>{prettyVal(s)}</option>)}
                  </select></label>
                <label className="apx-field"><span>DUNS / Tax validation</span>
                  <select value={taxStatus} onChange={(e) => setTaxStatus(e.target.value as ValidationStatus)}>
                    {validationOptions.map((s) => <option key={s} value={s}>{prettyVal(s)}</option>)}
                  </select></label>
              </div>
            </article>

            <article className="apx-table-card onb-card">
              <div className="onb-card-head">
                <h3><CreditCard size={17} /> Payment setup</h3>
                <span className="onb-step">Step 4</span>
              </div>
              <label className="onb-toggle">
                <input type="checkbox" checked={paymentMethodSetup} onChange={(e) => setPaymentMethodSetup(e.target.checked)} />
                <span>Payment method captured during onboarding</span>
              </label>
              <div className="onb-fields">
                <label className="apx-field"><span>Method type</span>
                  <select value={paymentMethodType} onChange={(e) => setPaymentMethodType(e.target.value as any)}>
                    <option value="CARD">Card</option>
                    <option value="BANK_TRANSFER">Bank transfer</option>
                    <option value="MANUAL">Manual</option>
                  </select></label>
                <label className="apx-field"><span>Last 4 (optional)</span>
                  <input value={paymentLast4} onChange={(e) => setPaymentLast4(e.target.value.replace(/\D/g, '').slice(0, 4))} placeholder="1234" /></label>
              </div>
              <button type="button" className="dnb-tool-btn" onClick={onValidatePayment} disabled={validatingPayment}>
                {validatingPayment ? 'Validating…' : 'Validate payment for checkout'}
              </button>
              <div className="onb-chips">
                <span className={`onb-chip ${(profile?.payment_validation_status || 'PENDING').toLowerCase()}`}>Payment: {prettyVal(profile?.payment_validation_status || 'PENDING')}</span>
                <span className={`onb-chip ${creditStatus.toLowerCase()}`}>Credit: {prettyVal(creditStatus)}</span>
                <span className={`onb-chip ${taxStatus.toLowerCase()}`}>Tax: {prettyVal(taxStatus)}</span>
              </div>
            </article>

            <article className="apx-table-card onb-card onb-card-full">
              <div className="onb-card-head">
                <h3><ShieldCheck size={17} /> Completion status</h3>
                <span className="onb-step">Final</span>
              </div>
              <p className="apx-modal-sub" style={{ marginTop: 0 }}>
                {profile?.onboarding_completed ? 'Onboarding complete — your workspace is ready.' : 'Onboarding incomplete. Remaining requirements are listed below.'}
              </p>
              <ul className="onb-reqs">
                {(profile?.missing_requirements || []).map((item) => (
                  <li key={item} className="missing"><span className="onb-req-dot" /> {item}</li>
                ))}
                {(profile?.missing_requirements || []).length === 0 && (
                  <li className="done"><CheckCircle2 size={15} /> All onboarding requirements satisfied.</li>
                )}
              </ul>
              <div className="onb-actions">
                <button className="apx-add-btn" type="submit" disabled={saving}>
                  {saving ? 'Saving…' : 'Save onboarding'}
                </button>
                {profile?.onboarding_completed && (
                  <button className="dnb-tool-btn" type="button" onClick={() => navigate('/shop/dashboard')}>Go to dashboard</button>
                )}
                <button
                  className="dnb-tool-btn"
                  type="button"
                  onClick={() => { window.localStorage.setItem('so2_onboarding_skip', '1'); navigate('/shop/dashboard'); }}
                >
                  Skip for now
                </button>
              </div>
            </article>
          </form>
        </>
      )}
    </section>
  );
};
