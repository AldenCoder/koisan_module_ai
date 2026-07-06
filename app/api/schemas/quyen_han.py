from datetime import datetime
from typing import Optional, List
from beanie import PydanticObjectId
from pydantic import BaseModel, Field

class QuyenHanBase(BaseModel):
    ten: str = Field(..., max_length=100, description="Tên quyền hạn")
    mo_ta: Optional[str] = Field(None, max_length=150, description="Mô tả chi tiết về quyền hạn")

class QuyenHanCreate(QuyenHanBase):
    pass

class QuyenHanUpdate(BaseModel):
    ten: Optional[str] = Field(None, max_length=100)
    mo_ta: Optional[str] = Field(None, max_length=150)

class QuyenHanResponse(QuyenHanBase):
    id: PydanticObjectId = Field(..., description="ID của quyền hạn")
    thoi_gian_tao: datetime
    thoi_gian_sua: datetime

    class Config:
        from_attributes = True
        arbitrary_types_allowed = True

class QuyenHanListResponse(BaseModel):
    items: List[QuyenHanResponse]
    total: int
    page: int
    size: int