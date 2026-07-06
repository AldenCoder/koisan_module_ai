from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status, Response
from typing import List, Optional

from app.api.dependencies.error_codes import ErrorCode
from app.core.security import get_current_user, require_permission, CurrentUser
from app.models.nguoi_dung import NguoiDung
from app.models.tac_nhan import TacNhan
from app.models.quyen_han import QuyenHan
from app.models.nguoi_dung_tac_nhan import NguoiDungTacNhan
from app.models.tac_nhan_quyen_han import TacNhanQuyenHan
from app.api.schemas.quyen_han import QuyenHanResponse, QuyenHanListResponse
from app.api.schemas.tac_nhan import TacNhanListResponse
from app.api.schemas.tac_nhan_quyen_han import TacNhanQuyenHanResponse, AssignListQuyenHanRequest, AssignListQuyenHanResponse

router = APIRouter()

# ---------------- Helpers ----------------
async def _ensure_tacnhan_exists(tac_nhan_id: PydanticObjectId) -> TacNhan:
    tac_nhan = await TacNhan.get(tac_nhan_id)
    if not tac_nhan or not tac_nhan.hoat_dong:
        raise HTTPException(status_code=404, detail=ErrorCode.TAC_NHAN_NOT_FOUND)
    return tac_nhan

async def _ensure_quyenhan_exists(quyen_han_id: PydanticObjectId) -> QuyenHan:
    quyen_han = await QuyenHan.get(quyen_han_id)
    if not quyen_han or not quyen_han.hoat_dong:
        raise HTTPException(status_code=404, detail=ErrorCode.QUYEN_HAN_NOT_FOUND)
    return quyen_han


# --------------------------------------------------------------------
# GÁN QUYỀN CHO TÁC NHÂN (ADMIN-ONLY)
# --------------------------------------------------------------------
@router.post("/{tac_nhan_id}/assign/{quyen_han_id}", response_model=TacNhanQuyenHanResponse)
async def assign_quyenhan_to_tacnhan(
    tac_nhan_id: PydanticObjectId,
    quyen_han_id: PydanticObjectId,
    response: Response,
    current_user: CurrentUser= Depends(require_permission("tac_nhan_quyen_han:create")),
):
    tac_nhan = await _ensure_tacnhan_exists(tac_nhan_id)
    quyen_han = await _ensure_quyenhan_exists(quyen_han_id)

    link = await TacNhanQuyenHan.find_one({
        "tac_nhan_id": tac_nhan_id,
        "quyen_han_id": quyen_han_id,
    })
    if link:
        response.status_code = status.HTTP_200_OK
    else:
        link = TacNhanQuyenHan(tac_nhan_id=tac_nhan_id, quyen_han_id=quyen_han_id)
        await link.insert()
        response.status_code = status.HTTP_201_CREATED

    return {
        "id": link.id,
        "tac_nhan": tac_nhan,
        "quyen_han": quyen_han,
        "thoi_gian_tao": link.thoi_gian_tao,
    }


# --------------------------------------------------------------------
# GỠ QUYỀN KHỎI TÁC NHÂN (ADMIN-ONLY)
# --------------------------------------------------------------------
@router.post("/{tac_nhan_id}/unassign/{quyen_han_id}", status_code=status.HTTP_200_OK)
async def unassign_quyenhan_from_tacnhan(
    tac_nhan_id: PydanticObjectId,
    quyen_han_id: PydanticObjectId,
    current_user: CurrentUser = Depends(require_permission("tac_nhan_quyen_han:delete")),
):
    await _ensure_tacnhan_exists(tac_nhan_id)
    await _ensure_quyenhan_exists(quyen_han_id)

    link = await TacNhanQuyenHan.find_one({
        "tac_nhan_id": tac_nhan_id,
        "quyen_han_id": quyen_han_id,
    })
    if not link:
        return {"message": "Permission was not assigned."}
    
    await link.delete()
    return {"message": "Permission unassigned successfully."}


# --------------------------------------------------------------------
# LIỆT KÊ QUYỀN CỦA 1 TÁC NHÂN
# --------------------------------------------------------------------
@router.get("/{tac_nhan_id}/quyen-han", response_model=QuyenHanListResponse)
async def list_quyenhan_of_tacnhan(
    tac_nhan_id: PydanticObjectId,
    current_user: CurrentUser = Depends(require_permission("tac_nhan_quyen_han:view")),
    page: int = Query(1, ge=1, description="Số trang"),
    size: int = Query(10, ge=1, le=100, description="Số lượng mỗi trang"),
    q: Optional[str] = Query(None, description="Tìm theo tên quyền"),
):
    await _ensure_tacnhan_exists(tac_nhan_id)

    links = await TacNhanQuyenHan.find(
        TacNhanQuyenHan.tac_nhan_id == tac_nhan_id
    ).to_list()
    quyen_han_ids = [l.quyen_han_id for l in links]
    if not quyen_han_ids:
        return QuyenHanListResponse(items=[], total=0, page=page, size=size)

    skip = (page - 1) * size
    filter_query = {"_id": {"$in": quyen_han_ids}, "hoat_dong": True}
    if q:
        filter_query["ten"] = {"$regex": q, "$options": "i"}

    query = QuyenHan.find(filter_query)
    total = await query.count()
    items = await query.skip(skip).limit(size).to_list()
    return QuyenHanListResponse(
        items=items,
        total=total,
        page=page,
        size=size
    )


