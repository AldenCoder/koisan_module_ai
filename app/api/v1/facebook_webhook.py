from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query, Request

from app.api.dependencies.time import VN_TZ, now_vn
from app.core.config import settings
from app.models.conversations import Conversation, ConversationStatus
from app.models.messages import Message
from app.services.conversation_service import update_conversation_crud_service
from app.services.facebook_message_service import (
    MAX_FACEBOOK_PRODUCT_IMAGES,
    send_facebook_text_and_images,
)
from app.services.facebook_handover_detection_service import detect_handover_reply
from app.services.google_drive_image_service import (
    GoogleDriveImageService,
    extract_drive_folder_urls_from_text,
    split_text_and_drive_folder_urls,
)
from app.services.ai_version_context_service import (
    build_versioned_ai_user,
    get_system_version_for_new_conversation,
    parse_version,
    prepare_ai_version_for_customer_message,
    reset_ai_initialization_for_version_session,
)
from logs.logging_config import logger

router = APIRouter()

_latest_message_lock = Lock()
_latest_message: Dict[str, Any] = {}
_processing_message_mid_lock = Lock()
_processing_message_mids: set[str] = set()
_sender_buffer_lock = Lock()
_sender_buffers: Dict[str, Dict[str, Any]] = {}

FB_AI_INIT_MESSAGE = (
    "Hãy đọc file markdown tại /data/workspace/koisan_chatbot_brain/SKILL.md và bắt đầu koisan chatbot."
)
FB_AI_TEST_MODE_NOTE = "hãy nhớ bạn đang trong chế độ koisan chatbot"
FB_AI_FIXED_TIMEOUT_SECONDS = 60.0
FACEBOOK_MESSAGE_CUSTOMER = "customer_message"
FACEBOOK_MESSAGE_BOT_ECHO = "bot_echo"
FACEBOOK_MESSAGE_ADMIN = "admin_message"
FACEBOOK_SUPPRESSED_BY_PAUSE_REASONS = {
    "conversation_paused_by_admin",
    "conversation_paused_before_send",
}
FACEBOOK_NON_RETRYABLE_FAILURE_REASONS = {
    "facebook_reply_non_retryable",
}
DRIVE_FOLDER_URL_RESPONSE_KEYS = {
    "drive_folder_url",
    "drive_folder_urls",
    "drive_folder_link",
    "drive_folder_links",
    "drive_url",
    "drive_urls",
    "drive_link",
    "drive_links",
    "lookbook_url",
    "lookbook_urls",
    "lookbook_link",
    "lookbook_links",
}
IMAGE_LIMIT_RESPONSE_KEYS = {
    "image_limit",
    "imageLimit",
    "max_images",
    "maxImages",
    "limit_images",
    "limitImages",
}


@dataclass(frozen=True)
class PreparedFacebookReply:
    text: str
    image_urls: list[str]
    drive_folder_urls: list[str]
    drive_folder_error_count: int = 0


def _get_verify_token() -> Optional[str]:
    # Prefer explicit webhook token; fallback to page access token for quick setup.
    return settings.fb_webhook_verify_token or settings.fb_page_access_token


def _get_sender_buffer_seconds() -> int:
    seconds = int(getattr(settings, "fb_sender_buffer_seconds", 15) or 15)
    return max(1, seconds)


def _get_fb_ai_chat_url() -> str:
    return (getattr(settings, "fb_ai_chat_url", "") or "").strip()


def _get_fb_ai_bearer_token() -> str:
    return (getattr(settings, "fb_ai_bearer_token", "") or "").strip()


def _get_fb_ai_retry_attempts() -> int:
    raw = getattr(settings, "fb_ai_retry_attempts", 3)
    try:
        value = int(raw or 3)
    except (TypeError, ValueError):
        value = 3
    return max(1, value)


def _get_fb_ai_retry_backoff_seconds() -> float:
    raw = getattr(settings, "fb_ai_retry_backoff_seconds", 1.0)
    try:
        value = float(raw or 1.0)
    except (TypeError, ValueError):
        value = 1.0
    return max(0.1, value)


def _get_fb_ai_requeue_delay_seconds() -> int:
    raw = getattr(settings, "fb_ai_requeue_delay_seconds", 10)
    try:
        value = int(raw or 10)
    except (TypeError, ValueError):
        value = 10
    return max(1, value)


def _get_fb_admin_takeover_pause_minutes() -> int:
    raw = getattr(settings, "fb_admin_takeover_pause_minutes", 10)
    try:
        value = int(raw or 10)
    except (TypeError, ValueError):
        value = 10
    return max(1, value)


def _to_vn_aware_datetime(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).astimezone(VN_TZ)
    return value.astimezone(VN_TZ)


def _mask_token_for_log(token: str) -> str:
    normalized = str(token or "")
    if not normalized:
        return ""
    if len(normalized) <= 10:
        return "*" * len(normalized)
    return f"{normalized[:4]}...{normalized[-4:]}"


def _preview_text(value: Any, *, limit: int = 500) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...(truncated)"


def _build_http_response_log_payload(response: httpx.Response) -> Dict[str, Any]:
    try:
        body_text = response.text
    except Exception as exc:
        body_text = f"<failed to read response.text: {exc}>"

    try:
        parsed_json = response.json()
    except Exception:
        parsed_json = None

    try:
        elapsed_seconds = response.elapsed.total_seconds()
    except Exception:
        elapsed_seconds = None

    try:
        header_items = list(response.headers.multi_items())
    except Exception:
        header_items = []

    try:
        cookies = dict(response.cookies)
    except Exception:
        cookies = {}

    return {
        "status_code": response.status_code,
        "reason_phrase": response.reason_phrase,
        "url": str(response.url),
        "http_version": response.http_version,
        "headers": header_items,
        "cookies": cookies,
        "encoding": response.encoding,
        "elapsed_seconds": elapsed_seconds,
        "body_text": body_text,
        "json": parsed_json,
    }


def _has_non_retryable_facebook_error(value: Any) -> bool:
    if isinstance(value, dict):
        if bool(value.get("non_retryable")):
            return True
        return any(_has_non_retryable_facebook_error(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_non_retryable_facebook_error(item) for item in value)
    return False


def _extract_text_from_ai_content(content: Any) -> Optional[str]:
    if content is None:
        return None
    if isinstance(content, str):
        return content if content else None
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                if item:
                    parts.append(item)
                continue
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str) and text:
                parts.append(text)
                continue
            nested_content = item.get("content")
            nested_text = _extract_text_from_ai_content(nested_content)
            if nested_text:
                parts.append(nested_text)
        if parts:
            return "".join(parts)
    return None


