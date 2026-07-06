from datetime import datetime
from enum import Enum
from typing import List, Optional

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel

from app.api.dependencies.time import now_vn


class ConversationStatus(str, Enum):
    NEW = "new"
    CONFIRMED = "confirmed"
    HANDOVER = "handover"
    APILIMIT = "apilimit"
    ORDER_PENDING = "order_pending"


class Conversation(Document):
    channel: Optional[str] = Field(default=None, max_length=100)
    customer_name: Optional[str] = Field(default=None, max_length=100)
    customer_id: Optional[str] = Field(default=None, max_length=100)
    pancake_page_id: Optional[str] = Field(default=None, max_length=100)
    pancake_conversation_id: Optional[str] = Field(default=None, max_length=255)
    pancake_thread_type: Optional[str] = Field(default=None, max_length=20)
    pancake_info_url: Optional[str] = Field(default=None, max_length=500)
    order_note: Optional[str] = Field(default=None, max_length=20000)
    is_active: bool = Field(default=True)
    status: ConversationStatus = Field(default=ConversationStatus.NEW)
    summaries: Optional[List[str]] = Field(default=None)
    version: Optional[str] = Field(default=None, max_length=32)
    fb_ai_initialized: bool = Field(default=False)
    fb_ai_initialized_at: Optional[datetime] = Field(default=None)
    bot_paused_until: Optional[datetime] = Field(default=None)
    bot_paused_at: Optional[datetime] = Field(default=None)
    bot_paused_reason: Optional[str] = Field(default=None, max_length=100)
    bot_paused_by: Optional[str] = Field(default=None, max_length=100)
    created_at: datetime = Field(default_factory=now_vn)
    updated_at: datetime = Field(default_factory=now_vn)

    class Settings:
        name = "conversations"
        indexes = [
            IndexModel([("customer_name", ASCENDING)], name="idx_conv_customer_name"),
            IndexModel([("customer_id", ASCENDING)], name="idx_conv_customer_id"),
            IndexModel(
                [("pancake_page_id", ASCENDING), ("pancake_conversation_id", ASCENDING)],
                name="uq_conv_pancake_thread",
                unique=True,
                partialFilterExpression={
                    "pancake_page_id": {"$type": "string"},
                    "pancake_conversation_id": {"$type": "string"},
                },
            ),
            IndexModel([("is_active", ASCENDING)], name="idx_conv_is_active"),
            IndexModel([("status", ASCENDING)], name="idx_conv_status"),
            IndexModel([("bot_paused_until", ASCENDING)], name="idx_conv_bot_paused_until"),
            IndexModel([("updated_at", ASCENDING)], name="idx_conv_updated_at"),
        ]
