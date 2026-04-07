import { ActivitySquare, CircleHelp, Headphones, LayoutGrid, LogOut, Mail, Package, PanelLeft, PanelRight, ReceiptText, RefreshCcw, Router, Search, ShieldCheck, ShoppingCart, UserCircle2, Users, Workflow, House, Rows3 } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useShop } from '../../context/ShopContext';
import { CartDrawer } from './CartDrawer';
import { ChatBot } from '../ChatBot';

export const ShopShell = () => {
  const { user, logout } = useAuth();
  const { cart } = useShop();
  const navigate = useNavigate();
  const location = useLocation();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);
  const [solutionBuilderCollapsed, setSolutionBuilderCollapsed] = useState(false);
  const permissionSet = new Set(user?.effective_permissions ?? []);
  const canManageCatalogSync = permissionSet.has('manage_catalog_sync');
  const canManageManagedServices = permissionSet.has('manage_managed_services');
  const canManageUserAccess = permissionSet.has('manage_users');
  const canManageLifecycle = permissionSet.has('manage_lifecycle');
  const canViewLifecycle = permissionSet.has('view_lifecycle');
  const canViewBilling = permissionSet.has('view_billing');
  const onboardingCompleted = Boolean(user?.onboarding_completed);
  const onboardingSkipped = window.localStorage.getItem('so2_onboarding_skip') === '1';
  const profileName = user?.email ? user.email.split('@')[0] : 'Secure Office User';
  const showSolutionBuilder = useMemo(() => {
    const path = location.pathname;
    return (
      path === '/shop/routers'
      || path.startsWith('/shop/routers/')
      || path === '/shop/services'
      || path.startsWith('/shop/solution-flow')
    );
  }, [location.pathname]);

  useEffect(() => {
    if (!showSolutionBuilder) setSolutionBuilderCollapsed(false);
  }, [showSolutionBuilder]);

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
        sidebarCollapsed ? 'sidebar-collapsed' : '',
        showSolutionBuilder ? '' : 'no-drawer-layout',
        showSolutionBuilder && solutionBuilderCollapsed ? 'builder-collapsed' : '',
      ].filter(Boolean).join(' ')}
    >
      <aside className={`left-nav ${sidebarCollapsed ? 'collapsed' : ''}`}>
        <div className="sidebar-body">
          <div className="left-brand streamly-brand">
            <span className="brand-mark streamly-mark" aria-hidden="true">
              <ShieldCheck size={15} />
            </span>
            <span className="sidebar-fade-target">Secure Office</span>
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

          <label className="sidebar-search" aria-label="Search">
            <Search size={14} />
            <input className="sidebar-fade-target" placeholder="Search" />
          </label>

          <div className="nav-section-label sidebar-fade-target">Menu</div>
          <nav className="main-nav streamly-nav">
            <NavLink to="/shop/dashboard">
              <Rows3 size={15} />
              <span className="sidebar-fade-target">Dashboard</span>
            </NavLink>
            <NavLink to="/shop/flow-options">
              <Workflow size={15} />
              <span className="sidebar-fade-target">New Request</span>
            </NavLink>
            <NavLink to="/shop/designs">
              <LayoutGrid size={15} />
              <span className="sidebar-fade-target">Design History</span>
            </NavLink>
            <NavLink to="/shop/home">
              <House size={15} />
              <span className="sidebar-fade-target">Home</span>
            </NavLink>
            <NavLink to="/shop/onboarding">
              <LayoutGrid size={15} />
              <span className="sidebar-fade-target">Onboarding</span>
            </NavLink>
            <NavLink to="/shop/routers">
              <Router size={15} />
              <span className="sidebar-fade-target">Catalog</span>
            </NavLink>
            <NavLink to="/shop/services">
              <LayoutGrid size={15} />
              <span className="sidebar-fade-target">Services</span>
            </NavLink>
          </nav>

          <div className="nav-section-label sidebar-fade-target">Library</div>
          <nav className="main-nav streamly-nav">
            <NavLink to="/shop/orders">
              <Package size={15} />
              <span className="sidebar-fade-target">Orders</span>
            </NavLink>
            {canViewLifecycle && (
              <NavLink to="/shop/lifecycle">
                <ActivitySquare size={15} />
                <span className="sidebar-fade-target">Lifecycle</span>
              </NavLink>
            )}
            {canViewBilling && (
              <NavLink to="/shop/billing">
                <ReceiptText size={15} />
                <span className="sidebar-fade-target">Billing</span>
              </NavLink>
            )}
            <NavLink to="/shop/support">
              <Headphones size={15} />
              <span className="sidebar-fade-target">Support</span>
            </NavLink>
          </nav>

          <div className="nav-section-label sidebar-fade-target">General</div>
          <nav className="main-nav streamly-nav">
            {canManageCatalogSync && (
              <NavLink to="/shop/admin/catalog-sync">
                <RefreshCcw size={15} />
                <span className="sidebar-fade-target">Catalog Sync</span>
              </NavLink>
            )}
            {canManageManagedServices && (
              <NavLink to="/shop/admin/managed-services">
                <LayoutGrid size={15} />
                <span className="sidebar-fade-target">Admin Services</span>
              </NavLink>
            )}
            {canManageUserAccess && (
              <NavLink to="/shop/admin/user-access">
                <Users size={15} />
                <span className="sidebar-fade-target">User Access</span>
              </NavLink>
            )}
            {canManageLifecycle && (
              <NavLink to="/shop/admin/design-submissions">
                <Workflow size={15} />
                <span className="sidebar-fade-target">Design Ops Queue</span>
              </NavLink>
            )}
            {canManageLifecycle && (
              <NavLink to="/shop/admin/order-notifications">
                <Mail size={15} />
                <span className="sidebar-fade-target">Order Emails</span>
              </NavLink>
            )}
            <button
              className="sidebar-action-btn"
              onClick={async () => {
                await logout();
                navigate('/login', { replace: true });
              }}
            >
              <LogOut size={15} />
              <span className="sidebar-fade-target">Logout</span>
            </button>
          </nav>

          <div className="sidebar-profile">
            <span className="avatar-wrap">
              <UserCircle2 size={20} />
            </span>
            <div className="profile-copy sidebar-fade-target">
              <strong>{profileName}</strong>
              <span>{user?.email || 'user@secureoffice.com'}</span>
            </div>
            <CircleHelp size={14} className="sidebar-fade-target" />
          </div>
        </div>

      </aside>

      <main className="shop-main">
        <header className="shop-main-topbar">
          {showSolutionBuilder && (
            <button
              className="icon-circle-btn builder-toggle-btn"
              onClick={() => setSolutionBuilderCollapsed((v) => !v)}
              aria-label={solutionBuilderCollapsed ? 'Expand solution builder' : 'Collapse solution builder'}
              title={solutionBuilderCollapsed ? 'Expand solution builder' : 'Collapse solution builder'}
            >
              <PanelRight size={16} />
            </button>
          )}
          <button className="icon-circle-btn cart-icon-btn" onClick={() => navigate('/shop/cart')} aria-label="Open cart">
            <ShoppingCart size={16} />
            <span className="cart-badge">{cart?.lines?.length || 0}</span>
          </button>
        </header>
        <Outlet />
      </main>
      {showSolutionBuilder && (
        <CartDrawer collapsed={solutionBuilderCollapsed} onToggleCollapse={() => setSolutionBuilderCollapsed((v) => !v)} />
      )}
      <ChatBot />
    </div>
  );
};
