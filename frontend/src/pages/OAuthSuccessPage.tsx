import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export const OAuthSuccessPage = () => {
  const navigate = useNavigate();
  const { ensureSession } = useAuth();

  useEffect(() => {
    // Read the saved redirect synchronously, before the async ensureSession.
    // Under React.StrictMode the effect runs twice; if we read inside the
    // .then (after removeItem) the second pass sees null and falls back to
    // /shop, which then redirects to /shop/dashboard — clobbering the real
    // destination. Reading here means both passes capture the same target.
    const saved = localStorage.getItem('secureOfficePostAuthRedirect') || '/shop';
    const target = saved.startsWith('/') ? saved : '/shop';
    ensureSession()
      .then(() => {
        localStorage.removeItem('secureOfficePostAuthRedirect');
        navigate(target, { replace: true });
      })
      .catch(() => navigate('/login', { replace: true }));
  }, [ensureSession, navigate]);

  return <div className="auth-page"><div className="card">Completing SSO login...</div></div>;
};
