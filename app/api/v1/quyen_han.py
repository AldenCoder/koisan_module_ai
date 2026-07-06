from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Optional

from app.api.dependencies.error_codes import ErrorCode
from app.api.schemas.quyen_han import QuyenHanCreate, QuyenHanResponse, QuyenHanUpdate, QuyenHanListResponse
from app.core.security import get_current_user, require_permission, CurrentUser
from app.models.quyen_han import QuyenHan
from app.models.tac_nhan_quyen_han import TacNhanQuyenHan
from app.api.dependencies.time import now_vn
from logs.logging_config import logger

router = APIRouter()


@router.post("/", response_model=QuyenHanResponse, status_code=status.HTTP_201_CREATED)
async def create_quyen_han(
    data: QuyenHanCreate, current_user: CurrentUser = Depends(require_permission("quyen_han:create"))
):
    try:
        logger.info(f"User '{current_user.email}' is creating permission '{data.ten}'.")
        existing_quyen_han = await QuyenHan.find_one(QuyenHan.ten == data.ten)
        if existing_quyen_han:
            logger.warning(f"Permission name '{data.ten}' already exists.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=ErrorCode.TEN_QUYEN_HAN_EXISTS
            )
        quyen_han = QuyenHan(**data.model_dump())
        await quyen_han.insert()
        logger.info(f"Permission '{data.ten}' created successfully with ID: {quyen_han.id}.")
        return quyen_han
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error creating permission '{data.ten}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorCode.INTERNAL_SERVER_ERROR
        )


@router.get("/", response_model=QuyenHanListResponse)
async def get_all_quyen_han(
    current_user: CurrentUser = Depends(get_current_user),
    page: int = Query(1, ge=1, description="Số trang"),
    size: int = Query(10, ge=1, le=100, description="Số lượng mỗi trang"),
    q: Optional[str] = Query(None, description="Tìm theo tên quyền"),
):
    try:
        skip = (page - 1) * size
        filter_query = {"hoat_dong": True}
        if q:
            filter_query["ten"] = {"$regex": q, "$options": "i"}
        
        query = QuyenHan.find(filter_query)
        total = await query.count()
        quyen_han_list = await query.skip(skip).limit(size).to_list()
        return QuyenHanListResponse(
            items=quyen_han_list,
            total=total,    
            page=page,
            size=size
        )
    except Exception as e:
        logger.error(f"Error fetching all permissions: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorCode.INTERNAL_SERVER_ERROR
        )


@router.get("/{quyen_han_id}", response_model=QuyenHanResponse)
async def get_quyen_han_by_id(
    quyen_han_id: PydanticObjectId, current_user: CurrentUser = Depends(get_current_user)
):
    try:
        quyen_han = await QuyenHan.find_one({"_id": quyen_han_id, "hoat_dong": True})
        if not quyen_han:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=ErrorCode.QUYEN_HAN_NOT_FOUND
            )
        return quyen_han
    except Exception as e:
        logger.error(f"Error fetching permission with ID '{quyen_han_id}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorCode.INTERNAL_SERVER_ERROR
        )


@router.put("/{quyen_han_id}", response_model=QuyenHanResponse)
async def update_quyen_han(
    quyen_han_id: PydanticObjectId,
    data: QuyenHanUpdate,
    current_user: CurrentUser = Depends(require_permission("quyen_han:edit")),
):
    try:
        quyen_han = await QuyenHan.find_one({"_id": quyen_han_id, "hoat_dong": True})
        if not quyen_han:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=ErrorCode.QUYEN_HAN_NOT_FOUND
            )

        update_data = data.model_dump(exclude_unset=True)
        logger.info(f"User '{current_user.email}' is updating permission ID '{quyen_han_id}' with data: {update_data}.")

        new_name = update_data.get("ten")
        if new_name and new_name != quyen_han.ten:
            existed = await QuyenHan.find_one({"ten": new_name, "_id": {"$ne": quyen_han_id}})
            if existed:
                logger.warning(f"Update permission failed for ID '{quyen_han_id}'. Name '{new_name}' already exists.")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=ErrorCode.TEN_QUYEN_HAN_EXISTS
                )
            
        for key, value in update_data.items():
            setattr(quyen_han, key, value)
        
        quyen_han.thoi_gian_sua = now_vn()
        await quyen_han.save()
        logger.info(f"Permission ID '{quyen_han_id}' updated successfully.")
        return quyen_han
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error updating permission ID '{quyen_han_id}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorCode.INTERNAL_SERVER_ERROR
        )


@router.delete("/{quyen_han_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quyen_han(
    quyen_han_id: PydanticObjectId, current_user: CurrentUser = Depends(require_permission("quyen_han:delete")),
):
    try:
        logger.info(f"User '{current_user.email}' is attempting to delete permission ID '{quyen_han_id}'.")
        quyen_han = await QuyenHan.find_one({"_id": quyen_han_id, "hoat_dong": True})
        if not quyen_han:
            logger.warning(f"Attempt to delete non-existent permission ID '{quyen_han_id}'.")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=ErrorCode.QUYEN_HAN_NOT_FOUND
            )
        
        in_use = await TacNhanQuyenHan.find(TacNhanQuyenHan.quyen_han_id == quyen_han_id).count()
        if in_use > 0:
            logger.warning(f"Attempt to delete permission ID '{quyen_han_id}' which is currently in use.")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ErrorCode.QUYEN_HAN_IN_USE,
            )
        
        quyen_han.hoat_dong = False
        quyen_han.thoi_gian_sua = now_vn()
        await quyen_han.save()
        logger.info(f"Permission ID '{quyen_han_id}' deactivated successfully by user '{current_user.email}'.")
        return None
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error deleting permission ID '{quyen_han_id}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorCode.INTERNAL_SERVER_ERROR
        )