from datetime import datetime
from typing import Optional

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import ASCENDING, IndexModel

from app.api.dependencies.time import now_vn


class StateMissingSlot(Document):
    conversation_state_id: PydanticObjectId = Field(...)
    slot_catalog_name: Optional[str] = Field(default=None, max_length=100)
    priority: Optional[str] = Field(default=None, max_length=100)
    sort_order: Optional[str] = Field(default=None, max_length=100)
    created_at: datetime = Field(default_factory=now_vn)
    updated_at: datetime = Field(default_factory=now_vn)

    class Settings:
        name = "state_missing_slots"
        indexes = [
            IndexModel([("conversation_state_id", ASCENDING)], name="idx_missing_slots_state_id"),
            IndexModel([("slot_catalog_name", ASCENDING)], name="idx_missing_slots_slot_catalog_name"),
        ]
