import os
import random
import string
import re
from datetime import datetime, timedelta, timezone
from beanie import PydanticObjectId
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Query, status, BackgroundTasks
from pydantic import EmailStr
from bson import ObjectId
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig

from app.api.dependencies.error_codes import ErrorCode
from app.api.schemas.nguoi_dung import (
    NguoiDungCreate,
    NguoiDungCreateByAdmin,
    NguoiDungResponse,
    NguoiDungUpdate,
    NguoiDungListResponse,
    LoginRequest,
    ChangePasswordRequest,
    Token,
    ResetPasswordRequest,
    ForgotPasswordRequest,
    VerifyOTPRequest,
    VerifyOTPResponse,
    ResendOTPRequest,
    LoginOTPSentResponse,
)
from app.core.security import (
    blacklist_token,
    create_access_token,
    get_password_hash,                 
    get_current_user,
    verify_password,
    CurrentUser,
    require_permission,
    decode_jwt_token,
)
from app.core.rate_limiter import limiter
from app.models.nguoi_dung import NguoiDung
from app.models.tac_nhan import TacNhan
from app.models.nguoi_dung_tac_nhan import NguoiDungTacNhan
from logs.logging_config import logger
from app.api.dependencies.time import now_vn
from app.api.utils.text_utils import remove_accents
from app.core.config import settings


router = APIRouter()
RATE_LIMIT = os.getenv("RATE_LIMIT", "5/minute")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

#Cấu hình email
conf = ConnectionConfig(
    MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
    MAIL_FROM=os.getenv("MAIL_FROM"),
    MAIL_PORT=int(os.getenv("MAIL_PORT", 587)),
    MAIL_SERVER=os.getenv("MAIL_SERVER"),
    MAIL_STARTTLS=os.getenv("MAIL_STARTTLS", "True").lower() == "true",
    MAIL_SSL_TLS=os.getenv("MAIL_SSL_TLS", "False").lower() == "true",
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True
)


# --- Helpers ---
async def _get_user_details(user_id: PydanticObjectId) -> Optional[dict]:
    """
    Hàm helper nội bộ để lấy thông tin chi tiết của người dùng,
    bao gồm cả thông tin cơ quan và các tác nhân được gán.
    """
    try:
        pipeline = [
            {"$match": {"_id": user_id}},
            {
                "$lookup": {
                    "from": NguoiDungTacNhan.Settings.name,
                    "localField": "_id",
                    "foreignField": "nguoi_dung_id",
                    "as": "nguoi_dung_tac_nhan_info",
                }
            },
            {
                "$lookup": {
                    "from": TacNhan.Settings.name,
                    "let": {"tac_nhan_ids": "$nguoi_dung_tac_nhan_info.tac_nhan_id"},
                    "pipeline": [
                        {
                            "$match": {
                                "$expr": {"$in": ["$_id", "$$tac_nhan_ids"]},
                                "hoat_dong": True
                            }
                        }
                    ],
                    "as": "tac_nhan_details",
                }
            },
            {
                "$addFields": {
                    "id": "$_id",
                    "tac_nhan": {
                        "$map": {
                            "input": "$tac_nhan_details",
                            "as": "tn",
                            "in": {
                                "$mergeObjects": ["$$tn", {"id": "$$tn._id"}]
                            }
                        }
                    }
                }
            },
            {
                "$project": {
                    "mat_khau": 0, "otp": 0, "otp_het_han": 0, "otp_tao_luc": 0,
                    "nguoi_dung_tac_nhan_info": 0, "tac_nhan_details": 0, "tac_nhan._id": 0
                }
            },
        ]

        user_cursor = NguoiDung.aggregate(pipeline)
        user_list = await user_cursor.to_list(length=1)
        return user_list[0] if user_list else None
    except Exception as e:
        logger.error(f"Error fetching details for user_id '{user_id}': {e}", exc_info=True)
        return None

def generate_otp(length: int = 6) -> str:
    """Generate a numeric OTP of given length."""
    return "".join(random.choices(string.digits, k=length))


