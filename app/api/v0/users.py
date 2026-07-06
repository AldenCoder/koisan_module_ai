# import os
# from datetime import datetime, timedelta, timezone
# from typing import Optional

# from dotenv import load_dotenv
# from fastapi import APIRouter, Depends, HTTPException
# from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
# from jose import JWTError, jwt

# from app.api.schemas.users import (
#     LoginRequest,
#     LoginResponse,
#     RegisterRequest,
#     TokenData,
#     UserResponse,
#     UserUpdate,
# )

# load_dotenv()
# SECRET_KEY = os.getenv("SECRET_KEY")
# ALGORITHM = "HS256"

# router = APIRouter()
# security = HTTPBearer()


# def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
#     to_encode = data.copy()
#     expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
#     to_encode.update({"exp": expire})
#     encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
#     return encoded_jwt


# def get_current_user(
#     credentials: HTTPAuthorizationCredentials = Depends(security),
# ) -> TokenData:
#     token = credentials.credentials
#     try:
#         payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
#         user_id = payload.get("sub")
#         email = payload.get("email")
#         role = payload.get("role")
#         shop_id = payload.get("shop_id")
#         user_name = payload.get(
#             "user_name", email.split("@")[0]
#         )  # Lấy từ payload hoặc tạo từ email

#         if user_id is None or email is None or role is None:
#             raise HTTPException(status_code=401, detail="Invalid token payload")

#         return TokenData(
#             user_id=user_id,
#             email=email,
#             role=role,
#             shop_id=shop_id,
#             user_name=user_name,
#         )
#     except JWTError:
#         raise HTTPException(status_code=401, detail="Invalid token")


# @router.post("/register", response_model=UserResponse)
# async def register(data: RegisterRequest):
#     try:
#         if data.email == "exists@example.com":
#             raise HTTPException(status_code=400, detail="Email already exists")

#         user_id = "user_" + datetime.now().strftime("%Y%m%d%H%M%S")
#         now = datetime.now(timezone.utc)

#         address_id = None
#         address_data = None
#         if data.address:
#             address_id = "addr_" + datetime.now().strftime("%Y%m%d%H%M%S")

#             address_data = UserAddressResponse(
#                 id=address_id,
#                 name=data.address.name or data.user_name,
#                 addressable_type="user",
#                 user_id=user_id,
#                 phone_number=data.address.phone_number,
#                 province_code=data.address.province_code or "",
#                 province_name=data.address.province_name or "",
#                 district_code=data.address.district_code or "",
#                 district_name=data.address.district_name or "",
#                 ward_code=data.address.ward_code or "",
#                 ward_name=data.address.ward_name or "",
#                 address=data.address.address or "",
#                 created_at=now,
#                 updated_at=now,
#             )

#         return UserResponse(
#             user_id=user_id,
#             user_name=data.user_name,
#             address_id=address_id,
#             shop_id=data.shop_id,
#             email=data.email,
#             role=data.role,
#             work_shift=data.work_shift,
#             address=address_data,
#         )
#     except HTTPException as e:
#         raise e
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# ACCESS_TOKEN_EXPIRE_MINUTES = 60


# @router.post("/login", response_model=LoginResponse)
# async def login(data: LoginRequest):
#     # if data.email != "alden@example.com" or data.password != "alden":
#     #     raise HTTPException(status_code=401, detail="Invalid credentials")

#     access_token = create_access_token(
#         data={
#             "sub": "user123",
#             "email": "admin@example.com",
#             "role": 1,
#             "shop_id": "shop123",
#         },
#         expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
#     )

#     return LoginResponse(
#         access_token=access_token,
#         token_type="bearer",
#         user_id="user123",
#         shop_id="shop123",
#         role=1,
#         user_name="admin",
#         email="admin@example.com",
#     )


# @router.post("/logout", response_model=UserResponse)
# async def logout(current_user: TokenData = Depends(get_current_user)):
#     return UserResponse(user_id=str(current_user.user_id))


# @router.get("/", response_model=list[UserResponse])
# async def get_users():
#     users = []
#     users.append(
#         UserResponse(
#             user_id="user_admin",
#             user_name="Admin User",
#             email="admin@example.com",
#             role=0,  # Admin role
#             work_shift="day",
#         )
#     )

#     for i in range(9):
#         users.append(
#             UserResponse(
#                 user_id=f"user_{i}",
#                 user_name=f"User {i}",
#                 email=f"user{i}@example.com",
#                 role=(i % 4) + 1,
#                 work_shift="day" if i % 2 == 0 else "night",
#             )
#         )

#     return users


# @router.get("/{user_id}", response_model=UserResponse)
# async def get_user(user_id: str, current_user: TokenData = Depends(get_current_user)):
#     return UserResponse(
#         user_id="user_id",
#         user_name="hello",
#         email="hello@gmail.com",
#         role=1,
#         work_shift="day",
#     )


# @router.put("/{user_id}", response_model=UserResponse)
# async def update_user(user_id: str, data: UserUpdate):
#     return UserResponse(
#         user_id="user_id",
#         user_name="hello",
#         email="hello@gmail.com",
#         role=1,
#         work_shift="day",
#     )


# @router.delete("/{user_id}", response_model=UserResponse)
# async def delete_user(user_id: str):
#     return UserResponse(
#         user_id="user_id",
#         user_name="hello",
#         email="hello@gmail.com",
#         role=1,
#         work_shift="day",
#     )
