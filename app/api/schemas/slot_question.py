from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class SlotQuestionGenerationRequest(BaseModel):
    slot_name: str = Field(...)
    branch: Optional[str] = Field(None)
    intent: str = Field(...)
    known_slots: Dict[str, Any] = Field(default_factory=dict)
    user_text: str = Field(...)
    customer_name: Optional[str] = Field(None)
    conversation_id: Optional[str] = Field(
        None,
        description="Conversation id de lay 5 message gan nhat cho prompt tao cau hoi slot.",
    )


class SlotQuestionGenerationResponse(BaseModel):
    slot_name: str = Field(...)
    question: str = Field(...)
    slot_context: Dict[str, Any] = Field(default_factory=dict)
    raw_response: str = Field(...)
