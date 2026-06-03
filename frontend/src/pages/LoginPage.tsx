import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { AuthShell } from '../components/AuthShell';
import { useAuth } from '../context/AuthContext';
import { extractApiError, isValidEmail } from '../utils/extractApiError';

// Must match backend otp_resend_cooldown_seconds. The backend enforces the real
// limit; this just drives the button countdown so users don't bounce off a 429.
const RESEND_COOLDOWN_SECONDS = 60;

export const LoginPage = () => {
  const { user, loading: authLoading, requestLoginOtp, verifyLoginOtp, startGoogleSSO, startMicrosoftSSO } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [otp, setOtp] = useState('');
  const [otpRequested, setOtpRequested] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(false);
  const [resendIn, setResendIn] = useState(0);
  // Synchronous re-entry guard. `loading` state disables the button, but a
  // state update isn't applied until React re-renders — a second click landing
  // in the same tick can slip past `disabled={loading}` and fire a duplicate
  // request (BUG-020). A ref updates immediately, so it blocks the second call.
  const inFlightRef = useRef(false);

  // Tick the resend countdown down to zero.
  useEffect(() => {
    if (resendIn <= 0) return;
    const id = setTimeout(() => setResendIn((s) => s - 1), 1000);
    return () => clearTimeout(id);
  }, [resendIn]);

  const [nextRoute, hasExplicitNext] = useMemo(() => {
    const queryNext = new URLSearchParams(location.search).get('next');
    const stateNext = typeof location.state === 'object' && location.state && 'from' in location.state
      ? String((location.state as { from?: string }).from || '')
      : '';
    const savedRedirect = localStorage.getItem('secureOfficePostAuthRedirect') || '';
    const explicit = queryNext || stateNext || savedRedirect;
    const target = explicit || '/shop';
    return [target.startsWith('/') ? target : '/shop', !!explicit] as const;
  }, [location.search, location.state]);

  useEffect(() => {
    if (!authLoading && user) {
      localStorage.removeItem('secureOfficePostAuthRedirect');
      navigate(nextRoute, { replace: true });
    }
  }, [authLoading, user, nextRoute, navigate]);

  useEffect(() => {
    const queryNext = new URLSearchParams(location.search).get('next');
    if (hasExplicitNext && !queryNext) {
      navigate(`/login?next=${encodeURIComponent(nextRoute)}`, { replace: true });
    }
  }, [hasExplicitNext, nextRoute, location.search, navigate]);

  const onRequestOtp = async (e: FormEvent) => {
    e.preventDefault();
    if (!email) return;
    if (!isValidEmail(email)) { setError('Please enter a valid email address'); return; }
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    setError('');
    setNotice('');
    setLoading(true);
    try {
      await requestLoginOtp(email);
      setOtpRequested(true);
      setNotice('If an account exists, an OTP has been sent to your email.');
      setResendIn(RESEND_COOLDOWN_SECONDS);
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to send OTP'));
    } finally {
      setLoading(false);
      inFlightRef.current = false;
    }
  };

  const onResendOtp = async () => {
    if (!email || resendIn > 0 || loading) return;
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    setError('');
    setNotice('');
    setLoading(true);
    try {
      await requestLoginOtp(email);
      setNotice('A new OTP has been sent to your email.');
      setResendIn(RESEND_COOLDOWN_SECONDS);
    } catch (err: any) {
      // Backend may still be cooling down (e.g. after a page reload reset the
      // local timer) or the per-window cap is hit — surface its message and,
      // for a cooldown 429, restart the local countdown to stay in sync.
      setError(extractApiError(err, 'Failed to resend OTP'));
      if (err?.response?.status === 429) setResendIn(RESEND_COOLDOWN_SECONDS);
    } finally {
      setLoading(false);
      inFlightRef.current = false;
    }
  };

  const onVerifyOtp = async (e: FormEvent) => {
    e.preventDefault();
    if (!email || !otp) return;
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    setError('');
    setNotice('');
    setLoading(true);
    try {
      await verifyLoginOtp({ email, otp });
      localStorage.removeItem('secureOfficePostAuthRedirect');
      navigate(nextRoute, { replace: true });
    } catch (err: any) {
      const message = extractApiError(err, 'OTP verification failed');
      // 429 = OTP locked after too many wrong attempts. Send the user back to
      // the request step so they can get a fresh code instead of being stuck
      // on a form that can no longer succeed.
      if (err?.response?.status === 429) {
        setOtp('');
        setOtpRequested(false);
        setError('');
        setNotice(message);
      } else {
        setError(message);
      }
    } finally {
      setLoading(false);
      inFlightRef.current = false;
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
          <button className="ghost-btn" type="button" onClick={onResendOtp} disabled={loading || resendIn > 0}>
            {resendIn > 0 ? `Resend code in ${resendIn}s` : 'Resend code'}
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

      <div className="alt-link">No account? <Link to={hasExplicitNext ? `/signup?next=${encodeURIComponent(nextRoute)}` : '/signup'}>Sign up</Link></div>
      <div className="alt-link">
        <Link to="/business-intake">Edit business profile intake</Link>
      </div>
    </AuthShell>
  );
};
