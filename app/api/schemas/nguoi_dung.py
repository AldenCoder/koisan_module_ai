from typing import Optional, List
from datetime import datetime
from beanie import PydanticObjectId
from fastapi import HTTPException
from pydantic import BaseModel, EmailStr, field_validator, model_validator, Field
from app.api.dependencies.error_codes import ErrorCode
from app.api.schemas.tac_nhan import TacNhanResponse

class NguoiDungBase(BaseModel):
    email: EmailStr = Field(..., description="Email của người dùng, phải là duy nhất.")
    ten: str = Field(..., max_length=100, description="Tên đầy đủ của người dùng.")

    @field_validator("email")
    def validate_email_domain(cls, v):
        allowed_domains = (".com", ".vn")
        if not any(v.endswith(d) for d in allowed_domains):
            raise HTTPException(
                status_code=400, detail=ErrorCode.EMAIL_DOMAIN_NOT_ALLOWED)
        return v

class NguoiDungCreate(NguoiDungBase):
    password: str = Field(..., description="Mật khẩu của người dùng.")

    @field_validator("password")
    def validate_password(cls, v):
        if " " in v:
            raise HTTPException(
                status_code=400, detail=ErrorCode.PASSWORD_MUST_NOT_CONTAIN_SPACES
            )
        if len(v) < 6:
            raise HTTPException(
                status_code=400,
                detail=ErrorCode.PASSWORD_MUST_BE_AT_LEAST_6_CHARACTERS,
            )
        return v

class NguoiDungCreateByAdmin(NguoiDungCreate):
    tac_nhan_ids: Optional[List[PydanticObjectId]] = Field(
        default=None, 
        description="Danh sách ID các tác nhân (roles) muốn gán cho user."
    )

class NguoiDungUpdate(BaseModel):
    ten: Optional[str] = Field(None, max_length=100)
    hoat_dong: Optional[bool] = None


class NguoiDungResponse(NguoiDungBase):
    id: PydanticObjectId = Field(..., description="ID của người dùng trong MongoDB.")
    hoat_dong: bool = Field(..., description="Trạng thái hoạt động của tài khoản.")
    ten_khong_dau: Optional[str] = Field(None, description="Tên không dấu để tìm kiếm.")
    thoi_gian_tao: datetime = Field(..., description="Thời điểm tài khoản được tạo.")
    thoi_gian_sua: datetime = Field(..., description="Thời điểm thông tin tài khoản được cập nhật lần cuối.")
    tac_nhan: Optional[List[TacNhanResponse]] = Field(None, description="Danh sách tác nhân liên quan đến người dùng.")


    class Config:
        from_attributes = True
        arbitrary_types_allowed = True


class NguoiDungListResponse(BaseModel):
    nguoi_dung: list[NguoiDungResponse]
    total: int
    page: int
    size: int


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    # user_id: Optional[str] = None
    email: Optional[str] = None

# class LoginResponse(BaseModel):
#     access_token: str
#     token_type: str = "bearer"
#     user_id: str
#     username: str
#     # address: Optional[AddressCreate] = None


# class RegisterRequest(BaseModel):
#     username: str
#     password: str

#     @field_validator("password")
#     def validate_password(cls, v):
#         if len(v) < 6:
#             raise HTTPException(
#                 status_code=400, detail=ErrorCode.PASSWORD_MUST_BE_AT_LEAST_6_CHARACTERS
#             )
#         return v


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str
    confirm_new_password: str

    @field_validator("new_password")
    def validate_new_password_length(cls, v):
        if len(v) < 6:
            raise HTTPException(
                status_code=400,
                detail=ErrorCode.PASSWORD_MUST_BE_AT_LEAST_6_CHARACTERS,
            )
        return v

    @model_validator(mode="after")
    def check_passwords_match(self):
        if self.new_password != self.confirm_new_password:
            raise HTTPException(
                status_code=400,
                detail=ErrorCode.PASSWORD_MISMATCH,
            )
        return self
    

class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
    confirm_new_password: str

    @field_validator("new_password")
    def validate_new_password_length(cls, v):
        if len(v) < 6:
            raise HTTPException(
                status_code=400,
                detail=ErrorCode.PASSWORD_MUST_BE_AT_LEAST_6_CHARACTERS,
            )
        return v

    @model_validator(mode="after")
    def check_passwords_match(self):
        if self.new_password != self.confirm_new_password:
            raise HTTPException(
                status_code=400,
                detail=ErrorCode.PASSWORD_MISMATCH,
            )
        return self
    

class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6, description="Mã OTP được gửi đến email của người dùng.")


class ResendOTPRequest(BaseModel):
    email: EmailStr


class LoginOTPSentResponse(BaseModel):
    message: str


class VerifyOTPResponse(BaseModel):
    token: Token
    user: NguoiDungResponse