def _extract_text_from_ai_response(data: Any) -> Optional[str]:
    if data is None:
        return None
    if isinstance(data, str):
        return data if data else None
    if isinstance(data, list):
        for item in data:
            resolved = _extract_text_from_ai_response(item)
            if resolved:
                return resolved
        return None
    if isinstance(data, dict):
        choices = data.get("choices")
        if isinstance(choices, list):
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                message = choice.get("message")
                if isinstance(message, dict):
                    content = _extract_text_from_ai_content(message.get("content"))
                    if content:
                        return content
                    nested = _extract_text_from_ai_response(message)
                    if nested:
                        return nested
                delta = choice.get("delta")
                if isinstance(delta, dict):
                    delta_content = _extract_text_from_ai_content(delta.get("content"))
                    if delta_content:
                        return delta_content
        for key in [
            "assistant_message",
            "answer",
            "message",
            "response",
            "text",
            "content",
            "output",
            "result",
            "data",
        ]:
            if key in data:
                resolved = _extract_text_from_ai_response(data.get(key))
                if resolved:
                    return resolved
    return None


def _merge_unique_strings(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for raw_value in group:
            value = str(raw_value or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            merged.append(value)
    return merged


def _extract_drive_folder_urls_from_ai_response(data: Any) -> list[str]:
    urls: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, str):
            urls.extend(extract_drive_folder_urls_from_text(value))
            return
        if isinstance(value, list):
            for item in value:
                collect(item)
            return
        if isinstance(value, dict):
            for nested_value in value.values():
                collect(nested_value)

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, nested_value in value.items():
                if str(key) in DRIVE_FOLDER_URL_RESPONSE_KEYS:
                    collect(nested_value)
                elif isinstance(nested_value, (dict, list)):
                    visit(nested_value)
            return
        if isinstance(value, list):
            for item in value:
                visit(item)

    visit(data)
    return _merge_unique_strings(urls)


def _extract_image_limit_from_ai_response(data: Any) -> Optional[int]:
    def visit(value: Any) -> Optional[int]:
        if isinstance(value, dict):
            for key, nested_value in value.items():
                if str(key) in IMAGE_LIMIT_RESPONSE_KEYS:
                    try:
                        return int(nested_value)
                    except (TypeError, ValueError):
                        return None
                if isinstance(nested_value, (dict, list)):
                    nested_result = visit(nested_value)
                    if nested_result is not None:
                        return nested_result
            return None
        if isinstance(value, list):
            for item in value:
                nested_result = visit(item)
                if nested_result is not None:
                    return nested_result
        return None

    raw_limit = visit(data)
    if raw_limit is None:
        return None
    return max(0, min(raw_limit, MAX_FACEBOOK_PRODUCT_IMAGES))


async def _prepare_facebook_reply_from_ai_response(
    *,
    response_data: Any,
    assistant_message: str,
) -> PreparedFacebookReply:
    split_result = split_text_and_drive_folder_urls(assistant_message)
    drive_folder_urls = _merge_unique_strings(
        _extract_drive_folder_urls_from_ai_response(response_data),
        split_result.drive_folder_urls,
    )
    image_limit = _extract_image_limit_from_ai_response(response_data)
    if image_limit is None:
        image_limit = MAX_FACEBOOK_PRODUCT_IMAGES

    image_urls: list[str] = []
    drive_folder_error_count = 0
    if drive_folder_urls and image_limit > 0:
        folder_results = await GoogleDriveImageService().lookup_folder_images(drive_folder_urls)
        drive_folder_error_count = sum(1 for folder in folder_results if folder.error)
        seen_image_urls: set[str] = set()

        for folder in folder_results:
            for image in folder.images:
                if image.imageUrl in seen_image_urls:
                    continue
                seen_image_urls.add(image.imageUrl)
                image_urls.append(image.imageUrl)
                if len(image_urls) >= image_limit:
                    break
            if len(image_urls) >= image_limit:
                break

        logger.info(
            "FB_AI_DRIVE_IMAGES_PREPARED drive_folder_count=%s folder_error_count=%s image_count=%s image_limit=%s",
            len(drive_folder_urls),
            drive_folder_error_count,
            len(image_urls),
            image_limit,
        )

    return PreparedFacebookReply(
        text=split_result.text,
        image_urls=image_urls,
        drive_folder_urls=drive_folder_urls,
        drive_folder_error_count=drive_folder_error_count,
    )


async def _update_handover_conversation_status(
    *,
    conversation: Conversation,
    handover_detection: Dict[str, Any],
) -> Dict[str, Any]:
    if not bool(handover_detection.get("detected")):
        return {"updated": False, "reason": "handover_not_detected"}

    conversation_id = str(getattr(conversation, "id", "") or "").strip()
    if not conversation_id:
        logger.warning(
            "FB_HANDOVER_STATUS_UPDATE_SKIPPED reason=handover_missing_conversation_id matched_pattern=%s",
            handover_detection.get("matched_pattern"),
        )
        return {"updated": False, "reason": "handover_missing_conversation_id"}

    try:
        updated_conversation = await update_conversation_crud_service(
            conversation_id,
            status=ConversationStatus.HANDOVER,
        )
    except Exception as exc:
        logger.exception(
            "FB_HANDOVER_STATUS_UPDATE_FAILED conversation_id=%s matched_pattern=%s error=%s",
            conversation_id,
            handover_detection.get("matched_pattern"),
            exc,
        )
        return {
            "updated": False,
            "reason": "handover_status_update_failed",
            "error": str(exc),
        }

    if updated_conversation is None:
        logger.warning(
            "FB_HANDOVER_STATUS_UPDATE_SKIPPED reason=handover_conversation_not_found conversation_id=%s matched_pattern=%s",
            conversation_id,
            handover_detection.get("matched_pattern"),
        )
        return {"updated": False, "reason": "handover_conversation_not_found"}

    conversation.status = ConversationStatus.HANDOVER
    logger.info(
        "FB_HANDOVER_STATUS_UPDATED conversation_id=%s matched_pattern=%s status=%s",
        conversation_id,
        handover_detection.get("matched_pattern"),
        ConversationStatus.HANDOVER.value,
    )
    return {
        "updated": True,
        "conversation_id": conversation_id,
        "status": ConversationStatus.HANDOVER.value,
    }


def _build_ai_test_mode_note(*, conversation_id: Optional[Any] = None) -> str:
    normalized_conversation_id = str(conversation_id or "").strip()
    if not normalized_conversation_id:
        return FB_AI_TEST_MODE_NOTE
    return f"{FB_AI_TEST_MODE_NOTE}, conversation_id: {normalized_conversation_id}"


def _build_ai_chat_payload(
    *,
    user: str,
    content: str,
    conversation_id: Optional[Any] = None,
) -> Dict[str, Any]:
    normalized_content = str(content)
    if normalized_content == FB_AI_INIT_MESSAGE:
        content_with_test_note = normalized_content
    else:
        content_with_test_note = f"{normalized_content}\n\n{_build_ai_test_mode_note(conversation_id=conversation_id)}"
    return {
        "user": user,
        "messages": [
            {
                "role": "user",
                "content": content_with_test_note,
            }
        ],
        "stream": False,
    }


async def _post_ai_chat_with_retry(
    *,
    payload: Dict[str, Any],
    sender_id: str,
    message_mid: Optional[str],
    purpose: str,
) -> Dict[str, Any]:
    chat_url = _get_fb_ai_chat_url()
    if not chat_url:
        logger.error(
            "FB_AI_CALL_SKIPPED missing_fb_ai_chat_url sender_id=%s message_mid=%s purpose=%s",
            sender_id,
            message_mid,
            purpose,
        )
        return {"ok": False, "reason": "missing_fb_ai_chat_url"}

    access_token = _get_fb_ai_bearer_token()
    if not access_token:
        logger.error(
            "FB_AI_CALL_SKIPPED missing_fb_ai_bearer_token sender_id=%s message_mid=%s purpose=%s",
            sender_id,
            message_mid,
            purpose,
        )
        return {"ok": False, "reason": "missing_fb_ai_bearer_token"}

    attempts = _get_fb_ai_retry_attempts()
    timeout_seconds = FB_AI_FIXED_TIMEOUT_SECONDS
    backoff_seconds = _get_fb_ai_retry_backoff_seconds()
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    last_status_code: Optional[int] = None
    last_error: Optional[str] = None

    for attempt in range(1, attempts + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(chat_url, headers=headers, json=payload)

            logger.info(
                "FB_AI_RESPONSE_RECEIVED sender_id=%s message_mid=%s purpose=%s attempt=%s response=%s",
                sender_id,
                message_mid,
                purpose,
                attempt,
                json.dumps(
                    _build_http_response_log_payload(response),
                    ensure_ascii=False,
                    default=str,
                ),
            )

            if response.status_code < 400:
                try:
                    response_data = response.json()
                except Exception:
                    response_data = response.text
                logger.info(
                    "FB_AI_CALL_OK sender_id=%s message_mid=%s purpose=%s attempt=%s status_code=%s token=%s",
                    sender_id,
                    message_mid,
                    purpose,
                    attempt,
                    response.status_code,
                    _mask_token_for_log(access_token),
                )
                return {
                    "ok": True,
                    "status_code": response.status_code,
                    "response_data": response_data,
                }

            last_status_code = response.status_code
            last_error = response.text
            logger.warning(
                "FB_AI_CALL_HTTP_ERROR sender_id=%s message_mid=%s purpose=%s attempt=%s status_code=%s response=%s",
                sender_id,
                message_mid,
                purpose,
                attempt,
                response.status_code,
                _preview_text(response.text),
            )
        except Exception as exc:
            last_error = str(exc).strip() or repr(exc)
            logger.exception(
                "FB_AI_CALL_EXCEPTION sender_id=%s message_mid=%s purpose=%s attempt=%s error=%s",
                sender_id,
                message_mid,
                purpose,
                attempt,
                exc,
            )

        if attempt < attempts:
            delay = backoff_seconds * (2 ** (attempt - 1))
            await asyncio.sleep(delay)

    return {
        "ok": False,
        "reason": "ai_chat_http_error" if last_status_code is not None else "ai_chat_request_failed",
        "status_code": last_status_code,
        "error": last_error,
    }


def _classify_facebook_message(latest: Dict[str, Any]) -> str:
    if not bool(latest.get("is_echo")):
        return FACEBOOK_MESSAGE_CUSTOMER

    metadata = str(latest.get("metadata") or "").strip()
    if metadata.startswith("source_mid:"):
        return FACEBOOK_MESSAGE_BOT_ECHO

    return FACEBOOK_MESSAGE_ADMIN


def _is_bot_paused(conversation: Optional[Conversation], current_time: Optional[datetime] = None) -> bool:
    if conversation is None:
        return False

    paused_until = _to_vn_aware_datetime(getattr(conversation, "bot_paused_until", None))
    if paused_until is None:
        return False

    now_value = _to_vn_aware_datetime(current_time) or now_vn()
    return now_value < paused_until


async def _resume_conversation_if_pause_expired(
    conversation: Conversation,
    current_time: Optional[datetime] = None,
) -> bool:
    paused_until = _to_vn_aware_datetime(getattr(conversation, "bot_paused_until", None))
    if paused_until is None:
        return False

    now_value = _to_vn_aware_datetime(current_time) or now_vn()
    if now_value < paused_until:
        return False

    conversation.bot_paused_until = None
    conversation.bot_paused_at = None
    conversation.bot_paused_reason = None
    conversation.bot_paused_by = None
    await conversation.save()
    logger.info(
        "FB_CONVERSATION_ADMIN_PAUSE_EXPIRED conversation_id=%s expired_at=%s",
        conversation.id,
        paused_until.isoformat(),
    )
    return True


async def _get_or_create_sender_conversation(latest: Dict[str, Any]) -> Conversation:
    sender_id = str(latest.get("sender_id") or "").strip()
    if not sender_id:
        raise ValueError("Missing sender_id")

    conversation = await Conversation.find(Conversation.customer_id == sender_id).sort(-Conversation.updated_at).first_or_none()

    channel = str(latest.get("page_name") or latest.get("page_id") or "").strip() or None
    sender_name = str(latest.get("sender_name") or "").strip() or None

    if conversation is None:
        conversation = Conversation(
            channel=channel,
            customer_name=sender_name,
            customer_id=sender_id,
            is_active=True,
            version=get_system_version_for_new_conversation(),
            created_at=now_vn(),
            updated_at=now_vn(),
        )
        await conversation.insert()
        logger.info(
            "FB_CONVERSATION_CREATED sender_id=%s conversation_id=%s",
            sender_id,
            conversation.id,
        )
        return conversation

    has_updates = False
    if channel and conversation.channel != channel:
        conversation.channel = channel
        has_updates = True
    if sender_name and conversation.customer_name != sender_name:
        conversation.customer_name = sender_name
        has_updates = True
    if not conversation.is_active:
        conversation.is_active = True
        has_updates = True

    if has_updates:
        conversation.updated_at = now_vn()
        await conversation.save()

    return conversation


async def _get_or_create_conversation_from_admin_echo(latest: Dict[str, Any]) -> Conversation:
    customer_id = str(latest.get("recipient_id") or "").strip()
    if not customer_id:
        raise ValueError("Missing recipient_id for admin echo")

    conversation = await Conversation.find(
        Conversation.customer_id == customer_id
    ).sort(-Conversation.updated_at).first_or_none()

    if conversation is None:
        channel = str(latest.get("page_name") or latest.get("page_id") or "").strip() or None
        conversation = Conversation(
            channel=channel,
            customer_name=None,
            customer_id=customer_id,
            is_active=True,
            version=get_system_version_for_new_conversation(),
            created_at=now_vn(),
            updated_at=now_vn(),
        )
        await conversation.insert()
        logger.info(
            "FB_CONVERSATION_CREATED_FROM_ADMIN_ECHO customer_id=%s conversation_id=%s",
            customer_id,
            conversation.id,
        )
        return conversation

    return conversation


async def _pause_conversation_for_admin_takeover(
    conversation: Conversation,
    latest: Dict[str, Any],
) -> Dict[str, Any]:
    paused_at = now_vn()
    paused_until = paused_at + timedelta(minutes=_get_fb_admin_takeover_pause_minutes())
    paused_by = str(latest.get("sender_id") or latest.get("page_id") or "").strip() or None

    conversation.bot_paused_at = paused_at
    conversation.bot_paused_until = paused_until
    conversation.bot_paused_reason = "admin_message"
    conversation.bot_paused_by = paused_by
    await conversation.save()

    logger.info(
        "FB_CONVERSATION_PAUSED_BY_ADMIN conversation_id=%s customer_id=%s paused_until=%s message_mid=%s",
        conversation.id,
        conversation.customer_id,
        paused_until.isoformat(),
        latest.get("message_mid"),
    )
    return {
        "conversation_id": str(conversation.id),
        "customer_id": conversation.customer_id,
        "bot_paused_until": paused_until,
    }


async def _save_admin_message(conversation: Conversation, latest: Dict[str, Any]) -> Dict[str, Any]:
    message_mid = str(latest.get("message_mid") or "").strip() or None
    if message_mid:
        try:
            existing_message = await Message.find_one(Message.message_mid == message_mid)
        except Exception:
            existing_message = None
        if existing_message:
            return {"saved": False, "reason": "duplicate_message_mid"}

    admin_message = Message(
        conversation_id=conversation.id,
        message_mid=message_mid,
        role="staff",
        content=str(latest.get("text") or ""),
        meta={
            "source": "facebook_webhook_admin_echo",
            "page_id": latest.get("page_id"),
            "customer_id": latest.get("recipient_id"),
            "metadata": latest.get("metadata"),
            "app_id": latest.get("app_id"),
            "timestamp": latest.get("timestamp"),
        },
        created_at=now_vn(),
        updated_at=now_vn(),
    )
    await admin_message.insert()
    return {"saved": True, "message_id": str(admin_message.id)}


async def _ensure_sender_initialized(
    *,
    latest: Dict[str, Any],
    conversation: Conversation,
    ai_user: Optional[str] = None,
) -> Dict[str, Any]:
    if bool(getattr(conversation, "fb_ai_initialized", False)):
        return {"ok": True, "initialized": True, "reason": "already_initialized"}

    sender_id = str(latest.get("sender_id") or "").strip()
    normalized_ai_user = str(ai_user or sender_id).strip()
    message_mid = str(latest.get("message_mid") or "").strip() or None
    init_payload = _build_ai_chat_payload(user=normalized_ai_user, content=FB_AI_INIT_MESSAGE)

    init_result = await _post_ai_chat_with_retry(
        payload=init_payload,
        sender_id=normalized_ai_user,
        message_mid=message_mid,
        purpose="init",
    )
    if not bool(init_result.get("ok")):
        logger.error(
            "FB_AI_INIT_FAILED sender_id=%s message_mid=%s reason=%s status_code=%s error=%s",
            normalized_ai_user,
            message_mid,
            init_result.get("reason"),
            init_result.get("status_code"),
            _preview_text(init_result.get("error")),
        )
        return {"ok": False, "reason": "init_failed", "init_result": init_result}

    conversation.fb_ai_initialized = True
    conversation.fb_ai_initialized_at = now_vn()
    conversation.updated_at = now_vn()
    await conversation.save()

    logger.info(
        "FB_AI_INIT_COMPLETED sender_id=%s conversation_id=%s message_mid=%s",
        normalized_ai_user,
        conversation.id,
        message_mid,
    )
    return {"ok": True, "initialized": True, "reason": "initialized_now"}


async def _prepare_versioned_ai_session(
    *,
    latest: Dict[str, Any],
    conversation: Conversation,
    target_version: str,
) -> Dict[str, Any]:
    sender_id = str(latest.get("sender_id") or "").strip()
    message_mid = str(latest.get("message_mid") or "").strip() or None
    try:
        normalized_version = parse_version(target_version).normalized
        ai_user = build_versioned_ai_user(sender_id, normalized_version)
    except ValueError as exc:
        logger.error(
            "FB_AI_VERSION_SESSION_PREPARE_FAILED sender_id=%s conversation_id=%s message_mid=%s target_version=%s reason=%s",
            sender_id,
            getattr(conversation, "id", None),
            message_mid,
            target_version,
            exc,
        )
        return {
            "ok": False,
            "reason": "invalid_ai_version_session",
            "error": str(exc),
        }

    try:
        await reset_ai_initialization_for_version_session(conversation)
    except Exception as exc:
        logger.exception(
            "FB_AI_VERSION_INIT_STATE_RESET_FAILED sender_id=%s conversation_id=%s message_mid=%s target_version=%s error=%s",
            sender_id,
            getattr(conversation, "id", None),
            message_mid,
            normalized_version,
            exc,
        )
        return {
            "ok": False,
            "reason": "ai_version_init_state_reset_failed",
            "ai_user": ai_user,
            "version": normalized_version,
            "error": str(exc),
        }

    init_result = await _ensure_sender_initialized(
        latest=latest,
        conversation=conversation,
        ai_user=ai_user,
    )
    if not bool(init_result.get("ok")):
        return {
            "ok": False,
            "reason": "ai_version_init_failed",
            "ai_user": ai_user,
            "version": normalized_version,
            "init_result": init_result,
        }

    return {
        "ok": True,
        "reason": "ai_version_session_initialized",
        "ai_user": ai_user,
        "version": normalized_version,
        "init_result": init_result,
    }


async def _save_forwarded_messages(
    *,
    conversation: Conversation,
    latest: Dict[str, Any],
    assistant_message: str,
) -> None:
    message_mid = str(latest.get("message_mid") or "").strip() or None
    sender_id = str(latest.get("sender_id") or "").strip()
    page_id = str(latest.get("page_id") or "").strip()
    user_text = latest.get("text")
    if user_text is None:
        user_text = ""

    user_message = Message(
        conversation_id=conversation.id,
        message_mid=message_mid,
        role="user",
        content=str(user_text),
        meta={
            "source": "facebook_webhook_ai_forward",
            "sender_id": sender_id,
            "page_id": page_id,
            "timestamp": latest.get("timestamp"),
            "metadata": latest.get("metadata"),
            "app_id": latest.get("app_id"),
        },
        created_at=now_vn(),
        updated_at=now_vn(),
    )
    await user_message.insert()

    bot_message = Message(
        conversation_id=conversation.id,
        message_mid=None,
        role="bot",
        content=assistant_message,
        meta={
            "source": "facebook_webhook_ai_forward",
            "reply_to_message_mid": message_mid,
            "sender_id": sender_id,
            "page_id": page_id,
            "timestamp": latest.get("timestamp"),
            "source_metadata": latest.get("metadata"),
            "source_app_id": latest.get("app_id"),
        },
        created_at=now_vn(),
        updated_at=now_vn(),
    )
    await bot_message.insert()

    conversation.updated_at = now_vn()
    await conversation.save()


def _finalize_buffered_message_mids(message_mids: list[str]) -> None:
    with _processing_message_mid_lock:
        for mid in message_mids:
            if mid:
                _processing_message_mids.discard(mid)


def _cancel_sender_buffer(sender_id: str) -> Dict[str, Any]:
    normalized_sender_id = str(sender_id or "").strip()
    if not normalized_sender_id:
        return {"cancelled": False, "message_count": 0, "message_mids": []}

    with _sender_buffer_lock:
        sender_state = _sender_buffers.pop(normalized_sender_id, None)

    if not sender_state:
        return {"cancelled": False, "message_count": 0, "message_mids": []}

    task = sender_state.get("task")
    if task and not task.done():
        task.cancel()

    messages = list(sender_state.get("messages") or [])
    message_mids = [
        str(item.get("message_mid") or "").strip()
        for item in messages
        if isinstance(item, dict) and str(item.get("message_mid") or "").strip()
    ]
    _finalize_buffered_message_mids(message_mids)

    logger.info(
        "FB_ADMIN_TAKEOVER_CANCELLED_SENDER_BUFFER sender_id=%s message_count=%s",
        normalized_sender_id,
        len(messages),
    )
    return {
        "cancelled": True,
        "message_count": len(messages),
        "message_mids": message_mids,
    }


async def _handle_admin_message(latest: Dict[str, Any]) -> Dict[str, Any]:
    logger.info(
        "FB_WEBHOOK_ADMIN_MESSAGE_DETECTED page_id=%s recipient_id=%s message_mid=%s",
        latest.get("page_id"),
        latest.get("recipient_id"),
        latest.get("message_mid"),
    )
    conversation = await _get_or_create_conversation_from_admin_echo(latest)
    pause_result = await _pause_conversation_for_admin_takeover(conversation, latest)
    message_result = await _save_admin_message(conversation, latest)
    buffer_result = _cancel_sender_buffer(str(latest.get("recipient_id") or ""))

    return {
        **pause_result,
        "message_result": message_result,
        "buffer_result": buffer_result,
    }


async def _ensure_customer_message_can_enqueue(latest: Dict[str, Any]) -> Dict[str, Any]:
    conversation = await _get_or_create_sender_conversation(latest)
    resumed = await _resume_conversation_if_pause_expired(conversation)
    if _is_bot_paused(conversation):
        logger.info(
            "FB_CUSTOMER_MESSAGE_IGNORED_HUMAN_ACTIVE conversation_id=%s sender_id=%s message_mid=%s paused_until=%s",
            conversation.id,
            latest.get("sender_id"),
            latest.get("message_mid"),
            getattr(conversation, "bot_paused_until", None),
        )
        return {
            "ok": False,
            "reason": "conversation_paused_by_admin",
            "conversation_id": str(conversation.id),
            "bot_paused_until": getattr(conversation, "bot_paused_until", None),
        }

    return {
        "ok": True,
        "conversation_id": str(conversation.id),
        "resumed": resumed,
    }


async def _reload_conversation_for_pause_check(conversation: Conversation) -> Conversation:
    conversation_id = getattr(conversation, "id", None)
    if not conversation_id:
        return conversation

    try:
        fresh_conversation = await Conversation.get(conversation_id)
    except Exception:
        return conversation
    return fresh_conversation or conversation


async def _run_ai_forward_and_reply(latest: Dict[str, Any]) -> Dict[str, Any]:
    sender_id = str(latest.get("sender_id") or "").strip()
    message_mid = str(latest.get("message_mid") or "").strip() or None

    conversation = await _get_or_create_sender_conversation(latest)
    await _resume_conversation_if_pause_expired(conversation)
    if _is_bot_paused(conversation):
        logger.info(
            "FB_CUSTOMER_MESSAGE_IGNORED_HUMAN_ACTIVE conversation_id=%s sender_id=%s message_mid=%s paused_until=%s",
            conversation.id,
            sender_id,
            message_mid,
            getattr(conversation, "bot_paused_until", None),
        )
        return {
            "ok": False,
            "reason": "conversation_paused_by_admin",
            "conversation_id": str(conversation.id),
        }

    user_text = latest.get("text")
    if user_text is None:
        user_text = ""

    async def init_version_ai_session(
        active_conversation: Conversation,
        ai_user: str,
    ) -> Dict[str, Any]:
        return await _ensure_sender_initialized(
            latest=latest,
            conversation=active_conversation,
            ai_user=ai_user,
        )

    async def send_version_context_message(
        active_conversation: Conversation,
        ai_user: str,
        content: str,
        purpose: str,
    ) -> Dict[str, Any]:
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

    if hasattr(conversation, "version"):
        version_result = await prepare_ai_version_for_customer_message(
            conversation=conversation,
            sender_id=sender_id,
            current_message=str(user_text),
            message_mid=message_mid,
            exclude_message_mids=[message_mid] if message_mid else None,
            init_ai_session=init_version_ai_session,
            send_ai_message=send_version_context_message,
            reload_conversation=_reload_conversation_for_pause_check,
            purpose="user_message",
            log_prefix="FB_AI_VERSION",
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
    if bool(version_result.get("upgraded")):
        ai_result = version_result.get("ai_result") or {}
    else:
        init_kwargs: Dict[str, Any] = {"latest": latest, "conversation": conversation}
        if ai_user != sender_id:
            init_kwargs["ai_user"] = ai_user
        init_result = await _ensure_sender_initialized(**init_kwargs)
        if not bool(init_result.get("ok")):
            return {"ok": False, "reason": "init_failed", "init_result": init_result}

        payload = _build_ai_chat_payload(
            user=ai_user,
            content=str(user_text),
            conversation_id=conversation.id,
        )

        ai_result = await _post_ai_chat_with_retry(
            payload=payload,
            sender_id=ai_user,
            message_mid=message_mid,
            purpose="user_message",
        )
    if not bool(ai_result.get("ok")):
        return {"ok": False, "reason": "ai_call_failed", "ai_result": ai_result}

    response_data = ai_result.get("response_data")
    assistant_message = _extract_text_from_ai_response(response_data)
    if not assistant_message:
        logger.error(
            "FB_AI_RESPONSE_EMPTY sender_id=%s message_mid=%s response_data=%s",
            sender_id,
            message_mid,
            _preview_text(response_data),
        )
        return {
            "ok": False,
            "reason": "ai_response_empty",
            "response_data": response_data,
        }

    conversation = await _reload_conversation_for_pause_check(conversation)
    await _resume_conversation_if_pause_expired(conversation)
    if _is_bot_paused(conversation):
        logger.info(
            "FB_BOT_REPLY_SUPPRESSED_BY_ADMIN_TAKEOVER conversation_id=%s sender_id=%s message_mid=%s paused_until=%s",
            conversation.id,
            sender_id,
            message_mid,
            getattr(conversation, "bot_paused_until", None),
        )
        return {
            "ok": False,
            "reason": "conversation_paused_before_send",
            "conversation_id": str(conversation.id),
        }

    prepared_reply = await _prepare_facebook_reply_from_ai_response(
        response_data=response_data,
        assistant_message=assistant_message,
    )
    handover_detection = detect_handover_reply(prepared_reply.text or assistant_message)
    handover_status_update = {"updated": False, "reason": "handover_not_detected"}
    if bool(handover_detection.get("detected")):
        handover_status_update = await _update_handover_conversation_status(
            conversation=conversation,
            handover_detection=handover_detection,
        )

    send_result = await _send_facebook_reply(
        recipient_id=sender_id,
        message_text=prepared_reply.text,
        reply_to_mid=message_mid,
        image_urls=prepared_reply.image_urls,
    )
    if (
        not send_result
        or (
            isinstance(send_result, dict)
            and (send_result.get("status_code") or send_result.get("ok") is False)
        )
    ):
        non_retryable = _has_non_retryable_facebook_error(send_result)
        failure_reason = "facebook_reply_non_retryable" if non_retryable else "facebook_reply_failed"
        logger.error(
            "FB_SEND_REPLY_AFTER_AI_FAILED sender_id=%s message_mid=%s reason=%s non_retryable=%s send_result=%s",
            sender_id,
            message_mid,
            failure_reason,
            non_retryable,
            _preview_text(send_result),
        )
        return {
            "ok": False,
            "reason": failure_reason,
            "non_retryable": non_retryable,
            "send_result": send_result,
        }

    try:
        await _save_forwarded_messages(
            conversation=conversation,
            latest=latest,
            assistant_message=prepared_reply.text or assistant_message,
        )
    except Exception as exc:
        logger.exception(
            "FB_SAVE_FORWARDED_MESSAGES_FAILED sender_id=%s message_mid=%s error=%s",
            sender_id,
            message_mid,
            exc,
        )

    return {
        "ok": True,
        "assistant_message": assistant_message,
        "reply_text": prepared_reply.text,
        "image_urls": prepared_reply.image_urls,
        "drive_folder_urls": prepared_reply.drive_folder_urls,
        "handover_detection": handover_detection,
        "handover_status_update": handover_status_update,
        "send_result": send_result,
    }


async def _fetch_participant_names_from_conversations(sender_id: str, page_id: str) -> Dict[str, Optional[str]]:
    result: Dict[str, Optional[str]] = {
        "sender_name": None,
        "page_name": None,
    }

    token = (settings.fb_page_access_token or "").strip()
    if not token or not sender_id:
        return result

    url = "https://graph.facebook.com/v19.0/me/conversations"
    params = {
        "user_id": sender_id,
        "fields": "participants",
        "access_token": token,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
        if response.status_code != 200:
            return result

        data = response.json()

        if not isinstance(data, dict):
            return result

        conversations = data.get("data")
        if not isinstance(conversations, list):
            return result

        for conversation in conversations:
            if not isinstance(conversation, dict):
                continue

            participants = (conversation.get("participants") or {}).get("data", [])
            if not isinstance(participants, list):
                continue

            for participant in participants:
                if not isinstance(participant, dict):
                    continue
                participant_id = str(participant.get("id") or "")
                participant_name = participant.get("name")
                resolved_name = str(participant_name) if participant_name else None
                if participant_id == sender_id:
                    result["sender_name"] = resolved_name
                if page_id and participant_id == page_id:
                    result["page_name"] = resolved_name

                if result["sender_name"] and (result["page_name"] or not page_id):
                    return result

        return result
    except Exception:
        return result


async def _fetch_sender_name_direct(sender_id: str) -> Optional[str]:
    token = (settings.fb_page_access_token or "").strip()
    if not token or not sender_id:
        return None

    url = f"https://graph.facebook.com/v19.0/{sender_id}"
    params = {
        "fields": "name",
        "access_token": token,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
        if response.status_code != 200:
            return None

        data = response.json()
        name = data.get("name") if isinstance(data, dict) else None
        resolved = str(name) if name else None
        return resolved
    except Exception:
        return None


async def _process_sender_buffer_after_delay(sender_id: str, delay_seconds: Optional[int] = None) -> None:
    wait_seconds = delay_seconds if delay_seconds is not None else _get_sender_buffer_seconds()
    try:
        await asyncio.sleep(wait_seconds)
    except asyncio.CancelledError:
        return

    with _sender_buffer_lock:
        sender_state = _sender_buffers.pop(sender_id, None)

    if not sender_state:
        return

    messages = sender_state.get("messages") or []
    if not messages:
        return

    succeeded_mids: list[str] = []
    failed_messages: list[Dict[str, Any]] = []

    for item in messages:
        latest = dict(item)
        message_mid = str(latest.get("message_mid") or "").strip()
        retry_count = int(latest.get("delivery_retry_count") or 0)
        try:
            run_result = await _run_ai_forward_and_reply(latest)
        except Exception as exc:
            logger.exception(
                "FB_BUFFER_PROCESS_EXCEPTION sender_id=%s message_mid=%s retry_count=%s error=%s",
                sender_id,
                message_mid,
                retry_count,
                exc,
            )
            run_result = {"ok": False, "reason": "process_exception"}

        if bool(run_result.get("ok")):
            if message_mid:
                succeeded_mids.append(message_mid)
            continue

        reason = str(run_result.get("reason") or "")
        if reason in FACEBOOK_SUPPRESSED_BY_PAUSE_REASONS:
            if message_mid:
                succeeded_mids.append(message_mid)
            logger.info(
                "FB_BUFFER_MESSAGE_SUPPRESSED sender_id=%s message_mid=%s reason=%s",
                sender_id,
                message_mid,
                reason,
            )
            continue

        if reason in FACEBOOK_NON_RETRYABLE_FAILURE_REASONS or bool(run_result.get("non_retryable")):
            if message_mid:
                succeeded_mids.append(message_mid)
            logger.error(
                "FB_BUFFER_MESSAGE_DROPPED_NON_RETRYABLE sender_id=%s message_mid=%s retry_count=%s reason=%s result=%s",
                sender_id,
                message_mid,
                retry_count,
                reason,
                _preview_text(run_result),
            )
            continue

        latest["delivery_retry_count"] = retry_count + 1
        failed_messages.append(latest)
        logger.warning(
            "FB_FORWARD_RETRY_SCHEDULED sender_id=%s message_mid=%s retry_count=%s reason=%s",
            sender_id,
            message_mid,
            latest["delivery_retry_count"],
            reason,
        )

    if succeeded_mids:
        _finalize_buffered_message_mids(succeeded_mids)

    if not failed_messages:
        return

    with _sender_buffer_lock:
        sender_state = _sender_buffers.get(sender_id)
        if not sender_state:
            sender_state = {"messages": [], "task": None}
            _sender_buffers[sender_id] = sender_state

        sender_state["messages"] = failed_messages + list(sender_state.get("messages") or [])

        existing_task = sender_state.get("task")
        if existing_task and not existing_task.done():
            existing_task.cancel()
        sender_state["task"] = asyncio.create_task(
            _process_sender_buffer_after_delay(
                sender_id,
                delay_seconds=_get_fb_ai_requeue_delay_seconds(),
            )
        )


async def _enqueue_sender_message(latest: Dict[str, Any]) -> Dict[str, Any]:
    sender_id = str(latest.get("sender_id") or "").strip()
    if not sender_id:
        return {"buffer_size": 0, "wait_seconds": _get_sender_buffer_seconds()}

    snapshot = {
        "page_id": latest.get("page_id"),
        "page_name": latest.get("page_name"),
        "sender_id": latest.get("sender_id"),
        "sender_name": latest.get("sender_name"),
        "recipient_id": latest.get("recipient_id"),
        "timestamp": latest.get("timestamp"),
        "message_mid": latest.get("message_mid"),
        "text": latest.get("text"),
        "metadata": latest.get("metadata"),
        "app_id": latest.get("app_id"),
        "delivery_retry_count": int(latest.get("delivery_retry_count") or 0),
    }

    with _sender_buffer_lock:
        sender_state = _sender_buffers.get(sender_id)
        if not sender_state:
            sender_state = {"messages": [], "task": None}
            _sender_buffers[sender_id] = sender_state

        sender_state["messages"].append(snapshot)

        existing_task = sender_state.get("task")
        if existing_task and not existing_task.done():
            existing_task.cancel()

        sender_state["task"] = asyncio.create_task(_process_sender_buffer_after_delay(sender_id))
        buffer_size = len(sender_state["messages"])

    return {"buffer_size": buffer_size, "wait_seconds": _get_sender_buffer_seconds()}


async def _send_facebook_reply(
    recipient_id: str,
    message_text: str,
    reply_to_mid: Optional[str],
    image_urls: Optional[list[str]] = None,
) -> Optional[Dict[str, Any]]:
    token = (settings.fb_page_access_token or "").strip()
    has_message = bool(str(message_text or "").strip()) or bool(image_urls)
    if not token or not recipient_id or not has_message:
        logger.error(
            "FB_SEND_REPLY_SKIPPED missing_required_data has_token=%s has_recipient=%s has_message=%s reply_to_mid=%s",
            bool(token),
            bool(recipient_id),
            has_message,
            reply_to_mid,
        )
        if not token:
            reason = "missing_fb_page_access_token"
        elif not recipient_id:
            reason = "missing_recipient"
        else:
            reason = "missing_message_text_or_image"
        return {"ok": False, "reason": reason, "non_retryable": True}

    result = await send_facebook_text_and_images(
        recipient_id=recipient_id,
        message_text=message_text,
        page_access_token=token,
        page_id=settings.fb_page_id,
        reply_to_mid=reply_to_mid,
        image_urls=image_urls,
        max_image_count=MAX_FACEBOOK_PRODUCT_IMAGES,
    )
    if bool(result.get("ok")):
        logger.info(
            "FB_SEND_REPLY_OK recipient_id=%s reply_to_mid=%s text_length=%s image_count=%s skipped_image_count=%s",
            recipient_id,
            reply_to_mid,
            len(result.get("text") or ""),
            len(result.get("image_urls") or []),
            result.get("skipped_image_url_count"),
        )
    else:
        logger.error(
            "FB_SEND_REPLY_FAILED recipient_id=%s reply_to_mid=%s reason=%s text_length=%s image_count=%s",
            recipient_id,
            reply_to_mid,
            result.get("reason"),
            len(result.get("text") or ""),
            len(result.get("image_urls") or []),
        )
    return result


def _extract_incoming_messages(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    entries = payload.get("entry")
    if not isinstance(entries, list):
        return []

    extracted: list[Dict[str, Any]] = []
    sequence = 0

    for entry in entries:
        entry_id = str(entry.get("id", "")).strip()

        messaging_list = entry.get("messaging")
        if not isinstance(messaging_list, list):
            continue

        for event in messaging_list:
            message = event.get("message")
            if not isinstance(message, dict):
                continue

            text = message.get("text")
            if text is None:
                continue

            message_mid = str(message.get("mid") or "")
            is_echo = bool(message.get("is_echo"))
            metadata = str(message.get("metadata") or "")
            app_id = message.get("app_id")

            ts = int(event.get("timestamp") or 0)
            sender_id = str((event.get("sender") or {}).get("id") or "")
            recipient_id = str((event.get("recipient") or {}).get("id") or "")

            candidate = {
                "page_id": entry_id,
                "sender_id": sender_id,
                "recipient_id": recipient_id,
                "timestamp": ts,
                "_sequence": sequence,
                "message_mid": message_mid,
                "is_echo": is_echo,
                "text": str(text),
                "metadata": metadata,
                "app_id": app_id,
                "raw": event,
            }
            extracted.append(candidate)
            sequence += 1

    extracted.sort(key=lambda item: (int(item.get("timestamp") or 0), int(item.get("_sequence") or 0)))
    for item in extracted:
        item.pop("_sequence", None)
    return extracted


@router.get("/webhook")
async def verify_webhook(
    mode: Optional[str] = Query(default=None, alias="hub.mode"),
    verify_token: Optional[str] = Query(default=None, alias="hub.verify_token"),
    challenge: Optional[str] = Query(default=None, alias="hub.challenge"),
):
    expected = _get_verify_token()
    if not expected:
        raise HTTPException(status_code=500, detail="Missing FB_PAGE_ACCESS_TOKEN or FB_WEBHOOK_VERIFY_TOKEN")

    if mode == "subscribe" and verify_token == expected and challenge is not None:
        return int(challenge) if challenge.isdigit() else challenge

    raise HTTPException(status_code=403, detail="Webhook verification failed")


@router.post("/webhook")
async def receive_webhook(request: Request):
    if not settings.fb_page_id:
        raise HTTPException(status_code=500, detail="Missing FB_PAGE_ID in environment")

    client_ip = request.client.host if request.client else "unknown"
    request_path = request.url.path if request.url else "/api/v1/facebook/webhook"

    body = await request.body()
    if not body:
        logger.info(
            "FB_WEBHOOK_REQUEST_EMPTY client_ip=%s path=%s",
            client_ip,
            request_path,
        )
        return {"status": "ignored", "reason": "empty_body"}

    raw_body = body.decode("utf-8", errors="ignore")
    logger.info(
        "FB_WEBHOOK_RAW_PAYLOAD client_ip=%s path=%s payload=%s",
        client_ip,
        request_path,
        raw_body,
    )

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return {"status": "ignored", "reason": "invalid_json"}

    if not isinstance(payload, dict):
        return {"status": "ignored", "reason": "invalid_payload_type"}

    if payload.get("object") != "page":
        return {"status": "ignored", "reason": "object_is_not_page"}

    incoming_messages = _extract_incoming_messages(payload)
    if not incoming_messages:
        return {
            "status": "EVENT_RECEIVED",
            "raw_body": raw_body,
            "latest_message": None,
            "sender_name": None,
        }

    queued_messages: list[Dict[str, Any]] = []
    ignored_messages: list[Dict[str, Any]] = []
    names_cache: Dict[tuple[str, str], Dict[str, Optional[str]]] = {}
    latest_queued: Optional[Dict[str, Any]] = None

    for latest in incoming_messages:
        message_mid = str(latest.get("message_mid") or "").strip()
        sender_id = str(latest.get("sender_id") or "")
        page_id = str(latest.get("page_id") or "")
        message_kind = _classify_facebook_message(latest)

        if message_kind == FACEBOOK_MESSAGE_BOT_ECHO:
            logger.info(
                "FB_WEBHOOK_BOT_ECHO_IGNORED page_id=%s sender_id=%s message_mid=%s metadata=%s",
                page_id,
                sender_id,
                message_mid,
                latest.get("metadata"),
            )
            ignored_messages.append(
                {
                    "message_mid": message_mid,
                    "sender_id": sender_id,
                    "kind": message_kind,
                    "reason": "bot_echo",
                }
            )
            continue

        if message_kind == FACEBOOK_MESSAGE_ADMIN:
            try:
                admin_result = await _handle_admin_message(latest)
                ignored_messages.append(
                    {
                        "message_mid": message_mid,
                        "sender_id": sender_id,
                        "kind": message_kind,
                        "reason": "admin_message_paused_conversation",
                        "conversation_id": admin_result.get("conversation_id"),
                        "buffer_result": admin_result.get("buffer_result"),
                    }
                )
            except Exception as exc:
                logger.exception(
                    "FB_WEBHOOK_ADMIN_MESSAGE_FAILED page_id=%s sender_id=%s recipient_id=%s message_mid=%s error=%s",
                    page_id,
                    sender_id,
                    latest.get("recipient_id"),
                    message_mid,
                    exc,
                )
                ignored_messages.append(
                    {
                        "message_mid": message_mid,
                        "sender_id": sender_id,
                        "kind": message_kind,
                        "reason": "admin_message_pause_failed",
                    }
                )
            continue

        cache_key = (sender_id, page_id)
        names = names_cache.get(cache_key)
        if names is None:
            names = await _fetch_participant_names_from_conversations(sender_id, page_id)
            sender_name_cached = names.get("sender_name")
            if not sender_name_cached:
                sender_name_cached = await _fetch_sender_name_direct(sender_id)
                names["sender_name"] = sender_name_cached
            names_cache[cache_key] = names

        sender_name = names.get("sender_name")
        page_name = names.get("page_name")

        if sender_name:
            latest["sender_name"] = sender_name
        if page_name:
            latest["page_name"] = page_name

        # Additional guard requested: if sender name matches page/channel name, ignore.
        if sender_name and page_name and sender_name.strip().lower() == page_name.strip().lower():
            ignored_messages.append(
                {
                    "message_mid": message_mid,
                    "sender_id": sender_id,
                    "reason": "sender_is_page_name",
                }
            )
            continue

        # Additional guard requested: if sender_name equals any existing conversation.channel, ignore.
        if sender_name:
            existing_channel = await Conversation.find_one(Conversation.channel == sender_name)
            if existing_channel:
                ignored_messages.append(
                    {
                        "message_mid": message_mid,
                        "sender_id": sender_id,
                        "reason": "sender_matches_conversation_channel",
                    }
                )
                continue

        if message_mid:
            existing_message = await Message.find_one(Message.message_mid == message_mid)
            if existing_message:
                ignored_messages.append(
                    {
                        "message_mid": message_mid,
                        "sender_id": sender_id,
                        "reason": "duplicate_message_mid",
                    }
                )
                continue

            with _processing_message_mid_lock:
                if message_mid in _processing_message_mids:
                    ignored_messages.append(
                        {
                            "message_mid": message_mid,
                            "sender_id": sender_id,
                            "reason": "duplicate_message_mid_inflight",
                        }
                    )
                    continue
                _processing_message_mids.add(message_mid)

        try:
            active_result = await _ensure_customer_message_can_enqueue(latest)
        except Exception as exc:
            if message_mid:
                with _processing_message_mid_lock:
                    _processing_message_mids.discard(message_mid)
            logger.exception(
                "FB_CUSTOMER_MESSAGE_STATE_CHECK_FAILED sender_id=%s message_mid=%s error=%s",
                sender_id,
                message_mid,
                exc,
            )
            ignored_messages.append(
                {
                    "message_mid": message_mid,
                    "sender_id": sender_id,
                    "kind": message_kind,
                    "reason": "conversation_state_check_failed",
                }
            )
            continue

        if not bool(active_result.get("ok")):
            if message_mid:
                with _processing_message_mid_lock:
                    _processing_message_mids.discard(message_mid)
            ignored_messages.append(
                {
                    "message_mid": message_mid,
                    "sender_id": sender_id,
                    "kind": message_kind,
                    "reason": active_result.get("reason"),
                    "conversation_id": active_result.get("conversation_id"),
                    "bot_paused_until": active_result.get("bot_paused_until"),
                }
            )
            continue

        with _latest_message_lock:
            _latest_message.clear()
            _latest_message.update(latest)

        logger.info(
            "FB_WEBHOOK_NEW_MESSAGE page_id=%s page_name=%s sender_id=%s sender_name=%s message_mid=%s text=%s timestamp=%s",
            latest.get("page_id"),
            latest.get("page_name"),
            latest.get("sender_id"),
            latest.get("sender_name"),
            latest.get("message_mid"),
            latest.get("text"),
            latest.get("timestamp"),
        )

        try:
            enqueue_result = await _enqueue_sender_message(latest)
            queued_messages.append(
                {
                    "message_mid": message_mid,
                    "sender_id": sender_id,
                    "sender_name": latest.get("sender_name"),
                    "buffer_size": enqueue_result.get("buffer_size"),
                    "wait_seconds": enqueue_result.get("wait_seconds"),
                }
            )
            latest_queued = latest
        except Exception:
            if message_mid:
                with _processing_message_mid_lock:
                    _processing_message_mids.discard(message_mid)
            ignored_messages.append(
                {
                    "message_mid": message_mid,
                    "sender_id": sender_id,
                    "reason": "queue_failed",
                }
            )

    if queued_messages:
        return {
            "status": "QUEUED",
            "raw_body": raw_body,
            "latest_message": latest_queued,
            "queued_count": len(queued_messages),
            "queued_messages": queued_messages,
            "ignored_count": len(ignored_messages),
            "ignored_messages": ignored_messages,
            "sender_name": latest_queued.get("sender_name") if latest_queued else None,
        }

    return {
        "status": "ignored",
        "reason": "no_message_enqueued",
        "raw_body": raw_body,
        "latest_message": None,
        "sender_name": None,
        "ignored_count": len(ignored_messages),
        "ignored_messages": ignored_messages,
    }


@router.get("/latest-message")
async def get_latest_message():
    with _latest_message_lock:
        if not _latest_message:
            return {"latest_message": None}
        return {"latest_message": dict(_latest_message)}
