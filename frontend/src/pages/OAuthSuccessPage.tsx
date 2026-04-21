import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export const OAuthSuccessPage = () => {
  const navigate = useNavigate();
  const { ensureSession } = useAuth();

  useEffect(() => {
    ensureSession()
      .then(() => {
        const redirect = localStorage.getItem('secureOfficePostAuthRedirect') || '/shop';
        localStorage.removeItem('secureOfficePostAuthRedirect');
        navigate(redirect.startsWith('/') ? redirect : '/shop', { replace: true });
      })
      .catch(() => navigate('/login', { replace: true }));
  }, [ensureSession, navigate]);

  return <div className="auth-page"><div className="card">Completing SSO login...</div></div>;
};
