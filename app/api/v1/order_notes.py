from fastapi import APIRouter, HTTPException, status

from app.api.schemas.order_note import (
    OrderNoteCreateRequest,
    OrderNoteCreateResponse,
)
from app.services.order_note_service import (
    OrderNoteConversationIdInvalid,
    create_order_note_service,
)


router = APIRouter()


@router.post("", response_model=OrderNoteCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_order_note(payload: OrderNoteCreateRequest) -> OrderNoteCreateResponse:
    try:
        result = await create_order_note_service(
            conversation_id=payload.conversation_id,
            order_note=payload.order_note,
        )
    except OrderNoteConversationIdInvalid as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not bool(result.get("success")):
        raise HTTPException(status_code=404, detail="Conversation not found")

    return OrderNoteCreateResponse(**result)
