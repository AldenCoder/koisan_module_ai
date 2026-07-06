from datetime import datetime
from typing import Optional

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import ASCENDING, IndexModel

from app.api.dependencies.time import now_vn


class ConversationState(Document):
    conversation_id: PydanticObjectId = Field(...)
    message_id: Optional[PydanticObjectId] = Field(default=None)
    branch_id: PydanticObjectId = Field(...)
    intent: Optional[str] = Field(default=None, max_length=100)
    rag_anchor_text: Optional[str] = Field(default=None)
    turn_index: Optional[str] = Field(default=None, max_length=100)
    next_action: Optional[str] = Field(default=None, max_length=100)
    prev_slot: Optional[str] = Field(default=None, max_length=100)
    next_slot: Optional[str] = Field(default=None, max_length=100)
    created_at: datetime = Field(default_factory=now_vn)
    updated_at: datetime = Field(default_factory=now_vn)

    class Settings:
        name = "conversation_states"
        indexes = [
            IndexModel([("conversation_id", ASCENDING)], name="idx_state_conversation_id"),
            IndexModel([("message_id", ASCENDING)], name="idx_state_message_id"),
            IndexModel([("branch_id", ASCENDING)], name="idx_state_branch_id"),
        ]
