import os
from typing import List, Optional
from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from fastapi.responses import JSONResponse
from app.core.security import get_current_user, require_permission, CurrentUser
from app.core.rate_limiter import limiter
from app.api.dependencies.error_codes import ErrorCode
from app.models.nguoi_dung import NguoiDung
from app.models.tac_nhan import TacNhan
from app.models.nguoi_dung_tac_nhan import NguoiDungTacNhan
from app.models.tac_nhan_quyen_han import TacNhanQuyenHan
from app.api.schemas.tac_nhan import TacNhanResponse, TacNhanListResponse
from app.api.dependencies.time import now_vn

router = APIRouter()
RATE_LIMIT = os.getenv("RATE_LIMIT", "5/minute")


# --------- Helpers ---------
async def _ensure_user_exists(user_id: PydanticObjectId) -> NguoiDung:
    user = await NguoiDung.get(user_id)
    if not user or not user.hoat_dong:
        raise HTTPException(status_code=404, detail=ErrorCode.USER_NOT_FOUND)
    return user

async def _ensure_agent_exists(agent_id: PydanticObjectId) -> TacNhan:
    agent = await TacNhan.get(agent_id)
    if not agent or not agent.hoat_dong:
        raise HTTPException(status_code=404, detail=ErrorCode.TAC_NHAN_NOT_FOUND)
    return agent

async def _cleanup_orphan_agent(agent_id: PydanticObjectId):
    remain = await NguoiDungTacNhan.find(
        NguoiDungTacNhan.tac_nhan_id == agent_id
    ).count()
    if remain == 0:
        agent_to_deactivate = await TacNhan.get(agent_id)
        if agent_to_deactivate:
            agent_to_deactivate.hoat_dong = False
            agent_to_deactivate.thoi_gian_sua = now_vn()
            await agent_to_deactivate.save()


# ------------------------------------------------------------
# GÁN TÁC NHÂN VÀO NGƯỜI DÙNG
# ------------------------------------------------------------
@router.post("/{user_id}/assign/{tac_nhan_id}")
@limiter.limit(RATE_LIMIT)
async def assign_agent_to_user(
    request: Request,
    user_id: PydanticObjectId,
    tac_nhan_id: PydanticObjectId,
    current_user: CurrentUser = Depends(require_permission("nguoi_dung:edit")),
):
    await _ensure_user_exists(user_id)
    await _ensure_agent_exists(tac_nhan_id)

    existed = await NguoiDungTacNhan.find_one({
        "nguoi_dung_id": user_id,
        "tac_nhan_id": tac_nhan_id,
    })
    if existed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ErrorCode.BAD_REQUEST
        )

    await NguoiDungTacNhan(nguoi_dung_id=user_id, tac_nhan_id=tac_nhan_id).insert()
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"message": "Gán tác nhân cho người dùng thành công."}
    )


# ------------------------------------------------------------
# GỠ TÁC NHÂN KHỎI NGƯỜI DÙNG
# ------------------------------------------------------------
@router.post("/{user_id}/unassign/{tac_nhan_id}")
@limiter.limit(RATE_LIMIT)
async def unassign_agent_from_user(
    request: Request,
    user_id: PydanticObjectId,
    tac_nhan_id: PydanticObjectId,
    current_user: CurrentUser = Depends(require_permission("nguoi_dung:edit")),
):
    await _ensure_user_exists(user_id)
    await _ensure_agent_exists(tac_nhan_id)

    link = await NguoiDungTacNhan.find_one({
        "nguoi_dung_id": user_id,
        "tac_nhan_id": tac_nhan_id,
    })
    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorCode.NOT_FOUND
        )
        
    await link.delete()
    await _cleanup_orphan_agent(tac_nhan_id)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "Gỡ tác nhân cho người dùng thành công."}
    )


# ------------------------------------------------------------
# LIỆT KÊ TÁC NHÂN CỦA 1 NGƯỜI DÙNG
# ------------------------------------------------------------
@router.get("/{user_id}/tac-nhan", response_model=TacNhanListResponse)
async def list_agents_of_user(
    user_id: PydanticObjectId,
    current_user: CurrentUser = Depends(require_permission("nguoi_dung:view")),
    page: int = Query(1, ge=1, description="Số trang"),
    size: int = Query(10, ge=1, le=100, description="Số lượng mỗi trang"),
    q: Optional[str] = Query(None, description="Tìm theo tên tác nhân"),
):
    await _ensure_user_exists(user_id)

    links = await NguoiDungTacNhan.find(
        NguoiDungTacNhan.nguoi_dung_id == user_id
    ).to_list()
    agent_ids = [l.tac_nhan_id for l in links]
    if not agent_ids:
        return TacNhanListResponse(items=[], total=0, page=page, size=size)

    skip = (page - 1) * size
    filter_query = {"_id": {"$in": agent_ids}, "hoat_dong": True}
    if q:
        filter_query["ten"] = {"$regex": q, "$options": "i"}

    query = TacNhan.find(filter_query)
    total = await query.count()
    agents = await query.skip(skip).limit(size).to_list()
    return TacNhanListResponse(
        items=agents,
        total=total,
        page=page,
        size=size
    )
