from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class SlotExtractionRequest(BaseModel):
    text: str = Field(...)
    intent: str = Field(...)
    branch_hint: Optional[str] = Field(None)


class SlotExtractionResponse(BaseModel):
    slot: Optional[str] = Field(None)
    value: Optional[Any] = Field(None)
    confidence: float = Field(default=0.0)
    slots: Dict[str, Any] = Field(default_factory=dict)
    raw_response: str = Field(default="")


class SlotStateUpdateRequest(BaseModel):
    text: str = Field(...)
    intent: str = Field(...)
    message_id: str = Field(..., description="message_id da duoc tao truoc do.")
    conversation_id: Optional[str] = Field(
        None,
        description="Gui null de tao conversation moi hoac truyen conversation_id hien tai.",
    )
    branch_name: Optional[str] = Field(None)
    slots: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    raw_response: str = Field(default="")


class SlotStateUpdateResponse(BaseModel):
    conversation_id: Optional[str] = Field(None)
    state_id: Optional[str] = Field(None)
    branch_id: Optional[str] = Field(None)
    branch_name: Optional[str] = Field(None)
    slot_id: Optional[str] = Field(None)
    slot_name: Optional[str] = Field(None)
    slots: Dict[str, Any] = Field(default_factory=dict)
    raw_response: str = Field(default="")
