import { FormEvent, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { AuthShell } from '../components/AuthShell';
import * as authApi from '../api/authApi';
import { extractApiError } from '../utils/extractApiError';

// Mirror of the backend password_strength_error rules so the user gets instant
// feedback. The backend remains the source of truth.
const passwordError = (pw: string): string | null => {
  if (pw.length < 12) return 'Password must be at least 12 characters long.';
  if (pw.length > 128) return 'Password must be at most 128 characters long.';
  if (!/[a-z]/.test(pw)) return 'Password must include a lowercase letter.';
  if (!/[A-Z]/.test(pw)) return 'Password must include an uppercase letter.';
  if (!/\d/.test(pw)) return 'Password must include a number.';
  if (!/[^A-Za-z0-9]/.test(pw)) return 'Password must include a symbol.';
  return null;
};

export const SuperAdminSetPasswordPage = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') || '';

  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  const liveError = useMemo(() => (password ? passwordError(password) : null), [password]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!token) { setError('This setup link is missing its token. Please use the link from your email.'); return; }
    const strengthErr = passwordError(password);
    if (strengthErr) { setError(strengthErr); return; }
    if (password !== confirm) { setError('Passwords do not match.'); return; }
    setError('');
    setLoading(true);
    try {
      await authApi.setSuperAdminPassword(token, password);
      setDone(true);
      setTimeout(() => navigate('/login', { replace: true }), 1500);
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to set password. The link may have expired or already been used.'));
    } finally {
      setLoading(false);
    }
  };

  if (done) {
    return (
      <AuthShell title="Password set" subtitle="Your super-admin account is ready">
        <p className="auth-success-text">Password set successfully. Redirecting you to sign in…</p>
        <div className="alt-link"><Link to="/login">Go to sign in</Link></div>
      </AuthShell>
    );
  }

  return (
    <AuthShell title="Set your password" subtitle="Create a password for your super-admin account">
      <form className="auth-form" onSubmit={onSubmit}>
        <input
          type="password"
          placeholder="New password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="new-password"
          required
        />
        <input
          type="password"
          placeholder="Confirm password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          autoComplete="new-password"
          required
        />
        <p className="auth-hint">At least 12 characters with an uppercase, lowercase, number, and symbol.</p>
        {liveError && <div className="error-text">{liveError}</div>}
        {error && !liveError && <div className="error-text">{error}</div>}
        <button className="primary-btn" type="submit" disabled={loading || !!liveError}>
          {loading ? 'Setting…' : 'Set password'}
        </button>
      </form>
    </AuthShell>
  );
};
