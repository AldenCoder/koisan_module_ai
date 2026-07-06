from datetime import datetime
from typing import Optional, List
from beanie import PydanticObjectId
from pydantic import BaseModel, Field
from app.api.schemas.quyen_han import QuyenHanResponse

class TacNhanBase(BaseModel):
    ten: str = Field(..., max_length=100, description="Tên của tác nhân")
    mo_ta: Optional[str] = Field(default=None, max_length=150, description="Mô tả chi tiết về tác nhân")

class TacNhanCreate(TacNhanBase):
    pass

class TacNhanUpdate(BaseModel):
    ten: Optional[str] = Field(default=None, max_length=100, description="Tên tác nhân")
    mo_ta: Optional[str] = Field(default=None, max_length=150, description="Mô tả")
    quyen_han_ids: Optional[List[PydanticObjectId]] = Field(default=None, description="Danh sách ID quyền hạn")

class TacNhanResponse(TacNhanBase):
    id: PydanticObjectId = Field(..., description="ID của tác nhân")
    thoi_gian_tao: datetime = Field(..., description="Thời điểm tạo (UTC)")
    thoi_gian_sua: datetime = Field(..., description="Thời điểm cập nhật lần cuối (UTC)")
    quyen_han: List[QuyenHanResponse] = Field(default_factory=list, description="Danh sách quyền hạn liên quan đến tác nhân")

    class Config:
        from_attributes = True
        arbitrary_types_allowed = True

class TacNhanListResponse(BaseModel):
    items: List[TacNhanResponse]
    total: int
    page: int
    size: int