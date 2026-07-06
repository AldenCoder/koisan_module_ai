from datetime import datetime
from typing import Optional
from beanie import Document
from pydantic import Field
from pymongo import IndexModel, ASCENDING
from app.api.dependencies.time import now_vn

class TacNhan(Document):
    ten: str = Field(..., max_length=100, description="Tên của tác nhân")
    mo_ta: Optional[str] = Field(default=None, max_length=150, description="Mô tả chi tiết về tác nhân")
    hoat_dong: bool = Field(default=True, description="Trạng thái hoạt động của tác nhân")
    mac_dinh: bool = Field(default=False, description="Đánh dấu tác nhân được tạo bởi hệ thống")
    thoi_gian_tao: datetime = Field(default_factory=now_vn, description="Thời điểm tạo tác nhân")
    thoi_gian_sua: datetime = Field(default_factory=now_vn, description="Thời điẻm cập nhật tác nhân lần cuối")

    class Settings:
        name = "tac_nhan"
        indexes = [
            IndexModel([("ten", ASCENDING)], unique=True),
            IndexModel([("mac_dinh", ASCENDING)]),
            IndexModel([("thoi_gian_tao", ASCENDING)]),
        ]

    class Config:
        arbitrary_types_allowed = True