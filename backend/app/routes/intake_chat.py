"""Public endpoint for the conversational business intake (no auth)."""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.intake_chat_service import IntakeChatService

router = APIRouter(prefix='/intake', tags=['Intake Chat'])


class IntakeChatMessage(BaseModel):
    role: str
    content: str


class IntakeChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: list[IntakeChatMessage] = Field(default_factory=list)
    current_fields: dict[str, Any] = Field(default_factory=dict)


class IntakeChatResponse(BaseModel):
    answer: str
    extracted: dict[str, Any]
    is_complete: bool


@router.post('/chat', response_model=IntakeChatResponse)
def intake_chat(body: IntakeChatRequest):
    svc = IntakeChatService()
    result = svc.chat(
        message=body.message,
        history=[m.model_dump() for m in body.history],
        current_fields=body.current_fields,
    )
    return IntakeChatResponse(**result)
