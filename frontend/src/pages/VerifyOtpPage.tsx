import { FormEvent, useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { AuthShell } from '../components/AuthShell';
import { useAuth } from '../context/AuthContext';
import { extractApiError, isValidEmail } from '../utils/extractApiError';

// Must match backend otp_resend_cooldown_seconds. The backend enforces the real
// limit; this just drives the button countdown so users don't bounce off a 429.
const RESEND_COOLDOWN_SECONDS = 60;

export const VerifyOtpPage = () => {
  const { verifyOtp, requestLoginOtp } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  // BUG-AUTH-011: the email used to arrive ONLY via router state, so a refresh
  // or a direct visit (e.g. after abandoning signup) left this page unusable —
  // no email, no way to resend. It's now an editable field seeded from state.
  const [email, setEmail] = useState(location.state?.email || '');
  const [otp, setOtp] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(false);
  const [resendIn, setResendIn] = useState(0);

  // Tick the resend countdown down to zero.
  useEffect(() => {
    if (resendIn <= 0) return;
    const id = setTimeout(() => setResendIn((s) => s - 1), 1000);
    return () => clearTimeout(id);
  }, [resendIn]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!isValidEmail(email)) { setError('Please enter a valid email address'); return; }
    setError('');
    setNotice('');
    setLoading(true);
    try {
      await verifyOtp({ email, otp });
      const nextRoute = location.state?.next || localStorage.getItem('secureOfficePostAuthRedirect') || '';
      localStorage.removeItem('secureOfficePostAuthRedirect');
      navigate(nextRoute || '/shop/onboarding', { replace: true });
    } catch (err: any) {
      setError(extractApiError(err, 'OTP verification failed'));
    } finally {
      setLoading(false);
    }
  };

  const onResend = async () => {
    if (resendIn > 0 || loading) return;
    if (!isValidEmail(email)) { setError('Enter your email above to resend the code'); return; }
    setError('');
    setNotice('');
    setLoading(true);
    try {
      // Reuses the login-OTP request, which now issues a fresh code to unverified
      // users too (BUG-AUTH-011) — the recovery path for an abandoned signup.
      await requestLoginOtp(email);
      setNotice('A new code has been sent to your email.');
      setResendIn(RESEND_COOLDOWN_SECONDS);
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to resend code'));
      if (err?.response?.status === 429) setResendIn(RESEND_COOLDOWN_SECONDS);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell title="Verify OTP" subtitle="Enter the 6-digit code sent to your email" showTabs={false}>
      <form className="auth-form" onSubmit={onSubmit}>
        <input
          type="email"
          placeholder="Email Address"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="username"
          required
        />
        <input type="text" placeholder="6-digit OTP" value={otp} onChange={(e) => setOtp(e.target.value)} pattern="\d{6}" maxLength={6} required autoFocus />
        {notice && <div className="mini-note">{notice}</div>}
        {error && <div className="error-text">{error}</div>}
        <button className="primary-btn" type="submit" disabled={loading}>{loading ? 'Verifying...' : 'Verify OTP'}</button>
        <button className="ghost-btn" type="button" onClick={onResend} disabled={loading || resendIn > 0}>
          {resendIn > 0 ? `Resend code in ${resendIn}s` : 'Resend code'}
        </button>
      </form>
    </AuthShell>
  );
};
