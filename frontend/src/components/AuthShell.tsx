import { Link, useLocation } from 'react-router-dom';

interface AuthShellProps {
  title: string;
  subtitle: string;
  children: React.ReactNode;
  showTabs?: boolean;
}

export const AuthShell = ({ title, subtitle, children, showTabs = true }: AuthShellProps) => {
  const location = useLocation();
  const isLogin = location.pathname === '/login';

  return (
    <div className="auth-page">
      <div className="auth-layout">
        <div className="auth-left">
          <div className="logo-row">
            <span className="logo-mark">➤</span>
            <span className="logo-text">Secure AI Office</span>
          </div>

          <div className="auth-content">
            <h1>{title}</h1>
            <p>{subtitle}</p>

            {showTabs && (
              <div className="auth-tabs">
                <Link to="/login" className={isLogin ? 'active' : ''}>Sign In</Link>
                <Link to="/signup" className={!isLogin ? 'active' : ''}>Signup</Link>
              </div>
            )}

            {children}
          </div>
        </div>

        <div className="auth-right">
          <div className="vault-bg-lines" />
          <div className="vault-illustration">
            <div className="vault-door" />
            <div className="vault-wheel" />
            <div className="vault-handle" />
          </div>
        </div>
      </div>
    </div>
  );
};
