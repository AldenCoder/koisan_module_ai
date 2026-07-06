from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from pydantic_core import ValidationError as PydanticCoreValidationError

from app.api.dependencies.time import VN_TZ, now_vn
from app.core.config import settings
from app.models.branches import Branch
from app.models.conversation_states import ConversationState
from app.models.conversations import Conversation, ConversationStatus
from app.models.messages import Message
from app.models.rag_service_tokens import RagServiceToken
from app.models.state_asked_slots import StateAskedSlot
from app.models.state_missing_slots import StateMissingSlot
from app.models.state_slots import StateSlot
from app.services.ai_service import (
    detect_intent,
    generate_slot_question,
)
from app.services.ai_version_context_service import get_system_version_for_new_conversation
from app.services.catalog_service import get_slot_definition
from logs.logging_config import logger


HANDOFF_FIXED_MESSAGE = "Em đã chuyển tin nhắn đến nhân viên hỗ trợ ạ, anh chị đợi 1 lát để được tư vấn..."


def _safe_json_dumps(data: Any) -> str:
    try:
        return json.dumps(data, ensure_ascii=False, default=str)
    except Exception:
        return str(data)


def _truncate_for_log(value: Any, *, max_len: int = 220) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return f"{text[:max_len]}..."


def _sanitize_rag_payload_for_log(payload: Dict[str, Any]) -> Dict[str, Any]:
    question = str(payload.get("question") or "").strip()
    conversation_history = payload.get("conversation_history")
    history_count = 0
    history_roles: List[str] = []

    if isinstance(conversation_history, list):
        history_count = len(conversation_history)
        for item in conversation_history:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip().lower()
            if role:
                history_roles.append(role)

    return {
        "question_length": len(question),
        "question_preview": _truncate_for_log(question),
        "conversation_history_count": history_count,
        "conversation_history_roles": history_roles,
    }


def _sanitize_rag_debug_for_log(debug: Dict[str, Any]) -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {
        "reason": debug.get("reason"),
        "status_code": debug.get("status_code"),
        "error_type": debug.get("error_type"),
    }

    if "payload" in debug and isinstance(debug.get("payload"), dict):
        snapshot["payload"] = _sanitize_rag_payload_for_log(debug["payload"])

    if "error" in debug and debug.get("error"):
        snapshot["error_preview"] = _truncate_for_log(debug["error"], max_len=160)

    response_data = debug.get("response_data")
    if isinstance(response_data, dict):
        snapshot["response_keys"] = sorted(response_data.keys())
        extracted_answer = _extract_text_from_response_payload(response_data)
        if extracted_answer:
            snapshot["response_answer_preview"] = _truncate_for_log(extracted_answer)
    elif isinstance(response_data, list):
        snapshot["response_type"] = "list"
        snapshot["response_items"] = len(response_data)
        extracted_answer = _extract_text_from_response_payload(response_data)
        if extracted_answer:
            snapshot["response_answer_preview"] = _truncate_for_log(extracted_answer)
    elif isinstance(response_data, str):
        snapshot["response_type"] = "str"
        snapshot["response_preview"] = _truncate_for_log(response_data)

    return snapshot


def _build_rag_response_log_snapshot(
    *,
    answer: Optional[str],
    debug: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "has_answer": bool(answer),
        "answer_preview": _truncate_for_log(answer or "", max_len=160),
        "debug": _sanitize_rag_debug_for_log(debug),
    }


def _is_question_like_text(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(text or "").strip().lower())
    if not normalized:
        return False
    if "?" in normalized:
        return True

    question_markers = [
        "cho em hỏi",
        "cho mình hỏi",
        "cho anh hỏi",
        "bên mình có",
        "tư vấn",
        "gói nào",
        "dịch vụ",
        "được không",
        "duoc khong",
        "bao nhiêu",
        "thế nào",
        "như thế nào",
    ]
    return any(marker in normalized for marker in question_markers)


def _is_slot_answer_turn(
    *,
    previous_next_slot: Optional[str],
    current_slots: Optional[Dict[str, Any]],
) -> bool:
    slot_name = str(previous_next_slot or "").strip()
    if not slot_name or not isinstance(current_slots, dict):
        return False
    return _has_slot_value(current_slots.get(slot_name))


def _backfill_rag_anchor_from_history(
    *,
    current_user_message: str,
    recent_conversation_history: Optional[List[Dict[str, str]]],
) -> Optional[str]:
    if not isinstance(recent_conversation_history, list):
        return None

    current_text = str(current_user_message or "").strip()
    user_messages: List[str] = []
    for item in recent_conversation_history:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if role == "user" and content:
            user_messages.append(content)

    if not user_messages:
        return None

    # Prefer the latest user utterance that looks like a real question,
    # excluding the current turn when possible.
    for candidate in reversed(user_messages):
        if current_text and candidate == current_text and len(user_messages) > 1:
            continue
        if _is_question_like_text(candidate):
            return candidate

    # Fallback to latest previous user utterance if no question-like text found.
    for candidate in reversed(user_messages):
        if current_text and candidate == current_text and len(user_messages) > 1:
            continue
        if candidate:
            return candidate

    return current_text or None


def extract_rag_anchor(
    *,
    current_user_message: str,
    current_intent: Optional[str],
    previous_next_slot: Optional[str],
    current_slots: Optional[Dict[str, Any]],
    recent_conversation_history: Optional[List[Dict[str, str]]],
    stored_rag_anchor: Optional[str],
) -> str:
    del current_intent  # Reserved for future anchor policy tuning.

    current_text = str(current_user_message or "").strip()
    stored_anchor = str(stored_rag_anchor or "").strip()
    if stored_anchor:
        return stored_anchor

    slot_answer_turn = _is_slot_answer_turn(
        previous_next_slot=previous_next_slot,
        current_slots=current_slots,
    )
    del slot_answer_turn  # Reserved for future policy adjustments.

    history_anchor = _backfill_rag_anchor_from_history(
        current_user_message=current_text,
        recent_conversation_history=recent_conversation_history,
    )
    if history_anchor:
        return history_anchor

    if current_text:
        return current_text

    history_anchor = _backfill_rag_anchor_from_history(
        current_user_message=current_text,
        recent_conversation_history=recent_conversation_history,
    )
    return history_anchor or ""


def _is_noisy_slot_text(value: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(value or "").strip().lower())
    if not normalized:
        return True

    noisy_values = {
        "none",
        "null",
        "nil",
        "n/a",
        "na",
        "unknown",
        "không rõ",
        "khong ro",
        "chưa rõ",
        "chua ro",
        "không biết",
        "khong biet",
        "{}",
        "[]",
    }
    return normalized in noisy_values


