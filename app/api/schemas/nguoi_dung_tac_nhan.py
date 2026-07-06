from datetime import datetime
from beanie import PydanticObjectId
from pydantic import BaseModel, Field


class NguoiDungTacNhanBase(BaseModel):
    nguoi_dung_id: PydanticObjectId = Field(..., description="ID người dùng")
    tac_nhan_id: PydanticObjectId = Field(..., description="ID tác nhân")


class NguoiDungTacNhanCreate(NguoiDungTacNhanBase):
    """Schema tạo mới liên kết người dùng ↔ tác nhân (thường dùng nội bộ)."""
    pass


class NguoiDungTacNhanResponse(NguoiDungTacNhanBase):
    id: PydanticObjectId = Field(..., description="ID liên kết")
    thoi_gian_tao: datetime = Field(..., description="Thời điểm tạo")
    thoi_gian_sua: datetime = Field(..., description="Thời điểm cập nhật lần cuối")

    class Config:
        from_attributes = True
        arbitrary_types_allowed = True
