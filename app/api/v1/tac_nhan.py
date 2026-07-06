from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from typing import Optional, List

from app.api.schemas.tac_nhan import TacNhanCreate, TacNhanResponse, TacNhanUpdate, TacNhanListResponse
from app.core.security import CurrentUser, require_permission, get_current_user
from app.models.tac_nhan import TacNhan
from app.models.quyen_han import QuyenHan
from app.models.nguoi_dung_tac_nhan import NguoiDungTacNhan
from app.models.tac_nhan_quyen_han import TacNhanQuyenHan
from app.api.dependencies.time import now_vn
from app.api.dependencies.error_codes import ErrorCode
from logs.logging_config import logger

router = APIRouter()


@router.post("/", response_model=TacNhanResponse, status_code=status.HTTP_201_CREATED)
async def create_tac_nhan(
    data: TacNhanCreate, current_user: CurrentUser = Depends(require_permission("tac_nhan:create"))
):
    try:
        logger.info(f"User '{current_user.email}' is creating agent '{data.ten}'.")
        existing_tac_nhan = await TacNhan.find_one(TacNhan.ten == data.ten)
        if existing_tac_nhan:
            logger.warning(f"Agent name '{data.ten}' already exists.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=ErrorCode.TEN_TAC_NHAN_EXISTS
            )
        logger.debug(f"Creating new TacNhan object for '{data.ten}'.")
        tac_nhan = TacNhan(**data.model_dump())
        await tac_nhan.insert()

        # logger.debug(f"Linking agent ID '{tac_nhan.id}' to user ID '{current_user.id}'.")
        # link = NguoiDungTacNhan(
        #     tac_nhan_id=tac_nhan.id, nguoi_dung_id=current_user.id
        # )
        # await link.insert()

        logger.info(f"Agent '{data.ten}' created with ID {tac_nhan.id} by user '{current_user.email}'.")
        return tac_nhan
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error creating agent '{data.ten}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorCode.INTERNAL_SERVER_ERROR
        )


@router.get("/", response_model=TacNhanListResponse)
async def get_all_tac_nhan(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    page: int = Query(1, ge=1, description="Số trang"),
    size: int = Query(10, ge=1, le=100, description="Số lượng mỗi trang"),
    q: Optional[str] = Query(None, description="Tìm theo tên"),
):
    try:
        logger.info(f"User '{current_user.email}' fetching all agents. Page: {page}, Size: {size}, Query: '{q}'.")
        skip = (page - 1) * size
        filter_query = {"hoat_dong": True}
        if q:
            filter_query["ten"] = {"$regex": q, "$options": "i"}
        logger.info(f"Executing count query for agents with filter: {filter_query}")
        query = TacNhan.find(filter_query)
        total = await query.count()

        logger.info("Building aggregation pipeline to fetch agents with permissions.")
        pipeline = [
            {"$match": filter_query},
            {"$sort": {"thoi_gian_tao": -1}},
            {"$skip": skip},
            {"$limit": size},
            {
                "$lookup": {
                    "from": TacNhanQuyenHan.Settings.name,
                    "localField": "_id",
                    "foreignField": "tac_nhan_id",
                    "as": "links",
                }
            },
            {

                "$lookup": {
                    "from": QuyenHan.Settings.name,
                    "localField": "links.quyen_han_id",
                    "foreignField": "_id",
                    "as": "quyen_han",
                }
            },
            {
                "$project": {
                    "links": 0
                }
            }
        ]
        logger.info(f"Executing aggregation pipeline for agents. Skip: {skip}, Limit: {size}.")
        tac_nhan_list_raw = await TacNhan.aggregate(pipeline).to_list()
        logger.info(f"Successfully fetched {len(tac_nhan_list_raw)} agents (Total: {total}).")

        processed_list = []
        for item in tac_nhan_list_raw:
            if '_id' in item:
                item['id'] = item.pop('_id')
            
            if 'quyen_han' in item and isinstance(item['quyen_han'], list):
                for qh in item['quyen_han']:
                    if isinstance(qh, dict) and '_id' in qh:
                        qh['id'] = qh.pop('_id')
            processed_list.append(item)
        
        return TacNhanListResponse(
            items=processed_list,
            total=total,
            page=page,
            size=size
        )
    except Exception as e:
        logger.error(f"Error fetching all agents: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorCode.INTERNAL_SERVER_ERROR
        )


@router.get("/{tac_nhan_id}", response_model=TacNhanResponse)
async def get_tac_nhan_by_id(
    tac_nhan_id: PydanticObjectId,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user)
):
    try:
        logger.info(f"User '{current_user.email}' fetching agent by ID '{tac_nhan_id}' with permissions.")
        logger.debug(f"Building aggregation pipeline for agent ID '{tac_nhan_id}'.")
        pipeline = [
            {"$match": {"_id": tac_nhan_id, "hoat_dong": True}},
            {
                "$lookup": {
                    "from": TacNhanQuyenHan.Settings.name,
                    "localField": "_id",
                    "foreignField": "tac_nhan_id",
                    "as": "links",
                }
            },
            {

                "$lookup": {
                    "from": QuyenHan.Settings.name,
                    "localField": "links.quyen_han_id",
                    "foreignField": "_id",
                    "as": "quyen_han",
                }
            },
            {
                "$project": {
                    "links": 0
                }
            },
            {"$limit": 1}
        ]
        logger.debug(f"Executing aggregation pipeline for agent ID '{tac_nhan_id}'.")
        result = await TacNhan.aggregate(pipeline).to_list()
        if not result:
            logger.warning(f"Agent ID '{tac_nhan_id}' not found or inactive for user '{current_user.email}'.")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=ErrorCode.TAC_NHAN_NOT_FOUND
            )
        logger.info(f"Successfully fetched agent ID '{tac_nhan_id}'.")

        item = result[0]

        if '_id' in item:
            item['id'] = item.pop('_id')
        
        if 'quyen_han' in item and isinstance(item['quyen_han'], list):
            for qh in item['quyen_han']:
                if isinstance(qh, dict) and '_id' in qh:
                    qh['id'] = qh.pop('_id')

        return item
    
    except Exception as e:
        logger.error(f"Error fetching agent ID '{tac_nhan_id}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorCode.INTERNAL_SERVER_ERROR
        )


