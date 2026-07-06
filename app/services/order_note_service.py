import re
from typing import Any, Dict, Optional

from app.api.dependencies.time import now_vn
from app.models.conversations import ConversationStatus
from app.services.conversation_service import get_conversation_by_id_service
from logs.logging_config import logger


ORDER_NOTE_CONVERSATION_ID_INVALID = "ORDER_NOTE_CONVERSATION_ID_INVALID"
ORDER_NOTE_CONVERSATION_NOT_FOUND = "ORDER_NOTE_CONVERSATION_NOT_FOUND"


class OrderNoteConversationIdInvalid(ValueError):
    pass


def _normalize_required_text(value: Optional[Any], *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized


def _next_order_note_index(existing_order_note: Optional[str]) -> int:
    text = str(existing_order_note or "")
    existing_count = len(re.findall(r"^\s*\d+\.", text, flags=re.MULTILINE))
    return existing_count + 1


def _status_value(value: Any) -> str:
    raw_value = getattr(value, "value", value)
    return str(raw_value or "").strip()


def _format_order_note_line(*, index: int, order_note: str) -> str:
    timestamp = now_vn().strftime("%H:%M")
    return f"{index}. [{timestamp}] {order_note}"


def _append_order_note(existing_order_note: Optional[str], *, order_note: str) -> tuple[str, int]:
    normalized_note = _normalize_required_text(order_note, field_name="order_note")
    next_index = _next_order_note_index(existing_order_note)
    line = _format_order_note_line(index=next_index, order_note=normalized_note)
    current_note = str(existing_order_note or "").strip()
    if not current_note:
        return line, next_index
    return f"{current_note}\n{line}", next_index


async def create_order_note_service(
    *,
    conversation_id: Optional[str],
    order_note: Optional[str],
) -> Dict[str, Any]:
    normalized_conversation_id = _normalize_required_text(
        conversation_id,
        field_name="conversation_id",
    )
    normalized_order_note = _normalize_required_text(order_note, field_name="order_note")

    try:
        conversation = await get_conversation_by_id_service(normalized_conversation_id)
    except ValueError as exc:
        logger.warning(
            "%s conversation_id=%s",
            ORDER_NOTE_CONVERSATION_ID_INVALID,
            normalized_conversation_id,
        )
        raise OrderNoteConversationIdInvalid("Invalid conversation_id format") from exc

    if conversation is None:
        logger.warning(
            "%s conversation_id=%s",
            ORDER_NOTE_CONVERSATION_NOT_FOUND,
            normalized_conversation_id,
        )
        return {
            "success": False,
            "reason": "conversation_not_found",
            "conversation_id": normalized_conversation_id,
        }

    current_status = getattr(conversation, "status", None)
    existing_note = (
        getattr(conversation, "order_note", None)
        if _status_value(current_status) == ConversationStatus.ORDER_PENDING.value
        else None
    )
    next_order_note, order_note_index = _append_order_note(
        existing_note,
        order_note=normalized_order_note,
    )

    conversation.order_note = next_order_note
    conversation.status = ConversationStatus.ORDER_PENDING
    conversation.updated_at = now_vn()
    await conversation.save()

    return {
        "success": True,
        "conversation_id": str(conversation.id),
        "status": ConversationStatus.ORDER_PENDING.value,
        "order_note": next_order_note,
        "order_note_index": order_note_index,
    }
