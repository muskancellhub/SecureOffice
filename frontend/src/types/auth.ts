export type UserRole = 'SUPER_ADMIN' | 'ADMIN' | 'USER';
export type UserType = 'CELLHUB' | 'VENDOR' | 'COMPANY';

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

export interface VendorSignupPayload {
  contact_name: string;
  contact_email: string;
  contact_phone?: string;
  password: string;
  company_name: string;
  address_street: string;
  address_city: string;
  address_state: string;
  address_zip: string;
  company_website: string;
  company_email: string;
  federal_tax_id: string;
  bbb_good_standing: boolean;
  sos_good_standing: boolean;
  corporate_liable_sales: boolean;
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
  user_type: UserType;
  permissions: string[];
  effective_permissions: string[];
  tenant_id: string;
  onboarding_completed: boolean;
}
