from typing import Any, Dict, Optional
from datetime import datetime
from enum import Enum

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel, ASCENDING

from app.api.dependencies.time import now_vn


class MessageRole(str, Enum):
    USER = "user"
    STAFF = "staff"
    BOT = "bot"
    SYSTEM = "system"


class Message(Document):
    conversation_id: PydanticObjectId = Field(...)
    message_mid: Optional[str] = Field(default=None, max_length=255)
    role: Optional[str] = Field(default=None, max_length=100)
    content: str = Field(...)
    meta: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=now_vn)
    updated_at: datetime = Field(default_factory=now_vn)

    class Settings:
        name = "messages"
        indexes = [
            IndexModel([("conversation_id", ASCENDING)], name="idx_msg_conversation_id"),
            IndexModel([("role", ASCENDING)], name="idx_msg_role"),
            IndexModel([("updated_at", ASCENDING)], name="idx_msg_updated_at"),
        ]

    class Config:
        arbitrary_types_allowed = True