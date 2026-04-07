import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export const DashboardPage = () => {
  const { user, logout } = useAuth();

  if (!user) {
    return null;
  }

  return (
    <div className="dashboard">
      <div className="dashboard-card">
        <h1>Dashboard</h1>
        <p>Signed in as <strong>{user.email}</strong></p>
        <p>Role: <strong>{user.role}</strong></p>
        <p>Tenant: <code>{user.tenant_id}</code></p>

        {user.role === 'SUPER_ADMIN' && <div className="role-box">Super Admin Console Enabled</div>}
        {user.role === 'ADMIN' && <div className="role-box">Admin Workspace Controls Enabled</div>}
        {user.role === 'USER' && <div className="role-box">Standard User Workspace</div>}

        <div className="top-actions">
          <Link to="/routers" className="ghost-link">Routers</Link>
          <Link to="/managed-services" className="ghost-link">Managed Services</Link>
          <Link to="/cart" className="ghost-link">Cart</Link>
        </div>

        <button className="primary-btn" onClick={logout}>Logout</button>
      </div>
    </div>
  );
};
