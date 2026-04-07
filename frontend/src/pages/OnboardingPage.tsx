import { Building2, CheckCircle2, CreditCard, FileCheck2, ShieldCheck } from 'lucide-react';
import { FormEvent, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import * as commerceApi from '../api/commerceApi';
import { useAuth } from '../context/AuthContext';
import type { OnboardingProfile, ValidationStatus } from '../types/commerce';

const validationOptions: ValidationStatus[] = ['PENDING', 'VERIFIED', 'FAILED'];

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
      setError(err?.response?.data?.detail || 'Failed to load onboarding profile');
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
      setError(err?.response?.data?.detail || 'Failed to save onboarding');
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
      setError(err?.response?.data?.detail || 'Payment validation failed');
    } finally {
      setValidatingPayment(false);
    }
  };

  return (
    <section className="content-wrap fade-in onboarding-page">
      <div className="onboarding-hero row-between">
        <div className="onboarding-hero-copy">
          <p className="onboarding-eyebrow">Enterprise Setup</p>
          <h1>Organization Onboarding</h1>
          <p className="lead">Configure compliance, billing, and admin ownership before procurement workflows go live.</p>
        </div>
        <div className="onboarding-stats">
          <div className="onboarding-stat">
            <span>Completion</span>
            <strong>{completionPct}%</strong>
          </div>
          <div className="onboarding-stat">
            <span>Missing Checks</span>
            <strong>{missingCount}</strong>
          </div>
          <div className="onboarding-stat">
            <span>Status</span>
            <strong>{profile?.onboarding_completed ? 'Ready' : 'Pending'}</strong>
          </div>
        </div>
      </div>

      {loading && <div className="onboarding-alert info">Loading onboarding data...</div>}
      {error && <div className="onboarding-alert error">{error}</div>}
      {notice && <div className="onboarding-alert success">{notice}</div>}

      {!loading && (
        <form className="onboarding-grid" onSubmit={onSave}>
          <article className="onboarding-card">
            <div className="onboarding-card-head">
              <h3><Building2 size={16} /> Company Setup</h3>
              <span className="section-step">Step 1</span>
            </div>
            <div className="onboarding-input-grid">
              <label className="field-label">
                Organization Name
                <input value={organizationName} onChange={(e) => setOrganizationName(e.target.value)} placeholder="SecureOffice LLC" required />
              </label>
              <label className="field-label">
                Admin Name
                <input value={adminName} onChange={(e) => setAdminName(e.target.value)} placeholder="Primary admin contact" required />
              </label>
            </div>
            <div className="onboarding-input-grid">
              <label className="field-label">
                Admin Email
                <input type="email" value={adminEmail} onChange={(e) => setAdminEmail(e.target.value)} placeholder="admin@company.com" required />
              </label>
              <label className="field-label">
                Admin Phone
                <input value={adminPhone} onChange={(e) => setAdminPhone(e.target.value)} placeholder="+1..." />
              </label>
            </div>
            <label className="toggle-row">
              <input type="checkbox" checked={companySetupCompleted} onChange={(e) => setCompanySetupCompleted(e.target.checked)} />
              <span>Basic company setup completed</span>
            </label>
          </article>

          <article className="onboarding-card">
            <div className="onboarding-card-head">
              <h3><FileCheck2 size={16} /> Compliance Validation</h3>
              <span className="section-step">Step 2</span>
            </div>
            <div className="onboarding-input-grid">
              <label className="field-label">
                DUNS Number
                <input value={dunsNumber} onChange={(e) => setDunsNumber(e.target.value)} placeholder="Optional if Tax ID exists" />
              </label>
              <label className="field-label">
                Tax ID
                <input value={taxId} onChange={(e) => setTaxId(e.target.value)} placeholder="Optional if DUNS exists" />
              </label>
            </div>
            <div className="onboarding-input-grid">
              <label className="field-label">
                Credit Validation
                <select value={creditStatus} onChange={(e) => setCreditStatus(e.target.value as ValidationStatus)}>
                  {validationOptions.map((status) => (
                    <option key={status} value={status}>{status}</option>
                  ))}
                </select>
              </label>
              <label className="field-label">
                DUNS / Tax Validation
                <select value={taxStatus} onChange={(e) => setTaxStatus(e.target.value as ValidationStatus)}>
                  {validationOptions.map((status) => (
                    <option key={status} value={status}>{status}</option>
                  ))}
                </select>
              </label>
            </div>
          </article>

          <article className="onboarding-card">
            <div className="onboarding-card-head">
              <h3><CreditCard size={16} /> Payment Setup</h3>
              <span className="section-step">Step 3</span>
            </div>
            <label className="toggle-row">
              <input type="checkbox" checked={paymentMethodSetup} onChange={(e) => setPaymentMethodSetup(e.target.checked)} />
              <span>Payment method captured during onboarding</span>
            </label>
            <div className="onboarding-input-grid">
              <label className="field-label">
                Method Type
                <select value={paymentMethodType} onChange={(e) => setPaymentMethodType(e.target.value as any)}>
                  <option value="CARD">Card</option>
                  <option value="BANK_TRANSFER">Bank Transfer</option>
                  <option value="MANUAL">Manual</option>
                </select>
              </label>
              <label className="field-label">
                Last 4 (optional)
                <input value={paymentLast4} onChange={(e) => setPaymentLast4(e.target.value.replace(/\D/g, '').slice(0, 4))} placeholder="1234" />
              </label>
            </div>
            <button type="button" className="secondary-btn" onClick={onValidatePayment} disabled={validatingPayment}>
              {validatingPayment ? 'Validating...' : 'Validate Payment for Checkout'}
            </button>
            <div className="onboarding-status-strip">
              <span className={`status-chip ${(profile?.payment_validation_status || 'PENDING').toLowerCase()}`}>
                Payment: {profile?.payment_validation_status || 'PENDING'}
              </span>
              <span className={`status-chip ${creditStatus.toLowerCase()}`}>Credit: {creditStatus}</span>
              <span className={`status-chip ${taxStatus.toLowerCase()}`}>Tax: {taxStatus}</span>
            </div>
          </article>

          <article className="onboarding-card full">
            <div className="onboarding-card-head">
              <h3><ShieldCheck size={16} /> Completion Status</h3>
              <span className="section-step">Final</span>
            </div>
            <p className="mini-note">
              {profile?.onboarding_completed ? 'Onboarding complete' : 'Onboarding incomplete. Missing requirements are listed below.'}
            </p>
            <ul className="plain-bullets">
              {(profile?.missing_requirements || []).map((item) => (
                <li key={item}>{item}</li>
              ))}
              {(profile?.missing_requirements || []).length === 0 && (
                <li><CheckCircle2 size={14} /> All onboarding requirements satisfied.</li>
              )}
            </ul>
            <div className="step-nav-row onboarding-actions">
              <button className="primary-btn" type="submit" disabled={saving}>
                {saving ? 'Saving...' : 'Save Onboarding'}
              </button>
              {profile?.onboarding_completed && (
                <button className="secondary-btn" type="button" onClick={() => navigate('/shop/dashboard')}>
                  Go to Dashboard
                </button>
              )}
              <button
                className="ghost-btn"
                type="button"
                onClick={() => {
                  window.localStorage.setItem('so2_onboarding_skip', '1');
                  navigate('/shop/dashboard');
                }}
              >
                Skip to Dashboard
              </button>
            </div>
          </article>
        </form>
      )}
    </section>
  );
};
