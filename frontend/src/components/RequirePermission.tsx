import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

/**
 * Router guard for permission-gated admin views.
 *
 * Sits inside <ProtectedRoute> (so `user` is already resolved and non-null by
 * the time this renders) and gates a page on the same `effective_permissions`
 * the sidebar checks — so the route guard and the sidebar link agree instead of
 * conflicting (BUG-UA-003). SUPER_ADMIN, whose effective_permissions include the
 * full set, passes naturally. Users without any of the required permissions are
 * redirected to the shop landing rather than shown a forbidden page.
 *
 * Pass a single permission or a list; the guard passes if the user holds ANY of
 * them (e.g. the products page hosts the financing tab, so it accepts either
 * manage_products or manage_pricing).
 */
export const RequirePermission = ({
  permission,
  children,
}: {
  permission: string | string[];
  children: JSX.Element;
}) => {
  const { user } = useAuth();

  const required = Array.isArray(permission) ? permission : [permission];
  const granted = new Set(user?.effective_permissions ?? []);
  const allowed = required.some((p) => granted.has(p));

  if (!allowed) {
    return <Navigate to="/shop" replace />;
  }

  return children;
};