@router.put("/{tac_nhan_id}", response_model=TacNhanResponse)
async def update_tac_nhan(
    tac_nhan_id: PydanticObjectId,
    data: TacNhanUpdate,
    current_user: CurrentUser = Depends(require_permission("tac_nhan:edit")),
):
    try:
        logger.debug(f"Finding agent ID '{tac_nhan_id}' for update by user '{current_user.email}'.")
        tac_nhan = await TacNhan.find_one({"_id": tac_nhan_id, "hoat_dong": True})
        if not tac_nhan:
            logger.warning(f"Agent ID '{tac_nhan_id}' not found for update.")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=ErrorCode.TAC_NHAN_NOT_FOUND
            )

        update_data = data.model_dump(exclude_unset=True)
        logger.info(f"User '{current_user.email}' is updating agent ID '{tac_nhan_id}' with data: {update_data}.")

        quyen_han_ids = update_data.pop("quyen_han_ids", None)

        new_name = update_data.get("ten")
        if new_name and new_name != tac_nhan.ten:
            logger.debug(f"Checking for name conflict for new name '{new_name}'.")
            existing_tac_nhan = await TacNhan.find_one(TacNhan.ten == new_name, TacNhan.id != tac_nhan_id)
            if existing_tac_nhan:
                logger.warning(f"Update agent failed for ID '{tac_nhan_id}'. Name '{new_name}' already exists.")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ErrorCode.TEN_TAC_NHAN_EXISTS
                )
            
        for key, value in update_data.items():
            setattr(tac_nhan, key, value)
        
        if quyen_han_ids is not None:
            logger.debug(f"Updating permissions for agent ID '{tac_nhan.id}'.")
            await TacNhanQuyenHan.find({"tac_nhan_id": tac_nhan.id}).delete()

            if quyen_han_ids:
                links_to_create = [
                    TacNhanQuyenHan(tac_nhan_id=tac_nhan.id, quyen_han_id=qh_id)
                    for qh_id in quyen_han_ids
                ]
                await TacNhanQuyenHan.insert_many(links_to_create)
                logger.info(f"Set {len(links_to_create)} permissions for agent ID '{tac_nhan.id}'.")
            else:
                logger.info(f"Removed all permissions for agent ID '{tac_nhan.id}'.")
            
        tac_nhan.thoi_gian_sua = now_vn()
        await tac_nhan.save()
        logger.info(f"Agent ID '{tac_nhan_id}' updated successfully.")

        logger.info(f"Re-fetching updated agent ID '{tac_nhan.id}' with permissions to return.")
        logger.debug(f"Building aggregation pipeline for updated agent ID '{tac_nhan.id}'.")
        pipeline = [
            {"$match": {"_id": tac_nhan.id}},
            {"$lookup": {"from": TacNhanQuyenHan.Settings.name, "localField": "_id", "foreignField": "tac_nhan_id", "as": "links"}},
            {"$lookup": {"from": QuyenHan.Settings.name, "localField": "links.quyen_han_id", "foreignField": "_id", "as": "quyen_han"}},
            {"$project": {"links": 0}},
            {"$limit": 1}
        ]

        logger.debug(f"Executing aggregation pipeline for updated agent ID '{tac_nhan.id}'.")
        result = await TacNhan.aggregate(pipeline).to_list()
        if not result:
            logger.error(f"Failed to re-fetch agent ID '{tac_nhan.id}' after update.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ErrorCode.INTERNAL_SERVER_ERROR
            )
        logger.info(f"Successfully re-fetched agent ID '{tac_nhan.id}' for response.")

        item = result[0]

        if '_id' in item:
            item['id'] = item.pop('_id')
        
        if 'quyen_han' in item and isinstance(item['quyen_han'], list):
            for qh in item['quyen_han']:
                if isinstance(qh, dict) and '_id' in qh:
                    qh['id'] = qh.pop('_id')

        return item
    
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error updating agent ID '{tac_nhan_id}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorCode.INTERNAL_SERVER_ERROR
        )


@router.delete("/{tac_nhan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tac_nhan(
    tac_nhan_id: PydanticObjectId,
    current_user: CurrentUser = Depends(require_permission("tac_nhan:delete"))
):
    try:
        logger.info(f"User '{current_user.email}' is attempting to delete agent ID '{tac_nhan_id}'.")
        tac_nhan = await TacNhan.find_one({"_id": tac_nhan_id, "hoat_dong": True})
        if not tac_nhan:
            logger.warning(f"Attempt to delete non-existent agent ID '{tac_nhan_id}'.")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=ErrorCode.TAC_NHAN_NOT_FOUND
            )
        
        logger.debug(f"Setting 'hoat_dong = False' for agent ID '{tac_nhan_id}'.")
        tac_nhan.hoat_dong = False
        tac_nhan.thoi_gian_sua = now_vn()
        await tac_nhan.save()
        logger.info(f"Agent ID '{tac_nhan_id}' deactivated successfully by user '{current_user.email}'.")
        return None
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error deleting agent ID '{tac_nhan_id}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorCode.INTERNAL_SERVER_ERROR
        )