async def send_otp_email(email: EmailStr, otp: str, user_name: str):
    """Gửi email chứa mã OTP."""
    html_content = f"""
    <html>
    <body>
        <p>Xin chào {user_name},</p>
        <p>Mã OTP của bạn là: <strong>{otp}</strong></p>
        <p>Mã này sẽ hết hạn sau 5 phút.</p>
        <p>Nếu bạn không yêu cầu mã này, vui lòng bỏ qua email này.</p>
    </body>
    </html>
    """
    message = MessageSchema(
        subject="Mã OTP Xác Thực",
        recipients=[email],
        body=html_content,
        subtype="html"
    )
    fm = FastMail(conf)
    await fm.send_message(message)
    logger.info(f"OTP email sent to {email}")


async def send_credentials_email(email: EmailStr, password: str, user_name: str, admin_name: str):
    """
    Gửi email thông báo tài khoản đã được tạo, kèm theo mật khẩu
    """
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
    login_link = f"{FRONTEND_URL}/login"

    html_content = f"""
    <html>
    <body>
        <p>Xin chào {user_name},</p>
        <p>Một tài khoản đã được tạo cho bạn trên hệ thống Trợ Lý Ảo bởi quản trị viên <strong>{admin_name}</strong>.</p>
        <p>Bạn có thể sử dụng thông tin dưới đây để đăng nhập:</p>
        <ul>
            <li><strong>Email (Tên đăng nhập):</strong> {email}</li>
            <li><strong>Mật khẩu:</strong> <code>{password}</code></li>
        </ul>
        <p>Vui lòng <a href="{login_link}">nhấp vào đây để đăng nhập</a>.</p>
        <p><strong>Lưu ý quan trọng:</strong> Vì lý do bảo mật, bạn nên đổi mật khẩu ngay sau lần đăng nhập đầu tiên.</p>
        <p>Trân trọng,</p>
        <p>Đội ngũ Trợ Lý Ảo</p>
    </body>
    </html>
    """

    message = MessageSchema(
        subject="Thông tin tài khoản Trợ Lý Ảo",
        recipients=[email],
        body=html_content,
        subtype="html"
    )
    fm = FastMail(conf)
    await fm.send_message(message)


@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit(RATE_LIMIT)
async def register(request: Request, data: NguoiDungCreate, background_tasks: BackgroundTasks):
    try:
        email_lower = data.email.lower()
        logger.info(f"Register endpoint called for email: {email_lower}")

        email_pattern = f"^{re.escape(email_lower)}$"
        existing_user = await NguoiDung.find_one({"email": {"$regex": email_pattern, "$options": "i"}})
        if existing_user:
            if not existing_user.da_xac_thuc_email:
                logger.warning(f"Email '{data.email}' đã tồn tại nhưng chưa được xác thực. Gửi lại OTP.")
                thoi_gian_cho = timedelta(seconds=60)
                if existing_user.otp_tao_luc:
                    thoi_gian_da_troi = datetime.now(timezone.utc) - existing_user.otp_tao_luc.replace(tzinfo=timezone.utc)
                    if thoi_gian_da_troi < thoi_gian_cho:
                        giay_con_lai = int((thoi_gian_cho - thoi_gian_da_troi).total_seconds())
                        logger.warning(f"Resend OTP request for user '{email_lower}' too soon. Please wait {giay_con_lai} seconds.")
                        raise HTTPException(
                            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail=ErrorCode.TOO_MANY_REQUESTS,
                        )
                logger.info(f"User '{email_lower}' exists but not verified. Resending OTP.")
                otp = generate_otp()
                existing_user.otp = get_password_hash(otp)
                existing_user.otp_het_han = datetime.now(timezone.utc) + timedelta(minutes=5)
                existing_user.otp_tao_luc = datetime.now(timezone.utc)
                await existing_user.save()
                background_tasks.add_task(send_otp_email, existing_user.email, otp, existing_user.ten)
                logger.info(f"Resend OTP email task for '{email_lower}' added to background.")
                return {"message": "Tài khoản đã tồn tại nhưng chưa được xác thực. Mã OTP đã được gửi lại đến email của bạn."}
            logger.warning(f"Registration failed: email '{email_lower}' already exists and verified.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorCode.EMAIL_EXISTS,
            )

        hashed_password = get_password_hash(data.password)
        otp = generate_otp()
        hashed_otp = get_password_hash(otp)

        new_user = NguoiDung(
            ten=data.ten,
            email=email_lower,
            mat_khau=hashed_password,
            otp=hashed_otp,
            otp_het_han=datetime.now(timezone.utc) + timedelta(minutes=5),
            otp_tao_luc=datetime.now(timezone.utc),
            hoat_dong=False,
            da_xac_thuc_email=False,
        )
        await new_user.insert()
        logger.info(f"User '{email_lower}' created, awaiting email verification.")

        try:
            default_tac_nhan = await TacNhan.find_one(TacNhan.ten == settings.DEFAULT_ROLE_NAME)
            if not default_tac_nhan:
                logger.critical(
                    f"LỖI HỆ THỐNG: Tác nhân mặc định '{settings.DEFAULT_ROLE_NAME}' không tìm thấy."
                    f"Người dùng '{data.email}' sẽ được tạo mà không có tác nhân."
                )
            else:
                await NguoiDungTacNhan(
                    nguoi_dung_id=new_user.id,
                    tac_nhan_id=default_tac_nhan.id
                ).insert()
                logger.info(f"Đã gán tác nhân mặc định '{settings.DEFAULT_ROLE_NAME}' cho người dùng '{data.email}'.")
        except Exception as e:
            logger.error(f"Lỗi khi gán tác nhân mặc định cho người dùng '{email_lower}': {e}", exc_info=True)

        background_tasks.add_task(send_otp_email, new_user.email, otp, new_user.ten)
        logger.info(f"Send OTP email task for '{email_lower}' added to background.")

        return {"message": "Đăng ký thành công. Vui lòng kiểm tra email của bạn để xác thực tài khoản."}

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Lỗi không xác định trong quá trình đăng ký của email '{data.email}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorCode.INTERNAL_SERVER_ERROR
        )
    

