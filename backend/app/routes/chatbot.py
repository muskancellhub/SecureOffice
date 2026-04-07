from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.middleware.dependencies import get_current_user
from app.services.chatbot_service import ChatbotService

router = APIRouter(prefix='/chatbot', tags=['Chatbot'])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str


@router.post('/ask', response_model=ChatResponse)
def ask_chatbot(
    body: ChatRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tenant_id = current_user.get('tenant_id', '')
    service = ChatbotService(db)
    answer = service.ask(
        tenant_id=tenant_id,
        message=body.message,
        history=[m.model_dump() for m in body.history],
    )
    return ChatResponse(answer=answer)
