from datetime import datetime
from typing import Optional

from beanie import Document
from pydantic import Field
from pymongo import IndexModel

from app.api.dependencies.time import now_vn


class Branch(Document):
    name: str = Field(..., max_length=100)
    label: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=now_vn)
    updated_at: datetime = Field(default_factory=now_vn)

    class Settings:
        name = "branches"
        indexes = [
            IndexModel("name", unique=True, name="uq_branch_name"),
        ]