@router.post("/verify-otp", response_model=VerifyOTPResponse)
@limiter.limit(RATE_LIMIT)
async def verify_otp(request: Request, data: VerifyOTPRequest):
    try:
        email_pattern = f"^{re.escape(data.email)}$"
        user = await NguoiDung.find_one({"email": {"$regex": email_pattern, "$options": "i"}})
        if not user:
            logger.warning(f"OTP verification failed: user with email '{data.email}' not found.")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ErrorCode.USER_NOT_FOUND,
            )
        
        if user.da_xac_thuc_email:
            logger.info(f"User '{data.email}' already verified.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorCode.USER_ALREADY_VERIFIED,
            )
        
        is_otp_het_han = True
        if user.otp_het_han:
            expires_at_aware = user.otp_het_han.replace(tzinfo=timezone.utc)
            if expires_at_aware >= datetime.now(timezone.utc):
                is_otp_het_han = False

        is_otp_valid = user.otp and not is_otp_het_han and verify_password(data.otp, user.otp)

        if not is_otp_valid:
            logger.warning(f"OTP verification failed for email '{data.email}': invalid or expired OTP.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorCode.INVALID_CREDENTIALS,
            )
        
        user.hoat_dong = True
        user.da_xac_thuc_email = True
        user.otp = None
        user.otp_het_han = None
        user.thoi_gian_sua = now_vn()
        await user.save()
        logger.info(f"User '{user.email}' verified successfully.")

        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.email}, expires_delta=access_token_expires
        )
        token_data = Token(access_token=access_token)

        pipeline = [
            {"$match": {"_id": user.id}},
            {"$addFields": {"id": "$_id"}},
            {"$project": {"mat_khau": 0, "otp": 0, "otp_expires_at": 0}},
        ]
        user_cursor = NguoiDung.aggregate(pipeline)
        user_details = await user_cursor.to_list(length=1)

        if not user_details:
            logger.error(f"User details not found after verification for email '{data.email}'.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ErrorCode.INTERNAL_SERVER_ERROR
            )
        
        return VerifyOTPResponse(token=token_data, user=user_details[0])
    
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error during OTP verification for email '{data.email}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorCode.INTERNAL_SERVER_ERROR
        )

