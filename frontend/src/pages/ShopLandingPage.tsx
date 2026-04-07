import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export const ShopLandingPage = () => {
  const { user } = useAuth();
  const onboardingSkipped = window.localStorage.getItem('so2_onboarding_skip') === '1';
  if (!user) return <Navigate to="/login" replace />;
  if (!user.onboarding_completed && !onboardingSkipped) return <Navigate to="/shop/onboarding" replace />;
  return <Navigate to="/shop/dashboard" replace />;
};
