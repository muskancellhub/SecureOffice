"""Schemas for the tenant directory (multi-tenant Phase 0)."""
from pydantic import BaseModel


class TenantSummary(BaseModel):
    id: str
    name: str
    tenant_type: str