@router.post("/resend-otp")
@limiter.limit(RATE_LIMIT)
async def resend_otp(request: Request, data: ResendOTPRequest, background_tasks: BackgroundTasks):
    try:
        email_pattern = f"^{re.escape(data.email)}$"
        user = await NguoiDung.find_one({"email": {"$regex": email_pattern, "$options": "i"}})
        if not user:
            logger.warning(f"Resend OTP request for non-existent user: {data.email}")
            return {"message": "Nếu email của bạn tồn tại và chưa được xác thực, mã OTP mới sẽ được gửi."}
        
        if user.da_xac_thuc_email:
            logger.info(f"User '{data.email}' already verified.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorCode.USER_ALREADY_VERIFIED,
            )
        
        thoi_gian_cho = timedelta(seconds=60)
        if user.otp_tao_luc:
            thoi_gian_da_troi = datetime.now(timezone.utc) - user.otp_tao_luc.replace(tzinfo=timezone.utc)
            if thoi_gian_da_troi < thoi_gian_cho:
                giay_con_lai = int((thoi_gian_cho - thoi_gian_da_troi).total_seconds())
                logger.warning(f"Resend OTP request for user '{data.email}' too soon. Please wait {giay_con_lai} seconds.")
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=ErrorCode.TOO_MANY_REQUESTS,
                )
        
        otp = generate_otp()
        user.otp = get_password_hash(otp)
        user.otp_het_han = datetime.now(timezone.utc) + timedelta(minutes=5)
        user.otp_tao_luc = datetime.now(timezone.utc)
        await user.save()

        background_tasks.add_task(send_otp_email, user.email, otp, user.ten)
        logger.info(f"Resent OTP email task for '{user.email}' added to background.")

        return {"message": "Mã OTP mới sẽ được gửi vào email của bạn."}
    
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error during resend OTP for email '{data.email}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorCode.INTERNAL_SERVER_ERROR
        )


@router.post("/login", response_model=VerifyOTPResponse)
@limiter.limit(RATE_LIMIT)
async def login(request: Request, data: LoginRequest):
    try:
        logger.info(f"Login attempt for email: {data.email}")
        email_pattern = f"^{re.escape(data.email)}$"
        user = await NguoiDung.find_one({"email": {"$regex": email_pattern, "$options": "i"}}, NguoiDung.hoat_dong == True)

        if not user or not verify_password(data.password, user.mat_khau):
            logger.warning(f"Invalid login attempt for email: {data.email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ErrorCode.INVALID_CREDENTIALS,
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if not user.hoat_dong or not user.da_xac_thuc_email:
            logger.warning(f"Login attempt for inactive or unverified user: {data.email}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ErrorCode.USER_NOT_VERIFIED,
            )

        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.email}, expires_delta=access_token_expires
        )
        token_data = Token(access_token=access_token)
        logger.info(f"User '{user.email}' logged in successfully.")

        pipeline = [
            {"$match": {"_id": user.id}},
            {"$addFields": {"id": "$_id"}},
            {"$project": {"mat_khau": 0, "otp": 0, "otp_expires_at": 0}},
        ]
        user_cursor = NguoiDung.aggregate(pipeline)
        user_data = await user_cursor.to_list(length=1)
        if not user_data:
            logger.error(f"User details not found after login for email '{data.email}'.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ErrorCode.INTERNAL_SERVER_ERROR
            )

        return VerifyOTPResponse(token=token_data, user=user_data[0])

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error during login for email '{data.email}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorCode.INTERNAL_SERVER_ERROR
        )


# --- ĐĂNG XUẤT ---
@router.post("/logout")
async def logout(
    request: Request, current_user: CurrentUser = Depends(get_current_user)
):
    try:
        logger.info(f"Logout endpoint called for user: {current_user.email}")
        auth_header = request.headers.get("authorization", "")
        token = auth_header.replace("Bearer ", "").strip()

        if token:
            blacklist_token(token)
            logger.info(f"Token blacklisted for user: {current_user.email}")

        return {"msg": "Đăng xuất thành công"}
    except Exception as e:
        logger.error(f"Error during logout for user '{current_user.email}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorCode.INTERNAL_SERVER_ERROR
        )


