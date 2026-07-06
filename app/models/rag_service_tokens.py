from datetime import datetime

from beanie import Document
from pydantic import Field
from pymongo import DESCENDING, IndexModel

from app.api.dependencies.time import now_vn


class RagServiceToken(Document):
    access_token: str = Field(...)
    token_type: str = Field(default="bearer", max_length=50)
    created_at: datetime = Field(default_factory=now_vn)
    updated_at: datetime = Field(default_factory=now_vn)

    class Settings:
        name = "rag_service_tokens"
        indexes = [
            IndexModel([("updated_at", DESCENDING)], name="idx_rag_token_updated_at"),
        ]
