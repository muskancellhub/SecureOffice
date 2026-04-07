from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class UpdateOrderNotificationRecipientsRequest(BaseModel):
    recipients: list[EmailStr] = Field(default_factory=list)


class OrderNotificationRecipientsResponse(BaseModel):
    tenant_id: str
    recipients: list[EmailStr] = Field(default_factory=list)
    updated_by_user_id: str | None = None
    updated_at: datetime
