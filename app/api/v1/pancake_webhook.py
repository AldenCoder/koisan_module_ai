from __future__ import annotations

import asyncio
import inspect
import json
import random
import time
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from threading import Lock
from typing import Any, Iterable, Optional

from beanie.odm.utils.parsing import parse_obj
from fastapi import APIRouter, Request
from pymongo.errors import DuplicateKeyError

from app.api.dependencies.time import VN_TZ, now_vn
from app.api.v1.facebook_webhook import (
    _build_ai_chat_payload,
    _ensure_sender_initialized,
    _extract_text_from_ai_response,
    _post_ai_chat_with_retry,
)
from app.core.config import settings
from app.models.conversations import Conversation, ConversationStatus
from app.models.messages import Message, MessageRole
from app.services.dangerous_keyword_service import (
    DangerousKeywordLoadError,
    check_dangerous_keyword,
)
from app.services.ai_version_context_service import (
    get_system_version_for_new_conversation,
    prepare_ai_version_for_customer_message,
)
from app.services.facebook_handover_detection_service import detect_handover_reply
from app.services.pancake_message_service import (
    PANCAKE_REPLY_COMMENT_ACTION,
    PANCAKE_REPLY_INBOX_ACTION,
    fetch_pancake_conversation_messages,
    sanitize_pancake_outgoing_message,
    send_pancake_content_ids,
    send_pancake_comment_content_ids,
    send_pancake_comment_reply,
    send_pancake_reply,
    upload_pancake_content,
)
from app.services.pancake_auto_consult_service import (
    PANCAKE_AUTO_CONSULT_SOURCE,
    PANCAKE_MESSAGE_AD_CARD,
    PANCAKE_MESSAGE_PAGE_COMMENT_REPLY_NOTICE,
    build_auto_consult_prompt_from_description,
    build_customer_comment_ai_message,
    extract_ad_card_source_detail,
    extract_page_comment_reply_source_detail,
    is_pancake_ad_card_message,
    is_pancake_page_comment_reply_notice,
)
from app.services.google_drive_image_service import GoogleDriveImageService
from app.services.pancake_drive_image_color_service import (
    build_color_match_terms,
    name_matches_color_terms,
    normalize_color_key,
    parse_drive_file_color_from_name,
)
from app.services.pancake_drive_image_service import (
    PancakeDriveImageService,
    PreparedPancakeDriveReply,
    build_drive_file_view_url,
    prepare_pancake_drive_reply,
)
from app.services.pancake_webhook_normalize_service import normalize_pancake_payload
from logs.logging_config import logger


router = APIRouter()
_processing_message_mid_lock = Lock()
_processing_message_mids: set[str] = set()
_pancake_image_echo_lock = Lock()
_pancake_image_echo_events: dict[tuple[str, str], list[dict[str, Any]]] = {}
_pancake_sender_buffer_lock = Lock()
_pancake_sender_buffers: dict[tuple[str, str, str], dict[str, Any]] = {}
_pancake_ad_context_buffer_lock = Lock()
_pancake_ad_context_buffers: dict[tuple[str, str, str], dict[str, Any]] = {}
_pancake_consumed_ad_context_mids: dict[tuple[str, str], float] = {}
PANCAKE_MESSAGE_USER_SOURCE = "pancake_webhook_ai_forward"
PANCAKE_MESSAGE_BOT_SOURCE = "pancake_webhook_ai_forward"
PANCAKE_MESSAGE_COMMENT_USER_SOURCE = "pancake_webhook_comment"
PANCAKE_MESSAGE_STAFF_SOURCE = "pancake_webhook_admin_echo"
PANCAKE_MESSAGE_INBOX = "INBOX"
PANCAKE_MESSAGE_COMMENT_TYPE = "COMMENT"
PANCAKE_THREAD_TYPE_INBOX = "inbox"
PANCAKE_THREAD_TYPE_COMMENT = "comment"
PANCAKE_MESSAGE_CUSTOMER = "customer_message"
PANCAKE_MESSAGE_CUSTOMER_COMMENT = "customer_comment"
PANCAKE_MESSAGE_BOT_ECHO = "page_echo_or_automation"
PANCAKE_MESSAGE_ADMIN = "human_admin_message"
PANCAKE_PUBLIC_API_ADMIN_NAME = "Public API"
PANCAKE_DANGEROUS_KEYWORD_BLOCKED_REASON = "pancake_dangerous_keyword_blocked"
PANCAKE_DANGEROUS_KEYWORD_UNAVAILABLE_REASON = "pancake_dangerous_keyword_unavailable"
PANCAKE_AI_QUOTA_ERROR_MARKER = "⚠️ You exceeded your current quota"
PANCAKE_AI_PLATFORM_ERROR_LINK_MARKER = "https://platform.openai.com"
PANCAKE_AI_FALLBACK_REPLY_MARKERS = (
    PANCAKE_AI_QUOTA_ERROR_MARKER,
    PANCAKE_AI_PLATFORM_ERROR_LINK_MARKER,
)
PANCAKE_AI_QUOTA_FALLBACK_REPLY = (
    "Chị chờ em 1 lát em check cho mình ạ."
)
PANCAKE_AI_QUOTA_PAUSE_REASON = "pancake_ai_quota_error"
PANCAKE_AI_QUOTA_PAUSED_BY = "system_ai_quota"
PANCAKE_AI_QUOTA_PAUSE_MINUTES = 10
PANCAKE_AI_HANDOVER_PAUSE_REASON = "pancake_ai_handover"
PANCAKE_AI_HANDOVER_PAUSE_MINUTES = 10
PANCAKE_REPEATED_BOT_REPLY_PAUSE_REASON = "pancake_repeated_bot_reply"
PANCAKE_REPEATED_BOT_REPLY_PAUSED_BY = "system_repeated_bot_reply"
PANCAKE_REPEATED_BOT_REPLY_PAUSE_MINUTES = 10
PANCAKE_REPEATED_BOT_REPLY_SIMILARITY_THRESHOLD = 0.95
PANCAKE_REPEATED_BOT_REPLY_FUZZY_MIN_CHARS = 40
PANCAKE_BOT_ECHO_LOOKBACK_MINUTES = 5
PANCAKE_USER_DUPLICATE_LOOKBACK_SECONDS = 10
PANCAKE_IMAGE_ECHO_MAX_DELIVERY_ATTEMPTS = 3
PANCAKE_IMAGE_ECHO_VERIFY_WAIT_SECONDS = 1.0
PANCAKE_IMAGE_ECHO_TRACKER_TTL_SECONDS = 30.0
PANCAKE_AD_CONTEXT_CONSUMED_TTL_SECONDS = 60.0
PANCAKE_IMAGE_ECHO_POLL_INTERVAL_SECONDS = 0.05
PANCAKE_IMAGE_ATTACHMENT_TYPES = {"image", "photo"}
PANCAKE_IMAGE_CONTENT_ID_FALLBACK_RATIO = 0.6
PANCAKE_IMAGE_CONTENT_READY_WAIT_SECONDS = 1.0
PANCAKE_HANDOVER_CONTEXT_DEFAULT_MAX_MESSAGES = 30
PANCAKE_HANDOVER_CONTEXT_MIN_MESSAGES = 1
PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES_LIMIT = 50


def _preview_text(value: Any, *, limit: int = 500) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...(truncated)"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _pancake_image_urls(normalized: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for raw_url in _as_list(normalized.get("image_urls")):
        image_url = str(raw_url or "").strip()
        if not image_url or image_url in seen:
            continue
        urls.append(image_url)
        seen.add(image_url)
    return urls


def _pancake_image_attachment_count(normalized: dict[str, Any]) -> int:
    raw_count = normalized.get("image_attachment_count")
    if isinstance(raw_count, int):
        return raw_count
    return sum(
        1
        for attachment in _as_list(normalized.get("attachments"))
        if str(_as_dict(attachment).get("type") or "").strip().lower()
        in PANCAKE_IMAGE_ATTACHMENT_TYPES
    )


def _has_pancake_image_attachment(normalized: dict[str, Any]) -> bool:
    return _pancake_image_attachment_count(normalized) > 0


def _has_pancake_image_urls(normalized: dict[str, Any]) -> bool:
    return bool(_pancake_image_urls(normalized))


def _pancake_customer_message_content(normalized: dict[str, Any]) -> str:
    text = str(normalized.get("text") or "").strip()
    if text:
        return text
    image_urls = _pancake_image_urls(normalized)
    if image_urls:
        return "\n".join(image_urls)
    return ""


def _build_pancake_ai_content(*, normalized: dict[str, Any], base_content: str) -> str:
    parts: list[str] = []
    normalized_base_content = str(base_content or "").strip()
    if normalized_base_content:
        parts.append(normalized_base_content)
    for image_url in _pancake_image_urls(normalized):
        if image_url not in parts:
            parts.append(image_url)
    return "\n".join(parts).strip()


def _pancake_from_debug_payload(value: Any) -> dict[str, Any]:
    raw_from = _as_dict(value)
    return {
        "id": raw_from.get("id"),
        "name": raw_from.get("name"),
        "email": raw_from.get("email"),
        "phone": raw_from.get("phone"),
        "page_customer_id": raw_from.get("page_customer_id"),
        "admin_name": raw_from.get("admin_name"),
        "uid": raw_from.get("uid"),
        "ai_generated": raw_from.get("ai_generated"),
    }


def _pancake_webhook_debug_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = _as_dict(payload.get("data"))
    conversation = _as_dict(data.get("conversation"))
    message = _as_dict(data.get("message"))
    post = _as_dict(data.get("post"))
    attachments = _as_list(message.get("attachments"))
    post_attachments = _as_list(post.get("attachments"))
    conversation_snippet = str(conversation.get("snippet") or "")
    message_text = str(message.get("message") or "")
    original_message = str(message.get("original_message") or "")
    post_message = str(post.get("message") or "")

    return {
        "event_type": payload.get("event_type"),
        "page_id": payload.get("page_id") or message.get("page_id"),
        "conversation": {
            "id": conversation.get("id"),
            "type": conversation.get("type"),
            "customer_id": conversation.get("customer_id"),
            "from": _pancake_from_debug_payload(conversation.get("from")),
            "snippet_present": bool(conversation_snippet),
            "snippet_length": len(conversation_snippet),
            "seen": conversation.get("seen"),
            "is_replied": conversation.get("is_replied"),
            "is_removed": conversation.get("is_removed"),
            "read_watermarks": conversation.get("read_watermarks"),
        },
        "message": {
            "id": message.get("id"),
            "conversation_id": message.get("conversation_id"),
            "page_id": message.get("page_id"),
            "type": message.get("type"),
            "from": _pancake_from_debug_payload(message.get("from")),
            "message_present": bool(message_text),
            "message_length": len(message_text),
            "original_message_present": bool(original_message),
            "original_message_length": len(original_message),
            "inserted_at": message.get("inserted_at"),
            "is_echo": message.get("is_echo"),
            "is_removed": message.get("is_removed"),
            "attachment_count": len(attachments),
        },
        "post": {
            "id": post.get("id"),
            "type": post.get("type"),
            "message_present": bool(post_message),
            "message_length": len(post_message),
            "attachment_count": len(post_attachments),
        },
    }


