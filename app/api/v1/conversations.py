from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.schemas.conversation import (
    ConversationCreateRequest,
    ConversationDeleteResponse,
    ConversationDetailResponse,
    ConversationInfoResponse,
    ConversationListResponse,
    ConversationListStatusFilterSchema,
    ConversationStatusSchema,
    ConversationUpdateRequest,
)
from app.core.security import CurrentUser, require_permission
from app.models.conversations import Conversation, ConversationStatus
from app.services.conversation_service import (
    create_conversation_crud_service,
    delete_conversation_service,
    get_conversation_detail_service,
    list_conversations_service,
    update_conversation_crud_service,
)

router = APIRouter()


def _conversation_status_to_str(status_value: Any) -> str:
    if isinstance(status_value, ConversationStatus):
        return status_value.value
    normalized = str(status_value or "").strip()
    return normalized or ConversationStatus.NEW.value


def _serialize_conversation(conversation: Conversation) -> Dict[str, Any]:
    return {
        "id": str(conversation.id),
        "channel": conversation.channel,
        "customer_name": conversation.customer_name,
        "customer_id": conversation.customer_id,
        "pancake_page_id": getattr(conversation, "pancake_page_id", None),
        "pancake_conversation_id": getattr(conversation, "pancake_conversation_id", None),
        "pancake_thread_type": getattr(conversation, "pancake_thread_type", None),
        "pancake_info_url": getattr(conversation, "pancake_info_url", None),
        "order_note": getattr(conversation, "order_note", None),
        "is_active": bool(conversation.is_active),
        "status": _conversation_status_to_str(conversation.status),
        "summaries": conversation.summaries,
        "version": getattr(conversation, "version", None),
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
    }


@router.post("/", response_model=ConversationInfoResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreateRequest,
    current_user: CurrentUser = Depends(require_permission("conversations:create")),
) -> ConversationInfoResponse:
    del current_user
    try:
        conversation = await create_conversation_crud_service(
            channel=payload.channel,
            customer_name=payload.customer_name,
            customer_id=payload.customer_id,
            status=payload.status,
            summaries=payload.summaries,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ConversationInfoResponse(**_serialize_conversation(conversation))


@router.get("/", response_model=ConversationListResponse)
async def list_conversations(
    status_filter: Optional[ConversationListStatusFilterSchema] = Query(
        default=None,
        alias="status",
        description="Filter theo status conversation: new, handover, apilimit, confirmed, or order_pending",
    ),
    keyword: Optional[str] = Query(
        default=None,
        description="Search theo customer_name / customer_id",
    ),
    page: int = Query(default=1, ge=1, description="Số trang"),
    size: int = Query(default=10, ge=1, le=100, description="Số lượng mỗi trang"),
    include_inactive: bool = Query(
        default=False,
        description="Bao gồm cả conversation đã soft-delete",
    ),
    current_user: CurrentUser = Depends(require_permission("conversations:view")),
) -> ConversationListResponse:
    del current_user
    try:
        rows = await list_conversations_service(
            status=status_filter,
            keyword=keyword,
            page=page,
            size=size,
            include_inactive=include_inactive,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ConversationListResponse(**rows)


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: str,
    include_inactive: bool = Query(
        default=True,
        description="Nếu true thì vẫn trả về conversation đã soft-delete",
    ),
    current_user: CurrentUser = Depends(require_permission("conversations:view")),
) -> ConversationDetailResponse:
    del current_user
    try:
        detail = await get_conversation_detail_service(
            conversation_id,
            include_inactive=include_inactive,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if detail is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return ConversationDetailResponse(**detail)


@router.patch("/{conversation_id}", response_model=ConversationInfoResponse)
async def update_conversation(
    conversation_id: str,
    payload: ConversationUpdateRequest,
    current_user: CurrentUser = Depends(require_permission("conversations:edit")),
) -> ConversationInfoResponse:
    del current_user
    update_data = payload.model_dump(exclude_unset=True)

    try:
        conversation = await update_conversation_crud_service(conversation_id, **update_data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return ConversationInfoResponse(**_serialize_conversation(conversation))


@router.delete("/{conversation_id}", response_model=ConversationDeleteResponse)
async def delete_conversation(
    conversation_id: str,
    soft_delete: bool = Query(default=True, description="Soft delete mặc định"),
    current_user: CurrentUser = Depends(require_permission("conversations:delete")),
) -> ConversationDeleteResponse:
    del current_user
    try:
        deleted = await delete_conversation_service(conversation_id, soft_delete=soft_delete)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return ConversationDeleteResponse(
        conversation_id=conversation_id,
        deleted=True,
        soft_delete=soft_delete,
    )
