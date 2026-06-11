from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class UpdateOrderNotificationRecipientsRequest(BaseModel):
    recipients: list[EmailStr] = Field(default_factory=list)


class OrderNotificationRecipientsResponse(BaseModel):
    tenant_id: str
    # Plain str (not EmailStr): response echoing trusted stored recipients; output
    # must not re-validate or reserved TLDs like .test would 500 (BUG-35).
    recipients: list[str] = Field(default_factory=list)
    updated_by_user_id: str | None = None
    updated_at: datetime
