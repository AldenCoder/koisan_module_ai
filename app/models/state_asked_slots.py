from datetime import datetime
from typing import Optional

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import ASCENDING, IndexModel

from app.api.dependencies.time import now_vn


class StateAskedSlot(Document):
    conversation_state_id: PydanticObjectId = Field(...)
    slot_catalog_name: Optional[str] = Field(default=None, max_length=100)
    created_at: datetime = Field(default_factory=now_vn)
    updated_at: datetime = Field(default_factory=now_vn)

    class Settings:
        name = "state_asked_slots"
        indexes = [
            IndexModel([("conversation_state_id", ASCENDING)], name="idx_asked_slots_state_id"),
            IndexModel([("slot_catalog_name", ASCENDING)], name="idx_asked_slots_slot_catalog_name"),
        ]
