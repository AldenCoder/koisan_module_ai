from __future__ import annotations

import re
from html import unescape
from typing import Any, Mapping


PANCAKE_SOURCE = "pancake_webhook"
PANCAKE_EVENT_MESSAGING = "messaging"
PANCAKE_EVENT_POST = "post"
PANCAKE_MESSAGE_INBOX = "INBOX"
PANCAKE_MESSAGE_COMMENT = "COMMENT"
PANCAKE_IMAGE_ATTACHMENT_TYPES = {"image", "photo"}


def strip_html_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"<[^>]+>", "", text)
    return unescape(text).strip()


def detect_pancake_platform(page_id: Any) -> str:
    normalized = str(page_id or "").strip().lower()
    if not normalized:
        return "unknown"
    if normalized.startswith("tt_"):
        return "tiktok"
    if normalized.startswith("zalo_") or normalized.startswith("zl_"):
        return "zalo"
    if normalized.isdigit():
        return "facebook"
    return "unknown"


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _clean_optional_string(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _extract_image_urls(attachments: list[Any]) -> list[str]:
    image_urls: list[str] = []
    seen: set[str] = set()
    for attachment in attachments:
        item = _as_mapping(attachment)
        attachment_type = str(item.get("type") or "").strip().lower()
        if attachment_type not in PANCAKE_IMAGE_ATTACHMENT_TYPES:
            continue
        image_url = _clean_optional_string(item.get("url"))
        if not image_url or image_url in seen:
            continue
        image_urls.append(image_url)
        seen.add(image_url)
    return image_urls


def _count_image_attachments(attachments: list[Any]) -> int:
    return sum(
        1
        for attachment in attachments
        if str(_as_mapping(attachment).get("type") or "").strip().lower()
        in PANCAKE_IMAGE_ATTACHMENT_TYPES
    )


def _is_comment_message_type(value: Any) -> bool:
    return str(value or "").strip().upper() == PANCAKE_MESSAGE_COMMENT


def _truncate_optional_text(value: Any, *, limit: int = 500) -> str | None:
    text = strip_html_text(value)
    if not text:
        return None
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...(truncated)"


def _extract_comment_message_id(
    *,
    message: Mapping[str, Any],
    comment: Mapping[str, Any],
) -> str | None:
    candidates = [
        message.get("comment_message_id"),
        message.get("comment_id"),
        message.get("message_id"),
        message.get("id"),
        comment.get("comment_message_id"),
        comment.get("comment_id"),
        comment.get("message_id"),
        comment.get("id"),
    ]
    for candidate in candidates:
        normalized = _clean_optional_string(candidate)
        if normalized:
            return normalized
    return None


def choose_pancake_sender_id(
    *,
    page_customer_id: str | None,
    platform_sender_id: str | None,
) -> str | None:
    return page_customer_id or platform_sender_id


def is_pancake_page_echo(
    *,
    page_id: str | None,
    platform_sender_id: str | None,
    message_type: str | None,
    raw_is_echo: Any,
) -> bool:
    normalized_page_id = str(page_id or "").strip()
    normalized_platform_sender_id = str(platform_sender_id or "").strip()
    normalized_message_type = str(message_type or "").strip().upper()

    if raw_is_echo is not None and bool(raw_is_echo):
        return True
    if normalized_page_id and normalized_platform_sender_id == normalized_page_id:
        return True
    return normalized_message_type not in {
        PANCAKE_MESSAGE_INBOX,
        PANCAKE_MESSAGE_COMMENT,
    }


def _build_result(*, ok: bool, reason: str | None, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": ok,
        "reason": reason,
        "event_type": data.get("event_type"),
        "page_id": data.get("page_id"),
        "message_mid": data.get("message_mid"),
        "data": data,
    }


def normalize_pancake_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = _as_mapping(payload.get("data"))
    conversation = _as_mapping(data.get("conversation"))
    message = _as_mapping(data.get("message"))
    comment = _as_mapping(data.get("comment"))
    post = _as_mapping(data.get("post"))
    message_from = _as_mapping(message.get("from") or comment.get("from"))
    conversation_from = _as_mapping(conversation.get("from"))

    event_type = _clean_optional_string(payload.get("event_type"))
    page_id = _clean_optional_string(payload.get("page_id") or message.get("page_id"))
    pancake_conversation_id = _clean_optional_string(
        conversation.get("id") or message.get("conversation_id") or comment.get("conversation_id")
    )
    conversation_type = _clean_optional_string(conversation.get("type") or message.get("type"))
    message_type = _clean_optional_string(message.get("type") or comment.get("type"))
    is_comment_message = _is_comment_message_type(message_type)
    comment_message_id = (
        _extract_comment_message_id(message=message, comment=comment)
        if is_comment_message
        else None
    )
    message_mid = _clean_optional_string(message.get("id") or (comment_message_id if is_comment_message else None))
    message_from_id = _clean_optional_string(message_from.get("id"))
    conversation_sender_id = _clean_optional_string(conversation_from.get("id"))
    conversation_customer_id = _clean_optional_string(conversation.get("customer_id"))
    platform_sender_id = _clean_optional_string(message_from_id or conversation_sender_id)
    page_customer_id = _clean_optional_string(message_from.get("page_customer_id"))
    sender_id = choose_pancake_sender_id(
        page_customer_id=page_customer_id,
        platform_sender_id=platform_sender_id,
    )
    conversation_sender_name = _clean_optional_string(conversation_from.get("name"))
    sender_name = _clean_optional_string(message_from.get("name") or conversation_sender_name)
    message_from_admin_name = _clean_optional_string(message_from.get("admin_name"))
    message_from_uid = _clean_optional_string(message_from.get("uid"))
    message_from_ai_generated = (
        message_from.get("ai_generated") if "ai_generated" in message_from else None
    )
    inserted_at = _clean_optional_string(message.get("inserted_at"))
    original_message = message.get("original_message", comment.get("original_message"))
    raw_message = message.get("message", comment.get("message"))
    original_text = str(original_message).strip() if original_message is not None else ""
    text = original_text or strip_html_text(raw_message)
    attachments = _as_list(message.get("attachments") or comment.get("attachments"))
    image_urls = _extract_image_urls(attachments)
    image_attachment_count = _count_image_attachments(attachments)
    post_id = _clean_optional_string(post.get("id"))
    post_type = _clean_optional_string(post.get("type"))
    post_message_preview = _truncate_optional_text(post.get("message"))
    post_message_text = strip_html_text(post.get("message"))
    post_attachments = _as_list(post.get("attachments"))
    is_removed = bool(message.get("is_removed")) if "is_removed" in message else False
    is_echo = is_pancake_page_echo(
        page_id=page_id,
        platform_sender_id=platform_sender_id,
        message_type=message_type,
        raw_is_echo=message.get("is_echo") if "is_echo" in message else None,
    )

    normalized = {
        "source": PANCAKE_SOURCE,
        "event_type": event_type,
        "page_id": page_id,
        "page_name": None,
        "sender_id": sender_id,
        "sender_name": sender_name,
        "recipient_id": page_id,
        "timestamp": inserted_at,
        "message_mid": message_mid,
        "message_type": message_type,
        "conversation_type": conversation_type,
        "is_echo": is_echo,
        "is_removed": is_removed,
        "text": text,
        "metadata": {
            "event_type": event_type,
            "conversation_type": conversation_type,
            "message_type": message_type,
            "is_removed": is_removed,
            "conversation_customer_id": conversation_customer_id,
            "conversation_sender_id": conversation_sender_id,
            "conversation_sender_name": conversation_sender_name,
            "message_from_id": message_from_id,
            "message_from_admin_name": message_from_admin_name,
            "message_from_uid": message_from_uid,
            "message_from_ai_generated": message_from_ai_generated,
            "comment_message_id": comment_message_id,
            "post_id": post_id,
            "post_type": post_type,
            "post_message_present": bool(post_message_text),
            "post_message_length": len(post_message_text),
            "post_message_preview": post_message_preview,
            "post_attachment_count": len(post_attachments),
            "image_attachment_count": image_attachment_count,
            "image_url_count": len(image_urls),
        },
        "app_id": None,
        "pancake_conversation_id": pancake_conversation_id,
        "platform": detect_pancake_platform(page_id),
        "platform_sender_id": platform_sender_id,
        "page_customer_id": page_customer_id,
        "conversation_customer_id": conversation_customer_id,
        "conversation_sender_id": conversation_sender_id,
        "conversation_sender_name": conversation_sender_name,
        "message_from_id": message_from_id,
        "message_from_admin_name": message_from_admin_name,
        "message_from_uid": message_from_uid,
        "message_from_ai_generated": message_from_ai_generated,
        "attachments": attachments,
        "image_urls": image_urls,
        "image_attachment_count": image_attachment_count,
        "image_url_count": len(image_urls),
        "comment_message_id": comment_message_id,
        "post_id": post_id,
        "post_type": post_type,
        "post_message_present": bool(post_message_text),
        "post_message_length": len(post_message_text),
        "post_message_preview": post_message_preview,
        "post_attachment_count": len(post_attachments),
        "raw": payload,
    }

    if event_type != PANCAKE_EVENT_MESSAGING and not is_comment_message:
        return _build_result(ok=False, reason="unsupported_event_type", data=normalized)
    if not page_id:
        return _build_result(ok=False, reason="missing_page_id", data=normalized)
    if not pancake_conversation_id:
        return _build_result(ok=False, reason="missing_pancake_conversation_id", data=normalized)
    if not sender_id:
        return _build_result(ok=False, reason="missing_sender_id", data=normalized)
    if not message_type:
        return _build_result(ok=False, reason="missing_message_type", data=normalized)
    if is_comment_message and not comment_message_id:
        return _build_result(
            ok=False,
            reason="missing_pancake_comment_message_id",
            data=normalized,
        )
    if not message_mid:
        return _build_result(ok=False, reason="missing_message_mid", data=normalized)
    if is_removed:
        return _build_result(ok=False, reason="message_removed", data=normalized)
    if not text and not attachments:
        return _build_result(ok=False, reason="missing_message_content", data=normalized)

    return _build_result(ok=True, reason=None, data=normalized)