# --------------------------------------------------------------------
# (Tuỳ chọn) Liệt kê các tác nhân của user hiện tại có 1 quyền X
# --------------------------------------------------------------------
@router.get("/by-quyen/{quyen_han_id}", response_model=TacNhanListResponse)
async def list_my_tacnhan_ids_by_quyenhan(
    quyen_han_id: PydanticObjectId,
    current_user: CurrentUser = Depends(get_current_user),
    page: int = Query(1, ge=1, description="Số trang"),
    size: int = Query(10, ge=1, le=100, description="Số lượng mỗi trang"), 
):
    await _ensure_quyenhan_exists(quyen_han_id)
    my_tacnhan_links = await NguoiDungTacNhan.find(
        NguoiDungTacNhan.nguoi_dung_id == current_user.id
    ).to_list()
    my_tacnhan_ids = {l.tac_nhan_id for l in my_tacnhan_links}
    if not my_tacnhan_ids:
        return TacNhanListResponse(items=[], total=0, page=page, size=size)

    tnh_qh_links = await TacNhanQuyenHan.find(
        {"tac_nhan_id": {"$in": list(my_tacnhan_ids)}, "quyen_han_id": quyen_han_id}
    ).to_list()

    tacnhan_ids_with_quyenhan = {l.tac_nhan_id for l in tnh_qh_links}
    if not tacnhan_ids_with_quyenhan:
        return TacNhanListResponse(items=[], total=0, page=page, size=size)
    
    skip = (page - 1) * size
    query = TacNhan.find({"_id": {"$in": tacnhan_ids_with_quyenhan}, "hoat_dong": True})
    total = await query.count()
    cac_tac_nhan = await query.skip(skip).limit(size).to_list()
    return TacNhanListResponse(
        items=cac_tac_nhan,
        total=total,
        page=page,
        size=size
    )


# --------------------------------------------------------------------
# Gán list quyền hạn cho tác nhân
# --------------------------------------------------------------------
@router.post(
    "/{tac_nhan_id}/assign-multiple",
    response_model=AssignListQuyenHanResponse,
    status_code=status.HTTP_201_CREATED,
)
async def assign_list_quyenhan_to_tacnhan(
    tac_nhan_id: PydanticObjectId,
    data: AssignListQuyenHanRequest,
    current_user: CurrentUser = Depends(require_permission("tac_nhan_quyen_han:create")),
):
    await _ensure_tacnhan_exists(tac_nhan_id)

    requested_quyenhan_ids = list(set(data.quyen_han_ids))
    if not requested_quyenhan_ids:
        return AssignListQuyenHanResponse(
            assigned_count=0,
            total_requested=0,
            message="No permission IDs provided.",
            assigned_quyen_han=[],
        )
    
    valid_quyenhan = await QuyenHan.find(
        {"_id": {"$in": requested_quyenhan_ids}, "hoat_dong": True}
    ).to_list()
    valid_quyenhan_ids = {quyen_han.id for quyen_han in valid_quyenhan}

    if len(valid_quyenhan_ids) != len(requested_quyenhan_ids):
        invalid_ids = set(requested_quyenhan_ids) - valid_quyenhan_ids
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid or inactive permission IDs: {', '.join(map(str, invalid_ids))}",
        )

    existing_links = await TacNhanQuyenHan.find(
        {"tac_nhan_id": tac_nhan_id, "quyen_han_id": {"$in": requested_quyenhan_ids}}
    ).to_list()
    existing_quyenhan_ids = {link.quyen_han_id for link in existing_links}

    new_quyenhan_ids_to_assign = valid_quyenhan_ids - existing_quyenhan_ids

    newly_assigned_quyenhan_objects = [qh for qh in valid_quyenhan if qh.id in new_quyenhan_ids_to_assign]
    new_links = [
        TacNhanQuyenHan(tac_nhan_id=tac_nhan_id, quyen_han_id=quyenhan_id)
        for quyenhan_id in new_quyenhan_ids_to_assign
    ]

    if new_links:
        await TacNhanQuyenHan.insert_many(new_links)

    return AssignListQuyenHanResponse(
        assigned_count=len(new_links),
        total_requested=len(requested_quyenhan_ids),
        message=f"Successfully assigned {len(new_links)} new permissions.",
        assigned_quyen_han=newly_assigned_quyenhan_objects,
    )