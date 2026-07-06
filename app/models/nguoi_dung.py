from datetime import datetime
from typing import Optional

from beanie import Document
from pydantic import EmailStr, Field
from pymongo import IndexModel, ASCENDING

from app.api.dependencies.time import now_vn


class NguoiDung(Document):
    ten: str = Field(..., max_length=100, description="Tên đầy đủ của người dùng")
    ten_khong_dau: Optional[str] = Field(default=None, max_length=100, description="Tên không dấu để tìm kiếm")
    email: EmailStr = Field(..., description="Địa chỉ email duy nhất của người dùng")
    mat_khau: str = Field(..., description="Mật khẩu đã được mã hóa của người dùng")
    hoat_dong: bool = Field(default=False, description="Trạng thái hoạt động của tài khoản")
    thoi_gian_tao: datetime = Field(default_factory=now_vn, description="Thời điểm tài khoản được tạo")
    thoi_gian_sua: datetime = Field(default_factory=now_vn, description="Thời điểm thông tin tài khoản được cập nhật lần cuối",)
    otp: Optional[str] = Field(default=None, description="Mã OTP cho xác thực hai yếu tố")
    otp_het_han: Optional[datetime] = Field(default=None, description="Thời điểm mã OTP hết hạn")
    otp_tao_luc: Optional[datetime] = Field(default=None, description="Thời điểm mã OTP được tạo")
    da_xac_thuc_email: bool = Field(default=False, description="Trạng thái xác thực email của người dùng")

    class Settings:
        name = "nguoi_dung"
        indexes = [
            IndexModel([("email", ASCENDING)], name="idx_email_unique", unique=True),
            IndexModel([("ten", ASCENDING)], name="idx_ten"),
        ]

    class Config:
        arbitrary_types_allowed = True
