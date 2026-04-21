import { FormEvent, useMemo, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { AuthShell } from '../components/AuthShell';
import { useAuth } from '../context/AuthContext';

export const LoginPage = () => {
  const { requestLoginOtp, verifyLoginOtp, startGoogleSSO, startMicrosoftSSO } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [otp, setOtp] = useState('');
  const [otpRequested, setOtpRequested] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(false);

  const nextRoute = useMemo(() => {
    const queryNext = new URLSearchParams(location.search).get('next');
    const stateNext = typeof location.state === 'object' && location.state && 'from' in location.state
      ? String((location.state as { from?: string }).from || '')
      : '';
    const savedRedirect = localStorage.getItem('secureOfficePostAuthRedirect') || '';
    const target = queryNext || stateNext || savedRedirect || '/shop';
    return target.startsWith('/') ? target : '/shop';
  }, [location.search, location.state]);

  const onRequestOtp = async (e: FormEvent) => {
    e.preventDefault();
    if (!email) return;
    setError('');
    setNotice('');
    setLoading(true);
    try {
      await requestLoginOtp(email);
      setOtpRequested(true);
      setNotice('OTP sent to your email.');
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to send OTP');
    } finally {
      setLoading(false);
    }
  };

  const onVerifyOtp = async (e: FormEvent) => {
    e.preventDefault();
    if (!email || !otp) return;
    setError('');
    setNotice('');
    setLoading(true);
    try {
      await verifyLoginOtp({ email, otp });
      localStorage.removeItem('secureOfficePostAuthRedirect');
      navigate(nextRoute, { replace: true });
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'OTP verification failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell title="Welcome Back" subtitle="Sign in with OTP sent to your email">
      {!otpRequested ? (
        <form className="auth-form" onSubmit={onRequestOtp}>
          <input type="email" placeholder="Email Address" value={email} onChange={(e) => setEmail(e.target.value)} required />
          {notice && <div className="mini-note">{notice}</div>}
          {error && <div className="error-text">{error}</div>}
          <button className="primary-btn" type="submit" disabled={loading}>
            {loading ? 'Sending OTP...' : 'Send OTP'}
          </button>
        </form>
      ) : (
        <form className="auth-form" onSubmit={onVerifyOtp}>
          <input type="email" placeholder="Email Address" value={email} onChange={(e) => setEmail(e.target.value)} required />
          <input
            type="text"
            placeholder="6-digit OTP"
            value={otp}
            onChange={(e) => setOtp(e.target.value)}
            pattern="\d{6}"
            maxLength={6}
            required
          />
          {notice && <div className="mini-note">{notice}</div>}
          {error && <div className="error-text">{error}</div>}
          <button className="primary-btn" type="submit" disabled={loading}>
            {loading ? 'Verifying...' : 'Verify & Continue'}
          </button>
          <button className="ghost-btn" type="button" onClick={() => setOtpRequested(false)} disabled={loading}>
            Change Email
          </button>
        </form>
      )}

      <div className="divider"><span>Or Continue With</span></div>
      <div className="social-row">
        <button className="social-btn" type="button" onClick={() => { localStorage.setItem('secureOfficePostAuthRedirect', nextRoute); startGoogleSSO(); }} aria-label="Continue with Google">
          <svg width="20" height="20" viewBox="0 0 48 48" aria-hidden="true">
            <path fill="#EA4335" d="M24 9.5c3.54 0 6.72 1.22 9.23 3.61l6.9-6.9C35.95 2.32 30.39 0 24 0 14.62 0 6.51 5.38 2.56 13.22l8.04 6.24C12.54 13.56 17.79 9.5 24 9.5z" />
            <path fill="#4285F4" d="M46.5 24.55c0-1.67-.15-3.27-.43-4.82H24v9.13h12.64c-.55 2.96-2.21 5.47-4.71 7.16l7.24 5.63C43.4 37.71 46.5 31.74 46.5 24.55z" />
            <path fill="#FBBC05" d="M10.6 28.54a14.52 14.52 0 0 1-.77-4.54c0-1.58.28-3.11.77-4.54l-8.04-6.24A23.94 23.94 0 0 0 0 24c0 3.86.92 7.52 2.56 10.78l8.04-6.24z" />
            <path fill="#34A853" d="M24 48c6.48 0 11.92-2.14 15.89-5.82l-7.24-5.63c-2.01 1.35-4.58 2.15-8.65 2.15-6.21 0-11.46-4.06-13.4-9.96l-8.04 6.24C6.51 42.62 14.62 48 24 48z" />
          </svg>
        </button>
        <button className="social-btn" type="button" onClick={() => { localStorage.setItem('secureOfficePostAuthRedirect', nextRoute); startMicrosoftSSO(); }} aria-label="Continue with Microsoft">
          <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
            <rect x="2" y="2" width="9" height="9" fill="#F25022" />
            <rect x="13" y="2" width="9" height="9" fill="#7FBA00" />
            <rect x="2" y="13" width="9" height="9" fill="#00A4EF" />
            <rect x="13" y="13" width="9" height="9" fill="#FFB900" />
          </svg>
        </button>
      </div>

      <div className="alt-link">No account? <Link to={nextRoute !== '/shop' ? `/signup?next=${encodeURIComponent(nextRoute)}` : '/signup'}>Sign up</Link></div>
      <div className="alt-link">
        <Link to="/business-intake">Edit business profile intake</Link>
      </div>
    </AuthShell>
  );
};
