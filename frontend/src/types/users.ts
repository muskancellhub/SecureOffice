import type { UserRole } from './auth';

export interface UserSummary {
  id: string;
  email: string;
  mobile: string | null;
  name: string;
  role: UserRole;
  permissions: string[];
  effective_permissions: string[];
  is_verified: boolean;
  tenant_id: string;
  created_at: string;
}

export interface CreateUserPayload {
  email: string;
  name: string;
  password: string;
  mobile?: string;
  role: UserRole;
  tenant_id?: string;
}

export interface PermissionCatalogItem {
  code: string;
  description: string;
}
