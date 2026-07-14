import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export const ShopLandingPage = () => {
  const { user } = useAuth();
  const onboardingSkipped = window.localStorage.getItem('so2_onboarding_skip') === '1';
  if (!user) return <Navigate to="/login" replace />;
  // Vendors (suppliers) get their own order-visibility dashboard, not the buyer
  // shop flow — and they skip the buyer onboarding wizard entirely.
  if (user.user_type === 'VENDOR') return <Navigate to="/shop/vendor" replace />;
  if (!user.onboarding_completed && !onboardingSkipped) return <Navigate to="/shop/onboarding" replace />;
  return <Navigate to="/shop/dashboard" replace />;
};
