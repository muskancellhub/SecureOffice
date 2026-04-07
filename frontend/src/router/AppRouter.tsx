import { Navigate, Route, Routes, useParams } from 'react-router-dom';
import { LoginPage } from '../pages/LoginPage';
import { SignupPage } from '../pages/SignupPage';
import { VerifyOtpPage } from '../pages/VerifyOtpPage';
import { DashboardPage } from '../pages/DashboardPage';
import { OAuthSuccessPage } from '../pages/OAuthSuccessPage';
import { ProtectedRoute } from '../components/ProtectedRoute';
import { ShopProvider } from '../context/ShopContext';
import { ShopShell } from '../components/shop/ShopShell';
import { ShopLandingPage } from '../pages/ShopLandingPage';
import { RoutersCatalogPage } from '../pages/RoutersCatalogPage';
import { RouterDetailsPage } from '../pages/RouterDetailsPage';
import { OrdersPage } from '../pages/OrdersPage';
import { QuoteDetailsPage } from '../pages/QuoteDetailsPage';
import { OrderDetailsPage } from '../pages/OrderDetailsPage';
import { SupportPage } from '../pages/SupportPage';
import { CartPage } from '../pages/CartPage';
import { AdminCatalogSyncPage } from '../pages/AdminCatalogSyncPage';
import { AdminManagedServicesPage } from '../pages/AdminManagedServicesPage';
import { AdminUserManagementPage } from '../pages/AdminUserManagementPage';
import { AdminOrderNotificationsPage } from '../pages/AdminOrderNotificationsPage';
import { BillingPage } from '../pages/BillingPage';
import { LifecyclePage } from '../pages/LifecyclePage';
import { CustomerDashboardPage } from '../pages/CustomerDashboardPage';
import { SolutionFlowPage } from '../pages/SolutionFlowPage';
import { IntroHomePage } from '../pages/IntroHomePage';
import { FlowOptionsPage } from '../pages/FlowOptionsPage';
import { OnboardingPage } from '../pages/OnboardingPage';
import { ManagedServicesCatalogPage } from '../pages/ManagedServicesCatalogPage';
import { BusinessIntakePage } from '../pages/BusinessIntakePage';
import { CalculatorResultsPage } from '../pages/CalculatorResultsPage';
import { NetworkDesignBuilderPage } from '../pages/NetworkDesignBuilderPage';
import { DesignHistoryPage } from '../pages/DesignHistoryPage';
import { DesignDetailPage } from '../pages/DesignDetailPage';
import { AdminDesignSubmissionsPage } from '../pages/AdminDesignSubmissionsPage';
import { PublicHomePage } from '../pages/PublicHomePage';

const LegacyQuoteRedirect = () => {
  const { quoteId } = useParams();
  if (!quoteId) return <Navigate to="/shop/orders" replace />;
  return <Navigate to={`/shop/quotes/${quoteId}`} replace />;
};

export const AppRouter = () => (
  <Routes>
    <Route path="/" element={<PublicHomePage />} />
    <Route path="/business-intake" element={<BusinessIntakePage />} />
    <Route path="/calculator-results" element={<CalculatorResultsPage />} />
    <Route path="/login" element={<LoginPage />} />
    <Route path="/signup" element={<SignupPage />} />
    <Route path="/verify-otp" element={<VerifyOtpPage />} />
    <Route path="/oauth/success" element={<OAuthSuccessPage />} />

    <Route
      element={
        <ProtectedRoute>
          <ShopProvider>
            <ShopShell />
          </ShopProvider>
        </ProtectedRoute>
      }
    >
      <Route path="/shop" element={<ShopLandingPage />} />
      <Route path="/shop/onboarding" element={<OnboardingPage />} />
      <Route path="/shop/home" element={<IntroHomePage />} />
      <Route path="/shop/flow-options" element={<FlowOptionsPage />} />
      <Route path="/shop/dashboard" element={<CustomerDashboardPage />} />
      <Route path="/shop/designs" element={<DesignHistoryPage />} />
      <Route path="/shop/designs/new" element={<NetworkDesignBuilderPage />} />
      <Route path="/shop/designs/:designId" element={<DesignDetailPage />} />
      <Route path="/shop/solution-flow" element={<SolutionFlowPage />} />
      <Route path="/shop/routers" element={<RoutersCatalogPage />} />
      <Route path="/shop/routers/:itemId" element={<RouterDetailsPage />} />
      <Route path="/shop/services" element={<ManagedServicesCatalogPage />} />
      <Route path="/shop/orders" element={<OrdersPage />} />
      <Route path="/shop/quotes/:quoteId" element={<QuoteDetailsPage />} />
      <Route path="/shop/quote/:quoteId" element={<LegacyQuoteRedirect />} />
      <Route path="/shop/support" element={<SupportPage />} />
      <Route path="/shop/lifecycle" element={<LifecyclePage />} />
      <Route path="/shop/billing" element={<BillingPage />} />
      <Route path="/shop/cart" element={<CartPage />} />
      <Route path="/shop/orders/:orderId" element={<OrderDetailsPage />} />
      <Route path="/shop/admin/catalog-sync" element={<AdminCatalogSyncPage />} />
      <Route path="/shop/admin/managed-services" element={<AdminManagedServicesPage />} />
      <Route path="/shop/admin/user-access" element={<AdminUserManagementPage />} />
      <Route path="/shop/admin/order-notifications" element={<AdminOrderNotificationsPage />} />
      <Route path="/shop/admin/design-submissions" element={<AdminDesignSubmissionsPage />} />
    </Route>

    <Route
      path="/dashboard"
      element={
        <ProtectedRoute>
          <DashboardPage />
        </ProtectedRoute>
      }
    />

    <Route path="/routers" element={<Navigate to="/shop/routers" replace />} />
    <Route path="/managed-services" element={<Navigate to="/shop/services" replace />} />
    <Route path="/cart" element={<Navigate to="/shop/cart" replace />} />
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes>
);
