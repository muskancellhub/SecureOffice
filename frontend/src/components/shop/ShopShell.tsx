import { Boxes, Landmark, LayoutGrid, LogOut, Mail, MonitorCheck, Package, PanelLeft, PencilRuler, ReceiptText, RefreshCcw, Router, ShieldCheck, ShoppingCart, Sparkles, Users } from 'lucide-react';
import { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useShop } from '../../context/ShopContext';
import { ChatBot } from '../ChatBot';
import { TenantSwitcher } from './TenantSwitcher';

export const ShopShell = () => {
  const { user, logout } = useAuth();
  const { cart } = useShop();
  const navigate = useNavigate();
  const location = useLocation();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const permissionSet = new Set(user?.effective_permissions ?? []);
  const canManageCatalogSync = permissionSet.has('manage_catalog_sync');
  const canManageProducts = permissionSet.has('manage_products');
  const canManagePricing = permissionSet.has('manage_pricing');
  const canManageManagedServices = permissionSet.has('manage_managed_services');
  const canManageUserAccess = permissionSet.has('manage_users');
  const canManageLifecycle = permissionSet.has('manage_lifecycle');
  const canViewBilling = permissionSet.has('view_billing');
  const onboardingCompleted = Boolean(user?.onboarding_completed);
  const onboardingSkipped = window.localStorage.getItem('so2_onboarding_skip') === '1';
  const profileName = user?.email ? user.email.split('@')[0] : 'Secure AI Office User';
  const profileInitials = profileName
    .split(/[\s._-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('') || 'U';
  useEffect(() => {
    if (!user) return;
    const path = location.pathname;
    if (!onboardingCompleted && !onboardingSkipped && path !== '/shop/onboarding') {
      navigate('/shop/onboarding', { replace: true });
    }
  }, [user, onboardingCompleted, onboardingSkipped, location.pathname, navigate]);

  return (
    <div
      className={[
        'shop-page',
        'no-drawer-layout',
        sidebarCollapsed ? 'sidebar-collapsed' : '',
      ].filter(Boolean).join(' ')}
    >
      <aside className={`left-nav ${sidebarCollapsed ? 'collapsed' : ''}`}>
        <div className="sidebar-body">
          <div className="left-brand streamly-brand">
            <span className="brand-mark streamly-mark" aria-hidden="true">
              <ShieldCheck size={17} />
            </span>
            <span className="brand-title-wrap sidebar-fade-target">
              <span className="brand-name">Secure AI Office</span>
              <span className="brand-sub">Network · Commerce</span>
            </span>
            <button
              type="button"
              className="brand-toggle-btn"
              onClick={() => setSidebarCollapsed((v) => !v)}
              aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            >
              <PanelLeft size={16} />
            </button>
          </div>

          <div className="nav-section-label sidebar-fade-target">Workspace</div>
          <nav className="main-nav streamly-nav">
            <NavLink to="/shop/dashboard">
              <LayoutGrid size={17} />
              <span className="sidebar-fade-target">Dashboard</span>
            </NavLink>
            <NavLink to="/shop/designs">
              <PencilRuler size={17} />
              <span className="sidebar-fade-target">Designs</span>
            </NavLink>
            <NavLink to="/shop/onboarding">
              <Sparkles size={17} />
              <span className="sidebar-fade-target">Onboarding</span>
            </NavLink>
          </nav>

          <div className="nav-section-label sidebar-fade-target">Commerce</div>
          <nav className="main-nav streamly-nav">
            <NavLink to="/shop/routers">
              <Router size={17} />
              <span className="sidebar-fade-target">Catalog</span>
            </NavLink>
            <NavLink to="/shop/services">
              <ShieldCheck size={17} />
              <span className="sidebar-fade-target">Managed Services</span>
            </NavLink>
            <NavLink to="/shop/cart">
              <ShoppingCart size={17} />
              <span className="sidebar-fade-target">Cart</span>
              {(cart?.lines?.length ?? 0) > 0 && (
                <span className="nav-badge sidebar-fade-target">{cart?.lines?.length}</span>
              )}
            </NavLink>
            <NavLink to="/shop/orders">
              <Package size={17} />
              <span className="sidebar-fade-target">Orders</span>
            </NavLink>
          </nav>

          <div className="nav-section-label sidebar-fade-target">Operate</div>
          <nav className="main-nav streamly-nav">
            {canViewBilling && (
              <NavLink to="/shop/billing">
                <ReceiptText size={17} />
                <span className="sidebar-fade-target">Billing</span>
              </NavLink>
            )}
            <NavLink to="/shop/zabbix">
              <MonitorCheck size={17} />
              <span className="sidebar-fade-target">Monitoring</span>
            </NavLink>
          </nav>

          <div className="nav-section-label sidebar-fade-target">Admin</div>
          <nav className="main-nav streamly-nav">
            {canManageProducts && (
              <NavLink to="/shop/admin/products">
                <Boxes size={17} />
                <span className="sidebar-fade-target">Products & Pricing</span>
              </NavLink>
            )}
            {canManagePricing && (
              <NavLink to="/shop/admin/financing">
                <Landmark size={17} />
                <span className="sidebar-fade-target">Financing</span>
              </NavLink>
            )}
            {canManageCatalogSync && (
              <NavLink to="/shop/admin/catalog-sync">
                <RefreshCcw size={17} />
                <span className="sidebar-fade-target">Catalog Sync</span>
              </NavLink>
            )}
            {canManageManagedServices && (
              <NavLink to="/shop/admin/managed-services">
                <LayoutGrid size={17} />
                <span className="sidebar-fade-target">Admin Services</span>
              </NavLink>
            )}
            {canManageUserAccess && (
              <NavLink to="/shop/admin/user-access">
                <Users size={17} />
                <span className="sidebar-fade-target">User Access</span>
              </NavLink>
            )}
            {canManageLifecycle && (
              <NavLink to="/shop/admin/order-notifications">
                <Mail size={17} />
                <span className="sidebar-fade-target">Order Emails</span>
              </NavLink>
            )}
          </nav>

          <div className="sidebar-profile">
            <span className="avatar-wrap avatar-initials" aria-hidden="true">
              {profileInitials}
            </span>
            <div className="profile-copy sidebar-fade-target">
              <strong>{profileName}</strong>
              <span>{user?.email || 'user@secureoffice.com'}</span>
            </div>
          </div>

          <button
            className="sidebar-action-btn sidebar-signout"
            onClick={async () => {
              await logout();
              navigate('/login', { replace: true });
            }}
          >
            <LogOut size={17} />
            <span className="sidebar-fade-target">Sign out</span>
          </button>
        </div>

      </aside>

      <main className="shop-main">
        <header className="shop-main-topbar">
          <TenantSwitcher />
          <button className="icon-circle-btn cart-icon-btn" onClick={() => navigate('/shop/cart')} aria-label="Open cart">
            <ShoppingCart size={16} />
            <span className="cart-badge">{cart?.lines?.length || 0}</span>
          </button>
        </header>
        <Outlet />
      </main>
      <ChatBot />
    </div>
  );
};
