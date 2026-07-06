from datetime import datetime
from typing import Optional
from beanie import Document
from pydantic import Field
from pymongo import IndexModel, ASCENDING
from app.api.dependencies.time import now_vn

class QuyenHan(Document):
    ten: str = Field(..., max_length=100, description="Tên quyền hạn")
    mo_ta: Optional[str] = Field(default=None, max_length=150, description="Mô tả chi tiết về quyền hạn")
    hoat_dong: bool = Field(default=True, description="Trạng thái hoạt động của quyền hạn")
    thoi_gian_tao: datetime = Field(default_factory=now_vn, description="Thời điểm tạo quyền hạn")
    thoi_gian_sua: datetime = Field(default_factory=now_vn, description="Thời điẻm cập nhật quyền hạn lần cuối")

    class Settings:
        name = "quyen_han"
        indexes = [
            IndexModel([("ten", ASCENDING)], name="idx_ten_quyen_han", unique=True),
        ]

    class Config:
        arbitrary_types_allowed = True