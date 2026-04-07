export type UserRole = 'SUPER_ADMIN' | 'ADMIN' | 'USER';

export interface LoginPayload {
  email: string;
  password: string;
}

export interface LoginOtpRequestPayload {
  email: string;
}

export interface LoginOtpVerifyPayload {
  email: string;
  otp: string;
}

export interface SignupPayload {
  email: string;
  password: string;
  mobile?: string;
  name: string;
}

export interface VerifyOtpPayload {
  email: string;
  otp: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: 'bearer';
  expires_in: number;
}

export interface MeResponse {
  user_id: string;
  email: string;
  role: UserRole;
  permissions: string[];
  effective_permissions: string[];
  tenant_id: string;
  onboarding_completed: boolean;
}
