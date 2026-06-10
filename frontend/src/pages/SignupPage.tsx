import { FormEvent, useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { AuthShell } from '../components/AuthShell';
import { useAuth } from '../context/AuthContext';
import { extractApiError, isValidEmail } from '../utils/extractApiError';
import { PhoneInput } from '../components/PhoneInput';

export const SignupPage = () => {
  const { user, loading: authLoading, signup } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const nextParam = new URLSearchParams(location.search).get('next') || '';

  useEffect(() => {
    if (!authLoading && user) {
      const target = nextParam || '/shop';
      navigate(target.startsWith('/') ? target : '/shop', { replace: true });
    }
  }, [authLoading, user, nextParam, navigate]);
  const [name, setName] = useState('');
  const [companyName, setCompanyName] = useState('');
  const [email, setEmail] = useState('');
  const [mobile, setMobile] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  // Free/public email providers are rejected — every account must map to a real
  // company domain (PLAN.md §1). Mirror the backend list for an instant hint.
  const FREE_EMAIL_DOMAINS = [
    'gmail.com', 'googlemail.com', 'outlook.com', 'hotmail.com', 'live.com', 'msn.com',
    'yahoo.com', 'yahoo.co.in', 'ymail.com', 'rocketmail.com', 'icloud.com', 'me.com',
    'mac.com', 'aol.com', 'protonmail.com', 'proton.me', 'pm.me', 'zoho.com', 'gmx.com',
    'gmx.net', 'mail.com', 'yandex.com', 'hey.com', 'fastmail.com', 'tutanota.com', 'tuta.io',
  ];

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!isValidEmail(email)) { setError('Please enter a valid email address'); return; }
    const domain = email.split('@')[1]?.trim().toLowerCase() || '';
    if (FREE_EMAIL_DOMAINS.includes(domain)) {
      setError('Please use your company email address.');
      return;
    }
    if (!companyName.trim()) { setError('Company name is required'); return; }
    setError('');
    setLoading(true);
    try {
      await signup({ name, email, mobile, password, company_name: companyName });
      navigate('/verify-otp', { state: { email, next: nextParam || localStorage.getItem('secureOfficePostAuthRedirect') || '' } });
    } catch (err: any) {
      setError(extractApiError(err, 'Signup failed'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell title="Create Account" subtitle="Sign up to start securing your workspace">
      <form className="auth-form" onSubmit={onSubmit}>
        <input type="text" placeholder="Full Name" value={name} onChange={(e) => setName(e.target.value)} required />
        <input type="text" placeholder="Company Name" value={companyName} onChange={(e) => setCompanyName(e.target.value)} required />
        <input type="email" placeholder="Company Email Address" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <PhoneInput value={mobile} onChange={setMobile} />
        <input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        {error && <div className="error-text">{error}</div>}
        <button className="primary-btn" type="submit" disabled={loading}>{loading ? 'Creating...' : 'Continue'}</button>
      </form>

      <div className="alt-link">Already have an account? <Link to={nextParam ? `/login?next=${encodeURIComponent(nextParam)}` : '/login'}>Sign in</Link></div>
    </AuthShell>
  );
};
