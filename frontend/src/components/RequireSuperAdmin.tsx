import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

/**
 * Router guard for SUPER_ADMIN-only admin views (multi-tenant Phase 0).
 *
 * Sits inside <ProtectedRoute> (so `user` is already resolved and non-null by
 * the time this renders) and gates the cross-tenant config views. Non-super
 * users are redirected to the shop landing rather than shown a forbidden page.
 */
export const RequireSuperAdmin = ({ children }: { children: JSX.Element }) => {
  const { user } = useAuth();

  if (user?.role !== 'SUPER_ADMIN') {
    return <Navigate to="/shop" replace />;
  }

  return children;
};
