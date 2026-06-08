import { Building2, CheckCircle2, CreditCard, FileCheck2, ShieldCheck } from 'lucide-react';
import { FormEvent, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import * as commerceApi from '../api/commerceApi';
import { useAuth } from '../context/AuthContext';
import type { OnboardingProfile, ValidationStatus } from '../types/commerce';
import { extractApiError, isValidEmail } from '../utils/extractApiError';

const validationOptions: ValidationStatus[] = ['PENDING', 'VERIFIED', 'FAILED'];

const prettyVal = (s: string): string => s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();

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
  const missingCount = profile?.missing_requirements?.length || 0;
  const completionPct = Math.max(0, Math.min(100, Math.round(((7 - Math.min(7, missingCount)) / 7) * 100)));

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
                <h3><FileCheck2 size={17} /> Compliance validation</h3>
                <span className="onb-step">Step 2</span>
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
                <span className="onb-step">Step 3</span>
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
