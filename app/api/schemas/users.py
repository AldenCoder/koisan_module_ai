from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel, EmailStr, field_validator, model_validator

from app.api.dependencies.error_codes import ErrorCode



class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    username: str
    # address: Optional[AddressCreate] = None


class TokenData(BaseModel):
    user_id: str



class RegisterRequest(BaseModel):
    username: str
    password: str

    @field_validator("password")
    def validate_password(cls, v):
        if len(v) < 6:
            raise HTTPException(
                status_code=400, detail=ErrorCode.PASSWORD_MUST_BE_AT_LEAST_6_CHARACTERS
            )
        return v


class UserResponse(BaseModel):
    id: str
    username: Optional[str] = None


class UserUpdate(BaseModel):
    username: Optional[str] = None

    @field_validator("username")
    def validate_user_name(cls, v):
        if " " in v:
            raise HTTPException(
                status_code=400, detail=ErrorCode.USERNAME_MUST_NOT_CONTAIN_SPACES
            )
        if len(v) < 6:
            raise HTTPException(
                status_code=400, detail=ErrorCode.USERNAME_MUST_BE_AT_LEAST_6_CHARACTERS
            )
        return v


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str
    confirm_new_password: str

    @field_validator("new_password")
    def validate_new_password(cls, v):
        if len(v) < 6:
            raise HTTPException(
                status_code=400, detail=ErrorCode.PASSWORD_MUST_BE_AT_LEAST_6_CHARACTERS
            )
        return v

    @model_validator(mode="after")
    def passwords_match(self):
        if self.new_password != self.confirm_new_password:
            raise HTTPException(status_code=400, detail=ErrorCode.PASSWORD_MISMATCH)
        return self


class UserListResponse(BaseModel):
    users: list[UserResponse]
    total: int
    page: int
    size: int