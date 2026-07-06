from datetime import datetime
from typing import Optional

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import ASCENDING, IndexModel

from app.api.dependencies.time import now_vn


class BranchSlot(Document):
    branch_id: PydanticObjectId = Field(...)
    slot_catalog_name: Optional[str] = Field(default=None, max_length=100)
    required: bool = Field(default=False)
    sort_order: Optional[int] = Field(default=None)
    created_at: datetime = Field(default_factory=now_vn)
    updated_at: datetime = Field(default_factory=now_vn)

    class Settings:
        name = "branch_slots"
        indexes = [
            IndexModel([("branch_id", ASCENDING)], name="idx_branch_slots_branch_id"),
            IndexModel([("slot_catalog_name", ASCENDING)], name="idx_branch_slots_slot_catalog_name"),
        ]
