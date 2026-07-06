from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from app.api.schemas.conversation import ConversationDetailResponse, ConversationStateShape


class ProcessMessageRequest(BaseModel):
    text: str = Field(...)
    conversation_id: Optional[str] = Field(
        None,
        description="Luot dau gui null de tao conversation moi. Khong dung gia tri placeholder 'string'.",
    )
    channel: Optional[str] = Field(None)
    customer_name: Optional[str] = Field(None)
    branch_id: Optional[str] = Field(
        None,
        description="Branch id da duoc xac dinh tu /extract-branch.",
    )
    intent: Optional[str] = Field(
        None,
        description="Intent da duoc xac dinh tu /extract-intent.",
    )
    branch: Optional[str] = Field(
        None,
        description="Branch da duoc xac dinh tu /extract-branch.",
    )
    extracted_slots: Dict[str, Any] = Field(
        default_factory=dict,
        description="Slot map da extract tu /extract-slots (de khong can goi GPT lai trong /response-message).",
    )


class ProcessMessageResponse(BaseModel):
    conversation_id: str = Field(...)
    message_id: str = Field(...)
    state_id: str = Field(...)
    state: ConversationStateShape = Field(...)
    assistant_message: Optional[str] = Field(None)
    conversation_detail: ConversationDetailResponse = Field(...)
