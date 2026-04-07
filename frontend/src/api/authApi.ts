import { api } from './client';
import type {
  LoginOtpRequestPayload,
  LoginOtpVerifyPayload,
  LoginPayload,
  MeResponse,
  SignupPayload,
  TokenResponse,
  VerifyOtpPayload,
} from '../types/auth';

export const signup = async (payload: SignupPayload) => {
  const { data } = await api.post('/auth/signup', payload);
  return data;
};

export const verifyOtp = async (payload: VerifyOtpPayload) => {
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
