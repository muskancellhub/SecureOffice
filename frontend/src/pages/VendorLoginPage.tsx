import { FormEvent, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { AuthShell } from '../components/AuthShell';
import { useAuth } from '../context/AuthContext';
import { extractApiError, isValidEmail } from '../utils/extractApiError';

export const VendorLoginPage = () => {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const nextParam = new URLSearchParams(location.search).get('next') || '';
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!isValidEmail(email)) { setError('Please enter a valid email address'); return; }
    setError('');
    setLoading(true);
    try {
      await login({ email, password });
      // Land on /shop, which routes vendors to their dashboard and everyone else
      // to the buyer flow (see ShopLandingPage).
      navigate(nextParam || '/shop', { replace: true });
    } catch (err: any) {
      setError(extractApiError(err, 'Login failed. Check your credentials.'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell title="Vendor Login" subtitle="Sign in to your vendor portal" showTabs={false}>
      <form className="auth-form" onSubmit={onSubmit}>
        <input
          type="email"
          placeholder="Email Address"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        {error && <div className="error-text">{error}</div>}
        <button className="primary-btn" type="submit" disabled={loading}>
          {loading ? 'Signing in...' : 'Sign In'}
        </button>
      </form>

      <div className="alt-link">
        Not a vendor yet? <Link to={nextParam ? `/vendor/register?next=${encodeURIComponent(nextParam)}` : '/vendor/register'}>Apply now</Link>
      </div>
      <div className="alt-link">
        <Link to={nextParam ? `/login?next=${encodeURIComponent(nextParam)}` : '/login'}>Customer / Staff login</Link>
      </div>
    </AuthShell>
  );
};