def _normalize_slot_value_for_summary(
    *,
    slot_value: Any,
    slot_type: Optional[str],
) -> Optional[str]:
    if not _has_slot_value(slot_value):
        return None

    normalized_type = str(slot_type or "").strip().lower()

    if normalized_type == "boolean":
        if isinstance(slot_value, bool):
            return "đã có" if slot_value else "chưa có"

        if isinstance(slot_value, (int, float)):
            return "đã có" if bool(slot_value) else "chưa có"

        if isinstance(slot_value, str):
            candidate = slot_value.strip().lower()
            truthy = {"true", "1", "yes", "y", "có", "co", "đã", "da", "rồi", "roi"}
            falsy = {"false", "0", "no", "n", "không", "khong", "chưa", "chua"}
            if candidate in truthy:
                return "đã có"
            if candidate in falsy:
                return "chưa có"
            return None if _is_noisy_slot_text(candidate) else slot_value.strip()

        return "đã có" if bool(slot_value) else "chưa có"

    if isinstance(slot_value, list):
        cleaned_items = [
            str(item).strip()
            for item in slot_value
            if str(item).strip() and not _is_noisy_slot_text(str(item))
        ]
        if not cleaned_items:
            return None
        return ", ".join(cleaned_items)

    if isinstance(slot_value, dict):
        flattened_items: List[str] = []
        for key in sorted(slot_value.keys()):
            raw_item = slot_value.get(key)
            if isinstance(raw_item, (dict, list)) or not _has_slot_value(raw_item):
                continue
            item_text = str(raw_item).strip()
            if _is_noisy_slot_text(item_text):
                continue
            key_text = str(key).strip()
            if key_text:
                flattened_items.append(f"{key_text}: {item_text}")
            else:
                flattened_items.append(item_text)
        if not flattened_items:
            return None
        return ", ".join(flattened_items)

    text_value = str(slot_value).strip()
    if _is_noisy_slot_text(text_value):
        return None

    return text_value


def _slot_name_to_display_label(slot_name: str) -> str:
    normalized = re.sub(r"[_\-]+", " ", str(slot_name or "").strip())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return str(slot_name or "")
    return normalized[:1].upper() + normalized[1:]


def render_slot_summary(
    *,
    slots: Dict[str, Any],
) -> List[str]:
    summaries_ranked: List[tuple[int, str, str, str]] = []

    for slot_name, slot_value in slots.items():
        if not slot_name:
            continue

        slot_def = get_slot_definition(slot_name) or {}
        value_text = _normalize_slot_value_for_summary(
            slot_value=slot_value,
            slot_type=slot_def.get("slot_type"),
        )
        if not value_text:
            continue

        slot_label = str(slot_def.get("label") or "").strip()
        slot_description = str(slot_def.get("description") or "").strip()
        priority = slot_def.get("priority")

        if slot_label:
            display_label = slot_label
        elif slot_description:
            display_label = slot_description
        else:
            display_label = _slot_name_to_display_label(slot_name)

        summary_text = f"{display_label}: {value_text}"
        summaries_ranked.append(
            (
                _priority_rank(priority),
                display_label.lower(),
                slot_name,
                summary_text,
            )
        )

    return [item[3] for item in sorted(summaries_ranked)]


def compose_rag_question(
    *,
    rag_anchor: str,
    slot_summary: List[str],
) -> str:
    lines: List[str] = []

    normalized_anchor = str(rag_anchor or "").strip()
    if normalized_anchor:
        lines.append(f"Nhu cầu khách: {normalized_anchor}")

    if slot_summary:
        lines.append("Thông tin đã xác nhận:")
        lines.extend(f"- {item}" for item in slot_summary)

    return "\n".join(lines).strip()


def _build_rag_question_text(
    *,
    latest_user_message: str,
    branch: Optional[str],
    slots: Dict[str, Any],
    current_intent: Optional[str] = None,
    previous_next_slot: Optional[str] = None,
    current_slots: Optional[Dict[str, Any]] = None,
    recent_conversation_history: Optional[List[Dict[str, str]]] = None,
    stored_rag_anchor: Optional[str] = None,
) -> str:
    del branch  # Keep signature stable while branch is intentionally excluded from RAG question.

    rag_anchor = extract_rag_anchor(
        current_user_message=latest_user_message,
        current_intent=current_intent,
        previous_next_slot=previous_next_slot,
        current_slots=current_slots,
        recent_conversation_history=recent_conversation_history,
        stored_rag_anchor=stored_rag_anchor,
    )
    slot_summary = render_slot_summary(slots=slots)

    question = compose_rag_question(
        rag_anchor=rag_anchor,
        slot_summary=slot_summary,
    )
    if question:
        return question

    return rag_anchor


def _parse_json_env(value: Optional[str], default: Any) -> Any:
    raw = (value or "").strip()
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _normalize_headers(value: Any) -> Dict[str, str]:
    if not isinstance(value, dict):
        return {}

    normalized: Dict[str, str] = {}
    for key, raw_value in value.items():
        header_name = str(key or "").strip()
        if not header_name:
            continue
        normalized[header_name] = str(raw_value or "").strip()
    return normalized


def _mask_token_for_log(token: Optional[str]) -> str:
    raw = str(token or "").strip()
    if not raw:
        return ""
    if len(raw) <= 14:
        return f"{raw[:4]}***"
    return f"{raw[:8]}...{raw[-6:]}"


def _get_rag_auth_login_url() -> str:
    return (
        os.getenv("RAG_AUTH_LOGIN_URL")
        or settings.rag_auth_login_url
        or "https://ragbrain-production.up.railway.app/api/v1/auth/login"
    ).strip()


def _get_rag_auth_credentials() -> tuple[str, str]:
    email = (os.getenv("RAG_AUTH_EMAIL") or settings.rag_auth_email or "").strip()
    password = (os.getenv("RAG_AUTH_PASSWORD") or settings.rag_auth_password or "").strip()
    return email, password


def _get_rag_auth_headers() -> Dict[str, str]:
    raw_headers = os.getenv("RAG_AUTH_HEADERS")
    if raw_headers is None:
        raw_headers = settings.rag_auth_headers
    headers = _normalize_headers(_parse_json_env(raw_headers, {}))
    if not any(key.lower() == "accept" for key in headers):
        headers["accept"] = "application/json"
    if not any(key.lower() == "content-type" for key in headers):
        headers["Content-Type"] = "application/json"
    return headers


def _get_rag_token_refresh_days() -> int:
    raw_days = (os.getenv("RAG_TOKEN_REFRESH_DAYS") or "").strip()
    if raw_days:
        refresh_days = _to_int_or_default(raw_days, 6)
    else:
        refresh_days = _to_int_or_default(getattr(settings, "rag_token_refresh_days", 6), 6)
    return max(refresh_days, 0)