# --- ĐỔI MẬT KHẨU ---
@router.post("/change-password", response_model=NguoiDungResponse)
async def change_password(
    request: Request,
    data: ChangePasswordRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        if not verify_password(data.old_password, current_user.mat_khau):
            logger.warning(f"Invalid old password for user: {current_user.email}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorCode.INVALID_CREDENTIALS,
            )


        user_doc = await NguoiDung.get(current_user.id)
        user_doc.mat_khau = get_password_hash(data.new_password)
        user_doc.thoi_gian_sua = now_vn()
        await user_doc.save()
        logger.info(f"Password changed successfully for user: {current_user.email}")
        return await _get_user_details(user_doc.id)


    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error changing password for user '{current_user.email}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorCode.INTERNAL_SERVER_ERROR,
        )


@router.get("/me", response_model=NguoiDungResponse)
async def read_users_me(current_user: CurrentUser = Depends(get_current_user)):
    user_details = await _get_user_details(current_user.id)
    if not user_details:
        logger.error(f"Could not find details for currently logged-in user '{current_user.email}'.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ErrorCode.USER_NOT_FOUND)
    return user_details

# --- QUÊN MẬT KHẨU ---
@router.post("/forgot-password")
async def forgot_password(request: Request, data: ForgotPasswordRequest, background_tasks: BackgroundTasks):
    try:
        logger.info(f"Forgot password request for email: {data.email}")
        email_pattern = f"^{re.escape(data.email)}$"
        user = await NguoiDung.find_one({"email": {"$regex": email_pattern, "$options": "i"}}, NguoiDung.hoat_dong == True)
        if not user:
            logger.warning(f"User not found for email: {data.email}")
            return {"msg": "Nếu email của bạn đã được đăng ký, bạn sẽ nhận được một liên kết đặt lại mật khẩu."}
        
        reset_token_expires = timedelta(minutes=15)
        reset_token = create_access_token(
            data={"sub": user.email, "scope": "password_reset"}, expires_delta=reset_token_expires
        )

        FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
        reset_link = f"{FRONTEND_URL}/reset-password?token={reset_token}"

        html_content = f"""
        <html>
        <body>
            <p>Xin chào {user.ten},</p>
            <p>Bạn đã yêu cầu đặt lại mật khẩu. Vui lòng nhấp vào liên kết bên dưới để đặt lại mật khẩu của bạn:</p>
            <p><a href="{reset_link}">Đặt lại mật khẩu</a></p>
            <p>Liên kết này sẽ hết hạn sau 15 phút.</p>
            <p>Nếu bạn không yêu cầu điều này, vui lòng bỏ qua email này.</p>
        </body>
        </html>
        """

        message = MessageSchema(
            subject="Yêu cầu đặt lại mật khẩu",
            recipients=[user.email],
            body=html_content,
            subtype="html"
        )

        fm = FastMail(conf)
        background_tasks.add_task(fm.send_message, message)
        logger.info(f"Password reset link email task for '{user.email}' added to background.")
        return {"msg": "Nếu email của bạn đã được đăng ký, bạn sẽ nhận được một liên kết đặt lại mật khẩu."}
    
    except Exception as e:
        logger.error(f"Error during forgot password for email '{data.email}': {e}", exc_info=True)
        return {"msg": "Đã xảy ra lỗi. Yêu cầu thử lại sau."}
    

@router.post("/reset-password")
async def reset_password(request: Request, data: ResetPasswordRequest):
    email = None
    try:
        payload = decode_jwt_token(data.token)
        if not payload or payload.get("scope") != "password_reset":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorCode.RESET_TOKEN_INVALID,
            )
        
        email_from_token: str = payload.get("sub")
        if not email_from_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorCode.RESET_TOKEN_INVALID,
            )
        email = email_from_token

        expire_time = payload.get("exp")
        if not expire_time or datetime.fromtimestamp(expire_time) < datetime.now():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorCode.TOKEN_EXPIRED,
            )
        
        user = await NguoiDung.find_one(NguoiDung.email == email, NguoiDung.hoat_dong == True)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ErrorCode.USER_NOT_FOUND,
            )
        
        user.mat_khau = get_password_hash(data.new_password)
        user.thoi_gian_sua = now_vn()
        await user.save()
        
        logger.info(f"Password reset successfully for email: {email}")
        return {"msg": "Đặt lại mật khẩu thành công"}
    
    except HTTPException as e:
        raise e
    except Exception as e:
        error_email = email if email else "unknown"
        logger.error(f"Error during reset password for email '{error_email}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorCode.INTERNAL_SERVER_ERROR,
        )