def _json_log_payload(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _public_normalized_message(
    normalized: dict[str, Any],
    *,
    include_text: bool = True,
    include_attachments: bool = True,
) -> dict[str, Any]:
    text = str(normalized.get("text") or "")
    attachments = normalized.get("attachments") or []
    message = {
        "source": normalized.get("source"),
        "event_type": normalized.get("event_type"),
        "page_id": normalized.get("page_id"),
        "sender_id": normalized.get("sender_id"),
        "sender_name": normalized.get("sender_name"),
        "recipient_id": normalized.get("recipient_id"),
        "timestamp": normalized.get("timestamp"),
        "message_mid": normalized.get("message_mid"),
        "message_type": normalized.get("message_type"),
        "conversation_type": normalized.get("conversation_type"),
        "is_echo": normalized.get("is_echo"),
        "is_removed": normalized.get("is_removed"),
        "pancake_conversation_id": normalized.get("pancake_conversation_id"),
        "platform": normalized.get("platform"),
        "platform_sender_id": normalized.get("platform_sender_id"),
        "page_customer_id": normalized.get("page_customer_id"),
        "conversation_customer_id": normalized.get("conversation_customer_id"),
        "conversation_sender_id": normalized.get("conversation_sender_id"),
        "conversation_sender_name": normalized.get("conversation_sender_name"),
        "message_from_id": normalized.get("message_from_id"),
        "message_from_admin_name": normalized.get("message_from_admin_name"),
        "message_from_uid": normalized.get("message_from_uid"),
        "message_from_ai_generated": normalized.get("message_from_ai_generated"),
        "comment_message_id": normalized.get("comment_message_id"),
        "post_id": normalized.get("post_id"),
        "post_type": normalized.get("post_type"),
        "post_message_present": normalized.get("post_message_present"),
        "post_message_length": normalized.get("post_message_length"),
        "post_message_preview": normalized.get("post_message_preview"),
        "post_attachment_count": normalized.get("post_attachment_count"),
        "image_attachment_count": _pancake_image_attachment_count(normalized),
        "image_url_count": len(_pancake_image_urls(normalized)),
        "image_urls": _pancake_image_urls(normalized),
        "post_product_codes": normalized.get("post_product_codes") or [],
        "post_product_code_count": normalized.get("post_product_code_count") or 0,
        "comment_ai_message_augmented": bool(
            normalized.get("comment_ai_message_augmented")
        ),
        "comment_ai_initial_product_prompt": bool(
            normalized.get("comment_ai_initial_product_prompt")
        ),
        "comment_ai_follow_up": bool(normalized.get("comment_ai_follow_up")),
        "conversation_was_ai_initialized": bool(
            normalized.get("conversation_was_ai_initialized")
        ),
    }
    if include_text:
        message["text"] = normalized.get("text")
    else:
        message["text_present"] = bool(text)
        message["text_length"] = len(text)
    if include_attachments:
        message["attachments"] = normalized.get("attachments")
    else:
        message["attachment_count"] = len(attachments) if isinstance(attachments, list) else 0
    return message


def _pancake_message_meta(normalized: dict[str, Any], *, source: str) -> dict[str, Any]:
    meta = {
        "source": source,
        "page_id": normalized.get("page_id"),
        "sender_id": normalized.get("sender_id"),
        "platform": normalized.get("platform"),
        "platform_sender_id": normalized.get("platform_sender_id"),
        "page_customer_id": normalized.get("page_customer_id"),
        "conversation_customer_id": normalized.get("conversation_customer_id"),
        "conversation_sender_id": normalized.get("conversation_sender_id"),
        "conversation_sender_name": normalized.get("conversation_sender_name"),
        "message_from_id": normalized.get("message_from_id"),
        "message_from_admin_name": normalized.get("message_from_admin_name"),
        "message_from_uid": normalized.get("message_from_uid"),
        "message_from_ai_generated": normalized.get("message_from_ai_generated"),
        "pancake_conversation_id": normalized.get("pancake_conversation_id"),
        "timestamp": normalized.get("timestamp"),
        "attachments": normalized.get("attachments") or [],
        "image_urls": _pancake_image_urls(normalized),
        "image_attachment_count": _pancake_image_attachment_count(normalized),
        "image_url_count": len(_pancake_image_urls(normalized)),
        "comment_message_id": normalized.get("comment_message_id"),
        "post_id": normalized.get("post_id"),
        "post_type": normalized.get("post_type"),
        "post_message_present": normalized.get("post_message_present"),
        "post_message_length": normalized.get("post_message_length"),
        "post_message_preview": normalized.get("post_message_preview"),
        "post_attachment_count": normalized.get("post_attachment_count"),
        "post_product_codes": normalized.get("post_product_codes") or [],
        "post_product_code_count": normalized.get("post_product_code_count") or 0,
        "comment_ai_message_augmented": bool(
            normalized.get("comment_ai_message_augmented")
        ),
        "comment_ai_initial_product_prompt": bool(
            normalized.get("comment_ai_initial_product_prompt")
        ),
        "comment_ai_follow_up": bool(normalized.get("comment_ai_follow_up")),
        "conversation_was_ai_initialized": bool(
            normalized.get("conversation_was_ai_initialized")
        ),
        "message_type": normalized.get("message_type"),
        "conversation_type": normalized.get("conversation_type"),
        "merged_message_mids": normalized.get("merged_message_mids") or [],
        "merged_message_ids": normalized.get("merged_message_ids") or [],
    }
    auto_consult = _as_dict(normalized.get("auto_consult"))
    if auto_consult:
        meta["auto_consult"] = auto_consult
        for key in (
            "trigger_type",
            "trigger_message_mid",
            "product_codes",
            "product_code_count",
            "ad_id",
            "ad_message_mid",
            "post_id",
            "comment_id",
            "description_present",
            "description_length",
            "description_preview",
        ):
            if key in auto_consult:
                meta[key] = auto_consult.get(key)
    return meta


def _pancake_user_meta_source(normalized: dict[str, Any]) -> str:
    if str(normalized.get("source") or "").strip() == PANCAKE_AUTO_CONSULT_SOURCE:
        return PANCAKE_AUTO_CONSULT_SOURCE
    if str(normalized.get("message_type") or "").strip().upper() == PANCAKE_MESSAGE_COMMENT_TYPE:
        return PANCAKE_MESSAGE_COMMENT_USER_SOURCE
    return PANCAKE_MESSAGE_USER_SOURCE


def _pancake_bot_meta_source(normalized: dict[str, Any]) -> str:
    if str(normalized.get("source") or "").strip() == PANCAKE_AUTO_CONSULT_SOURCE:
        return PANCAKE_AUTO_CONSULT_SOURCE
    if str(normalized.get("message_type") or "").strip().upper() == PANCAKE_MESSAGE_COMMENT_TYPE:
        return PANCAKE_MESSAGE_COMMENT_USER_SOURCE
    return PANCAKE_MESSAGE_BOT_SOURCE


def _build_pancake_info_url(normalized: dict[str, Any]) -> str | None:
    page_id = str(normalized.get("page_id") or "").strip()
    pancake_conversation_id = str(
        normalized.get("pancake_conversation_id") or ""
    ).strip()
    if not page_id or not pancake_conversation_id:
        return None
    return f"https://pancake.vn/{page_id}?c_id={pancake_conversation_id}"


def _resolve_pancake_thread_type(normalized: dict[str, Any]) -> str | None:
    message_type = str(normalized.get("message_type") or "").strip().upper()
    comment_message_id = str(normalized.get("comment_message_id") or "").strip()
    if message_type == PANCAKE_MESSAGE_COMMENT_TYPE or comment_message_id:
        return PANCAKE_THREAD_TYPE_COMMENT
    if message_type == PANCAKE_MESSAGE_INBOX:
        return PANCAKE_THREAD_TYPE_INBOX
    return None


def _parse_pancake_conversation_document(raw_document: Any) -> Conversation | None:
    if raw_document is None:
        return None
    if isinstance(raw_document, Conversation):
        return raw_document
    if not isinstance(raw_document, dict):
        return raw_document
    return parse_obj(Conversation, raw_document)


async def _get_or_create_pancake_conversation(normalized: dict[str, Any]) -> Conversation:
    sender_id = str(normalized.get("sender_id") or "").strip()
    if not sender_id:
        raise ValueError("Missing sender_id")

    page_id = str(normalized.get("page_id") or "").strip()
    pancake_conversation_id = str(normalized.get("pancake_conversation_id") or "").strip()
    if not page_id:
        raise ValueError("Missing page_id")
    if not pancake_conversation_id:
        raise ValueError("Missing pancake_conversation_id")

    channel = str(normalized.get("page_name") or normalized.get("page_id") or "").strip() or None
    sender_name = str(normalized.get("sender_name") or "").strip() or None
    now = now_vn()
    pancake_info_url = _build_pancake_info_url(normalized)
    pancake_thread_type = _resolve_pancake_thread_type(normalized)

    filter_query = {
        "pancake_page_id": page_id,
        "pancake_conversation_id": pancake_conversation_id,
    }
    set_fields: dict[str, Any] = {
        "customer_id": sender_id,
        "pancake_page_id": page_id,
        "pancake_conversation_id": pancake_conversation_id,
        "is_active": True,
        "updated_at": now,
    }
    if channel:
        set_fields["channel"] = channel
    if sender_name:
        set_fields["customer_name"] = sender_name
    if pancake_info_url:
        set_fields["pancake_info_url"] = pancake_info_url

    set_on_insert: dict[str, Any] = {
        "created_at": now,
        "status": ConversationStatus.NEW.value,
    }
    conversation_version = get_system_version_for_new_conversation()
    if conversation_version:
        set_on_insert["version"] = conversation_version
    if pancake_thread_type:
        set_on_insert["pancake_thread_type"] = pancake_thread_type

    collection = Conversation.get_motor_collection()
    created = False
    try:
        update_result = await collection.update_one(
            filter_query,
            {"$set": set_fields, "$setOnInsert": set_on_insert},
            upsert=True,
        )
        created = bool(getattr(update_result, "upserted_id", None))
        raw_conversation = await collection.find_one(filter_query)
    except DuplicateKeyError:
        raw_conversation = await collection.find_one(filter_query)

    conversation = _parse_pancake_conversation_document(raw_conversation)
    if conversation is None:
        raise RuntimeError("Pancake conversation upsert returned no document")
    if pancake_thread_type and not str(getattr(conversation, "pancake_thread_type", None) or "").strip():
        await collection.update_one(
            {
                **filter_query,
                "$or": [
                    {"pancake_thread_type": {"$exists": False}},
                    {"pancake_thread_type": None},
                    {"pancake_thread_type": ""},
                ],
            },
            {"$set": {"pancake_thread_type": pancake_thread_type}},
        )
        refreshed_conversation = _parse_pancake_conversation_document(
            await collection.find_one(filter_query)
        )
        if refreshed_conversation is not None:
            conversation = refreshed_conversation

    if created:
        logger.info(
            "PANCAKE_CONVERSATION_CREATED sender_id=%s conversation_id=%s thread_type=%s",
            sender_id,
            conversation.id,
            getattr(conversation, "pancake_thread_type", None),
        )

    return conversation


async def _is_duplicate_pancake_message(message_mid: str | None) -> bool:
    normalized_mid = str(message_mid or "").strip()
    if not normalized_mid:
        return False
    existing_message = await Message.find_one(Message.message_mid == normalized_mid)
    return existing_message is not None


def _is_pancake_sender_page(normalized: dict[str, Any]) -> bool:
    page_id = str(normalized.get("page_id") or "").strip()
    if not page_id:
        return False
    sender_id = str(normalized.get("sender_id") or "").strip()
    platform_sender_id = str(normalized.get("platform_sender_id") or "").strip()
    return sender_id == page_id or platform_sender_id == page_id


def _get_pancake_admin_takeover_pause_minutes() -> int:
    raw = getattr(settings, "pancake_admin_takeover_pause_minutes", None)
    if raw is None:
        raw = getattr(settings, "fb_admin_takeover_pause_minutes", 10)
    try:
        value = int(raw or 10)
    except (TypeError, ValueError):
        value = 10
    return max(1, value)


def _get_pancake_sender_buffer_seconds() -> float:
    raw = getattr(settings, "pancake_sender_buffer_seconds", 5.0)
    if raw is None:
        raw = 5.0
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = 5.0
    return max(0.0, value)


def _get_pancake_handover_context_max_messages() -> int:
    raw = getattr(
        settings,
        "pancake_handover_context_max_messages",
        PANCAKE_HANDOVER_CONTEXT_DEFAULT_MAX_MESSAGES,
    )
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = PANCAKE_HANDOVER_CONTEXT_DEFAULT_MAX_MESSAGES
    return min(
        PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES_LIMIT,
        max(PANCAKE_HANDOVER_CONTEXT_MIN_MESSAGES, value),
    )


def _to_vn_aware_datetime(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).astimezone(VN_TZ)
    return value.astimezone(VN_TZ)


def _is_pancake_bot_paused(
    conversation: Optional[Conversation],
    current_time: Optional[datetime] = None,
) -> bool:
    if conversation is None:
        return False

    paused_until = _to_vn_aware_datetime(getattr(conversation, "bot_paused_until", None))
    if paused_until is None:
        return False

    now_value = _to_vn_aware_datetime(current_time) or now_vn()
    return now_value < paused_until


async def _resume_pancake_conversation_if_pause_expired_with_snapshot(
    conversation: Conversation,
    current_time: Optional[datetime] = None,
) -> dict[str, Any]:
    paused_at = _to_vn_aware_datetime(getattr(conversation, "bot_paused_at", None))
    paused_until = _to_vn_aware_datetime(getattr(conversation, "bot_paused_until", None))
    if paused_until is None:
        return {
            "resumed": False,
            "reason": "not_paused",
        }

    now_value = _to_vn_aware_datetime(current_time) or now_vn()
    if now_value < paused_until:
        return {
            "resumed": False,
            "reason": "pause_active",
            "bot_paused_at": paused_at,
            "bot_paused_until": paused_until,
            "bot_paused_reason": getattr(conversation, "bot_paused_reason", None),
            "bot_paused_by": getattr(conversation, "bot_paused_by", None),
        }

    snapshot = {
        "resumed": True,
        "reason": "pause_expired",
        "bot_paused_at": paused_at,
        "bot_paused_until": paused_until,
        "bot_paused_reason": getattr(conversation, "bot_paused_reason", None),
        "bot_paused_by": getattr(conversation, "bot_paused_by", None),
    }

    conversation.bot_paused_until = None
    conversation.bot_paused_at = None
    conversation.bot_paused_reason = None
    conversation.bot_paused_by = None
    await conversation.save()
    logger.info(
        "PANCAKE_CONVERSATION_ADMIN_PAUSE_EXPIRED conversation_id=%s expired_at=%s",
        conversation.id,
        paused_until.isoformat(),
    )
    return snapshot


async def _resume_pancake_conversation_if_pause_expired(
    conversation: Conversation,
    current_time: Optional[datetime] = None,
) -> bool:
    result = await _resume_pancake_conversation_if_pause_expired_with_snapshot(
        conversation,
        current_time=current_time,
    )
    return bool(result.get("resumed"))


def _pancake_handover_transcript_label(role: Any) -> str | None:
    normalized_role = str(role or "").strip().lower()
    if normalized_role == MessageRole.STAFF.value:
        return "[Nhân viên]"
    if normalized_role == MessageRole.USER.value:
        return "[Khách]"
    return None


async def _get_pancake_handover_transcript_items(
    *,
    conversation: Conversation,
    paused_at: datetime | None,
    before_message_created_at: datetime | None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    conversation_id = getattr(conversation, "id", None)
    if conversation_id is None:
        return []

    paused_at_value = _to_vn_aware_datetime(paused_at)
    before_value = _to_vn_aware_datetime(before_message_created_at)
    if paused_at_value is None or before_value is None:
        return []

    max_messages = limit if limit is not None else _get_pancake_handover_context_max_messages()
    try:
        normalized_limit = int(max_messages)
    except (TypeError, ValueError):
        normalized_limit = _get_pancake_handover_context_max_messages()
    normalized_limit = min(
        PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES_LIMIT,
        max(PANCAKE_HANDOVER_CONTEXT_MIN_MESSAGES, normalized_limit),
    )

    rows = await Message.find(
        {
            "conversation_id": conversation_id,
            "created_at": {"$gte": paused_at_value, "$lt": before_value},
            "role": {"$in": [MessageRole.STAFF.value, MessageRole.USER.value]},
            "content": {"$nin": ["", None]},
        }
    ).sort(-Message.created_at).limit(normalized_limit).to_list()

    items: list[dict[str, Any]] = []
    for row in reversed(rows):
        role = str(getattr(row, "role", "") or "").strip().lower()
        if role not in {MessageRole.STAFF.value, MessageRole.USER.value}:
            continue
        content = str(getattr(row, "content", "") or "").strip()
        if not content:
            continue
        items.append(
            {
                "role": role,
                "content": content,
                "created_at": getattr(row, "created_at", None),
            }
        )
    return items


def _build_pancake_handover_transcript_text(items: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for item in items:
        label = _pancake_handover_transcript_label(item.get("role"))
        if label is None:
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        lines.append(f"{label} {content}")
    return "\n".join(lines).strip()


def _pancake_handover_context_datetime(value: Any) -> str | None:
    dt_value = _to_vn_aware_datetime(value)
    return dt_value.isoformat() if dt_value is not None else None


def _pancake_handover_context_audit_meta(
    handover_context: dict[str, Any],
) -> dict[str, Any]:
    if not handover_context:
        return {}

    transcript_count = handover_context.get("transcript_message_count")
    try:
        message_count = int(transcript_count or 0)
    except (TypeError, ValueError):
        message_count = 0

    max_messages = handover_context.get("transcript_max_messages")
    try:
        normalized_max_messages = int(max_messages or 0)
    except (TypeError, ValueError):
        normalized_max_messages = 0

    injected = bool(handover_context.get("ai_content_injected"))
    reason = (
        handover_context.get("ai_content_reason")
        or handover_context.get("transcript_reason")
        or (None if injected else "not_injected")
    )
    return {
        "resumed": bool(handover_context.get("resumed")),
        "injected": injected,
        "reason": reason,
        "message_count": message_count,
        "max_messages": normalized_max_messages,
        "paused_at": _pancake_handover_context_datetime(
            handover_context.get("bot_paused_at")
        ),
        "paused_until": _pancake_handover_context_datetime(
            handover_context.get("bot_paused_until")
        ),
        "paused_reason": handover_context.get("bot_paused_reason"),
        "paused_by": handover_context.get("bot_paused_by"),
    }


async def _save_pancake_handover_context_user_message_meta(
    *,
    user_message: Message,
    normalized: dict[str, Any],
) -> dict[str, Any]:
    handover_context = _as_dict(normalized.get("handover_resume_context"))
    if not handover_context:
        return {"updated": False, "reason": "missing_handover_context"}

    audit_meta = _pancake_handover_context_audit_meta(handover_context)
    if not audit_meta:
        return {"updated": False, "reason": "missing_handover_audit_meta"}

    message_meta = getattr(user_message, "meta", None)
    if not isinstance(message_meta, dict):
        return {"updated": False, "reason": "missing_message_meta"}

    message_meta["handover_context"] = audit_meta
    setattr(user_message, "meta", message_meta)
    save = getattr(user_message, "save", None)
    if not callable(save):
        return {"updated": False, "reason": "message_save_unavailable", "meta": audit_meta}

    save_result = save()
    if inspect.isawaitable(save_result):
        await save_result
    return {"updated": True, "meta": audit_meta}


def _attach_pancake_handover_resume_context(
    *,
    conversation: Conversation,
    normalized: dict[str, Any],
    resume_context: dict[str, Any],
) -> bool:
    if not bool(resume_context.get("resumed")):
        return False

    normalized["handover_resume_context"] = resume_context
    logger.info(
        "PANCAKE_HANDOVER_CONTEXT_RESUME_DETECTED conversation_id=%s page_id=%s pancake_conversation_id=%s message_mid=%s sender_id=%s paused_at=%s paused_until=%s paused_reason=%s",
        getattr(conversation, "id", None),
        normalized.get("page_id"),
        normalized.get("pancake_conversation_id"),
        normalized.get("message_mid"),
        normalized.get("sender_id"),
        _pancake_handover_context_datetime(resume_context.get("bot_paused_at")),
        _pancake_handover_context_datetime(resume_context.get("bot_paused_until")),
        resume_context.get("bot_paused_reason"),
    )
    return True


def _build_pancake_handover_context_ai_content(
    *,
    transcript_text: str,
    current_customer_text: str,
) -> str:
    normalized_transcript = str(transcript_text or "").strip()
    normalized_current_text = str(current_customer_text or "").strip()
    if not normalized_transcript:
        return normalized_current_text
    return (
        "Bối cảnh trong lúc nhân viên hỗ trợ:\n"
        f"{normalized_transcript}\n\n"
        "Tin nhắn mới của khách:\n"
        f"{normalized_current_text}\n\n"
        "Hãy trả lời tiếp dựa trên bối cảnh trên, không hỏi lại thông tin đã có."
    ).strip()


def _apply_pancake_handover_context_to_ai_content(
    *,
    conversation: Conversation,
    normalized: dict[str, Any],
    ai_content: str,
) -> str:
    handover_context = dict(_as_dict(normalized.get("handover_resume_context")))
    if not handover_context:
        return ai_content

    transcript_text = str(handover_context.get("transcript_text") or "").strip()
    wrapped_content = _build_pancake_handover_context_ai_content(
        transcript_text=transcript_text,
        current_customer_text=ai_content,
    )
    try:
        message_count = int(handover_context.get("transcript_message_count") or 0)
    except (TypeError, ValueError):
        message_count = 0
    if transcript_text and wrapped_content != ai_content:
        handover_context["ai_content_injected"] = True
        handover_context["ai_content_reason"] = None
        normalized["handover_resume_context"] = handover_context
        logger.info(
            "PANCAKE_HANDOVER_CONTEXT_INJECTED conversation_id=%s page_id=%s pancake_conversation_id=%s message_mid=%s sender_id=%s message_count=%s max_messages=%s",
            getattr(conversation, "id", None),
            normalized.get("page_id"),
            normalized.get("pancake_conversation_id"),
            normalized.get("message_mid"),
            normalized.get("sender_id"),
            message_count,
            handover_context.get("transcript_max_messages"),
        )
        return wrapped_content

    if not bool(handover_context.get("resumed")):
        skip_reason = "missing_pause_snapshot"
    else:
        skip_reason = (
            handover_context.get("transcript_reason")
            or handover_context.get("ai_content_reason")
            or "empty_handover_transcript"
        )
    handover_context["ai_content_injected"] = False
    handover_context["ai_content_reason"] = skip_reason
    normalized["handover_resume_context"] = handover_context
    logger.info(
        "PANCAKE_HANDOVER_CONTEXT_SKIPPED conversation_id=%s page_id=%s pancake_conversation_id=%s message_mid=%s sender_id=%s reason=%s message_count=%s",
        getattr(conversation, "id", None),
        normalized.get("page_id"),
        normalized.get("pancake_conversation_id"),
        normalized.get("message_mid"),
        normalized.get("sender_id"),
        skip_reason,
        message_count,
    )
    return ai_content


def _mark_pancake_handover_context_not_injected(
    normalized: dict[str, Any],
    *,
    reason: str,
) -> None:
    handover_context = dict(_as_dict(normalized.get("handover_resume_context")))
    if not handover_context:
        return
    handover_context["ai_content_injected"] = False
    handover_context["ai_content_reason"] = reason
    normalized["handover_resume_context"] = handover_context


async def _prepare_pancake_handover_resume_context(
    *,
    conversation: Conversation,
    normalized: dict[str, Any],
    user_message: Message,
) -> dict[str, Any]:
    resume_context = _as_dict(normalized.get("handover_resume_context"))
    if not bool(resume_context.get("resumed")):
        return {"ok": False, "reason": "not_handover_resume"}

    paused_at = _to_vn_aware_datetime(resume_context.get("bot_paused_at"))
    before_message_created_at = _to_vn_aware_datetime(getattr(user_message, "created_at", None))
    if paused_at is None or before_message_created_at is None:
        result = {
            **resume_context,
            "transcript_text": "",
            "transcript_message_count": 0,
            "transcript_items": [],
            "transcript_reason": "missing_handover_window",
        }
        normalized["handover_resume_context"] = result
        return result

    limit = _get_pancake_handover_context_max_messages()
    try:
        logger.info(
            "PANCAKE_HANDOVER_CONTEXT_FETCH_START conversation_id=%s page_id=%s pancake_conversation_id=%s message_mid=%s sender_id=%s max_messages=%s",
            getattr(conversation, "id", None),
            normalized.get("page_id"),
            normalized.get("pancake_conversation_id"),
            normalized.get("message_mid"),
            normalized.get("sender_id"),
            limit,
        )
        items = await _get_pancake_handover_transcript_items(
            conversation=conversation,
            paused_at=paused_at,
            before_message_created_at=before_message_created_at,
            limit=limit,
        )
    except Exception as exc:
        logger.warning(
            "PANCAKE_HANDOVER_CONTEXT_FETCH_FAILED conversation_id=%s page_id=%s pancake_conversation_id=%s message_mid=%s sender_id=%s max_messages=%s error=%s",
            getattr(conversation, "id", None),
            normalized.get("page_id"),
            normalized.get("pancake_conversation_id"),
            normalized.get("message_mid"),
            normalized.get("sender_id"),
            limit,
            exc,
        )
        result = {
            **resume_context,
            "transcript_text": "",
            "transcript_message_count": 0,
            "transcript_items": [],
            "transcript_max_messages": limit,
            "transcript_reason": "handover_transcript_query_failed",
        }
        normalized["handover_resume_context"] = result
        return result

    transcript_text = _build_pancake_handover_transcript_text(items)
    result = {
        **resume_context,
        "transcript_text": transcript_text,
        "transcript_message_count": len(items),
        "transcript_items": items,
        "transcript_max_messages": limit,
        "transcript_reason": None if transcript_text else "empty_handover_transcript",
    }
    logger.info(
        "PANCAKE_HANDOVER_CONTEXT_FETCH_OK conversation_id=%s page_id=%s pancake_conversation_id=%s message_mid=%s sender_id=%s message_count=%s max_messages=%s reason=%s",
        getattr(conversation, "id", None),
        normalized.get("page_id"),
        normalized.get("pancake_conversation_id"),
        normalized.get("message_mid"),
        normalized.get("sender_id"),
        len(items),
        limit,
        result.get("transcript_reason"),
    )
    normalized["handover_resume_context"] = result
    return result


async def _reload_pancake_conversation_for_pause_check(conversation: Conversation) -> Conversation:
    conversation_id = getattr(conversation, "id", None)
    if not conversation_id:
        return conversation

    try:
        fresh_conversation = await Conversation.get(conversation_id)
    except Exception:
        return conversation
    return fresh_conversation or conversation


def _is_pancake_public_api_echo(normalized: dict[str, Any]) -> bool:
    admin_name = str(normalized.get("message_from_admin_name") or "").strip().lower()
    return admin_name == PANCAKE_PUBLIC_API_ADMIN_NAME.lower()


def _pancake_image_echo_attachment_count(normalized: dict[str, Any]) -> int:
    attachments = _as_list(normalized.get("attachments"))
    if attachments:
        return len(attachments)
    raw_count = normalized.get("attachment_count")
    return raw_count if isinstance(raw_count, int) else 0


def _is_pancake_public_api_image_echo(normalized: dict[str, Any]) -> bool:
    page_id = str(normalized.get("page_id") or "").strip()
    conversation_id = str(normalized.get("pancake_conversation_id") or "").strip()
    return bool(
        page_id
        and conversation_id
        and bool(normalized.get("is_echo"))
        and _is_pancake_public_api_echo(normalized)
        and _pancake_image_echo_attachment_count(normalized) > 0
    )


def _prune_pancake_image_echo_events_unlocked(now_monotonic: float) -> None:
    cutoff = now_monotonic - PANCAKE_IMAGE_ECHO_TRACKER_TTL_SECONDS
    for key in list(_pancake_image_echo_events.keys()):
        events = [
            event
            for event in _pancake_image_echo_events.get(key, [])
            if float(event.get("received_at_monotonic") or 0) >= cutoff
        ]
        if events:
            _pancake_image_echo_events[key] = events
        else:
            _pancake_image_echo_events.pop(key, None)


def _clear_pancake_image_echo_events() -> None:
    with _pancake_image_echo_lock:
        _pancake_image_echo_events.clear()


def _clear_pancake_sender_buffer() -> None:
    with _pancake_sender_buffer_lock:
        for entry in _pancake_sender_buffers.values():
            task = entry.get("task")
            if task is not None and not task.done():
                task.cancel()
        _pancake_sender_buffers.clear()


def _clear_pancake_ad_context_buffer() -> None:
    with _pancake_ad_context_buffer_lock:
        for entry in _pancake_ad_context_buffers.values():
            task = entry.get("task")
            if task is not None and not task.done():
                task.cancel()
        _pancake_ad_context_buffers.clear()
        _pancake_consumed_ad_context_mids.clear()


def _record_pancake_public_api_image_echo(
    normalized: dict[str, Any],
    *,
    received_at_monotonic: float | None = None,
) -> dict[str, Any] | None:
    if not _is_pancake_public_api_image_echo(normalized):
        return None

    page_id = str(normalized.get("page_id") or "").strip()
    conversation_id = str(normalized.get("pancake_conversation_id") or "").strip()
    received_at = time.monotonic() if received_at_monotonic is None else received_at_monotonic
    event = {
        "page_id": page_id,
        "pancake_conversation_id": conversation_id,
        "message_mid": normalized.get("message_mid"),
        "attachment_count": _pancake_image_echo_attachment_count(normalized),
        "timestamp": normalized.get("timestamp"),
        "received_at_monotonic": received_at,
    }

    with _pancake_image_echo_lock:
        _prune_pancake_image_echo_events_unlocked(received_at)
        _pancake_image_echo_events.setdefault((page_id, conversation_id), []).append(event)

    logger.info(
        "PANCAKE_IMAGE_ECHO_RECORDED page_id=%s conversation_id=%s message_mid=%s attachment_count=%s",
        page_id,
        conversation_id,
        event.get("message_mid"),
        event.get("attachment_count"),
    )
    return event


def _find_pancake_public_api_image_echo(
    *,
    page_id: str,
    conversation_id: str,
    since_monotonic: float,
) -> dict[str, Any] | None:
    normalized_page_id = str(page_id or "").strip()
    normalized_conversation_id = str(conversation_id or "").strip()
    if not normalized_page_id or not normalized_conversation_id:
        return None

    now_monotonic = time.monotonic()
    with _pancake_image_echo_lock:
        _prune_pancake_image_echo_events_unlocked(now_monotonic)
        events = list(
            _pancake_image_echo_events.get((normalized_page_id, normalized_conversation_id), [])
        )

    matching_events = [
        event
        for event in events
        if float(event.get("received_at_monotonic") or 0) >= since_monotonic
    ]
    if not matching_events:
        return None
    return min(matching_events, key=lambda event: float(event.get("received_at_monotonic") or 0))


async def _wait_for_pancake_public_api_image_echo(
    *,
    page_id: str,
    conversation_id: str,
    since_monotonic: float,
    timeout_seconds: float,
) -> dict[str, Any] | None:
    deadline = time.monotonic() + max(float(timeout_seconds), 0.0)
    while True:
        echo_event = _find_pancake_public_api_image_echo(
            page_id=page_id,
            conversation_id=conversation_id,
            since_monotonic=since_monotonic,
        )
        if echo_event is not None:
            return echo_event

        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds <= 0:
            return None
        await asyncio.sleep(min(PANCAKE_IMAGE_ECHO_POLL_INTERVAL_SECONDS, remaining_seconds))


def _has_pancake_message_content(normalized: dict[str, Any]) -> bool:
    text = str(normalized.get("text") or "").strip()
    attachments = normalized.get("attachments") or []
    return bool(text or attachments)


def _has_pancake_text_message(normalized: dict[str, Any]) -> bool:
    text = str(normalized.get("text") or "").strip()
    return bool(text)


def _has_pancake_ai_supported_content(normalized: dict[str, Any]) -> bool:
    return _has_pancake_text_message(normalized) or _has_pancake_image_urls(normalized)


def _is_pancake_human_admin_message(normalized: dict[str, Any]) -> bool:
    if not _is_pancake_sender_page(normalized):
        return False
    if _is_pancake_public_api_echo(normalized):
        return False
    admin_name = str(normalized.get("message_from_admin_name") or "").strip()
    uid = str(normalized.get("message_from_uid") or "").strip()
    return bool(admin_name and uid and _has_pancake_message_content(normalized))


def _classify_pancake_message(normalized: dict[str, Any]) -> str:
    if is_pancake_ad_card_message(normalized):
        return PANCAKE_MESSAGE_AD_CARD
    if is_pancake_page_comment_reply_notice(normalized):
        return PANCAKE_MESSAGE_PAGE_COMMENT_REPLY_NOTICE
    message_type = str(normalized.get("message_type") or "").strip().upper()
    if (
        message_type == PANCAKE_MESSAGE_COMMENT_TYPE
        and not bool(normalized.get("is_echo"))
        and not _is_pancake_sender_page(normalized)
        and str(normalized.get("comment_message_id") or "").strip()
    ):
        return PANCAKE_MESSAGE_CUSTOMER_COMMENT
    if not bool(normalized.get("is_echo")) and not _is_pancake_sender_page(normalized):
        return PANCAKE_MESSAGE_CUSTOMER
    if _is_pancake_human_admin_message(normalized):
        return PANCAKE_MESSAGE_ADMIN
    return PANCAKE_MESSAGE_BOT_ECHO


def _pancake_dangerous_keyword_result(
    normalized: dict[str, Any],
    *,
    message_kind: str,
    reason: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "ignored",
        "ok": False,
        "reason": reason,
        "message_mid": str(normalized.get("message_mid") or "").strip(),
        "message_kind": message_kind,
    }
    page_id = str(normalized.get("page_id") or "").strip()
    pancake_conversation_id = str(normalized.get("pancake_conversation_id") or "").strip()
    if page_id:
        result["page_id"] = page_id
    if pancake_conversation_id:
        result["pancake_conversation_id"] = pancake_conversation_id
    return result


def _check_pancake_dangerous_keyword_block(
    normalized: dict[str, Any],
    *,
    message_kind: str,
) -> dict[str, Any] | None:
    try:
        check_result = check_dangerous_keyword(normalized.get("text"))
    except DangerousKeywordLoadError as exc:
        logger.error(
            "PANCAKE_DANGEROUS_KEYWORD_CHECK_FAILED page_id=%s sender_id=%s message_mid=%s pancake_conversation_id=%s reason=%s path=%s",
            normalized.get("page_id"),
            normalized.get("sender_id"),
            normalized.get("message_mid"),
            normalized.get("pancake_conversation_id"),
            exc.reason,
            exc.path,
        )
        return _pancake_dangerous_keyword_result(
            normalized,
            message_kind=message_kind,
            reason=PANCAKE_DANGEROUS_KEYWORD_UNAVAILABLE_REASON,
        )

    if not bool(check_result.get("blocked")):
        return None

    logger.warning(
        "PANCAKE_DANGEROUS_KEYWORD_BLOCKED page_id=%s sender_id=%s message_mid=%s pancake_conversation_id=%s matched_keyword=%s reason=%s",
        normalized.get("page_id"),
        normalized.get("sender_id"),
        normalized.get("message_mid"),
        normalized.get("pancake_conversation_id"),
        check_result.get("matched_keyword"),
        PANCAKE_DANGEROUS_KEYWORD_BLOCKED_REASON,
    )
    return _pancake_dangerous_keyword_result(
        normalized,
        message_kind=message_kind,
        reason=PANCAKE_DANGEROUS_KEYWORD_BLOCKED_REASON,
    )


def _is_pancake_auto_consult_trigger(message_kind: str) -> bool:
    return message_kind in {
        PANCAKE_MESSAGE_AD_CARD,
        PANCAKE_MESSAGE_PAGE_COMMENT_REPLY_NOTICE,
    }


def _get_pancake_auto_consult_product_code_regex() -> str:
    return str(
        getattr(settings, "pancake_auto_consult_product_code_regex", "")
        or r"(?<![A-Za-z0-9])(?:[A-Za-z]?\d{6,8})(?:(?:[A-Za-z0-9]{1,3})|(?:[^\S\r\n]*-[^\S\r\n]*[A-Za-z0-9]{1,3}))?(?![A-Za-z0-9])"
    )


def _prepare_pancake_comment_ai_context(
    normalized: dict[str, Any],
    *,
    initial_product_prompt: bool = True,
) -> dict[str, Any]:
    message_type = str(normalized.get("message_type") or "").strip().upper()
    if message_type != PANCAKE_MESSAGE_COMMENT_TYPE:
        return {
            "content": str(normalized.get("text") or "").strip(),
            "product_codes": [],
            "product_code_count": 0,
            "augmented": False,
            "initial_product_prompt": False,
            "follow_up": False,
            "post_message_present": False,
        }

    context = build_customer_comment_ai_message(
        normalized,
        regex_pattern=_get_pancake_auto_consult_product_code_regex(),
        initial_product_prompt=initial_product_prompt,
    )
    product_codes = [
        str(code or "").strip()
        for code in (context.get("product_codes") or [])
        if str(code or "").strip()
    ]
    normalized["post_product_codes"] = product_codes
    normalized["post_product_code_count"] = len(product_codes)
    normalized["comment_ai_message_augmented"] = bool(context.get("augmented"))
    normalized["comment_ai_initial_product_prompt"] = bool(
        context.get("initial_product_prompt")
    )
    normalized["comment_ai_follow_up"] = bool(context.get("follow_up"))
    metadata = _as_dict(normalized.get("metadata"))
    metadata.update(
        {
            "post_product_codes": product_codes,
            "post_product_code_count": len(product_codes),
            "comment_ai_message_augmented": bool(context.get("augmented")),
            "comment_ai_initial_product_prompt": bool(
                context.get("initial_product_prompt")
            ),
            "comment_ai_follow_up": bool(context.get("follow_up")),
        }
    )
    normalized["metadata"] = metadata
    return context


def _is_pancake_auto_consult_enabled() -> bool:
    raw = getattr(settings, "pancake_auto_consult_enabled", False)
    if isinstance(raw, bool):
        return raw
    return str(raw or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _is_pancake_comment_auto_reply_enabled() -> bool:
    raw = getattr(settings, "pancake_comment_auto_reply_enabled", False)
    if isinstance(raw, bool):
        return raw
    return str(raw or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _coerce_pancake_channel_image_limit(value: Any, *, fallback: int = 3) -> int:
    try:
        fallback_value = int(fallback)
    except (TypeError, ValueError):
        fallback_value = 3
    try:
        parsed_value = int(value)
    except (TypeError, ValueError):
        parsed_value = fallback_value
    return max(1, parsed_value)


def _get_pancake_channel_image_limit(normalized: dict[str, Any]) -> int:
    message_type = str(normalized.get("message_type") or "").strip().upper()
    if message_type == PANCAKE_MESSAGE_COMMENT_TYPE:
        return _coerce_pancake_channel_image_limit(
            getattr(settings, "pancake_comment_image_max_count", 3),
            fallback=3,
        )
    return _coerce_pancake_channel_image_limit(
        getattr(settings, "pancake_inbox_image_max_count", 3),
        fallback=3,
    )


def _pancake_auto_consult_processing_key(*, trigger_type: str, trigger_message_mid: str) -> str:
    return f"pancake_auto_consult:{trigger_type}:{trigger_message_mid}"


def _resolve_pancake_auto_consult_customer_id(normalized: dict[str, Any]) -> str | None:
    page_id = str(normalized.get("page_id") or "").strip()
    for key in ("conversation_customer_id", "page_customer_id", "conversation_sender_id"):
        value = str(normalized.get(key) or "").strip()
        if value and value != page_id:
            return value
    return None


def _pancake_auto_consult_merge_key(normalized: dict[str, Any]) -> tuple[str, str, str] | None:
    page_id = str(normalized.get("page_id") or "").strip()
    pancake_conversation_id = str(normalized.get("pancake_conversation_id") or "").strip()
    customer_id = _resolve_pancake_auto_consult_customer_id(normalized)
    if not customer_id and not _is_pancake_sender_page(normalized):
        customer_id = str(normalized.get("sender_id") or "").strip()
    if not page_id or not pancake_conversation_id or not customer_id:
        return None
    return (page_id, pancake_conversation_id, customer_id)


def _pancake_auto_consult_trigger_key(
    *,
    trigger_type: str,
    trigger_message_mid: str,
) -> tuple[str, str] | None:
    normalized_trigger_type = str(trigger_type or "").strip()
    normalized_trigger_message_mid = str(trigger_message_mid or "").strip()
    if not normalized_trigger_type or not normalized_trigger_message_mid:
        return None
    return (normalized_trigger_type, normalized_trigger_message_mid)


def _prune_consumed_pancake_ad_context_mids_unlocked(now_monotonic: float) -> None:
    cutoff = now_monotonic - PANCAKE_AD_CONTEXT_CONSUMED_TTL_SECONDS
    for key, consumed_at in list(_pancake_consumed_ad_context_mids.items()):
        if consumed_at < cutoff:
            _pancake_consumed_ad_context_mids.pop(key, None)


def _mark_pancake_auto_consult_trigger_consumed(
    *,
    trigger_type: str,
    trigger_message_mid: str,
) -> None:
    trigger_key = _pancake_auto_consult_trigger_key(
        trigger_type=trigger_type,
        trigger_message_mid=trigger_message_mid,
    )
    if trigger_key is None:
        return
    now_monotonic = time.monotonic()
    with _pancake_ad_context_buffer_lock:
        _prune_consumed_pancake_ad_context_mids_unlocked(now_monotonic)
        _pancake_consumed_ad_context_mids[trigger_key] = now_monotonic


def _is_pancake_auto_consult_trigger_consumed_in_memory(
    *,
    trigger_type: str,
    trigger_message_mid: str,
) -> bool:
    trigger_key = _pancake_auto_consult_trigger_key(
        trigger_type=trigger_type,
        trigger_message_mid=trigger_message_mid,
    )
    if trigger_key is None:
        return False
    now_monotonic = time.monotonic()
    with _pancake_ad_context_buffer_lock:
        _prune_consumed_pancake_ad_context_mids_unlocked(now_monotonic)
        return trigger_key in _pancake_consumed_ad_context_mids


def _build_pancake_auto_consult_metadata(
    *,
    source_detail: dict[str, Any],
    prompt_result: dict[str, Any],
) -> dict[str, Any]:
    description = str(source_detail.get("description") or "").strip()
    product_codes = [
        str(code or "").strip()
        for code in (prompt_result.get("product_codes") or [])
        if str(code or "").strip()
    ]
    metadata: dict[str, Any] = {
        "trigger_type": source_detail.get("trigger_type"),
        "trigger_message_mid": source_detail.get("trigger_message_mid"),
        "product_codes": product_codes,
        "product_code_count": len(product_codes),
        "description_present": bool(description),
        "description_length": len(description),
    }
    if description:
        metadata["description_preview"] = _preview_text(description, limit=200)

    for key in ("ad_id", "ad_message_mid", "post_id", "comment_id"):
        value = str(source_detail.get(key) or "").strip()
        if value:
            metadata[key] = value
    return metadata


def _build_pancake_auto_consult_normalized(
    normalized: dict[str, Any],
    *,
    source_detail: dict[str, Any],
    prompt_result: dict[str, Any],
) -> dict[str, Any]:
    customer_id = _resolve_pancake_auto_consult_customer_id(normalized)
    if not customer_id:
        return {
            "ok": False,
            "reason": "pancake_auto_consult_customer_missing",
        }

    prompt = str(prompt_result.get("prompt") or "").strip()
    if not prompt:
        return {
            "ok": False,
            "reason": "pancake_auto_consult_prompt_missing",
        }

    page_id = str(normalized.get("page_id") or "").strip()
    conversation_sender_id = str(normalized.get("conversation_sender_id") or "").strip()
    conversation_sender_name = str(normalized.get("conversation_sender_name") or "").strip()
    auto_consult = _build_pancake_auto_consult_metadata(
        source_detail=source_detail,
        prompt_result=prompt_result,
    )
    synthetic = dict(normalized)
    synthetic.update(
        {
            "ok": True,
            "source": PANCAKE_AUTO_CONSULT_SOURCE,
            "sender_id": customer_id,
            "sender_name": conversation_sender_name or normalized.get("sender_name"),
            "recipient_id": page_id,
            "message_mid": auto_consult.get("trigger_message_mid"),
            "message_type": PANCAKE_MESSAGE_INBOX,
            "conversation_type": PANCAKE_MESSAGE_INBOX,
            "is_echo": False,
            "text": prompt,
            "attachments": [],
            "page_customer_id": customer_id,
            "auto_consult": auto_consult,
            "post_id": auto_consult.get("post_id") or normalized.get("post_id"),
        }
    )
    if conversation_sender_id and conversation_sender_id != page_id:
        synthetic["platform_sender_id"] = conversation_sender_id
    metadata = _as_dict(synthetic.get("metadata"))
    metadata["auto_consult"] = auto_consult
    synthetic["metadata"] = metadata
    return synthetic


def _build_pancake_auto_consult_merged_prompt(
    *,
    customer_text: Any,
    auto_consult_prompt: Any,
) -> str:
    normalized_customer_text = str(customer_text or "").strip()
    normalized_auto_consult_prompt = str(auto_consult_prompt or "").strip()
    if normalized_customer_text and normalized_auto_consult_prompt:
        return f"{normalized_customer_text.rstrip(' ,;')}, {normalized_auto_consult_prompt}"
    return normalized_customer_text or normalized_auto_consult_prompt


def _build_pancake_auto_consult_merged_normalized(
    customer_normalized: dict[str, Any],
    *,
    ad_normalized: dict[str, Any],
    source_detail: dict[str, Any],
    prompt_result: dict[str, Any],
) -> dict[str, Any]:
    prompt = _build_pancake_auto_consult_merged_prompt(
        customer_text=customer_normalized.get("text"),
        auto_consult_prompt=prompt_result.get("prompt"),
    )
    if not prompt:
        return {
            "ok": False,
            "reason": "pancake_auto_consult_prompt_missing",
        }

    auto_consult = _build_pancake_auto_consult_metadata(
        source_detail=source_detail,
        prompt_result=prompt_result,
    )
    auto_consult.update(
        {
            "merged_customer_message": True,
            "merged_customer_message_mid": customer_normalized.get("message_mid"),
            "merged_customer_message_mids": customer_normalized.get("merged_message_mids")
            or [customer_normalized.get("message_mid")],
        }
    )
    ad_message_mid = str(ad_normalized.get("message_mid") or "").strip()
    if ad_message_mid:
        auto_consult["trigger_message_mid"] = ad_message_mid
        auto_consult["ad_message_mid"] = ad_message_mid
    if ad_normalized.get("post_id") and not auto_consult.get("post_id"):
        auto_consult["post_id"] = ad_normalized.get("post_id")

    merged = dict(customer_normalized)
    merged["source"] = PANCAKE_AUTO_CONSULT_SOURCE
    merged["text"] = prompt
    merged["auto_consult"] = auto_consult
    merged["post_id"] = auto_consult.get("post_id") or customer_normalized.get("post_id")
    metadata = dict(_as_dict(merged.get("metadata")))
    metadata["auto_consult"] = auto_consult
    metadata["auto_consult_merged_with_customer_message"] = True
    merged["metadata"] = metadata
    return merged


async def _is_duplicate_pancake_auto_consult(
    *,
    trigger_type: str,
    trigger_message_mid: str,
) -> bool:
    normalized_trigger_type = str(trigger_type or "").strip()
    normalized_trigger_message_mid = str(trigger_message_mid or "").strip()
    if not normalized_trigger_type or not normalized_trigger_message_mid:
        return False
    if _is_pancake_auto_consult_trigger_consumed_in_memory(
        trigger_type=normalized_trigger_type,
        trigger_message_mid=normalized_trigger_message_mid,
    ):
        return True
    existing_message = await Message.find_one(
        {
            "message_mid": normalized_trigger_message_mid,
            "meta.source": PANCAKE_AUTO_CONSULT_SOURCE,
            "meta.trigger_type": normalized_trigger_type,
        }
    )
    if existing_message is not None:
        return True

    existing_merged_message = await Message.find_one(
        {
            "meta.auto_consult.trigger_message_mid": normalized_trigger_message_mid,
            "meta.auto_consult.trigger_type": normalized_trigger_type,
        }
    )
    return existing_merged_message is not None


async def _prepare_pancake_auto_consult(
    normalized: dict[str, Any],
    *,
    message_kind: str,
) -> dict[str, Any]:
    page_id = str(normalized.get("page_id") or "").strip()
    pancake_conversation_id = str(normalized.get("pancake_conversation_id") or "").strip()
    trigger_message_mid = str(normalized.get("message_mid") or "").strip()
    if not page_id:
        return {"ok": False, "reason": "missing_page_id"}
    if not pancake_conversation_id:
        return {"ok": False, "reason": "missing_pancake_conversation_id"}

    logger.info(
        "PANCAKE_AUTO_CONSULT_CONTEXT_FETCH_START page_id=%s conversation_id=%s trigger_type=%s trigger_message_mid=%s",
        page_id,
        pancake_conversation_id,
        message_kind,
        trigger_message_mid,
    )
    fetch_result = await fetch_pancake_conversation_messages(
        page_id=page_id,
        conversation_id=pancake_conversation_id,
    )
    if not bool(fetch_result.get("ok")):
        logger.warning(
            "PANCAKE_AUTO_CONSULT_CONTEXT_FETCH_FAILED page_id=%s conversation_id=%s trigger_type=%s trigger_message_mid=%s reason=%s",
            page_id,
            pancake_conversation_id,
            message_kind,
            trigger_message_mid,
            fetch_result.get("reason"),
        )
        return {
            "ok": False,
            "reason": fetch_result.get("reason") or "pancake_context_fetch_failed",
            "fetch_result": fetch_result,
        }

    logger.info(
        "PANCAKE_AUTO_CONSULT_CONTEXT_FETCH_OK page_id=%s conversation_id=%s trigger_type=%s trigger_message_mid=%s status_code=%s",
        page_id,
        pancake_conversation_id,
        message_kind,
        trigger_message_mid,
        fetch_result.get("status_code"),
    )

    response_data = fetch_result.get("response_data")
    if message_kind == PANCAKE_MESSAGE_AD_CARD:
        source_detail = extract_ad_card_source_detail(normalized, response_data)
    elif message_kind == PANCAKE_MESSAGE_PAGE_COMMENT_REPLY_NOTICE:
        source_detail = extract_page_comment_reply_source_detail(normalized, response_data)
    else:
        source_detail = {"ok": False, "reason": "unsupported_auto_consult_trigger"}

    if not bool(source_detail.get("ok")):
        logger.warning(
            "PANCAKE_AUTO_CONSULT_CONTEXT_PARSE_FAILED page_id=%s conversation_id=%s trigger_type=%s trigger_message_mid=%s reason=%s",
            page_id,
            pancake_conversation_id,
            message_kind,
            trigger_message_mid,
            source_detail.get("reason"),
        )
        return {
            "ok": False,
            "reason": source_detail.get("reason") or "pancake_context_parse_failed",
            "source_detail": source_detail,
        }

    prompt_result = build_auto_consult_prompt_from_description(
        source_detail.get("description"),
        regex_pattern=_get_pancake_auto_consult_product_code_regex(),
    )
    product_codes = prompt_result.get("product_codes") or []
    logger.info(
        "PANCAKE_AUTO_CONSULT_PRODUCT_CODE_EXTRACTED page_id=%s conversation_id=%s trigger_type=%s trigger_message_mid=%s product_code_count=%s",
        page_id,
        pancake_conversation_id,
        message_kind,
        trigger_message_mid,
        len(product_codes) if isinstance(product_codes, list) else 0,
    )
    if not bool(prompt_result.get("ok")):
        return {
            "ok": False,
            "reason": prompt_result.get("reason") or "pancake_auto_consult_prompt_failed",
            "source_detail": source_detail,
            "prompt_result": prompt_result,
        }

    return {
        "ok": True,
        "reason": None,
        "source_detail": source_detail,
        "prompt_result": prompt_result,
    }


def _resolve_pancake_admin_customer_id(normalized: dict[str, Any]) -> str | None:
    page_id = str(normalized.get("page_id") or "").strip()
    for key in ("conversation_customer_id", "page_customer_id", "conversation_sender_id"):
        value = str(normalized.get(key) or "").strip()
        if value and value != page_id:
            return value
    return None


def _normalized_for_pancake_admin_customer(normalized: dict[str, Any]) -> dict[str, Any]:
    customer_id = _resolve_pancake_admin_customer_id(normalized)
    if not customer_id:
        raise ValueError("Missing Pancake admin customer_id")

    page_id = str(normalized.get("page_id") or "").strip()
    conversation_sender_id = str(normalized.get("conversation_sender_id") or "").strip()
    conversation_sender_name = str(normalized.get("conversation_sender_name") or "").strip()
    customer_normalized = dict(normalized)
    customer_normalized["sender_id"] = customer_id
    customer_normalized["page_customer_id"] = customer_id
    if conversation_sender_id and conversation_sender_id != page_id:
        customer_normalized["platform_sender_id"] = conversation_sender_id
    if conversation_sender_name:
        customer_normalized["sender_name"] = conversation_sender_name
    return customer_normalized


async def _get_or_create_pancake_admin_conversation(normalized: dict[str, Any]) -> Conversation:
    return await _get_or_create_pancake_conversation(
        _normalized_for_pancake_admin_customer(normalized)
    )


async def _pause_pancake_conversation_for_admin_takeover(
    conversation: Conversation,
    normalized: dict[str, Any],
) -> dict[str, Any]:
    paused_at = now_vn()
    paused_until = paused_at + timedelta(minutes=_get_pancake_admin_takeover_pause_minutes())
    paused_by = (
        str(
            normalized.get("message_from_uid")
            or normalized.get("message_from_admin_name")
            or normalized.get("platform_sender_id")
            or normalized.get("page_id")
            or ""
        ).strip()
        or None
    )

    conversation.bot_paused_at = paused_at
    conversation.bot_paused_until = paused_until
    conversation.bot_paused_reason = "pancake_admin_message"
    conversation.bot_paused_by = paused_by
    await conversation.save()

    logger.info(
        "PANCAKE_CONVERSATION_PAUSED_BY_ADMIN conversation_id=%s customer_id=%s paused_by=%s paused_until=%s message_mid=%s",
        conversation.id,
        conversation.customer_id,
        paused_by,
        paused_until.isoformat(),
        normalized.get("message_mid"),
    )
    return {
        "conversation_id": str(conversation.id),
        "customer_id": conversation.customer_id,
        "bot_paused_until": paused_until,
        "bot_paused_by": paused_by,
    }


async def _pause_pancake_conversation_for_ai_quota_handover(
    *,
    conversation: Conversation,
    normalized: dict[str, Any],
    matched_marker: str | None = None,
) -> dict[str, Any]:
    conversation_id = str(getattr(conversation, "id", "") or "").strip()
    if not conversation_id:
        logger.warning(
            "PANCAKE_AI_QUOTA_HANDOVER_PAUSE_SKIPPED reason=missing_conversation_id message_mid=%s",
            normalized.get("message_mid"),
        )
        return {"updated": False, "reason": "missing_conversation_id"}

    paused_at = now_vn()
    pause_minutes = PANCAKE_AI_QUOTA_PAUSE_MINUTES
    paused_until = paused_at + timedelta(minutes=pause_minutes)

    conversation.status = ConversationStatus.APILIMIT
    conversation.bot_paused_at = paused_at
    conversation.bot_paused_until = paused_until
    conversation.bot_paused_reason = PANCAKE_AI_QUOTA_PAUSE_REASON
    conversation.bot_paused_by = PANCAKE_AI_QUOTA_PAUSED_BY

    try:
        await conversation.save()
    except Exception as exc:
        logger.exception(
            "PANCAKE_AI_QUOTA_HANDOVER_PAUSE_FAILED conversation_id=%s customer_id=%s message_mid=%s error=%s",
            conversation_id,
            getattr(conversation, "customer_id", None),
            normalized.get("message_mid"),
            exc,
        )
        return {
            "updated": False,
            "reason": "ai_quota_handover_pause_failed",
            "error": str(exc),
        }

    logger.warning(
        "PANCAKE_AI_QUOTA_HANDOVER_PAUSED conversation_id=%s customer_id=%s paused_until=%s pause_minutes=%s message_mid=%s matched_marker=%s",
        conversation_id,
        getattr(conversation, "customer_id", None),
        paused_until.isoformat(),
        pause_minutes,
        normalized.get("message_mid"),
        matched_marker,
    )
    return {
        "updated": True,
        "conversation_id": conversation_id,
        "customer_id": getattr(conversation, "customer_id", None),
        "status": ConversationStatus.APILIMIT.value,
        "bot_paused_at": paused_at,
        "bot_paused_until": paused_until,
        "bot_paused_reason": PANCAKE_AI_QUOTA_PAUSE_REASON,
        "bot_paused_by": PANCAKE_AI_QUOTA_PAUSED_BY,
        "pause_minutes": pause_minutes,
        "matched_marker": matched_marker,
    }


async def _maybe_pause_pancake_conversation_for_ai_quota_handover(
    *,
    conversation: Conversation,
    normalized: dict[str, Any],
    reply: dict[str, Any],
) -> dict[str, Any] | None:
    if not bool(reply.get("ai_quota_fallback")):
        return None
    return await _pause_pancake_conversation_for_ai_quota_handover(
        conversation=conversation,
        normalized=normalized,
        matched_marker=str(reply.get("ai_fallback_marker") or "").strip() or None,
    )


def _normalize_pancake_reply_for_repeat_check(reply_text: Any) -> str:
    sanitized = sanitize_pancake_outgoing_message(reply_text)
    return " ".join(str(sanitized or "").split()).casefold().strip()


def _calculate_pancake_reply_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


async def _get_recent_successful_pancake_bot_messages(
    *,
    conversation: Conversation,
    limit: int = 2,
) -> list[Message]:
    conversation_id = getattr(conversation, "id", None)
    if conversation_id is None:
        return []

    try:
        normalized_limit = max(1, int(limit))
    except (TypeError, ValueError):
        normalized_limit = 2

    try:
        return await Message.find(
            {
                "conversation_id": conversation_id,
                "role": MessageRole.BOT.value,
                "meta.pancake_send_result.ok": True,
            }
        ).sort(-Message.created_at).limit(normalized_limit).to_list()
    except Exception as exc:
        logger.debug(
            "PANCAKE_REPEATED_BOT_REPLY_CHECK_SKIPPED conversation_id=%s reason=query_failed error=%s",
            conversation_id,
            exc,
        )
        return []


async def _detect_pancake_repeated_bot_reply(
    *,
    conversation: Conversation,
    reply_text: str,
) -> dict[str, Any]:
    current_normalized = _normalize_pancake_reply_for_repeat_check(reply_text)
    if not current_normalized:
        return {"detected": False, "reason": "empty_current_reply"}

    previous_messages = await _get_recent_successful_pancake_bot_messages(
        conversation=conversation,
        limit=2,
    )
    if len(previous_messages) < 2:
        return {
            "detected": False,
            "reason": "not_enough_previous_bot_messages",
            "previous_count": len(previous_messages),
        }

    previous_normalized = [
        _normalize_pancake_reply_for_repeat_check(getattr(message, "content", ""))
        for message in previous_messages[:2]
    ]
    similarities = {
        "current_to_last_bot_1": _calculate_pancake_reply_similarity(
            current_normalized,
            previous_normalized[0],
        ),
        "current_to_last_bot_2": _calculate_pancake_reply_similarity(
            current_normalized,
            previous_normalized[1],
        ),
        "last_bot_1_to_last_bot_2": _calculate_pancake_reply_similarity(
            previous_normalized[0],
            previous_normalized[1],
        ),
    }
    if (
        previous_normalized[0]
        and previous_normalized[1]
        and current_normalized == previous_normalized[0] == previous_normalized[1]
    ):
        return {
            "detected": True,
            "reason": "current_reply_matches_two_previous_bot_messages",
            "match_count": 3,
            "previous_bot_message_ids": [
                str(getattr(message, "id", ""))
                for message in previous_messages[:2]
                if str(getattr(message, "id", "")).strip()
            ],
            "similarity_threshold": PANCAKE_REPEATED_BOT_REPLY_SIMILARITY_THRESHOLD,
            "similarities": similarities,
        }

    fuzzy_candidate_lengths = [
        len(current_normalized),
        len(previous_normalized[0]),
        len(previous_normalized[1]),
    ]
    if (
        previous_normalized[0]
        and previous_normalized[1]
        and min(fuzzy_candidate_lengths) >= PANCAKE_REPEATED_BOT_REPLY_FUZZY_MIN_CHARS
        and all(
            similarity >= PANCAKE_REPEATED_BOT_REPLY_SIMILARITY_THRESHOLD
            for similarity in similarities.values()
        )
    ):
        return {
            "detected": True,
            "reason": "current_reply_similar_to_two_previous_bot_messages",
            "match_count": 3,
            "previous_bot_message_ids": [
                str(getattr(message, "id", ""))
                for message in previous_messages[:2]
                if str(getattr(message, "id", "")).strip()
            ],
            "similarity_threshold": PANCAKE_REPEATED_BOT_REPLY_SIMILARITY_THRESHOLD,
            "fuzzy_min_chars": PANCAKE_REPEATED_BOT_REPLY_FUZZY_MIN_CHARS,
            "similarities": similarities,
            "normalized_lengths": {
                "current": fuzzy_candidate_lengths[0],
                "last_bot_1": fuzzy_candidate_lengths[1],
                "last_bot_2": fuzzy_candidate_lengths[2],
            },
        }

    return {
        "detected": False,
        "reason": "previous_bot_messages_differ",
        "previous_count": len(previous_messages),
        "similarity_threshold": PANCAKE_REPEATED_BOT_REPLY_SIMILARITY_THRESHOLD,
        "fuzzy_min_chars": PANCAKE_REPEATED_BOT_REPLY_FUZZY_MIN_CHARS,
        "similarities": similarities,
    }


async def _pause_pancake_conversation_for_repeated_bot_reply(
    *,
    conversation: Conversation,
    normalized: dict[str, Any],
    repeat_detection: dict[str, Any],
) -> dict[str, Any]:
    conversation_id = str(getattr(conversation, "id", "") or "").strip()
    if not conversation_id:
        logger.warning(
            "PANCAKE_REPEATED_BOT_REPLY_HANDOVER_SKIPPED reason=missing_conversation_id message_mid=%s",
            normalized.get("message_mid"),
        )
        return {"updated": False, "reason": "missing_conversation_id"}

    paused_at = now_vn()
    paused_until = paused_at + timedelta(minutes=PANCAKE_REPEATED_BOT_REPLY_PAUSE_MINUTES)

    conversation.status = ConversationStatus.HANDOVER
    conversation.bot_paused_at = paused_at
    conversation.bot_paused_until = paused_until
    conversation.bot_paused_reason = PANCAKE_REPEATED_BOT_REPLY_PAUSE_REASON
    conversation.bot_paused_by = PANCAKE_REPEATED_BOT_REPLY_PAUSED_BY
    conversation.updated_at = paused_at

    try:
        await conversation.save()
    except Exception as exc:
        logger.exception(
            "PANCAKE_REPEATED_BOT_REPLY_HANDOVER_FAILED conversation_id=%s message_mid=%s error=%s",
            conversation_id,
            normalized.get("message_mid"),
            exc,
        )
        return {
            "updated": False,
            "reason": "repeated_bot_reply_handover_failed",
            "error": str(exc),
        }

    logger.warning(
        "PANCAKE_REPEATED_BOT_REPLY_HANDOVER conversation_id=%s page_id=%s pancake_conversation_id=%s message_mid=%s pause_minutes=%s previous_bot_message_ids=%s",
        conversation_id,
        normalized.get("page_id"),
        normalized.get("pancake_conversation_id"),
        normalized.get("message_mid"),
        PANCAKE_REPEATED_BOT_REPLY_PAUSE_MINUTES,
        repeat_detection.get("previous_bot_message_ids"),
    )
    return {
        "updated": True,
        "conversation_id": conversation_id,
        "status": ConversationStatus.HANDOVER.value,
        "bot_paused_at": paused_at,
        "bot_paused_until": paused_until,
        "bot_paused_reason": PANCAKE_REPEATED_BOT_REPLY_PAUSE_REASON,
        "bot_paused_by": PANCAKE_REPEATED_BOT_REPLY_PAUSED_BY,
        "pause_minutes": PANCAKE_REPEATED_BOT_REPLY_PAUSE_MINUTES,
    }


async def _maybe_handover_pancake_repeated_bot_reply(
    *,
    conversation: Conversation,
    normalized: dict[str, Any],
    reply_text: str,
) -> dict[str, Any] | None:
    repeat_detection = await _detect_pancake_repeated_bot_reply(
        conversation=conversation,
        reply_text=reply_text,
    )
    if not bool(repeat_detection.get("detected")):
        return None

    handover_result = await _pause_pancake_conversation_for_repeated_bot_reply(
        conversation=conversation,
        normalized=normalized,
        repeat_detection=repeat_detection,
    )
    return {
        "detected": True,
        "reason": "repeated_bot_reply_handover",
        "repeat_detection": repeat_detection,
        "handover_result": handover_result,
    }


async def _is_pancake_recent_bot_echo(
    *,
    conversation: Conversation,
    normalized: dict[str, Any],
) -> bool:
    text = str(normalized.get("text") or "").strip()
    pancake_conversation_id = str(normalized.get("pancake_conversation_id") or "").strip()
    if not text or not pancake_conversation_id:
        return False

    cutoff = now_vn() - timedelta(minutes=PANCAKE_BOT_ECHO_LOOKBACK_MINUTES)
    existing_message = await Message.find_one(
        {
            "conversation_id": conversation.id,
            "role": "bot",
            "content": text,
            "meta.source": PANCAKE_MESSAGE_BOT_SOURCE,
            "meta.pancake_conversation_id": pancake_conversation_id,
            "updated_at": {"$gte": cutoff},
        }
    )
    return existing_message is not None


async def _is_pancake_recent_user_duplicate(
    *,
    conversation: Conversation,
    normalized: dict[str, Any],
) -> bool:
    text = _pancake_customer_message_content(normalized)
    pancake_conversation_id = str(normalized.get("pancake_conversation_id") or "").strip()
    if not text or not pancake_conversation_id:
        return False

    cutoff = now_vn() - timedelta(seconds=PANCAKE_USER_DUPLICATE_LOOKBACK_SECONDS)
    existing_message = await Message.find_one(
        {
            "conversation_id": conversation.id,
            "role": "user",
            "content": text,
            "meta.source": PANCAKE_MESSAGE_USER_SOURCE,
            "meta.pancake_conversation_id": pancake_conversation_id,
            "updated_at": {"$gte": cutoff},
        }
    )
    return existing_message is not None


def _try_mark_pancake_message_processing(message_mid: str | None) -> bool:
    normalized_mid = str(message_mid or "").strip()
    if not normalized_mid:
        return True
    with _processing_message_mid_lock:
        if normalized_mid in _processing_message_mids:
            return False
        _processing_message_mids.add(normalized_mid)
    return True


def _finalize_pancake_message_processing(message_mid: str | None) -> None:
    normalized_mid = str(message_mid or "").strip()
    if not normalized_mid:
        return
    with _processing_message_mid_lock:
        _processing_message_mids.discard(normalized_mid)


def _pancake_sender_buffer_key(normalized: dict[str, Any]) -> tuple[str, str, str] | None:
    page_id = str(normalized.get("page_id") or "").strip()
    pancake_conversation_id = str(normalized.get("pancake_conversation_id") or "").strip()
    sender_id = str(normalized.get("sender_id") or "").strip()
    if not page_id or not pancake_conversation_id or not sender_id:
        return None
    return (page_id, pancake_conversation_id, sender_id)


def _should_buffer_pancake_sender_message(
    normalized: dict[str, Any],
    *,
    message_kind: str,
) -> bool:
    if _get_pancake_sender_buffer_seconds() <= 0:
        return False
    if message_kind != PANCAKE_MESSAGE_CUSTOMER:
        return False
    if str(normalized.get("message_type") or "").strip().upper() != PANCAKE_MESSAGE_INBOX:
        return False
    return _has_pancake_ai_supported_content(normalized)


def _merge_pancake_buffer_items(items: list[dict[str, Any]]) -> dict[str, Any]:
    if not items:
        return {}

    base_item = items[0]
    merged = dict(_as_dict(base_item.get("normalized")))
    text_parts: list[str] = []
    attachments: list[Any] = []
    image_urls: list[str] = []
    seen_image_urls: set[str] = set()
    message_mids: list[str] = []
    message_ids: list[str] = []

    for item in items:
        normalized = _as_dict(item.get("normalized"))
        text = str(normalized.get("text") or "").strip()
        if text:
            text_parts.append(text)

        for attachment in _as_list(normalized.get("attachments")):
            attachments.append(attachment)

        for image_url in _pancake_image_urls(normalized):
            if image_url in seen_image_urls:
                continue
            image_urls.append(image_url)
            seen_image_urls.add(image_url)

        message_mid = str(normalized.get("message_mid") or "").strip()
        if message_mid:
            message_mids.append(message_mid)

        user_message = item.get("user_message")
        message_id = str(getattr(user_message, "id", "") or "").strip()
        if message_id:
            message_ids.append(message_id)

    merged["text"] = "\n".join(text_parts).strip()
    merged["attachments"] = attachments
    merged["image_urls"] = image_urls
    merged["image_attachment_count"] = sum(
        1
        for attachment in attachments
        if str(_as_dict(attachment).get("type") or "").strip().lower()
        in PANCAKE_IMAGE_ATTACHMENT_TYPES
    )
    merged["image_url_count"] = len(image_urls)
    merged["merged_message_mids"] = message_mids
    merged["merged_message_ids"] = message_ids
    metadata = dict(_as_dict(merged.get("metadata")))
    metadata.update(
        {
            "image_attachment_count": merged["image_attachment_count"],
            "image_url_count": len(image_urls),
            "merged_message_mids": message_mids,
            "merged_message_ids": message_ids,
        }
    )
    merged["metadata"] = metadata
    return merged


def _pop_pancake_sender_buffer_entry_for_key(
    key: tuple[str, str, str] | None,
    *,
    reason: str,
) -> dict[str, Any]:
    if key is None:
        return {
            "popped": False,
            "reason": "missing_sender_buffer_key",
            "entry": None,
            "message_count": 0,
            "message_mids": [],
        }

    with _pancake_sender_buffer_lock:
        entry = _pancake_sender_buffers.pop(key, None)

    if not entry:
        return {
            "popped": False,
            "reason": "sender_buffer_not_found",
            "entry": None,
            "message_count": 0,
            "message_mids": [],
        }

    task = entry.get("task")
    try:
        current_task = asyncio.current_task()
    except RuntimeError:
        current_task = None
    if task is not None and task is not current_task and not task.done():
        task.cancel()

    items = _as_list(entry.get("items"))
    message_mids = [
        str(_as_dict(item.get("normalized")).get("message_mid") or "").strip()
        for item in items
        if str(_as_dict(item.get("normalized")).get("message_mid") or "").strip()
    ]
    logger.info(
        "PANCAKE_SENDER_BUFFER_POPPED page_id=%s conversation_id=%s sender_id=%s message_count=%s reason=%s",
        key[0],
        key[1],
        key[2],
        len(items),
        reason,
    )
    return {
        "popped": True,
        "reason": reason,
        "entry": entry,
        "message_count": len(items),
        "message_mids": message_mids,
    }


def _cancel_pancake_sender_buffer_for_key(
    key: tuple[str, str, str] | None,
    *,
    reason: str,
) -> dict[str, Any]:
    result = _pop_pancake_sender_buffer_entry_for_key(key, reason=reason)
    return {
        "cancelled": bool(result.get("popped")),
        "reason": result.get("reason"),
        "message_count": result.get("message_count") or 0,
        "message_mids": result.get("message_mids") or [],
    }


def _cancel_pancake_sender_buffer(
    normalized: dict[str, Any],
    *,
    reason: str,
) -> dict[str, Any]:
    return _cancel_pancake_sender_buffer_for_key(
        _pancake_sender_buffer_key(normalized),
        reason=reason,
    )


def _is_pending_pancake_ad_context_trigger(
    *,
    trigger_type: str,
    trigger_message_mid: str,
) -> bool:
    trigger_key = _pancake_auto_consult_trigger_key(
        trigger_type=trigger_type,
        trigger_message_mid=trigger_message_mid,
    )
    if trigger_key is None:
        return False
    with _pancake_ad_context_buffer_lock:
        return any(
            _as_dict(entry.get("trigger_key")) == {
                "trigger_type": trigger_key[0],
                "trigger_message_mid": trigger_key[1],
            }
            for entry in _pancake_ad_context_buffers.values()
        )


def _pop_pending_pancake_ad_context_for_key(
    key: tuple[str, str, str] | None,
    *,
    reason: str,
) -> dict[str, Any]:
    if key is None:
        return {
            "popped": False,
            "reason": "missing_ad_context_key",
            "entry": None,
        }
    with _pancake_ad_context_buffer_lock:
        entry = _pancake_ad_context_buffers.pop(key, None)

    if not entry:
        return {
            "popped": False,
            "reason": "ad_context_not_found",
            "entry": None,
        }

    task = entry.get("task")
    try:
        current_task = asyncio.current_task()
    except RuntimeError:
        current_task = None
    if task is not None and task is not current_task and not task.done():
        task.cancel()

    normalized = _as_dict(entry.get("normalized"))
    logger.info(
        "PANCAKE_AD_CONTEXT_BUFFER_POPPED page_id=%s conversation_id=%s customer_id=%s trigger_type=%s trigger_message_mid=%s reason=%s",
        key[0],
        key[1],
        key[2],
        entry.get("message_kind"),
        normalized.get("message_mid"),
        reason,
    )
    return {
        "popped": True,
        "reason": reason,
        "entry": entry,
    }


async def _process_pancake_sender_buffer_with_auto_consult_context(
    *,
    key: tuple[str, str, str],
    sender_entry: dict[str, Any],
    ad_entry: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    normalized = _as_dict(ad_entry.get("normalized"))
    message_kind = str(ad_entry.get("message_kind") or PANCAKE_MESSAGE_AD_CARD)
    auto_consult_result = _as_dict(ad_entry.get("auto_consult_result"))
    message_mid = str(normalized.get("message_mid") or "").strip()
    _mark_pancake_auto_consult_trigger_consumed(
        trigger_type=message_kind,
        trigger_message_mid=message_mid,
    )
    logger.info(
        "PANCAKE_AD_CONTEXT_MERGE_START page_id=%s conversation_id=%s customer_id=%s trigger_type=%s trigger_message_mid=%s reason=%s",
        key[0],
        key[1],
        key[2],
        message_kind,
        message_mid,
        reason,
    )
    result = await _process_pancake_sender_buffer_entry(
        key,
        sender_entry,
        auto_consult_result=auto_consult_result,
        ad_normalized=normalized,
    )
    result["auto_consult_merged"] = True
    result["auto_consult_trigger_mid"] = message_mid
    result["auto_consult_trigger_kind"] = message_kind
    result["auto_consult_merge_reason"] = reason
    if reason == "ad_context_arrived":
        result["customer_message_kind"] = result.get("message_kind")
        result["message_kind"] = message_kind
    return result


async def _process_pending_pancake_ad_context_after_delay(
    key: tuple[str, str, str],
    *,
    delay_seconds: float | None = None,
) -> None:
    wait_seconds = _get_pancake_sender_buffer_seconds() if delay_seconds is None else delay_seconds
    try:
        await asyncio.sleep(max(float(wait_seconds), 0.0))
    except asyncio.CancelledError:
        return

    pending_result = _pop_pending_pancake_ad_context_for_key(
        key,
        reason="ad_context_wait_elapsed",
    )
    if not bool(pending_result.get("popped")):
        return

    ad_entry = _as_dict(pending_result.get("entry"))
    sender_result = _pop_pancake_sender_buffer_entry_for_key(
        key,
        reason="ad_context_wait_elapsed",
    )
    try:
        if bool(sender_result.get("popped")):
            result = await _process_pancake_sender_buffer_with_auto_consult_context(
                key=key,
                sender_entry=_as_dict(sender_result.get("entry")),
                ad_entry=ad_entry,
                reason="ad_context_wait_elapsed",
            )
        else:
            normalized = _as_dict(ad_entry.get("normalized"))
            message_kind = str(ad_entry.get("message_kind") or PANCAKE_MESSAGE_AD_CARD)
            auto_consult_result = _as_dict(ad_entry.get("auto_consult_result"))
            processing_key = _pancake_auto_consult_processing_key(
                trigger_type=message_kind,
                trigger_message_mid=str(normalized.get("message_mid") or "").strip(),
            )
            if not _try_mark_pancake_message_processing(processing_key):
                return
            try:
                if await _is_duplicate_pancake_auto_consult(
                    trigger_type=message_kind,
                    trigger_message_mid=str(normalized.get("message_mid") or "").strip(),
                ):
                    result = {
                        "status": "ignored",
                        "ok": False,
                        "reason": "duplicate_auto_consult",
                        "message_mid": normalized.get("message_mid"),
                        "message_kind": message_kind,
                    }
                else:
                    result = await _process_prepared_pancake_auto_consult_trigger(
                        normalized,
                        message_kind=message_kind,
                        auto_consult_result=auto_consult_result,
                    )
            finally:
                _finalize_pancake_message_processing(processing_key)
        logger.info(
            "PANCAKE_AD_CONTEXT_BUFFER_PROCESSED page_id=%s conversation_id=%s customer_id=%s status=%s reason=%s ok=%s",
            key[0],
            key[1],
            key[2],
            result.get("status"),
            result.get("reason"),
            result.get("ok"),
        )
    except Exception as exc:
        logger.exception(
            "PANCAKE_AD_CONTEXT_BUFFER_PROCESS_FAILED page_id=%s conversation_id=%s customer_id=%s error=%s",
            key[0],
            key[1],
            key[2],
            exc,
        )


def _enqueue_pending_pancake_ad_context(
    *,
    normalized: dict[str, Any],
    message_kind: str,
    auto_consult_result: dict[str, Any],
) -> dict[str, Any]:
    key = _pancake_auto_consult_merge_key(normalized)
    if key is None:
        return {"queued": False, "reason": "missing_ad_context_key"}

    wait_seconds = _get_pancake_sender_buffer_seconds()
    if wait_seconds <= 0:
        return {"queued": False, "reason": "ad_context_buffer_disabled"}

    message_mid = str(normalized.get("message_mid") or "").strip()
    trigger_key = _pancake_auto_consult_trigger_key(
        trigger_type=message_kind,
        trigger_message_mid=message_mid,
    )
    if trigger_key is None:
        return {"queued": False, "reason": "missing_auto_consult_trigger_mid"}

    with _pancake_ad_context_buffer_lock:
        for existing_entry in _pancake_ad_context_buffers.values():
            existing_trigger = _as_dict(existing_entry.get("trigger_key"))
            if (
                existing_trigger.get("trigger_type") == trigger_key[0]
                and existing_trigger.get("trigger_message_mid") == trigger_key[1]
            ):
                return {
                    "queued": False,
                    "reason": "duplicate_auto_consult_pending",
                }

        previous_entry = _pancake_ad_context_buffers.get(key)
        previous_task = _as_dict(previous_entry).get("task") if previous_entry else None
        if previous_task is not None and not previous_task.done():
            previous_task.cancel()

        entry = {
            "normalized": dict(normalized),
            "message_kind": message_kind,
            "auto_consult_result": dict(auto_consult_result),
            "trigger_key": {
                "trigger_type": trigger_key[0],
                "trigger_message_mid": trigger_key[1],
            },
            "created_at_monotonic": time.monotonic(),
        }
        entry["task"] = asyncio.create_task(
            _process_pending_pancake_ad_context_after_delay(
                key,
                delay_seconds=wait_seconds,
            )
        )
        _pancake_ad_context_buffers[key] = entry

    logger.info(
        "PANCAKE_AD_CONTEXT_BUFFER_QUEUED page_id=%s conversation_id=%s customer_id=%s trigger_type=%s trigger_message_mid=%s wait_seconds=%s",
        key[0],
        key[1],
        key[2],
        message_kind,
        message_mid,
        wait_seconds,
    )
    return {
        "queued": True,
        "reason": "queued_for_ad_context_buffer",
        "wait_seconds": wait_seconds,
    }


async def _try_merge_pending_pancake_ad_context_for_sender(
    normalized: dict[str, Any],
) -> dict[str, Any] | None:
    key = _pancake_auto_consult_merge_key(normalized)
    pending_result = _pop_pending_pancake_ad_context_for_key(
        key,
        reason="customer_message_arrived",
    )
    if not bool(pending_result.get("popped")):
        return None

    sender_result = _pop_pancake_sender_buffer_entry_for_key(
        key,
        reason="customer_message_arrived",
    )
    if not bool(sender_result.get("popped")):
        return {
            "status": "ignored",
            "ok": False,
            "reason": "missing_sender_buffer_for_pending_ad_context",
            "message_mid": normalized.get("message_mid"),
            "message_kind": PANCAKE_MESSAGE_CUSTOMER,
        }

    return await _process_pancake_sender_buffer_with_auto_consult_context(
        key=key,
        sender_entry=_as_dict(sender_result.get("entry")),
        ad_entry=_as_dict(pending_result.get("entry")),
        reason="customer_message_arrived",
    )


def _enqueue_pancake_sender_message_for_ai(
    *,
    conversation: Conversation,
    normalized: dict[str, Any],
    user_message: Message,
    message_kind: str,
) -> dict[str, Any]:
    if not _should_buffer_pancake_sender_message(normalized, message_kind=message_kind):
        return {"queued": False, "reason": "sender_buffer_not_needed"}

    key = _pancake_sender_buffer_key(normalized)
    if key is None:
        return {"queued": False, "reason": "missing_sender_buffer_key"}

    wait_seconds = _get_pancake_sender_buffer_seconds()
    if wait_seconds <= 0:
        return {"queued": False, "reason": "sender_buffer_disabled"}

    with _pancake_sender_buffer_lock:
        entry = _pancake_sender_buffers.get(key)
        if entry is None:
            entry = {
                "items": [],
                "created_at_monotonic": time.monotonic(),
            }
            _pancake_sender_buffers[key] = entry

        _as_list(entry.get("items")).append(
            {
                "normalized": dict(normalized),
                "user_message": user_message,
                "conversation": conversation,
                "message_kind": message_kind,
                "received_at_monotonic": time.monotonic(),
            }
        )

        task = entry.get("task")
        if task is not None and not task.done():
            task.cancel()
        entry["task"] = asyncio.create_task(
            _process_pancake_sender_buffer_after_delay(
                key,
                delay_seconds=wait_seconds,
            )
        )
        buffer_size = len(_as_list(entry.get("items")))

    logger.info(
        "PANCAKE_SENDER_BUFFER_QUEUED page_id=%s conversation_id=%s sender_id=%s message_mid=%s buffer_size=%s wait_seconds=%s",
        key[0],
        key[1],
        key[2],
        normalized.get("message_mid"),
        buffer_size,
        wait_seconds,
    )
    return {
        "queued": True,
        "reason": "queued_for_sender_buffer",
        "buffer_size": buffer_size,
        "wait_seconds": wait_seconds,
    }


async def _process_pancake_sender_buffer_after_delay(
    key: tuple[str, str, str],
    *,
    delay_seconds: float | None = None,
) -> None:
    wait_seconds = _get_pancake_sender_buffer_seconds() if delay_seconds is None else delay_seconds
    try:
        await asyncio.sleep(max(float(wait_seconds), 0.0))
    except asyncio.CancelledError:
        return

    with _pancake_sender_buffer_lock:
        entry = _pancake_sender_buffers.pop(key, None)

    if not entry:
        return

    try:
        result = await _process_pancake_sender_buffer_entry(key, entry)
        logger.info(
            "PANCAKE_SENDER_BUFFER_PROCESSED page_id=%s conversation_id=%s sender_id=%s status=%s reason=%s ok=%s message_mids=%s",
            key[0],
            key[1],
            key[2],
            result.get("status"),
            result.get("reason"),
            result.get("ok"),
            result.get("message_mids") or result.get("message_mid"),
        )
    except Exception as exc:
        logger.exception(
            "PANCAKE_SENDER_BUFFER_PROCESS_FAILED page_id=%s conversation_id=%s sender_id=%s error=%s",
            key[0],
            key[1],
            key[2],
            exc,
        )


async def _process_pancake_sender_buffer_entry(
    key: tuple[str, str, str],
    entry: dict[str, Any],
    *,
    auto_consult_result: dict[str, Any] | None = None,
    ad_normalized: dict[str, Any] | None = None,
) -> dict[str, Any]:
    items = _as_list(entry.get("items"))
    if not items:
        return {
            "status": "ignored",
            "ok": False,
            "reason": "empty_sender_buffer",
            "message_mids": [],
        }

    normalized = _merge_pancake_buffer_items(items)
    if auto_consult_result is None or ad_normalized is None:
        pending_result = _pop_pending_pancake_ad_context_for_key(
            key,
            reason="sender_buffer_ready",
        )
        if bool(pending_result.get("popped")):
            pending_entry = _as_dict(pending_result.get("entry"))
            auto_consult_result = _as_dict(pending_entry.get("auto_consult_result"))
            ad_normalized = _as_dict(pending_entry.get("normalized"))

    if auto_consult_result is not None and ad_normalized is not None:
        source_detail = _as_dict(auto_consult_result.get("source_detail"))
        prompt_result = _as_dict(auto_consult_result.get("prompt_result"))
        merged_result = _build_pancake_auto_consult_merged_normalized(
            normalized,
            ad_normalized=ad_normalized,
            source_detail=source_detail,
            prompt_result=prompt_result,
        )
        if not bool(merged_result.get("ok", True)):
            return {
                "status": "processed",
                "ok": False,
                "reason": merged_result.get("reason"),
                "message_mid": normalized.get("message_mid"),
                "message_mids": normalized.get("merged_message_mids") or [],
                "message_kind": PANCAKE_MESSAGE_CUSTOMER,
                "auto_consult": auto_consult_result,
            }
        normalized = merged_result
        auto_consult = _as_dict(normalized.get("auto_consult"))
        _mark_pancake_auto_consult_trigger_consumed(
            trigger_type=str(auto_consult.get("trigger_type") or PANCAKE_MESSAGE_AD_CARD),
            trigger_message_mid=str(auto_consult.get("trigger_message_mid") or ""),
        )

    first_item = _as_dict(items[0])
    user_message = first_item.get("user_message")
    if user_message is None:
        return {
            "status": "ignored",
            "ok": False,
            "reason": "missing_sender_buffer_user_message",
            "message_mids": normalized.get("merged_message_mids") or [],
        }

    conversation = first_item.get("conversation")
    if conversation is None:
        conversation = await _get_or_create_pancake_conversation(normalized)
    else:
        conversation = await _reload_pancake_conversation_for_pause_check(conversation)
    resume_context = await _resume_pancake_conversation_if_pause_expired_with_snapshot(
        conversation
    )
    if "handover_resume_context" not in normalized:
        _attach_pancake_handover_resume_context(
            conversation=conversation,
            normalized=normalized,
            resume_context=resume_context,
        )

    message_mid = str(normalized.get("message_mid") or "").strip()
    message_kind = str(first_item.get("message_kind") or PANCAKE_MESSAGE_CUSTOMER)
    if _is_pancake_bot_paused(conversation):
        logger.info(
            "PANCAKE_HANDOVER_CONTEXT_SKIPPED conversation_id=%s page_id=%s pancake_conversation_id=%s message_mid=%s sender_id=%s reason=conversation_still_paused message_count=0",
            conversation.id,
            normalized.get("page_id"),
            normalized.get("pancake_conversation_id"),
            message_mid,
            normalized.get("sender_id"),
        )
        conversation.updated_at = now_vn()
        await conversation.save()
        logger.info(
            "PANCAKE_SENDER_BUFFER_SUPPRESSED_BY_ADMIN_PAUSE conversation_id=%s sender_id=%s message_mids=%s paused_until=%s",
            conversation.id,
            key[2],
            normalized.get("merged_message_mids") or [message_mid],
            getattr(conversation, "bot_paused_until", None),
        )
        return {
            "status": "processed",
            "ok": False,
            "reason": "conversation_paused_by_admin",
            "conversation_id": str(conversation.id),
            "message_id": str(getattr(user_message, "id", "") or "").strip(),
            "message_mid": message_mid,
            "message_mids": normalized.get("merged_message_mids") or [message_mid],
            "message_kind": message_kind,
            "bot_paused_until": getattr(conversation, "bot_paused_until", None),
        }

    if bool(_as_dict(normalized.get("handover_resume_context")).get("resumed")):
        await _prepare_pancake_handover_resume_context(
            conversation=conversation,
            normalized=normalized,
            user_message=user_message,
        )

    logger.info(
        "PANCAKE_SENDER_BUFFER_AI_START page_id=%s conversation_id=%s sender_id=%s message_mids=%s buffer_size=%s",
        key[0],
        key[1],
        key[2],
        normalized.get("merged_message_mids") or [message_mid],
        len(items),
    )
    reply = await _generate_pancake_reply(conversation=conversation, normalized=normalized)
    await _save_pancake_handover_context_user_message_meta(
        user_message=user_message,
        normalized=normalized,
    )
    if not bool(reply.get("ok")):
        logger.warning(
            "PANCAKE_SENDER_BUFFER_AI_FAILED page_id=%s conversation_id=%s sender_id=%s message_mids=%s reason=%s",
            key[0],
            key[1],
            key[2],
            normalized.get("merged_message_mids") or [message_mid],
            reply.get("reason"),
        )
        return {
            "status": "processed",
            "ok": False,
            "reason": reply.get("reason"),
            "conversation_id": str(conversation.id),
            "message_id": str(getattr(user_message, "id", "") or "").strip(),
            "message_mid": message_mid,
            "message_mids": normalized.get("merged_message_mids") or [message_mid],
            "message_kind": message_kind,
        }

    return await _complete_pancake_ai_reply(
        conversation=conversation,
        normalized=normalized,
        user_message=user_message,
        reply=reply,
        message_kind=message_kind,
    )


def _match_pancake_ai_fallback_reply_marker(assistant_message: str) -> str | None:
    return next(
        (
            marker
            for marker in PANCAKE_AI_FALLBACK_REPLY_MARKERS
            if marker in assistant_message
        ),
        None,
    )


async def _save_pancake_user_message(conversation: Conversation, normalized: dict[str, Any]) -> Message:
    message = Message(
        conversation_id=conversation.id,
        message_mid=str(normalized.get("message_mid") or "").strip() or None,
        role="user",
        content=_pancake_customer_message_content(normalized),
        meta=_pancake_message_meta(normalized, source=_pancake_user_meta_source(normalized)),
        created_at=now_vn(),
        updated_at=now_vn(),
    )
    await message.insert()
    return message


async def _save_pancake_staff_message(conversation: Conversation, normalized: dict[str, Any]) -> Message:
    message = Message(
        conversation_id=conversation.id,
        message_mid=str(normalized.get("message_mid") or "").strip() or None,
        role="staff",
        content=str(normalized.get("text") or ""),
        meta=_pancake_message_meta(normalized, source=PANCAKE_MESSAGE_STAFF_SOURCE),
        created_at=now_vn(),
        updated_at=now_vn(),
    )
    await message.insert()
    return message


async def _save_pancake_bot_message(
    conversation: Conversation,
    normalized: dict[str, Any],
    *,
    reply_text: str,
    send_result: dict[str, Any],
    extra_meta: Optional[dict[str, Any]] = None,
) -> Message:
    meta = _pancake_message_meta(normalized, source=_pancake_bot_meta_source(normalized))
    meta.update(
        {
            "reply_to_message_mid": normalized.get("message_mid"),
            "pancake_send_result": send_result,
        }
    )
    if extra_meta:
        meta.update(extra_meta)
    message = Message(
        conversation_id=conversation.id,
        message_mid=None,
        role="bot",
        content=reply_text,
        meta=meta,
        created_at=now_vn(),
        updated_at=now_vn(),
    )
    await message.insert()
    return message


async def _update_pancake_handover_conversation_status(
    *,
    conversation: Conversation,
    handover_detection: dict[str, Any],
) -> dict[str, Any]:
    if not bool(handover_detection.get("detected")):
        return {"updated": False, "reason": "handover_not_detected"}

    conversation_id = str(getattr(conversation, "id", "") or "").strip()
    if not conversation_id:
        logger.warning(
            "PANCAKE_HANDOVER_STATUS_UPDATE_SKIPPED reason=handover_missing_conversation_id matched_pattern=%s",
            handover_detection.get("matched_pattern"),
        )
        return {"updated": False, "reason": "handover_missing_conversation_id"}

    paused_at = now_vn()
    paused_until = paused_at + timedelta(minutes=PANCAKE_AI_HANDOVER_PAUSE_MINUTES)

    conversation.status = ConversationStatus.HANDOVER
    conversation.bot_paused_at = paused_at
    conversation.bot_paused_until = paused_until
    conversation.bot_paused_reason = PANCAKE_AI_HANDOVER_PAUSE_REASON
    conversation.updated_at = paused_at

    try:
        await conversation.save()
    except Exception as exc:
        logger.exception(
            "PANCAKE_HANDOVER_STATUS_UPDATE_FAILED conversation_id=%s matched_pattern=%s error=%s",
            conversation_id,
            handover_detection.get("matched_pattern"),
            exc,
        )
        return {
            "updated": False,
            "reason": "handover_status_update_failed",
            "error": str(exc),
        }

    logger.info(
        "PANCAKE_HANDOVER_STATUS_UPDATED conversation_id=%s matched_pattern=%s status=%s paused_until=%s pause_minutes=%s",
        conversation_id,
        handover_detection.get("matched_pattern"),
        ConversationStatus.HANDOVER.value,
        paused_until.isoformat(),
        PANCAKE_AI_HANDOVER_PAUSE_MINUTES,
    )
    return {
        "updated": True,
        "conversation_id": conversation_id,
        "status": ConversationStatus.HANDOVER.value,
        "bot_paused_at": paused_at,
        "bot_paused_until": paused_until,
        "bot_paused_reason": PANCAKE_AI_HANDOVER_PAUSE_REASON,
        "pause_minutes": PANCAKE_AI_HANDOVER_PAUSE_MINUTES,
    }


async def _generate_pancake_reply(
    *,
    conversation: Conversation,
    normalized: dict[str, Any],
) -> dict[str, Any]:
    text = str(normalized.get("text") or "").strip()
    if not _has_pancake_ai_supported_content(normalized):
        return {"ok": False, "reason": "missing_message_content"}

    was_ai_initialized = bool(
        normalized.get("conversation_was_ai_initialized")
        if "conversation_was_ai_initialized" in normalized
        else getattr(conversation, "fb_ai_initialized", False)
    )
    normalized["conversation_was_ai_initialized"] = was_ai_initialized
    ai_context = _prepare_pancake_comment_ai_context(
        normalized,
        initial_product_prompt=not was_ai_initialized,
    )
    ai_content = _build_pancake_ai_content(
        normalized=normalized,
        base_content=str(ai_context.get("content") or text).strip(),
    )
    if not ai_content:
        return {"ok": False, "reason": "missing_message_content"}

    sender_id = str(normalized.get("sender_id") or "").strip()
    message_mid = str(normalized.get("message_mid") or "").strip() or None

    async def init_version_ai_session(
        active_conversation: Conversation,
        ai_user: str,
    ) -> dict[str, Any]:
        return await _ensure_sender_initialized(
            latest=normalized,
            conversation=active_conversation,
            ai_user=ai_user,
        )

    async def send_version_context_message(
        active_conversation: Conversation,
        ai_user: str,
        content: str,
        purpose: str,
    ) -> dict[str, Any]:
        payload = _build_ai_chat_payload(
            user=ai_user,
            content=content,
            conversation_id=active_conversation.id,
        )
        return await _post_ai_chat_with_retry(
            payload=payload,
            sender_id=ai_user,
            message_mid=message_mid,
            purpose=purpose,
        )

    exclude_message_mids = [
        str(value or "").strip()
        for value in (normalized.get("merged_message_mids") or [])
        if str(value or "").strip()
    ]
    if message_mid and message_mid not in exclude_message_mids:
        exclude_message_mids.append(message_mid)

    exclude_message_ids = [
        str(value or "").strip()
        for value in (normalized.get("merged_message_ids") or [])
        if str(value or "").strip()
    ]

    if hasattr(conversation, "version"):
        version_result = await prepare_ai_version_for_customer_message(
            conversation=conversation,
            sender_id=sender_id,
            current_message=ai_content,
            message_mid=message_mid,
            exclude_message_ids=exclude_message_ids,
            exclude_message_mids=exclude_message_mids,
            init_ai_session=init_version_ai_session,
            send_ai_message=send_version_context_message,
            reload_conversation=_reload_pancake_conversation_for_pause_check,
            purpose="pancake_user_message",
            log_prefix="PANCAKE_AI_VERSION",
        )
    else:
        version_result = {
            "ok": True,
            "upgraded": False,
            "reason": "conversation_version_attr_missing",
            "ai_user": sender_id,
            "conversation": conversation,
        }
    if not bool(version_result.get("ok")):
        return {
            "ok": False,
            "reason": version_result.get("reason") or "ai_version_failed",
            "version_result": version_result,
        }

    conversation = version_result.get("conversation") or conversation
    ai_user = str(version_result.get("ai_user") or sender_id).strip()

    if str(normalized.get("message_type") or "").strip().upper() == PANCAKE_MESSAGE_COMMENT_TYPE:
        logger.info(
            "PANCAKE_COMMENT_AI_MESSAGE_PREPARED page_id=%s conversation_id=%s sender_id=%s message_mid=%s post_id=%s product_code_count=%s augmented=%s",
            normalized.get("page_id"),
            normalized.get("pancake_conversation_id"),
            sender_id,
            message_mid,
            normalized.get("post_id"),
            ai_context.get("product_code_count"),
            bool(ai_context.get("augmented")),
        )

    if bool(version_result.get("upgraded")):
        _mark_pancake_handover_context_not_injected(
            normalized,
            reason="handled_by_ai_version_context",
        )
        ai_result = version_result.get("ai_result") or {}
    else:
        ai_content = _apply_pancake_handover_context_to_ai_content(
            conversation=conversation,
            normalized=normalized,
            ai_content=ai_content,
        )
        init_kwargs: dict[str, Any] = {"latest": normalized, "conversation": conversation}
        if ai_user != sender_id:
            init_kwargs["ai_user"] = ai_user
        init_result = await _ensure_sender_initialized(**init_kwargs)
        if not bool(init_result.get("ok")):
            return {
                "ok": False,
                "reason": "ai_init_failed",
                "init_result": init_result,
            }

        payload = _build_ai_chat_payload(
            user=ai_user,
            content=ai_content,
            conversation_id=conversation.id,
        )
        ai_result = await _post_ai_chat_with_retry(
            payload=payload,
            sender_id=ai_user,
            message_mid=message_mid,
            purpose="pancake_user_message",
        )
    if not bool(ai_result.get("ok")):
        return {
            "ok": False,
            "reason": "ai_call_failed",
            "ai_result": ai_result,
        }

    response_data = ai_result.get("response_data")
    assistant_message = _extract_text_from_ai_response(response_data)
    if not assistant_message:
        logger.error(
            "PANCAKE_AI_RESPONSE_EMPTY sender_id=%s message_mid=%s response_data=%s",
            sender_id,
            message_mid,
            _preview_text(response_data),
        )
        return {
            "ok": False,
            "reason": "ai_response_empty",
            "ai_result": ai_result,
        }

    matched_ai_fallback_marker = _match_pancake_ai_fallback_reply_marker(assistant_message)
    if matched_ai_fallback_marker:
        logger.warning(
            "PANCAKE_AI_QUOTA_RESPONSE_FALLBACK sender_id=%s message_mid=%s matched_marker=%s",
            sender_id,
            message_mid,
            matched_ai_fallback_marker,
        )
        assistant_message = PANCAKE_AI_QUOTA_FALLBACK_REPLY

    image_limit = _get_pancake_channel_image_limit(normalized)
    prepared_drive_reply = await _prepare_pancake_drive_reply_with_folder_images(
        assistant_message,
        image_limit=image_limit,
    )
    logger.info(
        "PANCAKE_AI_DRIVE_REPLY_PREPARED sender_id=%s message_mid=%s text_present=%s drive_file_count=%s drive_folder_count=%s requested_color=%s color_filter_applied=%s color_filter_reason=%s error_count=%s skipped_count=%s",
        sender_id,
        message_mid,
        bool(prepared_drive_reply.text),
        len(prepared_drive_reply.drive_file_urls),
        len(prepared_drive_reply.drive_folder_urls),
        prepared_drive_reply.requested_color,
        prepared_drive_reply.color_filter_applied,
        prepared_drive_reply.color_filter_reason,
        len(prepared_drive_reply.errors),
        prepared_drive_reply.skipped_count,
    )
    drive_image_cache_result = None
    if prepared_drive_reply.drive_file_urls:
        is_comment_reply = (
            str(normalized.get("message_type") or "").strip().upper()
            == PANCAKE_MESSAGE_COMMENT_TYPE
        )
        cache_kwargs: dict[str, Any] = {
            "image_limit": len(prepared_drive_reply.drive_file_urls),
            "reuse_uploaded_content_id": (
                _should_reuse_pancake_uploaded_content_id() and not is_comment_reply
            ),
        }
        if (
            prepared_drive_reply.drive_file_metadata
            or prepared_drive_reply.requested_color
            or prepared_drive_reply.requested_color_terms
        ):
            cache_kwargs["drive_file_metadata"] = prepared_drive_reply.drive_file_metadata
            cache_kwargs["require_color_metadata"] = bool(
                prepared_drive_reply.requested_color or prepared_drive_reply.requested_color_terms
            )
        drive_image_cache_result = await PancakeDriveImageService().ensure_local_images(
            prepared_drive_reply.drive_file_urls,
            **cache_kwargs,
        )
        cache_images = _get_cache_result_images(drive_image_cache_result)
        cache_errors = _get_cache_result_errors(drive_image_cache_result)
        logger.info(
            "PANCAKE_AI_DRIVE_IMAGE_CACHE_RESULT sender_id=%s message_mid=%s image_count=%s error_count=%s cache_hit_count=%s downloaded_count=%s content_id_count=%s local_present_count=%s",
            sender_id,
            message_mid,
            len(cache_images),
            len(cache_errors),
            sum(1 for image in cache_images if _drive_cache_image_value(image, "cache_hit")),
            sum(1 for image in cache_images if _drive_cache_image_value(image, "downloaded")),
            sum(1 for image in cache_images if _drive_cache_image_value(image, "content_id")),
            sum(1 for image in cache_images if _drive_cache_image_value(image, "local_present")),
        )
        if cache_errors:
            logger.warning(
                "PANCAKE_AI_DRIVE_IMAGE_CACHE_ERRORS sender_id=%s message_mid=%s errors=%s",
                sender_id,
                message_mid,
                cache_errors,
            )
    elif prepared_drive_reply.drive_folder_urls:
        logger.info(
            "PANCAKE_AI_DRIVE_IMAGE_CACHE_SKIPPED sender_id=%s message_mid=%s reason=no_drive_file_urls_after_prepare requested_color=%s color_filter_reason=%s",
            sender_id,
            message_mid,
            prepared_drive_reply.requested_color,
            prepared_drive_reply.color_filter_reason,
        )

    return {
        "ok": True,
        "reply_text": prepared_drive_reply.text,
        "source": "fb_ai_chat_url",
        "ai_result": ai_result,
        "ai_quota_fallback": bool(matched_ai_fallback_marker),
        "ai_fallback_marker": matched_ai_fallback_marker,
        "pancake_drive_reply": prepared_drive_reply.to_dict(),
        "pancake_drive_image_cache_result": (
            drive_image_cache_result.to_dict() if drive_image_cache_result is not None else None
        ),
        "handover_context": _pancake_handover_context_audit_meta(
            _as_dict(normalized.get("handover_resume_context"))
        )
        or None,
    }


async def _prepare_pancake_drive_reply_with_folder_images(
    message_text: str,
    *,
    image_limit: int | None = None,
) -> PreparedPancakeDriveReply:
    prepared = prepare_pancake_drive_reply(message_text, image_limit=image_limit)
    if not prepared.drive_folder_urls:
        return prepared

    drive_lookup_service = GoogleDriveImageService()
    nested_lookup = getattr(drive_lookup_service, "lookup_folder_images_nested", None)
    if callable(nested_lookup):
        nested_lookup_kwargs: dict[str, Any] = {
            "max_depth": _get_google_drive_folder_lookup_max_depth(),
            "requested_color": prepared.requested_color,
        }
        if _callable_accepts_keyword(nested_lookup, "requested_color_terms"):
            nested_lookup_kwargs["requested_color_terms"] = prepared.requested_color_terms
        folder_results = await nested_lookup(prepared.drive_folder_urls, **nested_lookup_kwargs)
    else:
        folder_results = await drive_lookup_service.lookup_folder_images(prepared.drive_folder_urls)
    drive_file_urls = list(prepared.drive_file_urls)
    drive_file_ids = list(prepared.drive_file_ids)
    accepted_file_ids = set(drive_file_ids)
    drive_file_metadata = dict(prepared.drive_file_metadata)
    errors = list(prepared.errors)
    folder_error_count = 0
    color_filter_match_count = 0
    color_filter_fallback_count = 0
    color_filter_active = bool(prepared.requested_color or prepared.requested_color_terms)

    for folder in folder_results:
        if folder.error:
            folder_error_count += 1
            errors.append(
                {
                    "drive_folder_url": folder.folder_url,
                    "drive_folder_id": folder.folder_id,
                    "reason": folder.error,
                }
            )
            continue

        selected_images: list[Any] = []
        if color_filter_active:
            selected_images = _select_random_pancake_drive_folder_images(
                folder.images,
                image_limit=prepared.image_limit,
                excluded_file_ids=accepted_file_ids,
                requested_color=prepared.requested_color,
                requested_color_terms=prepared.requested_color_terms,
                requested_color_phrases=prepared.requested_color_phrases,
            )
            color_filter_match_count += len(selected_images)
            if not selected_images:
                selected_images = _select_random_pancake_drive_folder_images(
                    folder.images,
                    image_limit=prepared.image_limit,
                    excluded_file_ids=accepted_file_ids,
                )
                color_filter_fallback_count += len(selected_images)
                if selected_images:
                    logger.warning(
                        "PANCAKE_AI_DRIVE_FOLDER_COLOR_NO_MATCH_RANDOM_FALLBACK drive_folder_id=%s requested_color=%s fallback_image_count=%s",
                        folder.folder_id,
                        prepared.requested_color,
                        len(selected_images),
                    )
        else:
            selected_images = _select_random_pancake_drive_folder_images(
                folder.images,
                image_limit=prepared.image_limit,
                excluded_file_ids=accepted_file_ids,
            )

        for image in selected_images:
            drive_file_id = str(getattr(image, "id", "") or "").strip()
            drive_file_name = str(getattr(image, "name", "") or "").strip() or None
            drive_file_color = (
                str(getattr(image, "drive_file_color", "") or "").strip()
                or parse_drive_file_color_from_name(drive_file_name)
            )
            if (
                not drive_file_color
                and prepared.requested_color
                and name_matches_color_terms(drive_file_name, prepared.requested_color_terms)
            ):
                drive_file_color = (
                    _requested_color_key_for_drive_image(
                        image,
                        requested_color_phrases=prepared.requested_color_phrases,
                    )
                    or prepared.requested_color
                )
            accepted_file_ids.add(drive_file_id)
            drive_file_ids.append(drive_file_id)
            drive_file_urls.append(build_drive_file_view_url(drive_file_id))
            logger.info(
                "PANCAKE_AI_DRIVE_FOLDER_IMAGE_SELECTED drive_folder_id=%s drive_file_id=%s drive_file_name=%s drive_file_color=%s requested_color=%s",
                folder.folder_id,
                drive_file_id,
                drive_file_name,
                drive_file_color,
                prepared.requested_color,
            )
            metadata: dict[str, Any] = {}
            if drive_file_name:
                metadata["drive_file_id"] = drive_file_id
                metadata["drive_file_name"] = drive_file_name
            if drive_file_color:
                metadata["drive_file_id"] = drive_file_id
                metadata["drive_file_color"] = drive_file_color
            if metadata:
                drive_file_metadata[drive_file_id] = metadata

    color_filter_reason = prepared.color_filter_reason
    if color_filter_active:
        if color_filter_fallback_count:
            color_filter_reason = "drive_color_no_match_random_fallback"
        else:
            color_filter_reason = None if color_filter_match_count else "drive_color_no_match"
        if not color_filter_match_count and not color_filter_fallback_count:
            logger.warning(
                "PANCAKE_AI_DRIVE_FOLDER_COLOR_NO_MATCH requested_color=%s folder_count=%s",
                prepared.requested_color,
                len(prepared.drive_folder_urls),
            )
            errors.append(
                {
                    "requested_color": prepared.requested_color,
                    "reason": "drive_color_no_match",
                }
            )

    logger.info(
        "PANCAKE_AI_DRIVE_FOLDER_IMAGES_PREPARED folder_count=%s folder_error_count=%s image_count=%s folder_image_limit=%s requested_color=%s color_match_count=%s color_fallback_count=%s",
        len(prepared.drive_folder_urls),
        folder_error_count,
        len(drive_file_ids) - len(prepared.drive_file_ids),
        prepared.image_limit,
        prepared.requested_color,
        color_filter_match_count,
        color_filter_fallback_count,
    )

    return PreparedPancakeDriveReply(
        text=prepared.text,
        drive_file_urls=drive_file_urls,
        drive_file_ids=drive_file_ids,
        image_limit=prepared.image_limit,
        requested_color=prepared.requested_color,
        requested_color_phrases=list(prepared.requested_color_phrases),
        requested_color_terms=list(prepared.requested_color_terms),
        color_filter_applied=color_filter_active,
        color_filter_reason=color_filter_reason,
        drive_file_metadata=drive_file_metadata,
        selected_drive_file_ids=drive_file_ids,
        drive_folder_urls=prepared.drive_folder_urls,
        drive_folder_results=[
            _pancake_drive_folder_result_to_color_dict(
                folder,
                selected_file_ids=set(drive_file_ids),
            )
            for folder in folder_results
        ],
        drive_folder_error_count=folder_error_count,
        content_ids=prepared.content_ids,
        errors=errors,
        skipped_count=prepared.skipped_count,
    )


def _pancake_drive_folder_result_to_color_dict(folder: Any, *, selected_file_ids: set[str]) -> dict[str, Any]:
    if not hasattr(folder, "to_dict"):
        return {}
    data = folder.to_dict()
    raw_images = data.get("images") if isinstance(data, dict) else None
    if not isinstance(raw_images, list):
        return data

    color_images: list[dict[str, Any]] = []
    for raw_image in raw_images:
        image = raw_image if isinstance(raw_image, dict) else {}
        drive_file_id = str(image.get("id") or "").strip()
        drive_file_name = str(image.get("name") or "").strip() or None
        image = dict(image)
        drive_file_color = (
            str(image.get("drive_file_color") or "").strip()
            or parse_drive_file_color_from_name(drive_file_name)
        )
        if drive_file_color:
            image["drive_file_color"] = drive_file_color
        if drive_file_id:
            image["selected"] = drive_file_id in selected_file_ids
        color_images.append(image)
    data["images"] = color_images
    return data


def _select_random_pancake_drive_folder_images(
    images: list[Any],
    *,
    image_limit: int,
    excluded_file_ids: set[str],
    requested_color: str | None = None,
    requested_color_terms: Iterable[str] | None = None,
    requested_color_phrases: Iterable[str] | None = None,
) -> list[Any]:
    candidates: list[Any] = []
    seen_file_ids: set[str] = set()
    normalized_requested_color_terms = list(requested_color_terms or [])
    color_filter_active = bool(requested_color or normalized_requested_color_terms)
    for image in images:
        drive_file_id = str(getattr(image, "id", "") or "").strip()
        if not drive_file_id or drive_file_id in excluded_file_ids or drive_file_id in seen_file_ids:
            continue
        if color_filter_active:
            if not _drive_image_matches_requested_color(
                image,
                requested_color=requested_color,
                requested_color_terms=normalized_requested_color_terms,
            ):
                continue
        seen_file_ids.add(drive_file_id)
        candidates.append(image)

    if not candidates:
        return []

    selection_count = min(max(1, int(image_limit or 1)), len(candidates))
    color_covered_selection = _select_random_images_covering_color_phrases(
        candidates,
        selection_count=selection_count,
        requested_color_phrases=requested_color_phrases,
    )
    if color_covered_selection:
        return color_covered_selection

    drive_color_covered_selection = _select_random_images_covering_drive_colors(
        candidates,
        selection_count=selection_count,
    )
    if drive_color_covered_selection:
        return drive_color_covered_selection

    return random.sample(candidates, selection_count)


def _drive_image_matches_requested_color(
    image: Any,
    *,
    requested_color: str | None = None,
    requested_color_terms: Iterable[str] | None = None,
) -> bool:
    normalized_requested_color_terms = list(requested_color_terms or [])
    drive_file_color = (
        str(getattr(image, "drive_file_color", "") or "").strip()
        or parse_drive_file_color_from_name(getattr(image, "name", None))
    )
    color_matches = bool(requested_color and drive_file_color == requested_color)
    if not color_matches and drive_file_color:
        color_matches = name_matches_color_terms(drive_file_color, normalized_requested_color_terms)
    if not color_matches:
        color_matches = name_matches_color_terms(getattr(image, "name", None), normalized_requested_color_terms)
    return color_matches


def _requested_color_phrase_term_groups(
    requested_color_phrases: Iterable[str] | None,
) -> list[tuple[str, list[str]]]:
    groups: list[tuple[str, list[str]]] = []
    seen_keys: set[str] = set()
    for phrase in requested_color_phrases or []:
        color_key = normalize_color_key(phrase)
        if not color_key or color_key in seen_keys:
            continue
        terms = build_color_match_terms([phrase])
        if not terms:
            continue
        groups.append((color_key, terms))
        seen_keys.add(color_key)
    return groups


def _select_random_images_covering_color_phrases(
    candidates: list[Any],
    *,
    selection_count: int,
    requested_color_phrases: Iterable[str] | None,
) -> list[Any]:
    phrase_term_groups = _requested_color_phrase_term_groups(requested_color_phrases)
    if selection_count <= 0 or len(phrase_term_groups) <= 1:
        return []

    matched_groups: list[tuple[str, list[str], list[Any]]] = []
    for color_key, terms in phrase_term_groups:
        matched_images = [
            image
            for image in candidates
            if _drive_image_matches_requested_color(image, requested_color_terms=terms)
        ]
        if matched_images:
            matched_groups.append((color_key, terms, matched_images))

    if len(matched_groups) <= 1:
        return []

    selected_images: list[Any] = []
    selected_file_ids: set[str] = set()
    covered_color_keys: set[str] = set()

    for color_key, terms, matched_images in matched_groups:
        if len(selected_images) >= selection_count:
            break
        if color_key in covered_color_keys:
            continue

        available_images = [
            image
            for image in matched_images
            if str(getattr(image, "id", "") or "").strip() not in selected_file_ids
        ]
        if not available_images:
            if any(
                _drive_image_matches_requested_color(image, requested_color_terms=terms)
                for image in selected_images
            ):
                covered_color_keys.add(color_key)
            continue

        chosen_image = random.sample(available_images, 1)[0]
        chosen_file_id = str(getattr(chosen_image, "id", "") or "").strip()
        selected_images.append(chosen_image)
        selected_file_ids.add(chosen_file_id)
        covered_color_keys.add(color_key)

    remaining_count = selection_count - len(selected_images)
    if remaining_count > 0:
        remaining_images = [
            image
            for image in candidates
            if str(getattr(image, "id", "") or "").strip() not in selected_file_ids
        ]
        if remaining_images:
            selected_images.extend(random.sample(remaining_images, min(remaining_count, len(remaining_images))))

    return selected_images


def _drive_image_color_key(image: Any) -> str | None:
    return (
        str(getattr(image, "drive_file_color", "") or "").strip()
        or parse_drive_file_color_from_name(getattr(image, "name", None))
    )


def _select_random_images_covering_drive_colors(
    candidates: list[Any],
    *,
    selection_count: int,
) -> list[Any]:
    if selection_count <= 0:
        return []

    grouped_images: dict[str, list[Any]] = {}
    color_order: list[str] = []
    for image in candidates:
        color_key = _drive_image_color_key(image)
        if not color_key:
            continue
        if color_key not in grouped_images:
            grouped_images[color_key] = []
            color_order.append(color_key)
        grouped_images[color_key].append(image)

    if len(color_order) <= 1:
        return []

    selected_images: list[Any] = []
    selected_file_ids: set[str] = set()
    covered_color_keys: set[str] = set()

    for color_key in color_order:
        if len(selected_images) >= selection_count:
            break
        if color_key in covered_color_keys:
            continue

        available_images = [
            image
            for image in grouped_images[color_key]
            if str(getattr(image, "id", "") or "").strip() not in selected_file_ids
        ]
        if not available_images:
            continue

        chosen_image = random.sample(available_images, 1)[0]
        chosen_file_id = str(getattr(chosen_image, "id", "") or "").strip()
        selected_images.append(chosen_image)
        selected_file_ids.add(chosen_file_id)
        covered_color_keys.add(color_key)

    remaining_count = selection_count - len(selected_images)
    if remaining_count > 0:
        remaining_images = [
            image
            for image in candidates
            if str(getattr(image, "id", "") or "").strip() not in selected_file_ids
        ]
        if remaining_images:
            selected_images.extend(random.sample(remaining_images, min(remaining_count, len(remaining_images))))

    logger.info(
        "PANCAKE_AI_DRIVE_FOLDER_COLOR_DIVERSE_SELECTION candidate_count=%s selection_count=%s covered_colors=%s random_fill_count=%s selected_count=%s",
        len(candidates),
        selection_count,
        list(covered_color_keys),
        max(0, len(selected_images) - len(covered_color_keys)),
        len(selected_images),
    )
    return selected_images


def _requested_color_key_for_drive_image(
    image: Any,
    *,
    requested_color_phrases: Iterable[str] | None,
) -> str | None:
    for color_key, terms in _requested_color_phrase_term_groups(requested_color_phrases):
        if _drive_image_matches_requested_color(image, requested_color_terms=terms):
            return color_key
    return None


def _select_random_pancake_drive_folder_image_ids(
    images: list[Any],
    *,
    image_limit: int,
    excluded_file_ids: set[str],
) -> list[str]:
    return [
        str(getattr(image, "id", "") or "").strip()
        for image in _select_random_pancake_drive_folder_images(
            images,
            image_limit=image_limit,
            excluded_file_ids=excluded_file_ids,
        )
    ]


def _resolve_pancake_reply_action(normalized: dict[str, Any]) -> str | None:
    message_type = str(normalized.get("message_type") or "").strip().upper()
    conversation_type = str(normalized.get("conversation_type") or "").strip().upper()
    if message_type == PANCAKE_MESSAGE_COMMENT_TYPE:
        return PANCAKE_REPLY_COMMENT_ACTION
    if message_type == PANCAKE_MESSAGE_INBOX or conversation_type == PANCAKE_MESSAGE_INBOX:
        return PANCAKE_REPLY_INBOX_ACTION
    return None


def _get_google_drive_folder_lookup_max_depth() -> int:
    raw = getattr(settings, "google_drive_folder_lookup_max_depth", 3)
    try:
        value = int(raw or 3)
    except (TypeError, ValueError):
        value = 3
    return max(1, min(value, 3))


def _callable_accepts_keyword(callback: Any, keyword: str) -> bool:
    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):
        return True
    return keyword in signature.parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )


def _should_reuse_pancake_uploaded_content_id() -> bool:
    raw = getattr(settings, "pancake_reuse_uploaded_content_id", True)
    if isinstance(raw, bool):
        return raw
    return str(raw or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _get_cache_result_images(cache_result: Any) -> list[Any]:
    raw_images = getattr(cache_result, "images", None)
    if isinstance(raw_images, list):
        return raw_images
    if hasattr(cache_result, "to_dict"):
        data = cache_result.to_dict()
        raw_images = data.get("images") if isinstance(data, dict) else None
        if isinstance(raw_images, list):
            return raw_images
    return []


def _get_cache_result_errors(cache_result: Any) -> list[Any]:
    raw_errors = getattr(cache_result, "errors", None)
    if isinstance(raw_errors, list):
        return raw_errors
    if hasattr(cache_result, "to_dict"):
        data = cache_result.to_dict()
        raw_errors = data.get("errors") if isinstance(data, dict) else None
        if isinstance(raw_errors, list):
            return raw_errors
    return []


def _drive_cache_image_value(image: Any, key: str) -> Any:
    if isinstance(image, dict):
        return image.get(key)
    return getattr(image, key, None)


def _pancake_image_echo_verified_result(
    *,
    echo_event: dict[str, Any],
    attempt: int,
    max_attempts: int,
    echo_wait_seconds: float,
    content_ids: list[str],
    delivery_attempts: list[dict[str, Any]],
    send_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "ok": True,
        "reason": None,
        "status_code": (send_result or {}).get("status_code"),
        "response_data": (send_result or {}).get("response_data"),
        "content_ids": content_ids,
        "attempt_count": attempt,
        "max_attempts": max_attempts,
        "echo_wait_seconds": echo_wait_seconds,
        "echo_verified": True,
        "verified_message_mid": echo_event.get("message_mid"),
        "verified_attachment_count": echo_event.get("attachment_count"),
        "delivery_attempts": delivery_attempts,
    }
    return result


def _split_pancake_content_ids_for_fallback(content_ids: list[str]) -> list[list[str]]:
    if not content_ids:
        return []
    if len(content_ids) == 1:
        return [content_ids]

    first_count = int((len(content_ids) * PANCAKE_IMAGE_CONTENT_ID_FALLBACK_RATIO) + 0.5)
    first_count = max(1, min(len(content_ids) - 1, first_count))
    return [content_ids[:first_count], content_ids[first_count:]]


def _single_pancake_content_ids_for_fallback(content_ids: list[str]) -> list[list[str]]:
    return [[content_id] for content_id in content_ids if content_id]


def _should_fallback_pancake_content_ids(
    *,
    content_ids: list[str],
    delivery_result: dict[str, Any],
) -> bool:
    if not content_ids:
        return False
    if bool(delivery_result.get("ok")):
        return False
    return delivery_result.get("reason") != "pancake_image_echo_not_observed"


async def _send_pancake_content_ids_with_echo_verification(
    *,
    page_id: str,
    conversation_id: str,
    message_mid: str | None,
    content_ids: list[str],
    action: str,
) -> dict[str, Any]:
    max_attempts = PANCAKE_IMAGE_ECHO_MAX_DELIVERY_ATTEMPTS
    echo_wait_seconds = PANCAKE_IMAGE_ECHO_VERIFY_WAIT_SECONDS
    delivery_started_at = time.monotonic()
    delivery_attempts: list[dict[str, Any]] = []
    last_send_result: dict[str, Any] | None = None

    logger.info(
        "PANCAKE_DRIVE_IMAGE_DELIVERY_VERIFY_START page_id=%s conversation_id=%s message_mid=%s content_id_count=%s max_attempts=%s echo_wait_seconds=%s",
        page_id,
        conversation_id,
        message_mid,
        len(content_ids),
        max_attempts,
        echo_wait_seconds,
    )

    for attempt in range(1, max_attempts + 1):
        existing_echo = _find_pancake_public_api_image_echo(
            page_id=page_id,
            conversation_id=conversation_id,
            since_monotonic=delivery_started_at,
        )
        if existing_echo is not None:
            logger.info(
                "PANCAKE_DRIVE_IMAGE_DELIVERY_VERIFIED_BEFORE_RETRY page_id=%s conversation_id=%s message_mid=%s attempt=%s verified_message_mid=%s verified_attachment_count=%s",
                page_id,
                conversation_id,
                message_mid,
                attempt,
                existing_echo.get("message_mid"),
                existing_echo.get("attachment_count"),
            )
            return _pancake_image_echo_verified_result(
                echo_event=existing_echo,
                attempt=max(1, attempt - 1),
                max_attempts=max_attempts,
                echo_wait_seconds=echo_wait_seconds,
                content_ids=content_ids,
                delivery_attempts=delivery_attempts,
                send_result=last_send_result,
            )

        logger.info(
            "PANCAKE_DRIVE_IMAGE_DELIVERY_ATTEMPT_START page_id=%s conversation_id=%s message_mid=%s attempt=%s max_attempts=%s content_id_count=%s",
            page_id,
            conversation_id,
            message_mid,
            attempt,
            max_attempts,
            len(content_ids),
        )
        send_result = await send_pancake_content_ids(
            page_id=page_id,
            conversation_id=conversation_id,
            content_ids=content_ids,
            action=action,
        )
        last_send_result = send_result
        attempt_record = {
            "attempt": attempt,
            "ok": bool(send_result.get("ok")),
            "status_code": send_result.get("status_code"),
            "reason": send_result.get("reason"),
            "content_id_count": len(content_ids),
            "echo_verified": False,
        }

        if not bool(send_result.get("ok")):
            delivery_attempts.append(attempt_record)
            logger.warning(
                "PANCAKE_DRIVE_IMAGE_DELIVERY_ATTEMPT_FAILED page_id=%s conversation_id=%s message_mid=%s attempt=%s status_code=%s reason=%s content_id_count=%s",
                page_id,
                conversation_id,
                message_mid,
                attempt,
                send_result.get("status_code"),
                send_result.get("reason"),
                len(content_ids),
            )
            return {
                "ok": False,
                "reason": send_result.get("reason") or "pancake_send_content_ids_failed",
                "status_code": send_result.get("status_code"),
                "response_data": send_result.get("response_data"),
                "content_ids": content_ids,
                "attempt_count": attempt,
                "max_attempts": max_attempts,
                "echo_wait_seconds": echo_wait_seconds,
                "echo_verified": False,
                "delivery_attempts": delivery_attempts,
                "send_result": send_result,
            }

        echo_event = await _wait_for_pancake_public_api_image_echo(
            page_id=page_id,
            conversation_id=conversation_id,
            since_monotonic=delivery_started_at,
            timeout_seconds=echo_wait_seconds,
        )
        if echo_event is not None:
            attempt_record.update(
                {
                    "echo_verified": True,
                    "verified_message_mid": echo_event.get("message_mid"),
                    "verified_attachment_count": echo_event.get("attachment_count"),
                }
            )
            delivery_attempts.append(attempt_record)
            logger.info(
                "PANCAKE_DRIVE_IMAGE_DELIVERY_VERIFIED page_id=%s conversation_id=%s message_mid=%s attempt=%s status_code=%s verified_message_mid=%s verified_attachment_count=%s",
                page_id,
                conversation_id,
                message_mid,
                attempt,
                send_result.get("status_code"),
                echo_event.get("message_mid"),
                echo_event.get("attachment_count"),
            )
            return _pancake_image_echo_verified_result(
                echo_event=echo_event,
                attempt=attempt,
                max_attempts=max_attempts,
                echo_wait_seconds=echo_wait_seconds,
                content_ids=content_ids,
                delivery_attempts=delivery_attempts,
                send_result=send_result,
            )

        attempt_record["reason"] = "pancake_image_echo_not_observed"
        delivery_attempts.append(attempt_record)
        logger.warning(
            "PANCAKE_DRIVE_IMAGE_DELIVERY_ATTEMPT_UNVERIFIED page_id=%s conversation_id=%s message_mid=%s attempt=%s status_code=%s content_id_count=%s echo_wait_seconds=%s reason=pancake_image_echo_not_observed",
            page_id,
            conversation_id,
            message_mid,
            attempt,
            send_result.get("status_code"),
            len(content_ids),
            echo_wait_seconds,
        )
        if attempt < max_attempts:
            logger.warning(
                "PANCAKE_DRIVE_IMAGE_DELIVERY_RETRY page_id=%s conversation_id=%s message_mid=%s next_attempt=%s content_id_count=%s reason=pancake_image_echo_not_observed",
                page_id,
                conversation_id,
                message_mid,
                attempt + 1,
                len(content_ids),
            )

    logger.warning(
        "PANCAKE_DRIVE_IMAGE_DELIVERY_UNVERIFIED page_id=%s conversation_id=%s message_mid=%s attempt_count=%s content_id_count=%s reason=pancake_image_echo_not_observed",
        page_id,
        conversation_id,
        message_mid,
        max_attempts,
        len(content_ids),
    )
    return {
        "ok": False,
        "reason": "pancake_image_echo_not_observed",
        "status_code": (last_send_result or {}).get("status_code"),
        "response_data": (last_send_result or {}).get("response_data"),
        "content_ids": content_ids,
        "attempt_count": max_attempts,
        "max_attempts": max_attempts,
        "echo_wait_seconds": echo_wait_seconds,
        "echo_verified": False,
        "unverified_after_attempts": True,
        "delivery_attempts": delivery_attempts,
        "send_result": last_send_result,
    }


async def _send_pancake_content_ids_with_split_fallback(
    *,
    page_id: str,
    conversation_id: str,
    message_mid: str | None,
    content_ids: list[str],
    action: str,
) -> dict[str, Any]:
    primary_result = await _send_pancake_content_ids_with_echo_verification(
        page_id=page_id,
        conversation_id=conversation_id,
        message_mid=message_mid,
        content_ids=content_ids,
        action=action,
    )
    if not _should_fallback_pancake_content_ids(
        content_ids=content_ids,
        delivery_result=primary_result,
    ):
        return primary_result

    chunks = _split_pancake_content_ids_for_fallback(content_ids)
    logger.warning(
        "PANCAKE_DRIVE_IMAGE_DELIVERY_SPLIT_FALLBACK_START page_id=%s conversation_id=%s message_mid=%s reason=%s content_id_count=%s split_ratio=%s split_count=%s",
        page_id,
        conversation_id,
        message_mid,
        primary_result.get("reason"),
        len(content_ids),
        PANCAKE_IMAGE_CONTENT_ID_FALLBACK_RATIO,
        len(chunks),
    )

    fallback_results: list[dict[str, Any]] = []
    for chunk_index, chunk_content_ids in enumerate(chunks, start=1):
        logger.info(
            "PANCAKE_DRIVE_IMAGE_DELIVERY_SPLIT_FALLBACK_ATTEMPT_START page_id=%s conversation_id=%s message_mid=%s split_index=%s split_count=%s content_id_count=%s",
            page_id,
            conversation_id,
            message_mid,
            chunk_index,
            len(chunks),
            len(chunk_content_ids),
        )
        chunk_result = await _send_pancake_content_ids_with_echo_verification(
            page_id=page_id,
            conversation_id=conversation_id,
            message_mid=message_mid,
            content_ids=chunk_content_ids,
            action=action,
        )
        fallback_record = {
            "chunk_index": chunk_index,
            "chunk_count": len(chunks),
            "split_index": chunk_index,
            "split_count": len(chunks),
            "content_ids": chunk_content_ids,
            "ok": bool(chunk_result.get("ok")),
            "reason": chunk_result.get("reason"),
            "attempt_count": chunk_result.get("attempt_count"),
            "echo_verified": bool(chunk_result.get("echo_verified")),
            "result": chunk_result,
        }
        fallback_results.append(fallback_record)
        log = logger.info if fallback_record["ok"] else logger.warning
        log(
            "PANCAKE_DRIVE_IMAGE_DELIVERY_SPLIT_FALLBACK_ATTEMPT_DONE page_id=%s conversation_id=%s message_mid=%s split_index=%s split_count=%s ok=%s reason=%s attempt_count=%s echo_verified=%s",
            page_id,
            conversation_id,
            message_mid,
            chunk_index,
            len(chunks),
            fallback_record["ok"],
            fallback_record["reason"],
            fallback_record["attempt_count"],
            fallback_record["echo_verified"],
        )

    unrecovered_split_failures: list[dict[str, Any]] = []
    single_fallback_content_ids: list[str] = []
    for fallback_record in fallback_results:
        if bool(fallback_record.get("ok")):
            continue
        chunk_content_ids = list(fallback_record.get("content_ids") or [])
        chunk_result = _as_dict(fallback_record.get("result"))
        if len(chunk_content_ids) > 1 and _should_fallback_pancake_content_ids(
            content_ids=chunk_content_ids,
            delivery_result=chunk_result,
        ):
            single_fallback_content_ids.extend(chunk_content_ids)
            continue
        unrecovered_split_failures.append(fallback_record)

    single_chunks = _single_pancake_content_ids_for_fallback(single_fallback_content_ids)
    single_fallback_results: list[dict[str, Any]] = []
    if single_chunks:
        logger.warning(
            "PANCAKE_DRIVE_IMAGE_DELIVERY_SINGLE_FALLBACK_START page_id=%s conversation_id=%s message_mid=%s content_id_count=%s single_count=%s",
            page_id,
            conversation_id,
            message_mid,
            len(single_fallback_content_ids),
            len(single_chunks),
        )
        for single_index, single_content_ids in enumerate(single_chunks, start=1):
            logger.info(
                "PANCAKE_DRIVE_IMAGE_DELIVERY_SINGLE_FALLBACK_ATTEMPT_START page_id=%s conversation_id=%s message_mid=%s single_index=%s single_count=%s content_id=%s",
                page_id,
                conversation_id,
                message_mid,
                single_index,
                len(single_chunks),
                single_content_ids[0],
            )
            single_result = await _send_pancake_content_ids_with_echo_verification(
                page_id=page_id,
                conversation_id=conversation_id,
                message_mid=message_mid,
                content_ids=single_content_ids,
                action=action,
            )
            single_record = {
                "single_index": single_index,
                "single_count": len(single_chunks),
                "content_ids": single_content_ids,
                "content_id": single_content_ids[0],
                "ok": bool(single_result.get("ok")),
                "reason": single_result.get("reason"),
                "attempt_count": single_result.get("attempt_count"),
                "echo_verified": bool(single_result.get("echo_verified")),
                "result": single_result,
            }
            single_fallback_results.append(single_record)
            log = logger.info if single_record["ok"] else logger.warning
            log(
                "PANCAKE_DRIVE_IMAGE_DELIVERY_SINGLE_FALLBACK_ATTEMPT_DONE page_id=%s conversation_id=%s message_mid=%s single_index=%s single_count=%s ok=%s reason=%s attempt_count=%s echo_verified=%s",
                page_id,
                conversation_id,
                message_mid,
                single_index,
                len(single_chunks),
                single_record["ok"],
                single_record["reason"],
                single_record["attempt_count"],
                single_record["echo_verified"],
            )

    single_fallback_failed_count = sum(1 for item in single_fallback_results if not bool(item.get("ok")))
    fallback_ok = (
        bool(fallback_results)
        and not unrecovered_split_failures
        and single_fallback_failed_count == 0
    )
    last_delivery_result = (
        single_fallback_results[-1]["result"]
        if single_fallback_results
        else (fallback_results[-1]["result"] if fallback_results else primary_result)
    )
    delivery_attempts = list(primary_result.get("delivery_attempts") or [])
    for fallback_record in fallback_results:
        chunk_result = _as_dict(fallback_record.get("result"))
        for attempt_record in chunk_result.get("delivery_attempts") or []:
            if isinstance(attempt_record, dict):
                attempt_record = {
                    **attempt_record,
                    "fallback_chunk_index": fallback_record["chunk_index"],
                    "fallback_chunk_count": fallback_record["chunk_count"],
                    "fallback_split_index": fallback_record["chunk_index"],
                    "fallback_split_count": fallback_record["chunk_count"],
                }
            delivery_attempts.append(attempt_record)
    for single_record in single_fallback_results:
        single_result = _as_dict(single_record.get("result"))
        for attempt_record in single_result.get("delivery_attempts") or []:
            if isinstance(attempt_record, dict):
                attempt_record = {
                    **attempt_record,
                    "single_fallback_index": single_record["single_index"],
                    "single_fallback_count": single_record["single_count"],
                    "fallback_single_index": single_record["single_index"],
                    "fallback_single_count": single_record["single_count"],
                }
            delivery_attempts.append(attempt_record)

    successful_delivery_records = [
        item
        for item in fallback_results
        if bool(item.get("ok"))
    ] + [
        item
        for item in single_fallback_results
        if bool(item.get("ok"))
    ]
    verified_attachment_counts = [
        item["result"].get("verified_attachment_count")
        for item in successful_delivery_records
        if isinstance(item.get("result"), dict)
    ]
    total_verified_attachment_count = (
        sum(verified_attachment_counts)
        if fallback_ok
        and verified_attachment_counts
        and len(verified_attachment_counts) == len(successful_delivery_records)
        and all(isinstance(count, int) for count in verified_attachment_counts)
        else None
    )
    final_reason = None
    if not fallback_ok:
        final_reason = (
            "pancake_content_id_single_fallback_failed"
            if single_fallback_failed_count
            else "pancake_content_id_split_fallback_failed"
        )

    logger.info(
        "PANCAKE_DRIVE_IMAGE_DELIVERY_SPLIT_FALLBACK_DONE page_id=%s conversation_id=%s message_mid=%s ok=%s split_count=%s failed_split_count=%s single_fallback_count=%s failed_single_count=%s",
        page_id,
        conversation_id,
        message_mid,
        fallback_ok,
        len(fallback_results),
        sum(1 for item in fallback_results if not bool(item.get("ok"))),
        len(single_fallback_results),
        single_fallback_failed_count,
    )
    return {
        "ok": fallback_ok,
        "reason": final_reason,
        "status_code": last_delivery_result.get("status_code"),
        "response_data": last_delivery_result.get("response_data"),
        "content_ids": content_ids,
        "attempt_count": sum(int(item.get("attempt_count") or 0) for item in fallback_results)
        + sum(int(item.get("attempt_count") or 0) for item in single_fallback_results),
        "max_attempts": primary_result.get("max_attempts"),
        "echo_wait_seconds": primary_result.get("echo_wait_seconds"),
        "echo_verified": fallback_ok
        and all(bool(item.get("echo_verified")) for item in successful_delivery_records),
        "verified_message_mid": last_delivery_result.get("verified_message_mid"),
        "verified_attachment_count": total_verified_attachment_count,
        "delivery_attempts": delivery_attempts,
        "fallback_used": True,
        "fallback_split_ratio": PANCAKE_IMAGE_CONTENT_ID_FALLBACK_RATIO,
        "fallback_splits": chunks,
        "fallback_chunk_size": None,
        "fallback_chunk_count": len(chunks),
        "fallback_split_count": len(chunks),
        "primary_send_result": primary_result,
        "fallback_results": fallback_results,
        "single_fallback_used": bool(single_fallback_results),
        "single_fallback_content_ids": single_fallback_content_ids,
        "single_fallback_splits": single_chunks,
        "single_fallback_count": len(single_fallback_results),
        "single_fallback_failed_count": single_fallback_failed_count,
        "single_fallback_results": single_fallback_results,
        "unrecovered_split_fallback_count": len(unrecovered_split_failures),
    }


async def _send_pancake_comment_content_ids_with_echo_verification(
    *,
    page_id: str,
    conversation_id: str,
    comment_message_id: str,
    message_mid: str | None,
    content_ids: list[str],
) -> dict[str, Any]:
    echo_wait_seconds = PANCAKE_IMAGE_ECHO_VERIFY_WAIT_SECONDS
    delivery_started_at = time.monotonic()
    logger.info(
        "PANCAKE_COMMENT_IMAGE_CONTENT_IDS_SEND_START page_id=%s conversation_id=%s message_mid=%s content_id_count=%s",
        page_id,
        conversation_id,
        message_mid,
        len(content_ids),
    )
    send_result = await send_pancake_comment_content_ids(
        page_id=page_id,
        conversation_id=conversation_id,
        comment_message_id=comment_message_id,
        content_ids=content_ids,
    )
    attempt_record = {
        "attempt": 1,
        "ok": bool(send_result.get("ok")),
        "status_code": send_result.get("status_code"),
        "reason": send_result.get("reason"),
        "echo_verified": False,
    }
    if not bool(send_result.get("ok")):
        return {
            "ok": False,
            "reason": send_result.get("reason")
            or "pancake_send_comment_content_ids_failed",
            "status_code": send_result.get("status_code"),
            "response_data": send_result.get("response_data"),
            "content_ids": content_ids,
            "attempt_count": 1,
            "max_attempts": 1,
            "echo_wait_seconds": echo_wait_seconds,
            "echo_verified": False,
            "delivery_attempts": [attempt_record],
            "send_result": send_result,
        }

    echo_event = await _wait_for_pancake_public_api_image_echo(
        page_id=page_id,
        conversation_id=conversation_id,
        since_monotonic=delivery_started_at,
        timeout_seconds=echo_wait_seconds,
    )
    if echo_event is not None:
        attempt_record.update(
            {
                "echo_verified": True,
                "verified_message_mid": echo_event.get("message_mid"),
                "verified_attachment_count": echo_event.get("attachment_count"),
            }
        )
        return _pancake_image_echo_verified_result(
            echo_event=echo_event,
            attempt=1,
            max_attempts=1,
            echo_wait_seconds=echo_wait_seconds,
            content_ids=content_ids,
            delivery_attempts=[attempt_record],
            send_result=send_result,
        )

    attempt_record["reason"] = "pancake_image_echo_not_observed"
    return {
        "ok": False,
        "reason": "pancake_image_echo_not_observed",
        "status_code": send_result.get("status_code"),
        "response_data": send_result.get("response_data"),
        "content_ids": content_ids,
        "attempt_count": 1,
        "max_attempts": 1,
        "echo_wait_seconds": echo_wait_seconds,
        "echo_verified": False,
        "unverified_after_attempts": True,
        "delivery_attempts": [attempt_record],
        "send_result": send_result,
    }


async def _send_pancake_comment_drive_images(
    *,
    normalized: dict[str, Any],
    drive_images: list[dict[str, Any]],
) -> dict[str, Any]:
    page_id = str(normalized.get("page_id") or "").strip()
    conversation_id = str(normalized.get("pancake_conversation_id") or "").strip()
    comment_message_id = str(normalized.get("comment_message_id") or "").strip()
    content_ids: list[str] = []
    upload_results: list[dict[str, Any]] = []
    upload_errors: list[dict[str, Any]] = []
    image_results: list[dict[str, Any]] = []

    for image in drive_images:
        drive_file_id = str(image.get("drive_file_id") or "").strip()
        local_path = str(image.get("local_path") or "").strip()
        drive_file_name = str(image.get("drive_file_name") or "").strip() or None
        drive_file_color = str(image.get("drive_file_color") or "").strip() or None
        if not local_path:
            error = {
                "drive_file_id": drive_file_id or None,
                "local_path": None,
                "reason": "missing_pancake_image_local_path",
            }
            upload_errors.append(error)
            image_results.append({"ok": False, **error})
            continue

        logger.info(
            "PANCAKE_COMMENT_IMAGE_UPLOAD_START page_id=%s conversation_id=%s message_mid=%s drive_file_id=%s local_path=%s",
            page_id,
            conversation_id,
            normalized.get("message_mid"),
            drive_file_id,
            local_path,
        )
        upload_result = await upload_pancake_content(
            page_id=page_id,
            file_path=local_path,
        )
        upload_record = {
            "drive_file_id": drive_file_id,
            "local_path": local_path,
            "ok": bool(upload_result.get("ok")),
            "content_id": upload_result.get("content_id"),
            "reason": upload_result.get("reason"),
            "status_code": upload_result.get("status_code"),
            "reused": False,
            "uploaded": True,
        }
        if drive_file_name:
            upload_record["drive_file_name"] = drive_file_name
        if drive_file_color:
            upload_record["drive_file_color"] = drive_file_color
        upload_results.append(upload_record)
        logger.info(
            "PANCAKE_COMMENT_IMAGE_UPLOAD_RESULT page_id=%s conversation_id=%s message_mid=%s drive_file_id=%s ok=%s status_code=%s reason=%s content_id=%s",
            page_id,
            conversation_id,
            normalized.get("message_mid"),
            drive_file_id,
            bool(upload_result.get("ok")),
            upload_result.get("status_code"),
            upload_result.get("reason"),
            upload_result.get("content_id"),
        )
        if not bool(upload_result.get("ok")):
            error = {
                "drive_file_id": drive_file_id or None,
                "local_path": local_path,
                "reason": upload_result.get("reason") or "pancake_upload_failed",
            }
            upload_errors.append(error)
            image_results.append({"ok": False, **error})
            continue

        content_id = str(upload_result.get("content_id") or "").strip()
        if not content_id:
            error = {
                "drive_file_id": drive_file_id or None,
                "local_path": local_path,
                "reason": "missing_pancake_content_id",
            }
            upload_errors.append(error)
            image_results.append({"ok": False, **error})
            continue

        content_ids.append(content_id)
        send_result = await _send_pancake_comment_content_ids_with_echo_verification(
            page_id=page_id,
            conversation_id=conversation_id,
            comment_message_id=comment_message_id,
            message_mid=normalized.get("message_mid"),
            content_ids=[content_id],
        )
        image_results.append(
            {
                **send_result,
                "drive_file_id": drive_file_id,
                "local_path": local_path,
            }
        )
        logger.info(
            "PANCAKE_COMMENT_IMAGE_CONTENT_IDS_SEND_RESULT page_id=%s conversation_id=%s message_mid=%s drive_file_id=%s content_id=%s ok=%s status_code=%s reason=%s echo_verified=%s",
            page_id,
            conversation_id,
            normalized.get("message_mid"),
            drive_file_id,
            content_id,
            bool(send_result.get("ok")),
            send_result.get("status_code"),
            send_result.get("reason"),
            bool(send_result.get("echo_verified")),
        )

    successful_results = [result for result in image_results if bool(result.get("ok"))]
    failed_results = [result for result in image_results if not bool(result.get("ok"))]
    return {
        "ok": bool(image_results) and not failed_results,
        "reason": (
            None
            if image_results and not failed_results
            else (
                failed_results[0].get("reason")
                if failed_results
                else "no_pancake_comment_image_content_ids"
            )
        ),
        "content_ids": content_ids,
        "upload_results": upload_results,
        "upload_errors": upload_errors,
        "image_results": image_results,
        "sent_image_count": len(successful_results),
        "failed_image_count": len(failed_results),
        "echo_verified": bool(image_results) and not failed_results,
        "verified_message_mids": [
            result.get("verified_message_mid")
            for result in successful_results
            if result.get("verified_message_mid")
        ],
        "verified_attachment_count": sum(
            int(result.get("verified_attachment_count") or 0)
            for result in successful_results
        ),
    }


def _extract_pancake_local_drive_images(reply: dict[str, Any]) -> list[dict[str, Any]]:
    cache_result = reply.get("pancake_drive_image_cache_result")
    if not isinstance(cache_result, dict):
        return []

    raw_images = cache_result.get("images")
    if not isinstance(raw_images, list):
        return []

    images: list[dict[str, Any]] = []
    for raw_image in raw_images:
        if not isinstance(raw_image, dict):
            continue
        if raw_image.get("error"):
            continue
        local_path = str(raw_image.get("local_path") or "").strip()
        drive_file_id = str(raw_image.get("drive_file_id") or "").strip()
        if not local_path or not drive_file_id:
            continue
        images.append(raw_image)
    return images


async def _wait_for_pancake_uploaded_content_ready(
    *,
    page_id: str,
    conversation_id: str,
    message_mid: str | None,
    uploaded_content_id_count: int,
    content_id_count: int,
) -> None:
    wait_seconds = PANCAKE_IMAGE_CONTENT_READY_WAIT_SECONDS
    if wait_seconds <= 0 or uploaded_content_id_count <= 0:
        return
    logger.info(
        "PANCAKE_DRIVE_IMAGE_CONTENT_READY_WAIT page_id=%s conversation_id=%s message_mid=%s wait_seconds=%s uploaded_content_id_count=%s content_id_count=%s",
        page_id,
        conversation_id,
        message_mid,
        wait_seconds,
        uploaded_content_id_count,
        content_id_count,
    )
    await asyncio.sleep(wait_seconds)


async def _send_pancake_drive_images(
    *,
    normalized: dict[str, Any],
    drive_images: list[dict[str, Any]],
    action: str,
) -> dict[str, Any]:
    if not drive_images:
        logger.info(
            "PANCAKE_DRIVE_IMAGE_SEND_SKIPPED page_id=%s conversation_id=%s message_mid=%s reason=no_pancake_drive_images",
            normalized.get("page_id"),
            normalized.get("pancake_conversation_id"),
            normalized.get("message_mid"),
        )
        return {
            "ok": False,
            "reason": "no_pancake_drive_images",
            "content_ids": [],
            "upload_results": [],
        }

    page_id = str(normalized.get("page_id") or "").strip()
    conversation_id = str(normalized.get("pancake_conversation_id") or "").strip()
    if action == PANCAKE_REPLY_COMMENT_ACTION:
        return await _send_pancake_comment_drive_images(
            normalized=normalized,
            drive_images=drive_images,
        )

    content_ids: list[str] = []
    upload_results: list[dict[str, Any]] = []
    upload_errors: list[dict[str, Any]] = []
    uploaded_content_id_count = 0
    drive_image_service = PancakeDriveImageService()
    reuse_uploaded_content_id = _should_reuse_pancake_uploaded_content_id()
    logger.info(
        "PANCAKE_DRIVE_IMAGE_SEND_START page_id=%s conversation_id=%s message_mid=%s image_count=%s action=%s reuse_uploaded_content_id=%s",
        page_id,
        conversation_id,
        normalized.get("message_mid"),
        len(drive_images),
        action,
        reuse_uploaded_content_id,
    )

    for image in drive_images:
        drive_file_id = str(image.get("drive_file_id") or "").strip()
        local_path = str(image.get("local_path") or "").strip()
        cached_content_id = str(image.get("content_id") or "").strip()
        drive_file_name = str(image.get("drive_file_name") or "").strip() or None
        drive_file_color = str(image.get("drive_file_color") or "").strip() or None
        if reuse_uploaded_content_id and cached_content_id:
            content_ids.append(cached_content_id)
            logger.info(
                "PANCAKE_DRIVE_IMAGE_CONTENT_ID_REUSED page_id=%s conversation_id=%s message_mid=%s drive_file_id=%s content_id=%s local_path=%s",
                page_id,
                conversation_id,
                normalized.get("message_mid"),
                drive_file_id,
                cached_content_id,
                local_path,
            )
            upload_record = {
                "drive_file_id": drive_file_id,
                "local_path": local_path,
                "ok": True,
                "content_id": cached_content_id,
                "reason": None,
                "status_code": None,
                "reused": True,
                "uploaded": False,
            }
            if drive_file_name:
                upload_record["drive_file_name"] = drive_file_name
            if drive_file_color:
                upload_record["drive_file_color"] = drive_file_color
            upload_results.append(upload_record)
            continue

        logger.info(
            "PANCAKE_DRIVE_IMAGE_UPLOAD_START page_id=%s conversation_id=%s message_mid=%s drive_file_id=%s local_path=%s drive_file_name=%s drive_file_color=%s",
            page_id,
            conversation_id,
            normalized.get("message_mid"),
            drive_file_id,
            local_path,
            drive_file_name,
            drive_file_color,
        )
        upload_result = await upload_pancake_content(page_id=page_id, file_path=local_path)
        logger.info(
            "PANCAKE_DRIVE_IMAGE_UPLOAD_RESULT page_id=%s conversation_id=%s message_mid=%s drive_file_id=%s ok=%s status_code=%s reason=%s content_id=%s",
            page_id,
            conversation_id,
            normalized.get("message_mid"),
            drive_file_id,
            bool(upload_result.get("ok")),
            upload_result.get("status_code"),
            upload_result.get("reason"),
            upload_result.get("content_id"),
        )
        upload_record = {
            "drive_file_id": drive_file_id,
            "local_path": local_path,
            "ok": bool(upload_result.get("ok")),
            "content_id": upload_result.get("content_id"),
            "reason": upload_result.get("reason"),
            "status_code": upload_result.get("status_code"),
            "reused": False,
            "uploaded": True,
        }
        if drive_file_name:
            upload_record["drive_file_name"] = drive_file_name
        if drive_file_color:
            upload_record["drive_file_color"] = drive_file_color
        upload_results.append(upload_record)

        if bool(upload_result.get("ok")):
            content_id = str(upload_result.get("content_id") or "").strip()
            if content_id:
                content_ids.append(content_id)
                uploaded_content_id_count += 1
                drive_image_service.record_uploaded_content_id(
                    drive_file_id=drive_file_id,
                    content_id=content_id,
                )
                remove_local_image = getattr(
                    drive_image_service,
                    "remove_local_image_for_drive_file_id",
                    None,
                )
                if reuse_uploaded_content_id and callable(remove_local_image):
                    upload_record["local_removed"] = bool(remove_local_image(drive_file_id))
                    logger.info(
                        "PANCAKE_DRIVE_IMAGE_LOCAL_REMOVE_AFTER_UPLOAD page_id=%s conversation_id=%s message_mid=%s drive_file_id=%s local_removed=%s",
                        page_id,
                        conversation_id,
                        normalized.get("message_mid"),
                        drive_file_id,
                        upload_record["local_removed"],
                    )
            continue

        upload_errors.append(
            {
                "drive_file_id": drive_file_id,
                "local_path": local_path,
                "reason": upload_result.get("reason") or "pancake_upload_failed",
            }
        )

    if not content_ids:
        logger.warning(
            "PANCAKE_DRIVE_IMAGE_UPLOAD_NO_CONTENT_IDS page_id=%s conversation_id=%s message_mid=%s errors=%s",
            page_id,
            conversation_id,
            normalized.get("message_mid"),
            upload_errors,
        )
        return {
            "ok": False,
            "reason": "no_pancake_image_content_ids",
            "content_ids": [],
            "upload_results": upload_results,
            "upload_errors": upload_errors,
        }

    await _wait_for_pancake_uploaded_content_ready(
        page_id=page_id,
        conversation_id=conversation_id,
        message_mid=normalized.get("message_mid"),
        uploaded_content_id_count=uploaded_content_id_count,
        content_id_count=len(content_ids),
    )

    logger.info(
        "PANCAKE_DRIVE_IMAGE_CONTENT_IDS_SEND_START page_id=%s conversation_id=%s message_mid=%s content_id_count=%s content_ids=%s",
        page_id,
        conversation_id,
        normalized.get("message_mid"),
        len(content_ids),
        content_ids,
    )
    image_send_result = await _send_pancake_content_ids_with_split_fallback(
        page_id=page_id,
        conversation_id=conversation_id,
        message_mid=normalized.get("message_mid"),
        content_ids=content_ids,
        action=action,
    )
    if not bool(image_send_result.get("ok")):
        logger.warning(
            "PANCAKE_DRIVE_IMAGE_SEND_FAILED page_id=%s conversation_id=%s message_mid=%s reason=%s content_ids=%s attempt_count=%s echo_verified=%s",
            page_id,
            conversation_id,
            normalized.get("message_mid"),
            image_send_result.get("reason"),
            content_ids,
            image_send_result.get("attempt_count"),
            image_send_result.get("echo_verified"),
        )
    else:
        logger.info(
            "PANCAKE_DRIVE_IMAGE_SEND_OK page_id=%s conversation_id=%s message_mid=%s content_id_count=%s status_code=%s attempt_count=%s echo_verified=%s verified_message_mid=%s verified_attachment_count=%s",
            page_id,
            conversation_id,
            normalized.get("message_mid"),
            len(content_ids),
            image_send_result.get("status_code"),
            image_send_result.get("attempt_count"),
            image_send_result.get("echo_verified"),
            image_send_result.get("verified_message_mid"),
            image_send_result.get("verified_attachment_count"),
        )

    result = {
        "ok": bool(image_send_result.get("ok")),
        "reason": None if bool(image_send_result.get("ok")) else image_send_result.get("reason"),
        "content_ids": content_ids,
        "upload_results": upload_results,
        "upload_errors": upload_errors,
        "send_result": image_send_result,
        "attempt_count": image_send_result.get("attempt_count"),
        "max_attempts": image_send_result.get("max_attempts"),
        "echo_wait_seconds": image_send_result.get("echo_wait_seconds"),
        "echo_verified": bool(image_send_result.get("echo_verified")),
        "verified_message_mid": image_send_result.get("verified_message_mid"),
        "verified_attachment_count": image_send_result.get("verified_attachment_count"),
        "delivery_attempts": image_send_result.get("delivery_attempts") or [],
    }
    if image_send_result.get("unverified_after_attempts") is not None:
        result["unverified_after_attempts"] = image_send_result.get("unverified_after_attempts")
    return result


async def _complete_pancake_ai_reply(
    *,
    conversation: Conversation,
    normalized: dict[str, Any],
    user_message: Message,
    reply: dict[str, Any],
    message_kind: str,
    extra_bot_meta: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    message_mid = str(normalized.get("message_mid") or "").strip()
    is_auto_consult = str(normalized.get("source") or "").strip() == PANCAKE_AUTO_CONSULT_SOURCE
    auto_consult = _as_dict(normalized.get("auto_consult"))

    reply_text = str(reply.get("reply_text") or "").strip()
    if not reply_text:
        return {
            "status": "processed",
            "ok": False,
            "reason": "missing_reply_message",
            "conversation_id": str(conversation.id),
            "message_id": str(user_message.id),
            "message_mid": message_mid,
            "message_kind": message_kind,
            "auto_consult": auto_consult or None,
            "pancake_drive_reply": reply.get("pancake_drive_reply"),
            "pancake_drive_image_cache_result": reply.get("pancake_drive_image_cache_result"),
        }
    action = _resolve_pancake_reply_action(normalized)
    if not action:
        return {
            "status": "processed",
            "ok": False,
            "reason": "unsupported_reply_action",
            "conversation_id": str(conversation.id),
            "message_id": str(user_message.id),
            "message_mid": message_mid,
            "message_kind": message_kind,
            "auto_consult": auto_consult or None,
        }

    conversation = await _reload_pancake_conversation_for_pause_check(conversation)
    await _resume_pancake_conversation_if_pause_expired(conversation)
    if _is_pancake_bot_paused(conversation):
        if is_auto_consult:
            logger.info(
                "PANCAKE_AUTO_CONSULT_SUPPRESSED_BY_ADMIN_PAUSE page_id=%s conversation_id=%s customer_id=%s trigger_type=%s trigger_message_mid=%s paused_until=%s reason=conversation_paused_before_send",
                normalized.get("page_id"),
                normalized.get("pancake_conversation_id"),
                normalized.get("sender_id"),
                auto_consult.get("trigger_type"),
                auto_consult.get("trigger_message_mid"),
                getattr(conversation, "bot_paused_until", None),
            )
        else:
            logger.info(
                "PANCAKE_BOT_REPLY_SUPPRESSED_BY_ADMIN_TAKEOVER conversation_id=%s sender_id=%s message_mid=%s paused_until=%s",
                conversation.id,
                normalized.get("sender_id"),
                message_mid,
                getattr(conversation, "bot_paused_until", None),
            )
        return {
            "status": "processed",
            "ok": False,
            "reason": "conversation_paused_before_send",
            "conversation_id": str(conversation.id),
            "message_id": str(user_message.id),
            "message_mid": message_mid,
            "message_kind": message_kind,
            "auto_consult": auto_consult or None,
            "bot_paused_until": getattr(conversation, "bot_paused_until", None),
        }

    repeated_bot_reply = await _maybe_handover_pancake_repeated_bot_reply(
        conversation=conversation,
        normalized=normalized,
        reply_text=reply_text,
    )
    if repeated_bot_reply is not None:
        return {
            "status": "processed",
            "ok": False,
            "reason": repeated_bot_reply["reason"],
            "conversation_id": str(conversation.id),
            "message_id": str(user_message.id),
            "message_mid": message_mid,
            "message_kind": message_kind,
            "auto_consult": auto_consult or None,
            "reply_source": reply.get("source"),
            "bot_paused_until": repeated_bot_reply["handover_result"].get("bot_paused_until"),
            "repeated_bot_reply": repeated_bot_reply,
        }

    if bool(reply.get("ai_quota_fallback")):
        handover_detection = {"detected": False, "reason": "ai_quota_fallback"}
        handover_status_update = {"updated": False, "reason": "ai_quota_fallback"}
    else:
        handover_detection = detect_handover_reply(reply_text)
        handover_status_update = {"updated": False, "reason": "handover_not_detected"}
        if bool(handover_detection.get("detected")):
            handover_status_update = await _update_pancake_handover_conversation_status(
                conversation=conversation,
                handover_detection=handover_detection,
            )

    send_result = await send_pancake_reply(
        page_id=str(normalized.get("page_id") or ""),
        conversation_id=str(normalized.get("pancake_conversation_id") or ""),
        message=reply_text,
        action=action,
    )
    if is_auto_consult:
        log_name = "PANCAKE_AUTO_CONSULT_SEND_OK" if bool(send_result.get("ok")) else "PANCAKE_AUTO_CONSULT_SEND_FAILED"
        logger.info(
            "%s page_id=%s conversation_id=%s customer_id=%s trigger_type=%s trigger_message_mid=%s product_codes=%s ok=%s status_code=%s reason=%s",
            log_name,
            normalized.get("page_id"),
            normalized.get("pancake_conversation_id"),
            normalized.get("sender_id"),
            auto_consult.get("trigger_type"),
            auto_consult.get("trigger_message_mid"),
            auto_consult.get("product_codes"),
            bool(send_result.get("ok")),
            send_result.get("status_code"),
            send_result.get("reason"),
        )
    drive_images = _extract_pancake_local_drive_images(reply)
    cache_result = reply.get("pancake_drive_image_cache_result")
    raw_cache_images = cache_result.get("images") if isinstance(cache_result, dict) else []
    raw_cache_errors = cache_result.get("errors") if isinstance(cache_result, dict) else []
    logger.info(
        "PANCAKE_DRIVE_IMAGES_EXTRACTED page_id=%s conversation_id=%s message_mid=%s text_send_ok=%s text_status_code=%s text_reason=%s cache_image_count=%s cache_error_count=%s sendable_image_count=%s",
        normalized.get("page_id"),
        normalized.get("pancake_conversation_id"),
        message_mid,
        bool(send_result.get("ok")),
        send_result.get("status_code"),
        send_result.get("reason"),
        len(raw_cache_images) if isinstance(raw_cache_images, list) else 0,
        len(raw_cache_errors) if isinstance(raw_cache_errors, list) else 0,
        len(drive_images),
    )
    image_send_result: dict[str, Any] | None = None
    if bool(send_result.get("ok")) and drive_images:
        image_send_result = await _send_pancake_drive_images(
            normalized=normalized,
            drive_images=drive_images,
            action=action,
        )
    elif drive_images:
        logger.warning(
            "PANCAKE_DRIVE_IMAGE_SEND_SKIPPED page_id=%s conversation_id=%s message_mid=%s reason=text_reply_failed_before_image_send text_reason=%s",
            normalized.get("page_id"),
            normalized.get("pancake_conversation_id"),
            message_mid,
            send_result.get("reason"),
        )
        image_send_result = {
            "ok": False,
            "reason": "text_reply_failed_before_image_send",
            "content_ids": [],
            "upload_results": [],
        }

    ai_quota_handover_result = await _maybe_pause_pancake_conversation_for_ai_quota_handover(
        conversation=conversation,
        normalized=normalized,
        reply=reply,
    )

    bot_extra_meta = {
        "pancake_drive_reply": reply.get("pancake_drive_reply"),
        "pancake_drive_image_cache_result": reply.get("pancake_drive_image_cache_result"),
        "handover_detection": handover_detection,
        "handover_status_update": handover_status_update,
    }
    if reply.get("handover_context"):
        bot_extra_meta["handover_context"] = reply.get("handover_context")
    if extra_bot_meta:
        bot_extra_meta.update(extra_bot_meta)
    if image_send_result is not None:
        bot_extra_meta["pancake_drive_image_send_result"] = image_send_result
    if ai_quota_handover_result is not None:
        bot_extra_meta["ai_quota_handover_result"] = ai_quota_handover_result

    bot_message = await _save_pancake_bot_message(
        conversation,
        normalized,
        reply_text=reply_text,
        send_result=send_result,
        extra_meta=bot_extra_meta,
    )
    conversation.updated_at = now_vn()
    await conversation.save()

    return {
        "status": "processed",
        "ok": bool(send_result.get("ok")),
        "reason": None if bool(send_result.get("ok")) else send_result.get("reason"),
        "conversation_id": str(conversation.id),
        "message_id": str(user_message.id),
        "bot_message_id": str(bot_message.id),
        "message_mid": message_mid,
        "message_kind": message_kind,
        "auto_consult": auto_consult or None,
        "reply_text": reply_text,
        "reply_source": reply.get("source"),
        "reply_result": send_result,
        "pancake_drive_reply": reply.get("pancake_drive_reply"),
        "pancake_drive_image_cache_result": reply.get("pancake_drive_image_cache_result"),
        "pancake_drive_image_send_result": image_send_result,
        "handover_detection": handover_detection,
        "handover_status_update": handover_status_update,
        "ai_quota_handover_result": ai_quota_handover_result,
    }


async def _process_prepared_pancake_auto_consult_trigger(
    normalized: dict[str, Any],
    *,
    message_kind: str,
    auto_consult_result: dict[str, Any],
) -> dict[str, Any]:
    message_mid = str(normalized.get("message_mid") or "").strip()
    page_id = str(normalized.get("page_id") or "").strip()
    pancake_conversation_id = str(normalized.get("pancake_conversation_id") or "").strip()

    synthetic_result = _build_pancake_auto_consult_normalized(
        normalized,
        source_detail=_as_dict(auto_consult_result.get("source_detail")),
        prompt_result=_as_dict(auto_consult_result.get("prompt_result")),
    )
    if not bool(synthetic_result.get("ok", True)):
        return {
            "status": "processed",
            "ok": False,
            "reason": synthetic_result.get("reason"),
            "message_mid": message_mid,
            "message_kind": message_kind,
            "auto_consult": auto_consult_result,
        }

    synthetic_normalized = synthetic_result
    auto_consult = _as_dict(synthetic_normalized.get("auto_consult"))
    conversation = await _get_or_create_pancake_conversation(synthetic_normalized)
    await _resume_pancake_conversation_if_pause_expired(conversation)

    if await _is_duplicate_pancake_auto_consult(
        trigger_type=message_kind,
        trigger_message_mid=message_mid,
    ):
        logger.info(
            "PANCAKE_AUTO_CONSULT_DUPLICATE_SKIPPED page_id=%s conversation_id=%s customer_id=%s trigger_type=%s trigger_message_mid=%s reason=duplicate_auto_consult_after_fetch",
            page_id,
            pancake_conversation_id,
            synthetic_normalized.get("sender_id"),
            message_kind,
            message_mid,
        )
        return {
            "status": "ignored",
            "ok": False,
            "reason": "duplicate_auto_consult",
            "conversation_id": str(conversation.id),
            "message_mid": message_mid,
            "message_kind": message_kind,
            "auto_consult": auto_consult,
        }

    user_message = await _save_pancake_user_message(conversation, synthetic_normalized)
    if _is_pancake_bot_paused(conversation):
        conversation.updated_at = now_vn()
        await conversation.save()
        logger.info(
            "PANCAKE_AUTO_CONSULT_SUPPRESSED_BY_ADMIN_PAUSE page_id=%s conversation_id=%s customer_id=%s trigger_type=%s trigger_message_mid=%s paused_until=%s reason=conversation_paused_by_admin",
            page_id,
            pancake_conversation_id,
            synthetic_normalized.get("sender_id"),
            message_kind,
            message_mid,
            getattr(conversation, "bot_paused_until", None),
        )
        return {
            "status": "processed",
            "ok": False,
            "reason": "conversation_paused_by_admin",
            "conversation_id": str(conversation.id),
            "message_id": str(user_message.id),
            "message_mid": message_mid,
            "message_kind": message_kind,
            "auto_consult": auto_consult,
            "bot_paused_until": getattr(conversation, "bot_paused_until", None),
        }

    logger.info(
        "PANCAKE_AUTO_CONSULT_AI_START page_id=%s conversation_id=%s customer_id=%s trigger_type=%s trigger_message_mid=%s product_codes=%s",
        page_id,
        pancake_conversation_id,
        synthetic_normalized.get("sender_id"),
        message_kind,
        message_mid,
        auto_consult.get("product_codes"),
    )
    reply = await _generate_pancake_reply(
        conversation=conversation,
        normalized=synthetic_normalized,
    )
    if not bool(reply.get("ok")):
        logger.warning(
            "PANCAKE_AUTO_CONSULT_AI_FAILED page_id=%s conversation_id=%s customer_id=%s trigger_type=%s trigger_message_mid=%s product_codes=%s reason=%s",
            page_id,
            pancake_conversation_id,
            synthetic_normalized.get("sender_id"),
            message_kind,
            message_mid,
            auto_consult.get("product_codes"),
            reply.get("reason"),
        )
        return {
            "status": "processed",
            "ok": False,
            "reason": reply.get("reason"),
            "conversation_id": str(conversation.id),
            "message_id": str(user_message.id),
            "message_mid": message_mid,
            "message_kind": message_kind,
            "auto_consult": auto_consult,
        }

    logger.info(
        "PANCAKE_AUTO_CONSULT_AI_OK page_id=%s conversation_id=%s customer_id=%s trigger_type=%s trigger_message_mid=%s product_codes=%s",
        page_id,
        pancake_conversation_id,
        synthetic_normalized.get("sender_id"),
        message_kind,
        message_mid,
        auto_consult.get("product_codes"),
    )
    _mark_pancake_auto_consult_trigger_consumed(
        trigger_type=message_kind,
        trigger_message_mid=message_mid,
    )
    return await _complete_pancake_ai_reply(
        conversation=conversation,
        normalized=synthetic_normalized,
        user_message=user_message,
        reply=reply,
        message_kind=message_kind,
        extra_bot_meta={"auto_consult": auto_consult},
    )


async def _process_pancake_auto_consult_trigger(
    normalized: dict[str, Any],
    *,
    message_kind: str,
) -> dict[str, Any]:
    message_mid = str(normalized.get("message_mid") or "").strip()
    page_id = str(normalized.get("page_id") or "").strip()
    pancake_conversation_id = str(normalized.get("pancake_conversation_id") or "").strip()
    if not _is_pancake_auto_consult_enabled():
        return {
            "status": "ignored",
            "ok": False,
            "reason": "pancake_auto_consult_disabled",
            "message_mid": message_mid,
            "message_kind": message_kind,
        }

    logger.info(
        "PANCAKE_AUTO_CONSULT_TRIGGER_DETECTED page_id=%s conversation_id=%s trigger_type=%s trigger_message_mid=%s",
        page_id,
        pancake_conversation_id,
        message_kind,
        message_mid,
    )
    if await _is_duplicate_pancake_auto_consult(
        trigger_type=message_kind,
        trigger_message_mid=message_mid,
    ):
        logger.info(
            "PANCAKE_AUTO_CONSULT_DUPLICATE_SKIPPED page_id=%s conversation_id=%s trigger_type=%s trigger_message_mid=%s reason=duplicate_auto_consult",
            page_id,
            pancake_conversation_id,
            message_kind,
            message_mid,
        )
        return {
            "status": "ignored",
            "ok": False,
            "reason": "duplicate_auto_consult",
            "message_mid": message_mid,
            "message_kind": message_kind,
        }
    if message_kind == PANCAKE_MESSAGE_AD_CARD and _is_pending_pancake_ad_context_trigger(
        trigger_type=message_kind,
        trigger_message_mid=message_mid,
    ):
        return {
            "status": "ignored",
            "ok": False,
            "reason": "duplicate_auto_consult_pending",
            "message_mid": message_mid,
            "message_kind": message_kind,
        }

    processing_key = _pancake_auto_consult_processing_key(
        trigger_type=message_kind,
        trigger_message_mid=message_mid,
    )
    if not _try_mark_pancake_message_processing(processing_key):
        return {
            "status": "ignored",
            "ok": False,
            "reason": "duplicate_auto_consult_inflight",
            "message_mid": message_mid,
            "message_kind": message_kind,
        }

    try:
        auto_consult_result = await _prepare_pancake_auto_consult(
            normalized,
            message_kind=message_kind,
        )
        if not bool(auto_consult_result.get("ok")):
            return {
                "status": "processed",
                "ok": False,
                "reason": auto_consult_result.get("reason"),
                "message_mid": message_mid,
                "message_kind": message_kind,
                "auto_consult": auto_consult_result,
            }

        if message_kind == PANCAKE_MESSAGE_AD_CARD:
            key = _pancake_auto_consult_merge_key(normalized)
            sender_result = _pop_pancake_sender_buffer_entry_for_key(
                key,
                reason="ad_context_arrived",
            )
            if key is not None and bool(sender_result.get("popped")):
                return await _process_pancake_sender_buffer_with_auto_consult_context(
                    key=key,
                    sender_entry=_as_dict(sender_result.get("entry")),
                    ad_entry={
                        "normalized": normalized,
                        "message_kind": message_kind,
                        "auto_consult_result": auto_consult_result,
                    },
                    reason="ad_context_arrived",
                )

            pending_result = _enqueue_pending_pancake_ad_context(
                normalized=normalized,
                message_kind=message_kind,
                auto_consult_result=auto_consult_result,
            )
            if bool(pending_result.get("queued")):
                return {
                    "status": "processed",
                    "ok": True,
                    "reason": pending_result.get("reason"),
                    "message_mid": message_mid,
                    "message_kind": message_kind,
                    "wait_seconds": pending_result.get("wait_seconds"),
                    "auto_consult": auto_consult_result,
                }
            if pending_result.get("reason") == "duplicate_auto_consult_pending":
                return {
                    "status": "ignored",
                    "ok": False,
                    "reason": pending_result.get("reason"),
                    "message_mid": message_mid,
                    "message_kind": message_kind,
                }

        return await _process_prepared_pancake_auto_consult_trigger(
            normalized,
            message_kind=message_kind,
            auto_consult_result=auto_consult_result,
        )
    finally:
        _finalize_pancake_message_processing(processing_key)


async def _process_normalized_message(normalized: dict[str, Any]) -> dict[str, Any]:
    message_mid = str(normalized.get("message_mid") or "").strip()
    message_type = str(normalized.get("message_type") or "").strip().upper()
    message_kind = _classify_pancake_message(normalized)
    is_customer_comment = message_kind == PANCAKE_MESSAGE_CUSTOMER_COMMENT

    if message_kind == PANCAKE_MESSAGE_BOT_ECHO:
        return {
            "status": "ignored",
            "reason": "pancake_echo_message",
            "message_mid": message_mid,
            "message_kind": message_kind,
        }

    if message_type not in {PANCAKE_MESSAGE_INBOX, PANCAKE_MESSAGE_COMMENT_TYPE}:
        return {
            "status": "ignored",
            "reason": "unsupported_message_type",
            "message_mid": message_mid,
            "message_kind": message_kind,
        }

    if _is_pancake_auto_consult_trigger(message_kind):
        return await _process_pancake_auto_consult_trigger(
            normalized,
            message_kind=message_kind,
        )

    if is_customer_comment:
        _prepare_pancake_comment_ai_context(normalized)

    if message_kind in {PANCAKE_MESSAGE_CUSTOMER, PANCAKE_MESSAGE_CUSTOMER_COMMENT}:
        dangerous_keyword_result = _check_pancake_dangerous_keyword_block(
            normalized,
            message_kind=message_kind,
        )
        if dangerous_keyword_result is not None:
            if message_kind == PANCAKE_MESSAGE_CUSTOMER:
                _cancel_pancake_sender_buffer(
                    normalized,
                    reason=str(dangerous_keyword_result.get("reason") or "dangerous_keyword"),
                )
            return dangerous_keyword_result

    if await _is_duplicate_pancake_message(message_mid):
        return {
            "status": "ignored",
            "reason": "duplicate_message_mid",
            "message_mid": message_mid,
            "message_kind": message_kind,
        }

    if not _try_mark_pancake_message_processing(message_mid):
        return {
            "status": "ignored",
            "reason": "duplicate_message_mid_inflight",
            "message_mid": message_mid,
            "message_kind": message_kind,
        }

    try:
        if message_kind == PANCAKE_MESSAGE_ADMIN:
            conversation = await _get_or_create_pancake_admin_conversation(normalized)
            staff_message = await _save_pancake_staff_message(conversation, normalized)
            try:
                buffer_result = _cancel_pancake_sender_buffer(
                    _normalized_for_pancake_admin_customer(normalized),
                    reason="admin_message",
                )
            except ValueError:
                buffer_result = {
                    "cancelled": False,
                    "reason": "missing_admin_customer_id",
                    "message_count": 0,
                    "message_mids": [],
                }
            pause_result = await _pause_pancake_conversation_for_admin_takeover(
                conversation,
                normalized,
            )
            return {
                "status": "ignored",
                "reason": "pancake_admin_message_paused_conversation",
                "conversation_id": str(conversation.id),
                "message_id": str(staff_message.id),
                "message_mid": message_mid,
                "message_kind": message_kind,
                "buffer_result": buffer_result,
                **pause_result,
            }

        conversation = await _get_or_create_pancake_conversation(normalized)
        resume_context = await _resume_pancake_conversation_if_pause_expired_with_snapshot(
            conversation
        )
        _attach_pancake_handover_resume_context(
            conversation=conversation,
            normalized=normalized,
            resume_context=resume_context,
        )

        if await _is_pancake_recent_bot_echo(conversation=conversation, normalized=normalized):
            return {
                "status": "ignored",
                "reason": "pancake_recent_bot_echo",
                "conversation_id": str(conversation.id),
                "message_mid": message_mid,
                "message_kind": message_kind,
            }

        if await _is_pancake_recent_user_duplicate(conversation=conversation, normalized=normalized):
            return {
                "status": "ignored",
                "reason": "pancake_recent_user_duplicate",
                "conversation_id": str(conversation.id),
                "message_mid": message_mid,
                "message_kind": message_kind,
            }

        if is_customer_comment:
            was_ai_initialized = bool(getattr(conversation, "fb_ai_initialized", False))
            normalized["conversation_was_ai_initialized"] = was_ai_initialized
            _prepare_pancake_comment_ai_context(
                normalized,
                initial_product_prompt=not was_ai_initialized,
            )

        user_message = await _save_pancake_user_message(conversation, normalized)
        if bool(_as_dict(normalized.get("handover_resume_context")).get("resumed")):
            await _prepare_pancake_handover_resume_context(
                conversation=conversation,
                normalized=normalized,
                user_message=user_message,
            )
        if _is_pancake_bot_paused(conversation):
            logger.info(
                "PANCAKE_HANDOVER_CONTEXT_SKIPPED conversation_id=%s page_id=%s pancake_conversation_id=%s message_mid=%s sender_id=%s reason=conversation_still_paused message_count=0",
                conversation.id,
                normalized.get("page_id"),
                normalized.get("pancake_conversation_id"),
                message_mid,
                normalized.get("sender_id"),
            )
            conversation.updated_at = now_vn()
            await conversation.save()
            logger.info(
                "PANCAKE_CUSTOMER_MESSAGE_IGNORED_HUMAN_ACTIVE conversation_id=%s sender_id=%s message_mid=%s paused_until=%s",
                conversation.id,
                normalized.get("sender_id"),
                message_mid,
                getattr(conversation, "bot_paused_until", None),
            )
            return {
                "status": "processed",
                "ok": False,
                "reason": "conversation_paused_by_admin",
                "conversation_id": str(conversation.id),
                "message_id": str(user_message.id),
                "message_mid": message_mid,
                "message_kind": message_kind,
                "bot_paused_until": getattr(conversation, "bot_paused_until", None),
            }

        if not _has_pancake_ai_supported_content(normalized):
            unsupported_reason = (
                "missing_public_image_url"
                if _has_pancake_image_attachment(normalized)
                else "unsupported_message_content_type"
            )
            return {
                "status": "processed",
                "ok": False,
                "reason": unsupported_reason,
                "conversation_id": str(conversation.id),
                "message_id": str(user_message.id),
                "message_mid": message_mid,
                "message_kind": message_kind,
            }

        buffer_result = _enqueue_pancake_sender_message_for_ai(
            conversation=conversation,
            normalized=normalized,
            user_message=user_message,
            message_kind=message_kind,
        )
        if bool(buffer_result.get("queued")):
            pending_ad_context_result = await _try_merge_pending_pancake_ad_context_for_sender(
                normalized
            )
            if pending_ad_context_result is not None:
                return pending_ad_context_result
            return {
                "status": "processed",
                "ok": True,
                "reason": buffer_result.get("reason"),
                "conversation_id": str(conversation.id),
                "message_id": str(user_message.id),
                "message_mid": message_mid,
                "message_kind": message_kind,
                "buffer_size": buffer_result.get("buffer_size"),
                "wait_seconds": buffer_result.get("wait_seconds"),
            }

        if is_customer_comment and not _is_pancake_comment_auto_reply_enabled():
            return {
                "status": "processed",
                "ok": False,
                "reason": "pancake_comment_auto_reply_disabled",
                "conversation_id": str(conversation.id),
                "message_id": str(user_message.id),
                "message_mid": message_mid,
                "message_kind": message_kind,
                "comment_message_id": normalized.get("comment_message_id"),
            }

        if is_customer_comment:
            required_comment_fields = (
                ("page_id", "missing_page_id"),
                (
                    "pancake_conversation_id",
                    "missing_pancake_conversation_id",
                ),
                (
                    "comment_message_id",
                    "missing_pancake_comment_message_id",
                ),
            )
            for field_name, missing_reason in required_comment_fields:
                if not str(normalized.get(field_name) or "").strip():
                    return {
                        "status": "processed",
                        "ok": False,
                        "reason": missing_reason,
                        "conversation_id": str(conversation.id),
                        "message_id": str(user_message.id),
                        "message_mid": message_mid,
                        "message_kind": message_kind,
                        "comment_message_id": normalized.get("comment_message_id"),
                    }
            logger.info(
                "PANCAKE_COMMENT_AI_START page_id=%s conversation_id=%s internal_conversation_id=%s comment_message_id=%s message_mid=%s",
                normalized.get("page_id"),
                normalized.get("pancake_conversation_id"),
                conversation.id,
                normalized.get("comment_message_id"),
                message_mid,
            )

        reply = await _generate_pancake_reply(conversation=conversation, normalized=normalized)
        await _save_pancake_handover_context_user_message_meta(
            user_message=user_message,
            normalized=normalized,
        )
        if not bool(reply.get("ok")):
            if is_customer_comment:
                logger.warning(
                    "PANCAKE_COMMENT_AI_FAILED page_id=%s conversation_id=%s internal_conversation_id=%s comment_message_id=%s message_mid=%s reason=%s",
                    normalized.get("page_id"),
                    normalized.get("pancake_conversation_id"),
                    conversation.id,
                    normalized.get("comment_message_id"),
                    message_mid,
                    reply.get("reason"),
                )
            return {
                "status": "processed",
                "ok": False,
                "reason": reply.get("reason"),
                "conversation_id": str(conversation.id),
                "message_id": str(user_message.id),
                "message_mid": message_mid,
                "message_kind": message_kind,
            }

        reply_text = str(reply.get("reply_text") or "").strip()
        if not reply_text:
            if is_customer_comment:
                logger.warning(
                    "PANCAKE_COMMENT_AI_FAILED page_id=%s conversation_id=%s internal_conversation_id=%s comment_message_id=%s message_mid=%s reason=missing_reply_message",
                    normalized.get("page_id"),
                    normalized.get("pancake_conversation_id"),
                    conversation.id,
                    normalized.get("comment_message_id"),
                    message_mid,
                )
            return {
                "status": "processed",
                "ok": False,
                "reason": "missing_reply_message",
                "conversation_id": str(conversation.id),
                "message_id": str(user_message.id),
                "message_mid": message_mid,
                "message_kind": message_kind,
                "pancake_drive_reply": reply.get("pancake_drive_reply"),
                "pancake_drive_image_cache_result": reply.get("pancake_drive_image_cache_result"),
            }
        if is_customer_comment:
            logger.info(
                "PANCAKE_COMMENT_AI_OK page_id=%s conversation_id=%s internal_conversation_id=%s comment_message_id=%s message_mid=%s reply_length=%s",
                normalized.get("page_id"),
                normalized.get("pancake_conversation_id"),
                conversation.id,
                normalized.get("comment_message_id"),
                message_mid,
                len(reply_text),
            )
        action = _resolve_pancake_reply_action(normalized)
        if not action:
            return {
                "status": "processed",
                "ok": False,
                "reason": "unsupported_reply_action",
                "conversation_id": str(conversation.id),
                "message_id": str(user_message.id),
                "message_mid": message_mid,
                "message_kind": message_kind,
            }

        conversation = await _reload_pancake_conversation_for_pause_check(conversation)
        await _resume_pancake_conversation_if_pause_expired(conversation)
        if _is_pancake_bot_paused(conversation):
            if is_customer_comment:
                logger.info(
                    "PANCAKE_COMMENT_REPLY_SUPPRESSED_BY_ADMIN_PAUSE page_id=%s conversation_id=%s internal_conversation_id=%s comment_message_id=%s message_mid=%s paused_until=%s reason=conversation_paused_before_send",
                    normalized.get("page_id"),
                    normalized.get("pancake_conversation_id"),
                    conversation.id,
                    normalized.get("comment_message_id"),
                    message_mid,
                    getattr(conversation, "bot_paused_until", None),
                )
            else:
                logger.info(
                    "PANCAKE_BOT_REPLY_SUPPRESSED_BY_ADMIN_TAKEOVER conversation_id=%s sender_id=%s message_mid=%s paused_until=%s",
                    conversation.id,
                    normalized.get("sender_id"),
                    message_mid,
                    getattr(conversation, "bot_paused_until", None),
                )
            return {
                "status": "processed",
                "ok": False,
                "reason": "conversation_paused_before_send",
                "conversation_id": str(conversation.id),
                "message_id": str(user_message.id),
                "message_mid": message_mid,
                "message_kind": message_kind,
                "bot_paused_until": getattr(conversation, "bot_paused_until", None),
            }

        repeated_bot_reply = await _maybe_handover_pancake_repeated_bot_reply(
            conversation=conversation,
            normalized=normalized,
            reply_text=reply_text,
        )
        if repeated_bot_reply is not None:
            return {
                "status": "processed",
                "ok": False,
                "reason": repeated_bot_reply["reason"],
                "conversation_id": str(conversation.id),
                "message_id": str(user_message.id),
                "message_mid": message_mid,
                "message_kind": message_kind,
                **(
                    {
                        "reply_action": action,
                        "comment_message_id": normalized.get("comment_message_id"),
                    }
                    if is_customer_comment
                    else {}
                ),
                "reply_source": reply.get("source"),
                "bot_paused_until": repeated_bot_reply["handover_result"].get("bot_paused_until"),
                "pancake_drive_reply": reply.get("pancake_drive_reply"),
                "pancake_drive_image_cache_result": reply.get("pancake_drive_image_cache_result"),
                "repeated_bot_reply": repeated_bot_reply,
            }

        if bool(reply.get("ai_quota_fallback")):
            handover_detection = {"detected": False, "reason": "ai_quota_fallback"}
            handover_status_update = {"updated": False, "reason": "ai_quota_fallback"}
        else:
            handover_detection = detect_handover_reply(reply_text)
            handover_status_update = {"updated": False, "reason": "handover_not_detected"}
            if bool(handover_detection.get("detected")):
                handover_status_update = await _update_pancake_handover_conversation_status(
                    conversation=conversation,
                    handover_detection=handover_detection,
                )

        if is_customer_comment:
            logger.info(
                "PANCAKE_COMMENT_REPLY_SEND_START page_id=%s conversation_id=%s internal_conversation_id=%s comment_message_id=%s message_mid=%s reply_length=%s",
                normalized.get("page_id"),
                normalized.get("pancake_conversation_id"),
                conversation.id,
                normalized.get("comment_message_id"),
                message_mid,
                len(reply_text),
            )
            send_result = await send_pancake_comment_reply(
                page_id=str(normalized.get("page_id") or ""),
                conversation_id=str(normalized.get("pancake_conversation_id") or ""),
                comment_message_id=str(normalized.get("comment_message_id") or ""),
                message=reply_text,
            )
            comment_send_log = (
                "PANCAKE_COMMENT_REPLY_SEND_OK"
                if bool(send_result.get("ok"))
                else "PANCAKE_COMMENT_REPLY_SEND_FAILED"
            )
            comment_send_logger = (
                logger.info if bool(send_result.get("ok")) else logger.warning
            )
            comment_send_logger(
                "%s page_id=%s conversation_id=%s internal_conversation_id=%s comment_message_id=%s message_mid=%s status_code=%s reason=%s",
                comment_send_log,
                normalized.get("page_id"),
                normalized.get("pancake_conversation_id"),
                conversation.id,
                normalized.get("comment_message_id"),
                message_mid,
                send_result.get("status_code"),
                send_result.get("reason"),
            )
        else:
            send_result = await send_pancake_reply(
                page_id=str(normalized.get("page_id") or ""),
                conversation_id=str(normalized.get("pancake_conversation_id") or ""),
                message=reply_text,
                action=action,
            )
        drive_images = _extract_pancake_local_drive_images(reply)
        cache_result = reply.get("pancake_drive_image_cache_result")
        raw_cache_images = cache_result.get("images") if isinstance(cache_result, dict) else []
        raw_cache_errors = cache_result.get("errors") if isinstance(cache_result, dict) else []
        logger.info(
            "PANCAKE_DRIVE_IMAGES_EXTRACTED page_id=%s conversation_id=%s message_mid=%s text_send_ok=%s text_status_code=%s text_reason=%s cache_image_count=%s cache_error_count=%s sendable_image_count=%s",
            normalized.get("page_id"),
            normalized.get("pancake_conversation_id"),
            message_mid,
            bool(send_result.get("ok")),
            send_result.get("status_code"),
            send_result.get("reason"),
            len(raw_cache_images) if isinstance(raw_cache_images, list) else 0,
            len(raw_cache_errors) if isinstance(raw_cache_errors, list) else 0,
            len(drive_images),
        )
        image_send_result: dict[str, Any] | None = None
        if bool(send_result.get("ok")) and drive_images:
            image_send_result = await _send_pancake_drive_images(
                normalized=normalized,
                drive_images=drive_images,
                action=action,
            )
        elif drive_images:
            logger.warning(
                "PANCAKE_DRIVE_IMAGE_SEND_SKIPPED page_id=%s conversation_id=%s message_mid=%s reason=text_reply_failed_before_image_send text_reason=%s",
                normalized.get("page_id"),
                normalized.get("pancake_conversation_id"),
                message_mid,
                send_result.get("reason"),
            )
            image_send_result = {
                "ok": False,
                "reason": "text_reply_failed_before_image_send",
                "content_ids": [],
                "upload_results": [],
            }

        ai_quota_handover_result = await _maybe_pause_pancake_conversation_for_ai_quota_handover(
            conversation=conversation,
            normalized=normalized,
            reply=reply,
        )

        bot_extra_meta = {
            "pancake_drive_reply": reply.get("pancake_drive_reply"),
            "pancake_drive_image_cache_result": reply.get("pancake_drive_image_cache_result"),
            "handover_detection": handover_detection,
            "handover_status_update": handover_status_update,
        }
        if reply.get("handover_context"):
            bot_extra_meta["handover_context"] = reply.get("handover_context")
        if is_customer_comment:
            bot_extra_meta.update(
                {
                    "reply_action": PANCAKE_REPLY_COMMENT_ACTION,
                    "comment_message_id": normalized.get("comment_message_id"),
                }
            )
        if image_send_result is not None:
            bot_extra_meta["pancake_drive_image_send_result"] = image_send_result
        if ai_quota_handover_result is not None:
            bot_extra_meta["ai_quota_handover_result"] = ai_quota_handover_result

        bot_message = await _save_pancake_bot_message(
            conversation,
            normalized,
            reply_text=reply_text,
            send_result=send_result,
            extra_meta=bot_extra_meta,
        )
        conversation.updated_at = now_vn()
        await conversation.save()

        return {
            "status": "processed",
            "ok": bool(send_result.get("ok")),
            "reason": None if bool(send_result.get("ok")) else send_result.get("reason"),
            "conversation_id": str(conversation.id),
            "message_id": str(user_message.id),
            "bot_message_id": str(bot_message.id),
            "message_mid": message_mid,
            "message_kind": message_kind,
            **(
                {
                    "reply_action": action,
                    "comment_message_id": normalized.get("comment_message_id"),
                }
                if is_customer_comment
                else {}
            ),
            "reply_text": reply_text,
            "reply_source": reply.get("source"),
            "reply_result": send_result,
            "pancake_drive_reply": reply.get("pancake_drive_reply"),
            "pancake_drive_image_cache_result": reply.get("pancake_drive_image_cache_result"),
            "pancake_drive_image_send_result": image_send_result,
            "handover_detection": handover_detection,
            "handover_status_update": handover_status_update,
            "ai_quota_handover_result": ai_quota_handover_result,
        }
    finally:
        _finalize_pancake_message_processing(message_mid)


@router.post("/webhook")
async def receive_webhook(request: Request):
    client_ip = request.client.host if request.client else "unknown"
    request_path = request.url.path if request.url else "/api/v1/pancake/webhook"

    body = await request.body()
    if not body:
        logger.info(
            "PANCAKE_WEBHOOK_REQUEST_EMPTY client_ip=%s path=%s",
            client_ip,
            request_path,
        )
        return {"status": "ignored", "reason": "empty_body"}

    logger.info(
        "PANCAKE_WEBHOOK_RAW_PAYLOAD client_ip=%s path=%s body_bytes=%s",
        client_ip,
        request_path,
        len(body),
    )

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return {"status": "ignored", "reason": "invalid_json"}

    if not isinstance(payload, dict):
        return {"status": "ignored", "reason": "invalid_payload_type"}

    logger.info(
        "PANCAKE_WEBHOOK_RECEIVED_DETAIL client_ip=%s path=%s detail=%s",
        client_ip,
        request_path,
        _json_log_payload(_pancake_webhook_debug_payload(payload)),
    )

    try:
        normalize_result = normalize_pancake_payload(payload)
    except Exception as exc:
        logger.exception(
            "PANCAKE_WEBHOOK_NORMALIZE_FAILED client_ip=%s path=%s error=%s",
            client_ip,
            request_path,
            exc,
        )
        return {"status": "ignored", "reason": "normalization_failed"}
    normalized = normalize_result.get("data") if isinstance(normalize_result.get("data"), dict) else {}
    if normalized:
        _prepare_pancake_comment_ai_context(normalized)
    reason = normalize_result.get("reason")
    logger.info(
        "PANCAKE_WEBHOOK_NORMALIZED_DETAIL reason=%s detail=%s",
        reason,
        _json_log_payload(
            _public_normalized_message(
                normalized,
                include_text=False,
                include_attachments=False,
            )
        ),
    )
    _record_pancake_public_api_image_echo(normalized)

    if not bool(normalize_result.get("ok")):
        logger.info(
            "PANCAKE_WEBHOOK_IGNORED reason=%s event_type=%s page_id=%s message_mid=%s",
            reason,
            normalized.get("event_type"),
            normalized.get("page_id"),
            normalized.get("message_mid"),
        )
        return {
            "status": "ignored",
            "reason": reason,
            "event_type": normalized.get("event_type"),
            "page_id": normalized.get("page_id"),
            "message_mid": normalized.get("message_mid"),
        }

    try:
        process_result = await _process_normalized_message(normalized)
    except Exception as exc:
        logger.exception(
            "PANCAKE_WEBHOOK_PROCESS_FAILED page_id=%s sender_id=%s message_mid=%s error=%s",
            normalized.get("page_id"),
            normalized.get("sender_id"),
            normalized.get("message_mid"),
            exc,
        )
        return {
            "status": "ignored",
            "reason": "processing_failed",
            "message_mid": normalized.get("message_mid"),
        }
    logger.info(
        "PANCAKE_WEBHOOK_PROCESSED status=%s reason=%s message_kind=%s page_id=%s sender_id=%s message_mid=%s",
        process_result.get("status"),
        process_result.get("reason"),
        process_result.get("message_kind"),
        normalized.get("page_id"),
        normalized.get("sender_id"),
        normalized.get("message_mid"),
    )
    if process_result.get("reason") in {
        PANCAKE_DANGEROUS_KEYWORD_BLOCKED_REASON,
        PANCAKE_DANGEROUS_KEYWORD_UNAVAILABLE_REASON,
    }:
        return process_result

    return {
        **process_result,
        "normalized_message": _public_normalized_message(normalized),
    }
