from datetime import datetime
from typing import List, Optional

from beanie import Document
from pydantic import Field
from pymongo import IndexModel

from app.api.dependencies.time import now_vn


class SlotCatalog(Document):
    name: str = Field(..., max_length=100)
    label: Optional[str] = Field(default=None, max_length=100)
    description: str = Field(...)
    required: bool = Field(default=False)
    slot_type: Optional[str] = Field(default=None, max_length=100)
    priority: Optional[str] = Field(default=None, max_length=100)
    applies_to: List[str] = Field(default_factory=list)
    synonyms: str = Field(default="")
    examples: str = Field(default="")
    evidence: str = Field(default="")
    created_at: datetime = Field(default_factory=now_vn)
    updated_at: datetime = Field(default_factory=now_vn)

    class Settings:
        name = "slot_catalog"
        indexes = [
            IndexModel("name", unique=True, name="uq_slot_catalog_name"),
        ]