# --- CREATE NGƯỜI DÙNG BY ADMIN ---
@router.post("/", response_model=NguoiDungResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(RATE_LIMIT)
async def create_user_by_admin(
    request: Request,
    data: NguoiDungCreateByAdmin,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(require_permission("nguoi_dung:create")),
):
    try:
        email_lower = data.email.lower()
        logger.info(f"Admin '{current_user.email}' is creating a new user with email: {email_lower}")

        email_pattern = f"^{re.escape(email_lower)}$"
        existing_user = await NguoiDung.find_one({"email": {"$regex": email_pattern, "$options": "i"}})
        if existing_user:
            logger.warning(f"Admin user creation failed: email '{email_lower}' already exists.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorCode.EMAIL_EXISTS,
            )
        hashed_password = get_password_hash(data.password)

        new_user = NguoiDung(
            ten=data.ten,
            email=email_lower,
            mat_khau=hashed_password,
            hoat_dong=True,
            da_xac_thuc_email=True,
        )
        await new_user.insert()
        logger.info(f"User '{email_lower}' created successfully by admin '{current_user.email}'.")

        try:
            if data.tac_nhan_ids:
                valid_tac_nhans = await TacNhan.find({"_id": {"$in": data.tac_nhan_ids}}).to_list()

                if len(valid_tac_nhans) != len(data.tac_nhan_ids):
                    valid_ids = {tn.id for tn in valid_tac_nhans}
                    invalid_ids = [uid for uid in data.tac_nhan_ids if uid not in valid_ids]
                    logger.warning(f"Admin sent invalid tac_nhan_ids for user {email_lower}: {invalid_ids}")

                if valid_tac_nhans:
                    user_tac_nhan_links = [
                        NguoiDungTacNhan(
                            nguoi_dung_id=new_user.id, 
                            tac_nhan_id=tn.id
                        ) for tn in valid_tac_nhans
                    ]
                    if user_tac_nhan_links:
                        await NguoiDungTacNhan.insert_many(user_tac_nhan_links)
                    logger.info(f"Assigned {len(user_tac_nhan_links)} roles to user '{email_lower}'.")
                else:
                    logger.warning("No valid roles found from input IDs.")

            else:
                default_tac_nhan = await TacNhan.find_one(TacNhan.ten == settings.DEFAULT_ROLE_NAME)
                if not default_tac_nhan:
                    logger.critical(
                        f"LỖI HỆ THỐNG: Tác nhân mặc định '{settings.DEFAULT_ROLE_NAME}' không tìm thấy."
                        f"Người dùng '{data.email}' (do admin tạo) sẽ được tạo mà không có tác nhân."
                    )
                else:
                    await NguoiDungTacNhan(
                        nguoi_dung_id=new_user.id,
                        tac_nhan_id=default_tac_nhan.id,
                    ).insert()
                    logger.info(f"Đã gán tác nhân mặc định '{settings.DEFAULT_ROLE_NAME}' cho người dùng '{data.email}' (do admin tạo).")
        except Exception as e:
            logger.error(f"Lỗi khi gán tác nhân mặc định cho người dùng '{email_lower}' (do admin tạo): {e}", exc_info=True)

        background_tasks.add_task(
            send_credentials_email,
            email=new_user.email,
            password=data.password,
            user_name=new_user.ten,
            admin_name=current_user.ten,
        )
        logger.info(f"Send credentials email task for '{email_lower}' added to background.")

        return await get_user_by_id(new_user.id, current_user)
    
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error creating user with email '{data.email}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorCode.INTERNAL_SERVER_ERROR
        )


