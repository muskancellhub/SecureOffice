export interface DesignOpsSettings {
  sla_default_days: number;
  auto_assign: boolean;
}

export interface AdminServicesSettings {
  // category-group key -> enabled. Absent = enabled (opt-out).
  enabled_categories: Record<string, boolean>;
}

export interface TenantSettings {
  tenant_id: string;
  design_ops: DesignOpsSettings;
  admin_services: AdminServicesSettings;
  feature_flags: Record<string, boolean>;
  updated_at: string | null;
}

export interface UpdateTenantSettingsPayload {
  design_ops?: DesignOpsSettings;
  admin_services?: AdminServicesSettings;
  feature_flags?: Record<string, boolean>;
}
