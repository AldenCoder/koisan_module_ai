from datetime import datetime, timezone
from typing import Optional

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel, ASCENDING
from app.api.dependencies.time import now_vn

class TacNhanQuyenHan(Document):
    tac_nhan_id: PydanticObjectId = Field(..., description="ID của tác nhân")
    quyen_han_id: PydanticObjectId = Field(..., description="ID của quyền hạn")
    thoi_gian_tao: datetime = Field(default_factory=now_vn, description="Thời điểm tạo liên kết (UTC))")

    class Settings:
        name = "tac_nhan_quyen_han"
        indexes = [
            IndexModel([("tac_nhan_id", ASCENDING), ("quyen_han_id", ASCENDING)], name="idx_tac_nhan_id_quyen_han_id", unique=True),
            IndexModel([("tac_nhan_id", ASCENDING)], name="idx_tac_nhan_id"),
            IndexModel([("quyen_han_id", ASCENDING)], name="idx_quyen_han_id"),
        ]

    class Config:
        arbitrary_types_allowed = True