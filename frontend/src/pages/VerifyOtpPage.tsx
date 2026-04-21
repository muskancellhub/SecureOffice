import { FormEvent, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { AuthShell } from '../components/AuthShell';
import { useAuth } from '../context/AuthContext';

export const VerifyOtpPage = () => {
  const { verifyOtp } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const email = location.state?.email || '';
  const [otp, setOtp] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await verifyOtp({ email, otp });
      const nextRoute = location.state?.next || localStorage.getItem('secureOfficePostAuthRedirect') || '';
      localStorage.removeItem('secureOfficePostAuthRedirect');
      navigate(nextRoute || '/shop/onboarding', { replace: true });
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'OTP verification failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell title="Verify OTP" subtitle="Enter the 6-digit code sent to your email" showTabs={false}>
      <form className="auth-form" onSubmit={onSubmit}>
        <input type="email" placeholder="Email Address" value={email} readOnly style={{ opacity: 0.7, cursor: 'not-allowed' }} required />
        <input type="text" placeholder="6-digit OTP" value={otp} onChange={(e) => setOtp(e.target.value)} pattern="\d{6}" maxLength={6} required autoFocus />
        {error && <div className="error-text">{error}</div>}
        <button className="primary-btn" type="submit" disabled={loading}>{loading ? 'Verifying...' : 'Verify OTP'}</button>
      </form>
    </AuthShell>
  );
};
