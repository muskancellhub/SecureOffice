import type { UserType } from './auth';

export interface TenantSummary {
  id: string;
  name: string;
  tenant_type: UserType; // 'CELLHUB' | 'VENDOR' | 'COMPANY'
}