# --- User Management Routes ---
@router.get("/", response_model=NguoiDungListResponse)
async def get_all_users(
    page: int = Query(1, ge=1, description="Số trang"),
    size: int = Query(10, ge=1, le=100, description="Số lượng kết quả mỗi trang"),
    current_user: CurrentUser = Depends(require_permission("nguoi_dung:view")),
):
    try:
        skip = (page - 1) * size
        pipeline = [
            {"$match": {"hoat_dong": True}},
            {
                "$lookup": {
                    "from": NguoiDungTacNhan.Settings.name,
                    "localField": "_id",
                    "foreignField": "nguoi_dung_id",
                    "as": "nguoi_dung_tac_nhan_info",
                }
            },
            {
                "$lookup": {
                    "from": TacNhan.Settings.name,
                    "let": {"tac_nhan_ids": "$nguoi_dung_tac_nhan_info.tac_nhan_id"},
                    "pipeline": [
                        {
                            "$match": {
                                "$expr": {"$in": ["$_id", "$$tac_nhan_ids"]},
                                "hoat_dong": True 
                            }
                        }
                    ],
                    "as": "tac_nhan_details",
                }
            },
            {
                "$addFields": {
                    "id": "$_id",
                    "tac_nhan": {
                        "$map": {
                            "input": "$tac_nhan_details",
                            "as": "tn",
                            "in": {
                                "$mergeObjects": ["$$tn", {"id": "$$tn._id"}]
                            }
                        }
                    }
                }
            },
            {
                "$project": {
                    "mat_khau": 0, "otp": 0, "otp_het_han": 0, "otp_tao_luc": 0,
                    "nguoi_dung_tac_nhan_info": 0, "tac_nhan_details": 0, "tac_nhan._id": 0
                }
            },
            {"$skip": skip},
            {"$limit": size},
        ]

        users_cursor = NguoiDung.aggregate(pipeline)
        users = await users_cursor.to_list(length=size)

        total_users = await NguoiDung.find({"hoat_dong": True}).count()

        return {"nguoi_dung": users, "total": total_users, "page": page, "size": size}
    except Exception as e:
        logger.error(f"Error fetching all users: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorCode.INTERNAL_SERVER_ERROR
        )


@router.get("/{user_id}", response_model=NguoiDungResponse)
async def get_user_by_id(
    user_id: PydanticObjectId,
    current_user: CurrentUser = Depends(require_permission("nguoi_dung:view")),
):
        user_details = await _get_user_details(user_id)
        if not user_details or not user_details.get("hoat_dong", False):
            logger.warning(f"User with ID '{user_id}' not found or inactive.")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ErrorCode.USER_NOT_FOUND,
            )
        return user_details


@router.put("/{user_id}", response_model=NguoiDungResponse)
@limiter.limit(RATE_LIMIT)
async def update_user(
    request: Request,
    user_id: PydanticObjectId,
    user_in: NguoiDungUpdate,
    current_user: CurrentUser = Depends(require_permission("nguoi_dung:edit")),
):
    try:
        user = await NguoiDung.find_one({"_id": user_id, "hoat_dong": True})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ErrorCode.USER_NOT_FOUND,
            )

        update_data = user_in.model_dump(exclude_unset=True)
        if not update_data:
            return await get_user_by_id(user_id, current_user)

        logger.info(f"User '{current_user.email}' is updating user ID '{user_id}' with data: {update_data}.")
        for key, value in update_data.items():
            setattr(user, key, value)

        user.thoi_gian_sua = now_vn()
        await user.save()
        logger.info(f"User ID '{user_id}' updated successfully.")
        return await get_user_by_id(user_id, current_user)
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error updating user ID '{user_id}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorCode.INTERNAL_SERVER_ERROR
        )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(RATE_LIMIT)
async def delete_user(
    request: Request,
    user_id: PydanticObjectId,
    current_user: CurrentUser = Depends(require_permission("nguoi_dung:delete")),
):
    try:
        logger.info(f"User '{current_user.email}' is attempting to delete user ID '{user_id}'.")
        user = await NguoiDung.find_one({"_id": user_id, "hoat_dong": True})
        if not user:
            logger.warning(f"Attempt to delete non-existent user ID '{user_id}'.")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ErrorCode.USER_NOT_FOUND,
            )
        
        user.hoat_dong = False
        user.thoi_gian_sua = now_vn()
        await user.save()
        logger.info(f"User {user_id} deleted by {current_user.email}")
        return None
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error deleting user ID '{user_id}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorCode.INTERNAL_SERVER_ERROR
        )

