import { FormEvent, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { AuthShell } from '../components/AuthShell';
import { useAuth } from '../context/AuthContext';

export const SignupPage = () => {
  const { signup } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const nextParam = new URLSearchParams(location.search).get('next') || '';
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [mobile, setMobile] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await signup({ name, email, mobile, password });
      navigate('/verify-otp', { state: { email, next: nextParam || localStorage.getItem('secureOfficePostAuthRedirect') || '' } });
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Signup failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell title="Create Account" subtitle="Sign up to start securing your workspace">
      <form className="auth-form" onSubmit={onSubmit}>
        <input type="text" placeholder="Full Name" value={name} onChange={(e) => setName(e.target.value)} required />
        <input type="email" placeholder="Email Address" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <input type="text" placeholder="Mobile" value={mobile} onChange={(e) => setMobile(e.target.value)} />
        <input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        {error && <div className="error-text">{error}</div>}
        <button className="primary-btn" type="submit" disabled={loading}>{loading ? 'Creating...' : 'Continue'}</button>
      </form>

      <div className="alt-link">Already have an account? <Link to={nextParam ? `/login?next=${encodeURIComponent(nextParam)}` : '/login'}>Sign in</Link></div>
    </AuthShell>
  );
};
