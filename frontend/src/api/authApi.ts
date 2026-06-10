import { api } from './client';
import type {
  LoginOtpRequestPayload,
  LoginOtpVerifyPayload,
  LoginPayload,
  MeResponse,
  SignupPayload,
  TokenResponse,
  VendorSignupPayload,
  VerifyOtpPayload,
} from '../types/auth';

export const signup = async (payload: SignupPayload) => {
  const { data } = await api.post('/auth/signup', payload);
  return data;
};

export const vendorSignup = async (payload: VendorSignupPayload) => {
  const { data } = await api.post('/auth/vendor/signup', payload);
  return data;
};

export const verifyOtp = async (payload: VerifyOtpPayload): Promise<TokenResponse> => {
  const { data } = await api.post('/auth/verify-otp', payload);
  return data;
};

export const login = async (payload: LoginPayload): Promise<TokenResponse> => {
  const { data } = await api.post('/auth/login', payload);
  return data;
};

export const requestLoginOtp = async (payload: LoginOtpRequestPayload) => {
  const { data } = await api.post('/auth/login/otp/request', payload);
  return data;
};

export const verifyLoginOtp = async (payload: LoginOtpVerifyPayload): Promise<TokenResponse> => {
  const { data } = await api.post('/auth/login/otp/verify', payload);
  return data;
};

export const refresh = async (): Promise<TokenResponse> => {
  const { data } = await api.post('/auth/refresh');
  return data;
};

// Super-admin password setup. Trigger is super-admin-only (sends an email link);
// set-password consumes the single-use token from that link.
export const triggerSuperAdminPasswordSetup = async (accessToken: string, email: string) => {
  const { data } = await api.post(
    '/auth/super-admin/password-setup',
    { email },
    { headers: { Authorization: `Bearer ${accessToken}` } },
  );
  return data;
};

export const setSuperAdminPassword = async (token: string, password: string) => {
  const { data } = await api.post('/auth/super-admin/set-password', { token, password });
  return data;
};

// Admin-set flow: an existing super admin directly sets an allowlisted teammate's password.
export const setSuperAdminCredentials = async (accessToken: string, email: string, password: string) => {
  const { data } = await api.post(
    '/auth/super-admin/set-credentials',
    { email, password },
    { headers: { Authorization: `Bearer ${accessToken}` } },
  );
  return data;
};

export const logout = async () => {
  const { data } = await api.post('/auth/logout');
  return data;
};

export const me = async (accessToken: string): Promise<MeResponse> => {
  const { data } = await api.get('/users/me', {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  });
  return data;
};
