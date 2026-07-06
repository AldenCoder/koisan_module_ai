from datetime import datetime, timezone
from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel, ASCENDING
from app.api.dependencies.time import now_vn

class NguoiDungTacNhan(Document):
    nguoi_dung_id: PydanticObjectId = Field(..., description="ID của người dùng")
    tac_nhan_id: PydanticObjectId = Field(..., description="ID của tác nhân")
    thoi_gian_tao: datetime = Field(default_factory=now_vn, description="Thời điểm tạo liên kết (UTC)")

    class Settings:
        name = "nguoi_dung_tac_nhan"
        indexes = [
            IndexModel([("nguoi_dung_id", ASCENDING), ("tac_nhan_id", ASCENDING)], name="idx_nguoi_dung_id_tac_nhan_id", unique=True),
            IndexModel([("nguoi_dung_id", ASCENDING)], name="idx_nguoi_dung_id"),
            IndexModel([("tac_nhan_id", ASCENDING)], name="idx_tac_nhan_id"),
        ]

    class Config:
        arbitrary_types_allowed = True