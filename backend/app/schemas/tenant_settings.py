"""Schemas for tenant_settings (multi-tenant Phase 3).

Typed sub-models give the UI a contract instead of an arbitrary blob. A PUT may
include any subset of the three sections; each included section replaces that
whole column (see TenantSettingsRepository).
"""
from datetime import datetime

from pydantic import BaseModel, Field


class DesignOpsSettings(BaseModel):
    sla_default_days: int = Field(default=5, ge=0, le=365)
    auto_assign: bool = False


class AdminServicesSettings(BaseModel):
    # Category-group key (e.g. 'network', 'security', 'end_user_devices') → enabled.
    # Absent key means enabled by default (opt-out model).
    enabled_categories: dict[str, bool] = Field(default_factory=dict)


class TenantSettingsResponse(BaseModel):
    tenant_id: str
    design_ops: DesignOpsSettings
    admin_services: AdminServicesSettings
    feature_flags: dict[str, bool] = Field(default_factory=dict)
    updated_at: datetime | None = None


class UpdateTenantSettingsRequest(BaseModel):
    design_ops: DesignOpsSettings | None = None
    admin_services: AdminServicesSettings | None = None
    feature_flags: dict[str, bool] | None = None
