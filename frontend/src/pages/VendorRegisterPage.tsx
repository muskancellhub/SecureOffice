import { FormEvent, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { AuthShell } from '../components/AuthShell';
import * as authApi from '../api/authApi';
import type { VendorSignupPayload } from '../types/auth';

const US_STATES = [
  'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA',
  'KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ',
  'NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT',
  'VA','WA','WV','WI','WY','DC',
];

const PUBLIC_DOMAINS = ['gmail.com','yahoo.com','hotmail.com','outlook.com','aol.com','icloud.com','mail.com','protonmail.com'];

export const VendorRegisterPage = () => {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  const [form, setForm] = useState<VendorSignupPayload>({
    contact_name: '',
    contact_email: '',
    contact_phone: '',
    password: '',
    company_name: '',
    address_street: '',
    address_city: '',
    address_state: '',
    address_zip: '',
    company_website: '',
    company_email: '',
    federal_tax_id: '',
    bbb_good_standing: false,
    sos_good_standing: false,
    corporate_liable_sales: false,
  });

  const set = (field: keyof VendorSignupPayload, value: string | boolean) =>
    setForm((prev) => ({ ...prev, [field]: value }));

  const validateStep1 = () => {
    if (!form.company_name || !form.address_street || !form.address_city || !form.address_state || !form.address_zip) {
      setError('Please fill in all address fields.');
      return false;
    }
    if (!form.company_website) {
      setError('Company website is required.');
      return false;
    }
    const emailDomain = form.company_email.split('@')[1]?.toLowerCase();
    if (!form.company_email || PUBLIC_DOMAINS.includes(emailDomain)) {
      setError('A corporate email is required (no public domains like gmail.com).');
      return false;
    }
    if (!form.federal_tax_id) {
      setError('Federal Tax ID is required.');
      return false;
    }
    return true;
  };

  const validateStep2 = () => {
    if (!form.bbb_good_standing) {
      setError('BBB good standing is required.');
      return false;
    }
    if (!form.sos_good_standing) {
      setError('Secretary of State good standing is required.');
      return false;
    }
    if (!form.corporate_liable_sales) {
      setError('Corporate liable sales confirmation is required.');
      return false;
    }
    return true;
  };

  const validateStep3 = () => {
    if (!form.contact_name || !form.contact_email || !form.password) {
      setError('Please fill in all required fields.');
      return false;
    }
    if (form.password.length < 6) {
      setError('Password must be at least 6 characters.');
      return false;
    }
    return true;
  };

  const nextStep = () => {
    setError('');
    if (step === 1 && !validateStep1()) return;
    if (step === 2 && !validateStep2()) return;
    setStep((s) => s + 1);
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    if (!validateStep3()) return;
    setLoading(true);
    try {
      await authApi.vendorSignup(form);
      setSuccess(true);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Registration failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <AuthShell title="Application Submitted" subtitle="Your vendor application is under review" showTabs={false}>
        <div className="vendor-success-msg">
          <p>Your vendor account has been created. You can now log in to the vendor portal.</p>
          <button className="primary-btn" onClick={() => navigate('/vendor/login')} style={{ marginTop: 16 }}>
            Go to Vendor Login
          </button>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell title="Become a Vendor" subtitle="Apply to sell on CellHub Marketplace" showTabs={false}>
      <div className="vendor-steps-indicator">
        {[1, 2, 3].map((s) => (
          <span key={s} className={`step-dot ${step === s ? 'active' : ''} ${step > s ? 'done' : ''}`}>
            {step > s ? '\u2713' : s}
          </span>
        ))}
      </div>

      <form className="auth-form vendor-register-form" onSubmit={onSubmit}>
        {step === 1 && (
          <>
            <h3 className="vendor-step-title">Company Information</h3>
            <input type="text" placeholder="Company Name *" value={form.company_name} onChange={(e) => set('company_name', e.target.value)} required />
            <input type="text" placeholder="Street Address (U.S. physical address, no PO Box) *" value={form.address_street} onChange={(e) => set('address_street', e.target.value)} required />
            <div className="vendor-row-2">
              <input type="text" placeholder="City *" value={form.address_city} onChange={(e) => set('address_city', e.target.value)} required />
              <select value={form.address_state} onChange={(e) => set('address_state', e.target.value)} required>
                <option value="">State *</option>
                {US_STATES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <input type="text" placeholder="ZIP Code *" value={form.address_zip} onChange={(e) => set('address_zip', e.target.value)} required maxLength={10} />
            <input type="url" placeholder="Company Website (https://...) *" value={form.company_website} onChange={(e) => set('company_website', e.target.value)} required />
            <input type="email" placeholder="Company Email (no public domains) *" value={form.company_email} onChange={(e) => set('company_email', e.target.value)} required />
            <input type="text" placeholder="Federal Tax ID (EIN) *" value={form.federal_tax_id} onChange={(e) => set('federal_tax_id', e.target.value)} required />
          </>
        )}

        {step === 2 && (
          <>
            <h3 className="vendor-step-title">Compliance & Eligibility</h3>
            <label className="vendor-check-row">
              <input type="checkbox" checked={form.bbb_good_standing} onChange={(e) => set('bbb_good_standing', e.target.checked)} />
              <span>Company is in good standing with the Better Business Bureau (BBB)</span>
            </label>
            <label className="vendor-check-row">
              <input type="checkbox" checked={form.sos_good_standing} onChange={(e) => set('sos_good_standing', e.target.checked)} />
              <span>Business is in good standing with the Secretary of State in the registered state</span>
            </label>
            <label className="vendor-check-row">
              <input type="checkbox" checked={form.corporate_liable_sales} onChange={(e) => set('corporate_liable_sales', e.target.checked)} />
              <span>Corporate liable sales only (no individual sales)</span>
            </label>
          </>
        )}

        {step === 3 && (
          <>
            <h3 className="vendor-step-title">Your Login Credentials</h3>
            <input type="text" placeholder="Full Name *" value={form.contact_name} onChange={(e) => set('contact_name', e.target.value)} required />
            <input type="email" placeholder="Login Email *" value={form.contact_email} onChange={(e) => set('contact_email', e.target.value)} required />
            <input type="tel" placeholder="Phone (optional)" value={form.contact_phone || ''} onChange={(e) => set('contact_phone', e.target.value)} />
            <input type="password" placeholder="Password (min 6 chars) *" value={form.password} onChange={(e) => set('password', e.target.value)} required minLength={6} />
          </>
        )}

        {error && <div className="error-text">{error}</div>}

        <div className="vendor-btn-row">
          {step > 1 && (
            <button className="ghost-btn" type="button" onClick={() => { setError(''); setStep((s) => s - 1); }}>
              Back
            </button>
          )}
          {step < 3 ? (
            <button className="primary-btn" type="button" onClick={nextStep}>
              Continue
            </button>
          ) : (
            <button className="primary-btn" type="submit" disabled={loading}>
              {loading ? 'Submitting...' : 'Submit Application'}
            </button>
          )}
        </div>
      </form>

      <div className="alt-link">
        Already a vendor? <Link to="/vendor/login">Sign in</Link>
      </div>
    </AuthShell>
  );
};
