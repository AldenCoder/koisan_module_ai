from datetime import datetime
from typing import List, Optional

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.api.dependencies.time import now_vn


class ImageAsset(Document):
    code: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=5000)
    url_images: List[str] = Field(..., min_length=1)
    created_at: datetime = Field(default_factory=now_vn)
    updated_at: datetime = Field(default_factory=now_vn)

    class Settings:
        name = "image_assets"
        indexes = [
            IndexModel(
                [("code", ASCENDING)],
                name="uniq_image_assets_code",
                unique=True,
            ),
            IndexModel(
                [("updated_at", DESCENDING)],
                name="idx_image_assets_updated_at",
            ),
        ]