def _get_token_age_days(updated_at: Any, now: Any) -> Optional[int]:
    updated_dt = _coerce_datetime(updated_at)
    now_dt = _coerce_datetime(now)
    if updated_dt is None or now_dt is None:
        return None
    try:
        return max(int((now_dt - updated_dt).total_seconds() // 86400), 0)
    except Exception:
        return None


def _is_rag_token_stale(*, updated_at: Any, now: Any, refresh_days: int) -> bool:
    updated_dt = _coerce_datetime(updated_at)
    now_dt = _coerce_datetime(now)
    if updated_dt is None or now_dt is None:
        return True
    try:
        return (now_dt - updated_dt) >= timedelta(days=refresh_days)
    except Exception:
        return True


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None

    if isinstance(value, dict) and "$date" in value:
        return _coerce_datetime(value.get("$date"))

    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = f"{raw[:-1]}+00:00"
        try:
            value = datetime.fromisoformat(raw)
        except Exception:
            return None

    if not isinstance(value, datetime):
        return None

    if value.tzinfo is None:
        # Mongo driver may return naive UTC datetimes by default.
        return value.replace(tzinfo=timezone.utc)
    return value


async def _get_latest_rag_token_row() -> Optional[RagServiceToken]:
    return await RagServiceToken.find({}).sort(-RagServiceToken.updated_at).first_or_none()


async def _upsert_rag_token_row(*, access_token: str, token_type: str) -> RagServiceToken:
    token_row = await _get_latest_rag_token_row()
    now = now_vn()
    normalized_token_type = str(token_type or "bearer").strip().lower() or "bearer"

    if token_row is None:
        created_row = RagServiceToken(
            access_token=access_token,
            token_type=normalized_token_type,
            created_at=now,
            updated_at=now,
        )
        await created_row.insert()
        return created_row

    token_row.access_token = access_token
    token_row.token_type = normalized_token_type
    token_row.updated_at = now
    if token_row.created_at is None:
        token_row.created_at = now
    await token_row.save()
    return token_row


async def _login_rag_and_get_token() -> tuple[str, str]:
    login_url = _get_rag_auth_login_url()
    if not login_url:
        raise ValueError("missing_rag_auth_login_url")

    email, password = _get_rag_auth_credentials()
    if not email or not password:
        raise ValueError("missing_rag_auth_credentials")

    login_payload = {
        "email": email,
        "password": password,
    }
    login_headers = _get_rag_auth_headers()

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(login_url, headers=login_headers, json=login_payload)

    if response.status_code >= 400:
        raise RuntimeError(f"rag_auth_http_error:{response.status_code}:{_truncate_for_log(response.text, max_len=160)}")

    try:
        response_data = response.json()
    except Exception as exc:
        raise RuntimeError("rag_auth_invalid_json_response") from exc

    if not isinstance(response_data, dict):
        raise RuntimeError("rag_auth_invalid_response_payload")

    access_token = str(response_data.get("access_token") or "").strip()
    token_type = str(response_data.get("token_type") or "bearer").strip().lower() or "bearer"
    if not access_token:
        raise RuntimeError("rag_auth_missing_access_token")

    logger.info(
        "RAG auth login success url=%s token_type=%s token_preview=%s",
        login_url,
        token_type,
        _mask_token_for_log(access_token),
    )
    return access_token, token_type


async def _get_valid_rag_access_token(*, force_refresh: bool = False) -> tuple[str, Dict[str, Any]]:
    now = now_vn()
    refresh_days = _get_rag_token_refresh_days()
    token_row = await _get_latest_rag_token_row()
    current_token = str(getattr(token_row, "access_token", "") or "").strip()
    should_refresh = (
        force_refresh
        or token_row is None
        or not current_token
        or _is_rag_token_stale(updated_at=getattr(token_row, "updated_at", None), now=now, refresh_days=refresh_days)
    )

    if should_refresh:
        access_token, token_type = await _login_rag_and_get_token()
        saved_row = await _upsert_rag_token_row(access_token=access_token, token_type=token_type)
        return saved_row.access_token, {
            "source": "login_refresh",
            "force_refresh": force_refresh,
            "refresh_days": refresh_days,
            "token_preview": _mask_token_for_log(saved_row.access_token),
        }

    age_days = _get_token_age_days(getattr(token_row, "updated_at", None), now)
    return current_token, {
        "source": "db_cache",
        "force_refresh": force_refresh,
        "refresh_days": refresh_days,
        "age_days": age_days,
        "token_preview": _mask_token_for_log(current_token),
    }


def _build_rag_headers_with_auth(*, access_token: str) -> Dict[str, str]:
    rag_headers = _normalize_headers(_parse_json_env(os.getenv("RAG_SERVICE_HEADERS"), {}))
    rag_headers["Authorization"] = f"Bearer {access_token}"

    if not any(key.lower() == "accept" for key in rag_headers):
        rag_headers["accept"] = "application/json"
    if not any(key.lower() == "content-type" for key in rag_headers):
        rag_headers["Content-Type"] = "application/json"
    return rag_headers


async def _send_rag_request(
    *,
    client: httpx.AsyncClient,
    rag_method: str,
    rag_url: str,
    rag_headers: Dict[str, str],
    payload: Dict[str, Any],
) -> httpx.Response:
    if rag_method == "GET":
        return await client.get(rag_url, headers=rag_headers, params=payload)
    return await client.request(rag_method, rag_url, headers=rag_headers, json=payload)


def _extract_text_from_response_payload(data: Any) -> Optional[str]:
    if data is None:
        return None
    if isinstance(data, str):
        candidate = data.strip()
        return candidate or None
    if isinstance(data, list):
        for item in data:
            resolved = _extract_text_from_response_payload(item)
            if resolved:
                return resolved
        return None
    if isinstance(data, dict):
        for key in [
            "answer",
            "message",
            "response",
            "text",
            "content",
            "result",
            "data",
        ]:
            if key in data:
                resolved = _extract_text_from_response_payload(data.get(key))
                if resolved:
                    return resolved
        return None
    return None


def _sanitize_rag_answer_text(answer: str) -> str:
    lines = [line.strip() for line in str(answer or "").splitlines()]
    filtered_lines: List[str] = []
    for line in lines:
        if not line:
            filtered_lines.append("")
            continue

        normalized_line = line.lower()
        if normalized_line.startswith("trang:"):
            continue
        if normalized_line.startswith("tên file:"):
            continue
        if normalized_line.startswith("ten file:"):
            continue

        filtered_lines.append(line)

    # Normalize blank lines after filtering metadata footer lines.
    compact_lines: List[str] = []
    previous_blank = False
    for line in filtered_lines:
        is_blank = not line
        if is_blank and previous_blank:
            continue
        compact_lines.append(line)
        previous_blank = is_blank

    return "\n".join(compact_lines).strip()


def _is_rag_no_data_answer(answer: str) -> bool:
    normalized = (answer or "").strip().lower()
    if not normalized:
        return True

    no_data_markers = [
        "không tìm thấy thông tin phù hợp",
        "khong tim thay thong tin phu hop",
        "không tìm thấy dữ liệu phù hợp",
        "khong tim thay du lieu phu hop",
        "no relevant information found",
        "couldn't find relevant information",
    ]
    return any(marker in normalized for marker in no_data_markers)


def _load_handoff_admin_recipients() -> List[str]:
    admin_file_name = (os.getenv("HANDOFF_ADMIN_FILE") or "").strip()
    if not admin_file_name:
        return []

    admin_path = Path(admin_file_name)
    if not admin_path.is_absolute():
        admin_path = Path.cwd() / admin_path
    if not admin_path.exists():
        return []

    recipients: List[str] = []
    for raw_line in admin_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        for token in line.replace(",", " ").split():
            candidate = token.strip()
            if candidate:
                recipients.append(candidate)
    return list(dict.fromkeys(recipients))


def _build_handoff_admin_message(
    *,
    conversation: Conversation,
    intent: str,
    branch: Optional[str],
    latest_user_message: str,
    slots: Dict[str, Any],
    reason: str,
) -> str:
    slot_parts: List[str] = []
    for slot_name, slot_value in slots.items():
        if _has_slot_value(slot_value):
            slot_parts.append(f"{slot_name}: {_to_slot_value(slot_value)}")
    slot_summary = ", ".join(slot_parts) if slot_parts else "Chưa có slot đã điền"

    return "\n".join(
        [
            "Can thiệp thủ công cho hội thoại Facebook.",
            f"Khách hàng: {conversation.customer_name or 'Chưa rõ tên'}",
            f"Facebook customer_id: {conversation.customer_id or 'Chưa có'}",
            f"Kênh: {conversation.channel or 'Chưa rõ'}",
            f"Intent hiện tại: {intent or 'unknown'}",
            f"Branch hiện tại: {branch or 'Chưa xác định'}",
            f"Lý do handoff: {reason or 'handoff_requested'}",
            f"Vấn đề khách đang nêu: {latest_user_message or 'Không có nội dung'}",
            f"Thông tin đã thu thập: {slot_summary}",
        ]
    )


async def _send_facebook_message(recipient_id: str, message_text: str, metadata: Optional[str] = None) -> Dict[str, Any]:
    token = (settings.fb_page_access_token or "").strip()
    if not token:
        return {"ok": False, "reason": "missing_fb_page_access_token"}
    if not recipient_id or not message_text:
        return {"ok": False, "reason": "missing_recipient_or_message"}

    payload: Dict[str, Any] = {
        "messaging_type": "MESSAGE_TAG",
        "tag": "ACCOUNT_UPDATE",
        "recipient": {"id": recipient_id},
        "message": {"text": message_text},
    }
    if metadata:
        payload["message"]["metadata"] = metadata

    url = "https://graph.facebook.com/v19.0/me/messages"
    params = {"access_token": token}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, params=params, json=payload)
        if response.status_code >= 400:
            return {
                "ok": False,
                "status_code": response.status_code,
                "error": response.text,
            }
        response_data = response.json()
        return {
            "ok": True,
            "data": response_data if isinstance(response_data, dict) else {"data": response_data},
        }
    except Exception as exc:
        return {"ok": False, "reason": f"send_failed:{exc}"}


async def _notify_handoff_admins(
    *,
    conversation: Conversation,
    intent: str,
    branch: Optional[str],
    latest_user_message: str,
    slots: Dict[str, Any],
    reason: str,
) -> Dict[str, Any]:
    recipients = _load_handoff_admin_recipients()
    if not recipients:
        return {"sent": 0, "results": [], "reason": "no_admin_recipients"}

    message_text = _build_handoff_admin_message(
        conversation=conversation,
        intent=intent,
        branch=branch,
        latest_user_message=latest_user_message,
        slots=slots,
        reason=reason,
    )

    tasks = [
        _send_facebook_message(recipient_id=recipient, message_text=message_text, metadata="handoff:admin_notify")
        for recipient in recipients
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    normalized_results: List[Dict[str, Any]] = []
    sent_count = 0
    for recipient, result in zip(recipients, results):
        if isinstance(result, Exception):
            normalized_results.append(
                {
                    "recipient_id": recipient,
                    "ok": False,
                    "reason": f"exception:{result}",
                }
            )
            continue

        row = {"recipient_id": recipient, **result}
        if row.get("ok"):
            sent_count += 1
        normalized_results.append(row)

    return {
        "sent": sent_count,
        "results": normalized_results,
    }


async def call_rag_service(
    *,
    latest_user_message: str,
    branch: Optional[str],
    intent: str,
    slots: Dict[str, Any],
    conversation_id: Optional[Any] = None,
    prebuilt_payload: Optional[Dict[str, Any]] = None,
    customer_name: Optional[str],
    customer_id: Optional[str],
    channel: Optional[str],
) -> tuple[Optional[str], Dict[str, Any]]:
    rag_url = (os.getenv("RAG_SERVICE_URL") or "").strip()
    if not rag_url:
        return None, {"reason": "missing_rag_service_url"}

    rag_method = (os.getenv("RAG_SERVICE_METHOD") or "POST").strip().upper()
    payload: Dict[str, Any] = prebuilt_payload or await _build_rag_payload(
        latest_user_message=latest_user_message,
        branch=branch,
        slots=slots,
        conversation_id=conversation_id,
    )

    try:
        access_token, auth_debug = await _get_valid_rag_access_token(force_refresh=False)
    except Exception as exc:
        logger.exception("Failed to get valid RAG access token")
        return None, {
            "reason": "rag_auth_failed",
            "error": str(exc).strip() or repr(exc),
            "error_type": type(exc).__name__,
            "payload": payload,
        }

    try:
        rag_headers = _build_rag_headers_with_auth(access_token=access_token)
        retry_401 = False
        refresh_auth_debug: Optional[Dict[str, Any]] = None

        async with httpx.AsyncClient(timeout=None) as client:
            response = await _send_rag_request(
                client=client,
                rag_method=rag_method,
                rag_url=rag_url,
                rag_headers=rag_headers,
                payload=payload,
            )
            if response.status_code == 401:
                retry_401 = True
                try:
                    refreshed_token, refresh_auth_debug = await _get_valid_rag_access_token(force_refresh=True)
                except Exception as exc:
                    logger.exception("Failed to refresh RAG access token after 401")
                    return None, {
                        "reason": "rag_auth_failed",
                        "error": str(exc).strip() or repr(exc),
                        "error_type": type(exc).__name__,
                        "payload": payload,
                        "retried_401": retry_401,
                        "auth": {
                            "initial": auth_debug,
                        },
                    }
                rag_headers = _build_rag_headers_with_auth(access_token=refreshed_token)
                response = await _send_rag_request(
                    client=client,
                    rag_method=rag_method,
                    rag_url=rag_url,
                    rag_headers=rag_headers,
                    payload=payload,
                )

        if response.status_code >= 400:
            return None, {
                "reason": "rag_http_error",
                "status_code": response.status_code,
                "error": response.text,
                "payload": payload,
                "retried_401": retry_401,
                "auth": {
                    "initial": auth_debug,
                    "refresh_after_401": refresh_auth_debug,
                },
            }

        try:
            response_data = response.json()
        except Exception:
            response_data = response.text

        answer = _extract_text_from_response_payload(response_data)
        if not answer:
            return None, {
                "reason": "rag_no_data_found",
                "payload": payload,
                "response_data": response_data,
                "retried_401": retry_401,
                "auth": {
                    "initial": auth_debug,
                    "refresh_after_401": refresh_auth_debug,
                },
            }

        cleaned_answer = _sanitize_rag_answer_text(answer)
        if _is_rag_no_data_answer(cleaned_answer):
            return None, {
                "reason": "rag_no_data_found",
                "payload": payload,
                "response_data": response_data,
                "answer": cleaned_answer,
                "retried_401": retry_401,
                "auth": {
                    "initial": auth_debug,
                    "refresh_after_401": refresh_auth_debug,
                },
            }

        return cleaned_answer, {
            "reason": "rag_answer_generated",
            "payload": payload,
            "response_data": response_data,
            "retried_401": retry_401,
            "auth": {
                "initial": auth_debug,
                "refresh_after_401": refresh_auth_debug,
            },
        }
    except Exception as exc:
        error_text = str(exc).strip() or repr(exc)
        reason = "rag_timeout" if isinstance(exc, httpx.TimeoutException) else "rag_request_failed"
        logger.exception(
            "RAG request failed reason=%s timeout=%s url=%s error_type=%s",
            reason,
            "disabled",
            rag_url,
            type(exc).__name__,
        )
        return None, {
            "reason": reason,
            "error": error_text,
            "error_type": type(exc).__name__,
            "timeout_seconds": None,
            "payload": payload,
            "auth": {
                "initial": auth_debug,
            },
        }


def _to_slot_value(slot_value: Any) -> str:
    if slot_value is None:
        return ""
    if isinstance(slot_value, list):
        return ", ".join(str(item) for item in slot_value)
    if isinstance(slot_value, dict):
        return str(slot_value)
    return str(slot_value)


def _has_slot_value(slot_value: Any) -> bool:
    if slot_value is None:
        return False
    if isinstance(slot_value, str):
        return bool(slot_value.strip())
    if isinstance(slot_value, list):
        return len(slot_value) > 0
    return True


def _should_skip_missing_slot(slot_name: str, slots: Dict[str, Any]) -> bool:
    normalized_slot = (slot_name or "").strip().lower()
    if normalized_slot != "prewedding_outdoor_location":
        return False

    shoot_type = str(slots.get("prewedding_shoot_type") or "").strip().lower()
    if not shoot_type:
        return False

    has_studio = "studio" in shoot_type
    has_outdoor_or_mix = any(
        token in shoot_type
        for token in ["ngoại", "ngoai", "outdoor", "kết hợp", "ket hop", "both", "cả hai", "ca hai"]
    )
    return has_studio and not has_outdoor_or_mix


def _build_asked_slot_values(asked_slots: List[str], slots: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for slot_name in asked_slots:
        if not slot_name:
            continue
        slot_value = slots.get(slot_name)
        if _has_slot_value(slot_value):
            result[slot_name] = slot_value
    return result


def _priority_rank(priority: Optional[str]) -> int:
    normalized = (priority or "").strip().lower()
    if normalized == "high":
        return 0
    if normalized == "medium":
        return 1
    if normalized == "low":
        return 2
    return 9


def _to_int_or_default(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


def _to_vn_aware_datetime(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None

    # Mongo/PyMongo often returns naive datetimes in UTC.
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(VN_TZ)


def _personalize_question(question: str, customer_name: Optional[str]) -> str:
    def _name_already_in_question(name: str, text: str) -> bool:
        normalized_name = name.strip().lower()
        normalized_text = text.strip().lower()
        if not normalized_name or not normalized_text:
            return False

        if normalized_name in normalized_text:
            return True

        name_tokens = re.findall(r"[0-9A-Za-zÀ-ỹ]+", normalized_name)
        if len(name_tokens) >= 2:
            tail_two = " ".join(name_tokens[-2:])
            if tail_two and tail_two in normalized_text:
                return True
        if len(name_tokens) >= 3:
            tail_three = " ".join(name_tokens[-3:])
            if tail_three and tail_three in normalized_text:
                return True

        strong_name_tokens = [token for token in name_tokens if len(token) >= 2]
        question_tokens = set(re.findall(r"[0-9A-Za-zÀ-ỹ]+", normalized_text))
        if not strong_name_tokens or not question_tokens:
            return False

        # If the question contains at least two meaningful name tokens,
        # consider it already personalized to avoid duplicating the name.
        shared_tokens = [token for token in strong_name_tokens if token in question_tokens]
        if len(shared_tokens) >= 2:
            return True

        # Backup check with trailing meaningful tokens only.
        if len(strong_name_tokens) >= 2:
            tail_tokens = strong_name_tokens[-2:]
            if all(token in question_tokens for token in tail_tokens):
                return True

        return False

    name = (customer_name or "").strip()
    if not name:
        return question

    normalized_question = (question or "").strip()
    if not normalized_question:
        return question

    if _name_already_in_question(name, normalized_question):
        return normalized_question

    if normalized_question.lower().startswith("dạ"):
        remainder = normalized_question[2:].lstrip(" ,")
        if remainder:
            return f"Dạ {name}, {remainder}"
    return f"Dạ {name}, {normalized_question}"


_UNSET = object()


def _normalize_optional_text_value(value: Optional[Any]) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_conversation_status(
    status: Optional[Any],
    *,
    allow_none: bool = False,
) -> Optional[ConversationStatus]:
    if status is None:
        return None if allow_none else ConversationStatus.NEW

    if isinstance(status, ConversationStatus):
        return status

    if isinstance(status, Enum):
        status = status.value

    normalized = str(status).strip().lower()
    if not normalized:
        return None if allow_none else ConversationStatus.NEW

    try:
        return ConversationStatus(normalized)
    except ValueError as exc:
        raise ValueError(
            "Invalid status. Allowed values: new, handover, apilimit, confirmed, order_pending"
        ) from exc


def _normalize_conversation_summaries(
    summaries: Optional[Any],
    *,
    allow_none: bool = True,
) -> Optional[List[str]]:
    if summaries is None:
        return None if allow_none else []

    if not isinstance(summaries, list):
        raise ValueError("summaries must be a list of strings")

    normalized: List[str] = []
    for item in summaries:
        if item is None:
            continue
        text = str(item).strip()
        if text:
            normalized.append(text)
    return normalized


def _conversation_status_to_str(status: Any) -> Optional[str]:
    if isinstance(status, ConversationStatus):
        return status.value
    if isinstance(status, Enum):
        status = status.value
    if status is None:
        return None
    normalized = str(status).strip()
    return normalized or None


async def get_conversation_by_id_service(
    conversation_id: Optional[str],
    *,
    include_inactive: bool = True,
) -> Optional[Conversation]:
    normalized_id = (conversation_id or "").strip()
    if not normalized_id or normalized_id.lower() == "string":
        return None

    try:
        conversation = await Conversation.get(normalized_id)
    except (ValueError, TypeError, PydanticCoreValidationError) as exc:
        raise ValueError("Invalid conversation_id format") from exc

    if not conversation:
        return None
    if not include_inactive and not conversation.is_active:
        return None
    return conversation


async def get_latest_conversation_by_customer_id_service(customer_id: Optional[str]) -> Optional[Conversation]:
    normalized_customer_id = (customer_id or "").strip()
    if not normalized_customer_id:
        return None

    return await Conversation.find(
        Conversation.customer_id == normalized_customer_id
    ).sort(-Conversation.updated_at).first_or_none()


async def get_latest_conversation_by_customer_name_service(customer_name: Optional[str]) -> Optional[Conversation]:
    normalized_customer_name = (customer_name or "").strip()
    if not normalized_customer_name:
        return None

    return await Conversation.find(
        Conversation.customer_name == normalized_customer_name
    ).sort(-Conversation.updated_at).first_or_none()


async def update_conversation_profile_service(
    conversation: Conversation,
    *,
    channel: Optional[str],
    customer_name: Optional[str],
    customer_id: Optional[str],
) -> Conversation:
    has_updates = False

    normalized_channel = _normalize_optional_text_value(channel)
    if normalized_channel and conversation.channel != normalized_channel:
        conversation.channel = normalized_channel
        has_updates = True

    normalized_customer_name = _normalize_optional_text_value(customer_name)
    if normalized_customer_name and conversation.customer_name != normalized_customer_name:
        conversation.customer_name = normalized_customer_name
        has_updates = True

    normalized_customer_id = _normalize_optional_text_value(customer_id)
    if normalized_customer_id and conversation.customer_id != normalized_customer_id:
        conversation.customer_id = normalized_customer_id
        has_updates = True

    if has_updates:
        conversation.updated_at = now_vn()
        await conversation.save()

    return conversation


async def create_conversation_service(
    *,
    channel: Optional[str],
    customer_name: Optional[str],
    customer_id: Optional[str],
    status: Optional[Any] = ConversationStatus.NEW,
    summaries: Optional[Any] = None,
) -> Conversation:
    normalized_status = _normalize_conversation_status(status, allow_none=False)
    normalized_summaries = _normalize_conversation_summaries(summaries, allow_none=True)

    conversation = Conversation(
        channel=_normalize_optional_text_value(channel),
        customer_name=_normalize_optional_text_value(customer_name),
        customer_id=_normalize_optional_text_value(customer_id),
        is_active=True,
        status=normalized_status or ConversationStatus.NEW,
        summaries=normalized_summaries,
        version=get_system_version_for_new_conversation(),
        created_at=now_vn(),
        updated_at=now_vn(),
    )
    await conversation.insert()
    return conversation


async def create_conversation_crud_service(
    *,
    channel: Optional[str] = None,
    customer_name: Optional[str] = None,
    customer_id: Optional[str] = None,
    status: Optional[Any] = ConversationStatus.NEW,
    summaries: Optional[Any] = None,
) -> Conversation:
    return await create_conversation_service(
        channel=channel,
        customer_name=customer_name,
        customer_id=customer_id,
        status=status,
        summaries=summaries,
    )


async def update_conversation_crud_service(
    conversation_id: Optional[str],
    *,
    channel: Any = _UNSET,
    customer_name: Any = _UNSET,
    customer_id: Any = _UNSET,
    status: Any = _UNSET,
    summaries: Any = _UNSET,
    is_active: Any = _UNSET,
) -> Optional[Conversation]:
    conversation = await get_conversation_by_id_service(conversation_id)
    if not conversation:
        return None

    has_updates = False

    if channel is not _UNSET:
        normalized_channel = _normalize_optional_text_value(channel)
        if conversation.channel != normalized_channel:
            conversation.channel = normalized_channel
            has_updates = True

    if customer_name is not _UNSET:
        normalized_customer_name = _normalize_optional_text_value(customer_name)
        if conversation.customer_name != normalized_customer_name:
            conversation.customer_name = normalized_customer_name
            has_updates = True

    if customer_id is not _UNSET:
        normalized_customer_id = _normalize_optional_text_value(customer_id)
        if conversation.customer_id != normalized_customer_id:
            conversation.customer_id = normalized_customer_id
            has_updates = True

    if status is not _UNSET:
        normalized_status = _normalize_conversation_status(status, allow_none=False)
        current_status = _conversation_status_to_str(conversation.status)
        if (
            normalized_status == ConversationStatus.CONFIRMED
            and current_status
            not in {
                ConversationStatus.HANDOVER.value,
                ConversationStatus.APILIMIT.value,
                ConversationStatus.CONFIRMED.value,
            }
        ):
            raise ValueError("Conversation can only be confirmed from handover or apilimit status")
        if normalized_status and conversation.status != normalized_status:
            conversation.status = normalized_status
            has_updates = True
            if (
                current_status == ConversationStatus.ORDER_PENDING.value
                and normalized_status == ConversationStatus.NEW
                and getattr(conversation, "order_note", None) is not None
            ):
                conversation.order_note = None
                has_updates = True

    if summaries is not _UNSET:
        normalized_summaries = _normalize_conversation_summaries(summaries, allow_none=True)
        if conversation.summaries != normalized_summaries:
            conversation.summaries = normalized_summaries
            has_updates = True

    if is_active is not _UNSET:
        if not isinstance(is_active, bool):
            raise ValueError("is_active must be a boolean")
        if conversation.is_active != is_active:
            conversation.is_active = is_active
            has_updates = True

    if has_updates:
        conversation.updated_at = now_vn()
        await conversation.save()

    return conversation


async def delete_conversation_service(
    conversation_id: Optional[str],
    *,
    soft_delete: bool = True,
) -> bool:
    conversation = await get_conversation_by_id_service(conversation_id)
    if not conversation:
        return False

    if soft_delete:
        if not conversation.is_active:
            return True
        conversation.is_active = False
        conversation.updated_at = now_vn()
        await conversation.save()
        return True

    await conversation.delete()
    return True


async def list_conversations_service(
    *,
    status: Optional[Any] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    size: int = 10,
    include_inactive: bool = False,
) -> Dict[str, Any]:
    normalized_page = max(1, _to_int_or_default(page, 1))
    normalized_size = min(100, max(1, _to_int_or_default(size, 10)))
    skip = (normalized_page - 1) * normalized_size

    match_query: Dict[str, Any] = {}
    if not include_inactive:
        match_query["is_active"] = True

    normalized_status: Optional[ConversationStatus] = None
    if status is not None and str(status).strip():
        normalized_status = _normalize_conversation_status(status, allow_none=False)
    if normalized_status:
        match_query["status"] = normalized_status.value

    normalized_keyword = str(keyword or "").strip()
    if normalized_keyword:
        match_query["$or"] = [
            {"customer_name": {"$regex": normalized_keyword, "$options": "i"}},
            {"customer_id": {"$regex": normalized_keyword, "$options": "i"}},
            {"channel": {"$regex": normalized_keyword, "$options": "i"}},
        ]

    pipeline = [
        {"$match": match_query},
        {"$sort": {"updated_at": -1}},
        {
            "$facet": {
                "items": [
                    {"$skip": skip},
                    {"$limit": normalized_size},
                    {
                        "$lookup": {
                            "from": Message.Settings.name,
                            "let": {"conversation_id": "$_id"},
                            "pipeline": [
                                {"$match": {"$expr": {"$eq": ["$conversation_id", "$$conversation_id"]}}},
                                {"$count": "count"},
                            ],
                            "as": "message_stats",
                        }
                    },
                    {
                        "$addFields": {
                            "message_count": {
                                "$ifNull": [{"$arrayElemAt": ["$message_stats.count", 0]}, 0]
                            }
                        }
                    },
                    {
                        "$project": {
                            "channel": 1,
                            "customer_name": 1,
                            "customer_id": 1,
                            "pancake_thread_type": 1,
                            "pancake_info_url": 1,
                            "order_note": 1,
                            "is_active": 1,
                            "status": 1,
                            "summaries": 1,
                            "version": 1,
                            "created_at": 1,
                            "updated_at": 1,
                            "message_count": 1,
                        }
                    },
                ],
                "total": [{"$count": "count"}],
            }
        },
    ]

    rows = await Conversation.aggregate(pipeline).to_list()
    data = rows[0] if rows else {}

    raw_items = data.get("items") or []
    items: List[Dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        raw_id = row.pop("_id", None)
        row["id"] = str(raw_id) if raw_id is not None else ""
        row["status"] = _conversation_status_to_str(row.get("status"))
        row["created_at"] = _to_vn_aware_datetime(row.get("created_at"))
        row["updated_at"] = _to_vn_aware_datetime(row.get("updated_at"))
        row["message_count"] = max(0, _to_int_or_default(row.get("message_count"), 0))
        items.append(row)

    total_rows = data.get("total") or []
    total = 0
    if total_rows and isinstance(total_rows[0], dict):
        total = max(0, _to_int_or_default(total_rows[0].get("count"), 0))

    return {
        "items": items,
        "total": total,
        "page": normalized_page,
        "size": normalized_size,
    }

async def _get_recent_user_history(conversation_id, limit: int = 5) -> List[str]:
    rows = await Message.find(
        {
            "conversation_id": conversation_id,
            "role": "user",
        }
    ).sort(-Message.created_at).limit(limit).to_list()

    # Return oldest -> newest so LLM sees natural timeline.
    history: List[str] = []
    for row in reversed(rows):
        content = (row.content or "").strip()
        if content:
            history.append(content)
    return history


async def _get_recent_conversation_history(
    conversation_id,
    limit: int = 5,
) -> List[Dict[str, str]]:
    rows = await Message.find(
        {
            "conversation_id": conversation_id,
        }
    ).sort(-Message.created_at).limit(limit).to_list()

    # Return oldest -> newest for better prompt chronology.
    history: List[Dict[str, str]] = []
    for row in reversed(rows):
        content = (row.content or "").strip()
        if not content:
            continue
        raw_role = (row.role or "user").strip().lower() or "user"
        if raw_role == "bot":
            role = "assistant"
        elif raw_role in {"user", "assistant", "system"}:
            role = raw_role
        else:
            role = "user"
        history.append({"role": role, "content": content})
    return history


async def _build_rag_payload(
    *,
    latest_user_message: str,
    branch: Optional[str],
    slots: Dict[str, Any],
    conversation_id: Optional[Any],
    current_intent: Optional[str] = None,
    previous_next_slot: Optional[str] = None,
    current_slots: Optional[Dict[str, Any]] = None,
    stored_rag_anchor: Optional[str] = None,
    recent_conversation_history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    conversation_history = recent_conversation_history
    if conversation_history is None:
        if conversation_id:
            conversation_history = await _get_recent_conversation_history(conversation_id, limit=5)
        else:
            conversation_history = []

    question_text = _build_rag_question_text(
        latest_user_message=latest_user_message,
        branch=branch,
        slots=slots,
        current_intent=current_intent,
        previous_next_slot=previous_next_slot,
        current_slots=current_slots,
        recent_conversation_history=conversation_history,
        stored_rag_anchor=stored_rag_anchor,
    )
    return {
        # RAG endpoint contract uses a single `question` field.
        "question": question_text,
        "conversation_history": conversation_history,
    }


async def _get_previous_state(conversation_id) -> Optional[ConversationState]:
    return await ConversationState.find(
        {
            "conversation_id": conversation_id,
            "branch_id": {"$exists": True},
        }
    ).sort(-ConversationState.updated_at).first_or_none()


async def _get_state_slots_map(state_id) -> Dict[str, Any]:
    rows = await StateSlot.find(StateSlot.conversation_state_id == state_id).to_list()
    slots: Dict[str, Any] = {}
    for row in rows:
        if row.slot_catalog_name:
            slots[row.slot_catalog_name] = row.slot_value_json.get("value", row.slot_value)
    return slots


async def _get_state_asked_slots(state_id) -> List[str]:
    rows = await StateAskedSlot.find(
        StateAskedSlot.conversation_state_id == state_id
    ).to_list()
    result: List[str] = []
    for row in rows:
        if row.slot_catalog_name:
            result.append(row.slot_catalog_name)
    return result


async def _get_state_missing_slots(state_id) -> List[StateMissingSlot]:
    return await StateMissingSlot.find(
        StateMissingSlot.conversation_state_id == state_id
    ).to_list()


def decide_next_action_service(
    *,
    missing_slots: List[str],
    slots: Dict[str, Any],
) -> tuple[Optional[str], Optional[str], str]:
    if missing_slots:
        return "ask_slot", missing_slots[0], "missing_slot_detected"

    return "call_rag", None, "no_missing_slot_call_rag"


async def _upsert_state_slot_value(
    state_id,
    slot_name: str,
    slot_value: Any,
) -> None:
    slot_row = await StateSlot.find_one(
        {
            "conversation_state_id": state_id,
            "slot_catalog_name": slot_name,
        }
    )
    if slot_row:
        slot_row.slot_value = _to_slot_value(slot_value)
        slot_row.slot_value_json = {"value": slot_value}
        slot_row.updated_at = now_vn()
        await slot_row.save()
        return

    slot_row = StateSlot(
        conversation_state_id=state_id,
        slot_catalog_name=slot_name,
        slot_value=_to_slot_value(slot_value),
        slot_value_json={"value": slot_value},
        created_at=now_vn(),
        updated_at=now_vn(),
    )
    await slot_row.insert()


def _serialize_base_document(doc: Any) -> Dict[str, Any]:
    return {
        "id": str(doc.id),
        "created_at": _to_vn_aware_datetime(doc.created_at),
        "updated_at": _to_vn_aware_datetime(doc.updated_at),
    }


def _serialize_message(message: Message) -> Dict[str, Any]:
    data = _serialize_base_document(message)
    data.update(
        {
            "conversation_id": str(message.conversation_id),
            "message_mid": message.message_mid,
            "role": message.role,
            "content": message.content,
            "meta": message.meta,
        }
    )
    return data


def _serialize_state_slot(slot: StateSlot) -> Dict[str, Any]:
    data = _serialize_base_document(slot)
    data.update(
        {
            "conversation_state_id": str(slot.conversation_state_id),
            "slot_catalog_name": slot.slot_catalog_name,
            "slot_value": slot.slot_value,
            "slot_value_json": slot.slot_value_json,
        }
    )
    return data


def _serialize_state_missing_slot(slot: StateMissingSlot) -> Dict[str, Any]:
    data = _serialize_base_document(slot)
    data.update(
        {
            "conversation_state_id": str(slot.conversation_state_id),
            "slot_catalog_name": slot.slot_catalog_name,
            "priority": slot.priority,
            "sort_order": slot.sort_order,
        }
    )
    return data


def _serialize_state_asked_slot(slot: StateAskedSlot) -> Dict[str, Any]:
    data = _serialize_base_document(slot)
    data.update(
        {
            "conversation_state_id": str(slot.conversation_state_id),
            "slot_catalog_name": slot.slot_catalog_name,
        }
    )
    return data


async def _build_conversation_detail(conversation: Conversation) -> Dict[str, Any]:
    messages = await Message.find(
        Message.conversation_id == conversation.id
    ).sort(Message.created_at).to_list()

    states = await ConversationState.find(
        {
            "conversation_id": conversation.id,
            "branch_id": {"$exists": True},
        }
    ).sort(ConversationState.created_at).to_list()

    state_ids = [state.id for state in states]
    branch_ids = list({state.branch_id for state in states})
    branch_name_map: Dict[str, str] = {}
    slots_by_state: Dict[str, List[Dict[str, Any]]] = {}
    missing_by_state: Dict[str, List[Dict[str, Any]]] = {}
    asked_by_state: Dict[str, List[Dict[str, Any]]] = {}

    if state_ids:
        state_slots = await StateSlot.find(
            {"conversation_state_id": {"$in": state_ids}}
        ).to_list()
        for slot in state_slots:
            key = str(slot.conversation_state_id)
            slots_by_state.setdefault(key, []).append(_serialize_state_slot(slot))

        state_missing_slots = await StateMissingSlot.find(
            {"conversation_state_id": {"$in": state_ids}}
        ).to_list()
        for slot in state_missing_slots:
            key = str(slot.conversation_state_id)
            missing_by_state.setdefault(key, []).append(_serialize_state_missing_slot(slot))

        state_asked_slots = await StateAskedSlot.find(
            {"conversation_state_id": {"$in": state_ids}}
        ).to_list()
        for slot in state_asked_slots:
            key = str(slot.conversation_state_id)
            asked_by_state.setdefault(key, []).append(_serialize_state_asked_slot(slot))

    if branch_ids:
        branches = await Branch.find({"_id": {"$in": branch_ids}}).to_list()
        branch_name_map = {str(branch.id): branch.name for branch in branches}

    conversation_data = _serialize_base_document(conversation)
    conversation_data.update(
        {
            "channel": conversation.channel,
            "customer_name": conversation.customer_name,
            "customer_id": conversation.customer_id,
            "pancake_thread_type": getattr(conversation, "pancake_thread_type", None),
            "pancake_info_url": getattr(conversation, "pancake_info_url", None),
            "order_note": getattr(conversation, "order_note", None),
            "is_active": conversation.is_active,
            "status": _conversation_status_to_str(conversation.status),
            "summaries": conversation.summaries,
            "version": getattr(conversation, "version", None),
        }
    )

    states_data: List[Dict[str, Any]] = []
    for conversation_state in states:
        state_id_str = str(conversation_state.id)
        state_data = _serialize_base_document(conversation_state)
        state_data.update(
            {
                "conversation_id": str(conversation_state.conversation_id),
                "message_id": str(conversation_state.message_id)
                if conversation_state.message_id
                else None,
                "branch_id": str(conversation_state.branch_id),
                "branch": branch_name_map.get(str(conversation_state.branch_id)),
                "intent": conversation_state.intent,
                "rag_anchor_text": conversation_state.rag_anchor_text,
                "turn_index": conversation_state.turn_index,
                "next_action": conversation_state.next_action,
                "prev_slot": conversation_state.prev_slot,
                "next_slot": conversation_state.next_slot,
                "state_slots": slots_by_state.get(state_id_str, []),
                "state_missing_slots": missing_by_state.get(state_id_str, []),
                "state_asked_slots": asked_by_state.get(state_id_str, []),
            }
        )
        states_data.append(state_data)

    return {
        "conversation": conversation_data,
        "messages": [_serialize_message(message) for message in messages],
        "conversation_states": states_data,
    }


async def extract_intent_service(
    text: str,
    conversation: Conversation,
    message_mid: Optional[str],
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
    logger.info(
        "API_EXTRACT_INTENT_REQUEST payload=%s",
        _safe_json_dumps(
            {
                "text": text,
                "conversation_id": str(conversation.id),
                "message_mid": message_mid,
                "metadata": metadata,
            }
        ),
    )

    previous_state = await _get_previous_state(conversation.id)
    asked_slots_context: List[str] = []
    missing_slots_context: List[str] = []
    if previous_state:
        asked_slots_context = await _get_state_asked_slots(previous_state.id)
        missing_rows_context = await _get_state_missing_slots(previous_state.id)
        missing_slots_context = [
            (row.slot_catalog_name or "").strip()
            for row in missing_rows_context
            if (row.slot_catalog_name or "").strip()
        ]

    history_messages = await _get_recent_user_history(conversation.id, limit=5)

    message = Message(
        conversation_id=conversation.id,
        message_mid=message_mid,
        role="user",
        content=text,
        meta=metadata,
        created_at=now_vn(),
        updated_at=now_vn(),
    )
    await message.insert()
    logger.info(
        "STEP_02_MESSAGE_SAVED conversation_id=%s message_id=%s",
        conversation.id,
        message.id,
    )

    intent, intent_confidence, intent_raw = await detect_intent(
        text,
        history=history_messages,
        asked_slots=asked_slots_context,
        missing_slots=missing_slots_context,
    )
    conversation.updated_at = now_vn()
    await conversation.save()
    result = {
        "intent": intent,
        "confidence": float(intent_confidence),
        "raw_response": intent_raw,
        "message_id": str(message.id),
        "conversation_id": str(conversation.id),
        "history_count": len(history_messages),
    }
    return result


async def get_latest_state_service(conversation_id) -> Optional[ConversationState]:
    return await _get_previous_state(conversation_id)


async def get_state_snapshot_service(state_id) -> Dict[str, Any]:
    slots = await _get_state_slots_map(state_id)
    missing_rows = await _get_state_missing_slots(state_id)
    asked_slots = await _get_state_asked_slots(state_id)
    missing_slots = [
        (row.slot_catalog_name or "").strip()
        for row in missing_rows
        if (row.slot_catalog_name or "").strip()
    ]
    asked_slots = [
        slot
        for slot in asked_slots
        if slot and _has_slot_value(slots.get(slot))
    ]
    return {
        "slots": slots,
        "missing_slots": missing_slots,
        "asked_slots": asked_slots,
    }


async def insert_bot_messages_service(
    *,
    conversation_id,
    reply_to_message_id: Optional[str],
    messages: List[str],
    state_id: Optional[str] = None,
    action: Optional[str] = None,
    slot: Optional[str] = None,
) -> List[str]:
    message_ids: List[str] = []
    for content in messages:
        normalized = (content or "").strip()
        if not normalized:
            continue
        bot_message = Message(
            conversation_id=conversation_id,
            role="bot",
            content=normalized,
            meta={
                "state_id": str(state_id) if state_id else None,
                "action": action,
                "slot": slot,
                "reply_to_message_id": str(reply_to_message_id) if reply_to_message_id else None,
            },
            created_at=now_vn(),
            updated_at=now_vn(),
        )
        await bot_message.insert()
        message_ids.append(str(bot_message.id))
    return message_ids


async def build_conversation_detail_service(conversation: Conversation) -> Dict[str, Any]:
    return await _build_conversation_detail(conversation)


async def get_conversation_detail_service(
    conversation_id: Optional[str],
    *,
    include_inactive: bool = True,
) -> Optional[Dict[str, Any]]:
    conversation = await get_conversation_by_id_service(
        conversation_id,
        include_inactive=include_inactive,
    )
    if not conversation:
        return None
    return await _build_conversation_detail(conversation)


async def get_conversation_messages_service(
    conversation_id: Optional[str],
    *,
    include_inactive: bool = True,
) -> Optional[List[Dict[str, Any]]]:
    conversation = await get_conversation_by_id_service(
        conversation_id,
        include_inactive=include_inactive,
    )
    if not conversation:
        return None

    messages = await Message.find(
        Message.conversation_id == conversation.id
    ).sort(Message.created_at).to_list()
    return [_serialize_message(message) for message in messages]


async def generate_slot_question_service(
    slot_name: str,
    branch: Optional[str],
    intent: str,
    known_slots: Dict[str, Any],
    user_text: str,
    customer_name: Optional[str] = None,
    conversation_id: Optional[str] = None,
    asked_slot_values: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    slot_context = get_slot_definition(slot_name) or {}

    recent_history: List[Dict[str, str]] = []
    resolved_conversation: Optional[Conversation] = None
    if conversation_id:
        normalized_id = conversation_id.strip()
        if normalized_id and normalized_id.lower() != "string":
            try:
                resolved_conversation = await Conversation.get(normalized_id)
            except (ValueError, TypeError, PydanticCoreValidationError) as exc:
                raise ValueError("Invalid conversation_id format") from exc

    if not resolved_conversation and customer_name:
        resolved_conversation = await Conversation.find(
            Conversation.customer_name == customer_name
        ).sort(-Conversation.updated_at).first_or_none()

    if resolved_conversation:
        recent_history = await _get_recent_conversation_history(resolved_conversation.id, limit=5)
        if not customer_name:
            customer_name = resolved_conversation.customer_name

    logger.info(
        "API_GENERATE_SLOT_QUESTION_CONTEXT slot_name=%s conversation_id=%s resolved_conversation_id=%s history_count=%s",
        slot_name,
        conversation_id,
        str(resolved_conversation.id) if resolved_conversation else None,
        len(recent_history),
    )

    question, raw = await generate_slot_question(
        slot_name=slot_name,
        branch=branch,
        intent=intent,
        known_slots=known_slots,
        asked_slot_values=asked_slot_values or {},
        user_text=user_text,
        customer_name=customer_name,
        recent_history=recent_history,
    )
    question = _personalize_question(question, customer_name)
    return {
        "slot_name": slot_name,
        "question": question,
        "slot_context": slot_context,
        "raw_response": raw,
    }
