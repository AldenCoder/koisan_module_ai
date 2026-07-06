from __future__ import annotations

import asyncio
import re
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Any, Awaitable, Callable, Iterable, Optional

from app.api.dependencies.time import now_vn
from app.core.config import settings
from app.models.conversations import Conversation
from app.models.messages import Message, MessageRole
from logs.logging_config import logger


BASELINE_CONVERSATION_VERSION = "1.0"
VERSION_STATUS_OLDER = "older"
VERSION_STATUS_SAME = "same"
VERSION_STATUS_NEWER = "newer"
VERSION_STATUS_INVALID = "invalid"
VERSION_STATUS_UNKNOWN = "unknown"
AI_VERSION_CONTEXT_MIN_MESSAGES = 1
AI_VERSION_CONTEXT_MAX_MESSAGES_LIMIT = 50
AI_VERSION_CONTEXT_DEFAULT_MAX_MESSAGES = 30

_VERSION_RE = re.compile(r"^\d+\.\d+(?:\.\d+)?$")
_URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)\S+")
AI_VERSION_HISTORY_ROLES = {
    MessageRole.STAFF.value,
    MessageRole.USER.value,
    MessageRole.BOT.value,
}
_upgrade_lock_registry_guard = Lock()
_upgrade_locks: dict[str, asyncio.Lock] = {}


@dataclass(frozen=True)
class ParsedVersion:
    raw: Any
    normalized: str
    parts: tuple[int, int, int]


@dataclass(frozen=True)
class VersionComparison:
    status: str
    conversation_version: Optional[str]
    system_version: Optional[str]
    reason: Optional[str] = None

    @property
    def should_upgrade(self) -> bool:
        return self.status == VERSION_STATUS_OLDER


@dataclass(frozen=True)
class VersionedAiUserSelection:
    ai_user: str
    version: Optional[str]
    status: str
    should_upgrade: bool = False
    reason: Optional[str] = None


@dataclass(frozen=True)
class AiVersionHistoryItem:
    role: str
    content: str
    created_at: Optional[datetime] = None
    message_id: Optional[str] = None
    message_mid: Optional[str] = None


InitAiSessionCallback = Callable[[Any, str], Awaitable[dict[str, Any]]]
SendAiMessageCallback = Callable[
    [Any, str, str, str],
    Awaitable[dict[str, Any]],
]
ReloadConversationCallback = Callable[[Any], Awaitable[Any]]


def get_ai_conversation_version() -> str:
    return str(getattr(settings, "ai_conversation_version", "1.1") or "").strip()


def get_ai_version_context_max_messages() -> int:
    raw = getattr(
        settings,
        "pancake_handover_context_max_messages",
        AI_VERSION_CONTEXT_DEFAULT_MAX_MESSAGES,
    )
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = AI_VERSION_CONTEXT_DEFAULT_MAX_MESSAGES
    return min(
        AI_VERSION_CONTEXT_MAX_MESSAGES_LIMIT,
        max(AI_VERSION_CONTEXT_MIN_MESSAGES, value),
    )


def normalize_conversation_version(value: Any) -> str:
    normalized = str(value or "").strip()
    return normalized or BASELINE_CONVERSATION_VERSION


def parse_version(value: Any) -> ParsedVersion:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError("missing_version")
    if not _VERSION_RE.fullmatch(normalized):
        raise ValueError("invalid_version_format")

    parts = tuple(int(part) for part in normalized.split("."))
    if len(parts) == 2:
        parts = (*parts, 0)
    return ParsedVersion(raw=value, normalized=normalized, parts=parts)


def compare_conversation_version(
    conversation_version: Any,
    system_version: Any,
) -> VersionComparison:
    normalized_conversation_version = normalize_conversation_version(conversation_version)
    try:
        parsed_conversation_version = parse_version(normalized_conversation_version)
    except ValueError as exc:
        return VersionComparison(
            status=VERSION_STATUS_INVALID,
            conversation_version=normalized_conversation_version,
            system_version=str(system_version or "").strip() or None,
            reason=f"invalid_conversation_version:{exc}",
        )

    try:
        parsed_system_version = parse_version(system_version)
    except ValueError as exc:
        return VersionComparison(
            status=VERSION_STATUS_INVALID,
            conversation_version=parsed_conversation_version.normalized,
            system_version=str(system_version or "").strip() or None,
            reason=f"invalid_system_version:{exc}",
        )

    if parsed_conversation_version.parts < parsed_system_version.parts:
        status = VERSION_STATUS_OLDER
    elif parsed_conversation_version.parts > parsed_system_version.parts:
        status = VERSION_STATUS_NEWER
    else:
        status = VERSION_STATUS_SAME

    return VersionComparison(
        status=status,
        conversation_version=parsed_conversation_version.normalized,
        system_version=parsed_system_version.normalized,
    )


def build_versioned_ai_user(sender_id: Any, version: Any) -> str:
    normalized_sender_id = str(sender_id or "").strip()
    if not normalized_sender_id:
        raise ValueError("missing_sender_id")

    parsed_version = parse_version(version)
    return f"{normalized_sender_id}:v{parsed_version.normalized}"


def select_ai_user_for_existing_flow(
    *,
    sender_id: Any,
    conversation_version: Any,
    system_version: Any | None = None,
) -> VersionedAiUserSelection:
    normalized_sender_id = str(sender_id or "").strip()
    if not normalized_sender_id:
        raise ValueError("missing_sender_id")

    target_system_version = get_ai_conversation_version() if system_version is None else system_version
    comparison = compare_conversation_version(conversation_version, target_system_version)
    if comparison.status == VERSION_STATUS_SAME:
        return VersionedAiUserSelection(
            ai_user=build_versioned_ai_user(normalized_sender_id, comparison.conversation_version),
            version=comparison.conversation_version,
            status=comparison.status,
        )
    if comparison.status == VERSION_STATUS_NEWER:
        return VersionedAiUserSelection(
            ai_user=build_versioned_ai_user(normalized_sender_id, comparison.conversation_version),
            version=comparison.conversation_version,
            status=comparison.status,
            reason="conversation_version_newer_than_system",
        )
    if comparison.status == VERSION_STATUS_OLDER:
        return VersionedAiUserSelection(
            ai_user=build_versioned_ai_user(normalized_sender_id, comparison.system_version),
            version=comparison.system_version,
            status=comparison.status,
            should_upgrade=True,
            reason="version_upgrade_required",
        )

    return VersionedAiUserSelection(
        ai_user=normalized_sender_id,
        version=comparison.conversation_version,
        status=comparison.status,
        reason=comparison.reason or "version_upgrade_required",
    )


def get_system_version_for_new_conversation() -> Optional[str]:
    version = get_ai_conversation_version()
    try:
        return parse_version(version).normalized
    except ValueError:
        return None


async def reset_ai_initialization_for_version_session(conversation: Any) -> None:
    conversation.fb_ai_initialized = False
    conversation.fb_ai_initialized_at = None
    conversation.updated_at = now_vn()
    await conversation.save()


async def mark_conversation_version_completed(
    conversation: Any,
    *,
    version: Any,
) -> None:
    parsed_version = parse_version(version)
    conversation.version = parsed_version.normalized
    conversation.updated_at = now_vn()
    await conversation.save()


def sanitize_history_text(content: Any) -> str:
    text = str(content or "").strip()
    if not text:
        return ""
    text = _URL_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip(" \t\r\n,;:-")
    return text


def _lock_key_for_conversation_version(conversation_id: Any, target_version: Any) -> str:
    return f"{str(conversation_id or '').strip()}:{str(target_version or '').strip()}"


def _get_upgrade_lock(conversation_id: Any, target_version: Any) -> asyncio.Lock:
    key = _lock_key_for_conversation_version(conversation_id, target_version)
    with _upgrade_lock_registry_guard:
        lock = _upgrade_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _upgrade_locks[key] = lock
        return lock


@asynccontextmanager
async def ai_version_upgrade_lock(conversation_id: Any, target_version: Any):
    lock = _get_upgrade_lock(conversation_id, target_version)
    await lock.acquire()
    try:
        yield
    finally:
        lock.release()


def clear_ai_version_upgrade_locks_for_tests() -> None:
    with _upgrade_lock_registry_guard:
        _upgrade_locks.clear()


def _normalize_excluded_values(values: Optional[Iterable[Any]]) -> set[str]:
    return {str(value).strip() for value in (values or []) if str(value).strip()}


def _message_sort_value(item: AiVersionHistoryItem) -> tuple[datetime, str]:
    created_at = item.created_at if isinstance(item.created_at, datetime) else datetime.min
    return (created_at, item.message_id or item.message_mid or "")


def _history_role_label(role: Any) -> Optional[str]:
    normalized_role = str(role or "").strip().lower()
    if normalized_role == MessageRole.STAFF.value:
        return "[Nhân viên]"
    if normalized_role == MessageRole.USER.value:
        return "[Khách]"
    if normalized_role == MessageRole.BOT.value:
        return "[Bot]"
    return None


def _should_skip_history_row(
    row: Any,
    *,
    exclude_message_ids: set[str],
    exclude_message_mids: set[str],
) -> bool:
    row_id = str(getattr(row, "id", "") or "").strip()
    if row_id and row_id in exclude_message_ids:
        return True

    message_mid = str(getattr(row, "message_mid", "") or "").strip()
    if message_mid and message_mid in exclude_message_mids:
        return True

    return False


def _row_to_history_item(row: Any) -> Optional[AiVersionHistoryItem]:
    role = str(getattr(row, "role", "") or "").strip().lower()
    if role not in AI_VERSION_HISTORY_ROLES:
        return None

    content = sanitize_history_text(getattr(row, "content", ""))
    if not content:
        return None

    return AiVersionHistoryItem(
        role=role,
        content=content,
        created_at=getattr(row, "created_at", None),
        message_id=str(getattr(row, "id", "") or "").strip() or None,
        message_mid=str(getattr(row, "message_mid", "") or "").strip() or None,
    )


async def get_ai_version_text_history_items(
    *,
    conversation_id: Any,
    limit: Optional[int] = None,
    before_created_at: Optional[datetime] = None,
    exclude_message_ids: Optional[Iterable[Any]] = None,
    exclude_message_mids: Optional[Iterable[Any]] = None,
) -> list[AiVersionHistoryItem]:
    if conversation_id is None:
        return []

    max_messages = get_ai_version_context_max_messages() if limit is None else limit
    try:
        normalized_limit = int(max_messages)
    except (TypeError, ValueError):
        normalized_limit = get_ai_version_context_max_messages()
    normalized_limit = min(
        AI_VERSION_CONTEXT_MAX_MESSAGES_LIMIT,
        max(AI_VERSION_CONTEXT_MIN_MESSAGES, normalized_limit),
    )

    excluded_ids = _normalize_excluded_values(exclude_message_ids)
    excluded_mids = _normalize_excluded_values(exclude_message_mids)

    query_filter: dict[str, Any] = {
        "conversation_id": conversation_id,
        "role": {"$in": sorted(AI_VERSION_HISTORY_ROLES)},
        "content": {"$nin": ["", None]},
    }
    if before_created_at is not None:
        query_filter["created_at"] = {"$lt": before_created_at}

    selected: list[AiVersionHistoryItem] = []
    offset = 0
    batch_size = max(normalized_limit * 3, 20)
    max_scan = max(normalized_limit * 10, batch_size)

    while len(selected) < normalized_limit and offset < max_scan:
        query = Message.find(query_filter).sort(-Message.created_at)
        supports_skip = hasattr(query, "skip")
        if supports_skip:
            query = query.skip(offset)
        rows = await query.limit(batch_size).to_list()
        if not rows:
            break

        for row in rows:
            if _should_skip_history_row(
                row,
                exclude_message_ids=excluded_ids,
                exclude_message_mids=excluded_mids,
            ):
                continue
            item = _row_to_history_item(row)
            if item is None:
                continue
            selected.append(item)
            if len(selected) >= normalized_limit:
                break

        if len(rows) < batch_size or not supports_skip:
            break
        offset += batch_size

    selected = sorted(selected[:normalized_limit], key=_message_sort_value)
    return selected


def render_ai_version_context_message(
    *,
    history_items: Iterable[AiVersionHistoryItem],
    current_message: Any,
) -> str:
    current_text = sanitize_history_text(current_message)
    rendered_history: list[str] = []
    for item in history_items:
        label = _history_role_label(item.role)
        if not label:
            continue
        content = sanitize_history_text(item.content)
        if content:
            rendered_history.append(f"{label} {content}")

    if not rendered_history:
        return current_text

    sections = [
        "Bối cảnh hội thoại trước khi cập nhật phiên bản AI:",
        "\n".join(rendered_history),
    ]
    if current_text:
        sections.extend(["Tin nhắn hiện tại của khách:", current_text])
    return "\n\n".join(sections)


async def reload_conversation_document(conversation: Any) -> Any:
    conversation_id = getattr(conversation, "id", None)
    if not conversation_id:
        return conversation
    try:
        fresh_conversation = await Conversation.get(conversation_id)
    except Exception as exc:
        logger.warning(
            "AI_VERSION_CONVERSATION_RELOAD_FAILED conversation_id=%s error=%s",
            conversation_id,
            exc,
        )
        return conversation
    return fresh_conversation or conversation


def _conversation_id_for_log(conversation: Any) -> str:
    return str(getattr(conversation, "id", "") or "").strip()


def _result_for_invalid_or_unsupported_version(
    *,
    sender_id: str,
    conversation: Any,
    comparison: VersionComparison,
    message_mid: Optional[str],
) -> dict[str, Any]:
    if comparison.reason and "invalid_system_version" in comparison.reason:
        logger.error(
            "AI_VERSION_CHECK_FAILED reason=invalid_system_version conversation_id=%s sender_id=%s message_mid=%s conversation_version=%s system_version=%s",
            _conversation_id_for_log(conversation),
            sender_id,
            message_mid,
            comparison.conversation_version,
            comparison.system_version,
        )
    else:
        logger.warning(
            "AI_VERSION_CHECK_FAILED reason=%s conversation_id=%s sender_id=%s message_mid=%s conversation_version=%s system_version=%s",
            comparison.reason,
            _conversation_id_for_log(conversation),
            sender_id,
            message_mid,
            comparison.conversation_version,
            comparison.system_version,
        )
    return {
        "ok": True,
        "upgraded": False,
        "upgrade_skipped": True,
        "reason": comparison.reason or "invalid_ai_version",
        "ai_user": sender_id,
        "conversation": conversation,
        "comparison": comparison,
    }


async def prepare_ai_version_for_customer_message(
    *,
    conversation: Any,
    sender_id: Any,
    current_message: Any,
    message_mid: Optional[str] = None,
    before_created_at: Optional[datetime] = None,
    exclude_message_ids: Optional[Iterable[Any]] = None,
    exclude_message_mids: Optional[Iterable[Any]] = None,
    init_ai_session: InitAiSessionCallback,
    send_ai_message: SendAiMessageCallback,
    reload_conversation: Optional[ReloadConversationCallback] = None,
    system_version: Any | None = None,
    purpose: str = "ai_version_context",
    log_prefix: str = "AI_VERSION",
) -> dict[str, Any]:
    normalized_sender_id = str(sender_id or "").strip()
    if not normalized_sender_id:
        return {
            "ok": False,
            "reason": "missing_sender_id",
            "conversation": conversation,
        }

    target_system_version = get_ai_conversation_version() if system_version is None else system_version
    comparison = compare_conversation_version(
        getattr(conversation, "version", None),
        target_system_version,
    )
    logger.info(
        "%s_CHECK conversation_id=%s sender_id=%s message_mid=%s conversation_version=%s system_version=%s status=%s",
        log_prefix,
        _conversation_id_for_log(conversation),
        normalized_sender_id,
        message_mid,
        comparison.conversation_version,
        comparison.system_version,
        comparison.status,
    )

    if comparison.status == VERSION_STATUS_INVALID:
        return _result_for_invalid_or_unsupported_version(
            sender_id=normalized_sender_id,
            conversation=conversation,
            comparison=comparison,
            message_mid=message_mid,
        )

    selection = select_ai_user_for_existing_flow(
        sender_id=normalized_sender_id,
        conversation_version=getattr(conversation, "version", None),
        system_version=target_system_version,
    )
    if comparison.status in {VERSION_STATUS_SAME, VERSION_STATUS_NEWER}:
        if comparison.status == VERSION_STATUS_NEWER:
            logger.warning(
                "%s_NEWER_VERSION conversation_id=%s sender_id=%s message_mid=%s conversation_version=%s system_version=%s",
                log_prefix,
                _conversation_id_for_log(conversation),
                normalized_sender_id,
                message_mid,
                comparison.conversation_version,
                comparison.system_version,
            )
        return {
            "ok": True,
            "upgraded": False,
            "reason": selection.reason or comparison.status,
            "ai_user": selection.ai_user,
            "conversation": conversation,
            "comparison": comparison,
        }

    sanitized_current_message = sanitize_history_text(current_message)
    if not sanitized_current_message:
        logger.warning(
            "%s_SKIPPED_UNSUPPORTED_CURRENT_MESSAGE conversation_id=%s sender_id=%s message_mid=%s target_version=%s",
            log_prefix,
            _conversation_id_for_log(conversation),
            normalized_sender_id,
            message_mid,
            comparison.system_version,
        )
        return {
            "ok": True,
            "upgraded": False,
            "upgrade_skipped": True,
            "reason": "unsupported_current_message_for_version_context",
            "ai_user": normalized_sender_id,
            "conversation": conversation,
            "comparison": comparison,
        }

    target_version = comparison.system_version
    if not target_version:
        return _result_for_invalid_or_unsupported_version(
            sender_id=normalized_sender_id,
            conversation=conversation,
            comparison=VersionComparison(
                status=VERSION_STATUS_INVALID,
                conversation_version=comparison.conversation_version,
                system_version=None,
                reason="invalid_system_version:missing_version",
            ),
            message_mid=message_mid,
        )

    lock_conversation_id = getattr(conversation, "id", None) or normalized_sender_id
    started_monotonic = time.monotonic()
    async with ai_version_upgrade_lock(lock_conversation_id, target_version):
        step_started = time.monotonic()
        active_conversation = conversation
        if reload_conversation is not None:
            active_conversation = await reload_conversation(conversation)
        else:
            active_conversation = await reload_conversation_document(conversation)

        comparison_after_lock = compare_conversation_version(
            getattr(active_conversation, "version", None),
            target_system_version,
        )
        logger.info(
            "%s_LOCK_ACQUIRED conversation_id=%s sender_id=%s message_mid=%s target_version=%s status_after_reload=%s wait_seconds=%.3f",
            log_prefix,
            _conversation_id_for_log(active_conversation),
            normalized_sender_id,
            message_mid,
            target_version,
            comparison_after_lock.status,
            step_started - started_monotonic,
        )
        if comparison_after_lock.status == VERSION_STATUS_INVALID:
            return _result_for_invalid_or_unsupported_version(
                sender_id=normalized_sender_id,
                conversation=active_conversation,
                comparison=comparison_after_lock,
                message_mid=message_mid,
            )
        if not comparison_after_lock.should_upgrade:
            selection_after_lock = select_ai_user_for_existing_flow(
                sender_id=normalized_sender_id,
                conversation_version=getattr(active_conversation, "version", None),
                system_version=target_system_version,
            )
            return {
                "ok": True,
                "upgraded": False,
                "reason": "version_already_current_after_lock",
                "ai_user": selection_after_lock.ai_user,
                "conversation": active_conversation,
                "comparison": comparison_after_lock,
            }

        try:
            ai_user = build_versioned_ai_user(normalized_sender_id, target_version)
        except ValueError as exc:
            logger.error(
                "%s_FAILED step=build_ai_user conversation_id=%s sender_id=%s message_mid=%s target_version=%s error=%s",
                log_prefix,
                _conversation_id_for_log(active_conversation),
                normalized_sender_id,
                message_mid,
                target_version,
                exc,
            )
            return {
                "ok": False,
                "reason": "ai_version_build_user_failed",
                "conversation": active_conversation,
                "error": str(exc),
            }

        try:
            await reset_ai_initialization_for_version_session(active_conversation)
        except Exception as exc:
            logger.exception(
                "%s_FAILED step=reset_init_state conversation_id=%s sender_id=%s message_mid=%s target_version=%s error=%s",
                log_prefix,
                _conversation_id_for_log(active_conversation),
                normalized_sender_id,
                message_mid,
                target_version,
                exc,
            )
            return {
                "ok": False,
                "reason": "ai_version_init_state_reset_failed",
                "ai_user": ai_user,
                "conversation": active_conversation,
                "error": str(exc),
            }

        init_started = time.monotonic()
        init_result = await init_ai_session(active_conversation, ai_user)
        logger.info(
            "%s_INIT_DONE conversation_id=%s sender_id=%s message_mid=%s target_version=%s ai_user=%s ok=%s duration_seconds=%.3f",
            log_prefix,
            _conversation_id_for_log(active_conversation),
            normalized_sender_id,
            message_mid,
            target_version,
            ai_user,
            bool(init_result.get("ok")),
            time.monotonic() - init_started,
        )
        if not bool(init_result.get("ok")):
            return {
                "ok": False,
                "reason": "ai_version_init_failed",
                "ai_user": ai_user,
                "conversation": active_conversation,
                "init_result": init_result,
            }

        try:
            history_items = await get_ai_version_text_history_items(
                conversation_id=getattr(active_conversation, "id", None),
                before_created_at=before_created_at,
                exclude_message_ids=exclude_message_ids,
                exclude_message_mids=exclude_message_mids,
            )
            history_reason = None
        except Exception as exc:
            logger.warning(
                "%s_HISTORY_QUERY_FAILED conversation_id=%s sender_id=%s message_mid=%s target_version=%s error=%s",
                log_prefix,
                _conversation_id_for_log(active_conversation),
                normalized_sender_id,
                message_mid,
                target_version,
                exc,
            )
            history_items = []
            history_reason = "history_query_failed"

        context_message = render_ai_version_context_message(
            history_items=history_items,
            current_message=sanitized_current_message,
        )
        logger.info(
            "%s_CONTEXT_PREPARED conversation_id=%s sender_id=%s message_mid=%s target_version=%s history_count=%s history_reason=%s",
            log_prefix,
            _conversation_id_for_log(active_conversation),
            normalized_sender_id,
            message_mid,
            target_version,
            len(history_items),
            history_reason,
        )
        context_started = time.monotonic()
        ai_result = await send_ai_message(
            active_conversation,
            ai_user,
            context_message,
            purpose,
        )
        logger.info(
            "%s_CONTEXT_SENT conversation_id=%s sender_id=%s message_mid=%s target_version=%s ai_user=%s ok=%s history_count=%s duration_seconds=%.3f",
            log_prefix,
            _conversation_id_for_log(active_conversation),
            normalized_sender_id,
            message_mid,
            target_version,
            ai_user,
            bool(ai_result.get("ok")),
            len(history_items),
            time.monotonic() - context_started,
        )
        if not bool(ai_result.get("ok")):
            return {
                "ok": False,
                "reason": "ai_version_context_call_failed",
                "ai_user": ai_user,
                "conversation": active_conversation,
                "ai_result": ai_result,
                "history_count": len(history_items),
            }

        try:
            await mark_conversation_version_completed(
                active_conversation,
                version=target_version,
            )
        except Exception as exc:
            logger.exception(
                "%s_FAILED step=save_version conversation_id=%s sender_id=%s message_mid=%s target_version=%s error=%s",
                log_prefix,
                _conversation_id_for_log(active_conversation),
                normalized_sender_id,
                message_mid,
                target_version,
                exc,
            )
            return {
                "ok": False,
                "reason": "ai_version_save_failed",
                "ai_user": ai_user,
                "conversation": active_conversation,
                "ai_result": ai_result,
                "history_count": len(history_items),
                "error": str(exc),
            }

        logger.info(
            "%s_COMPLETED conversation_id=%s sender_id=%s message_mid=%s old_version=%s target_version=%s history_count=%s total_seconds=%.3f",
            log_prefix,
            _conversation_id_for_log(active_conversation),
            normalized_sender_id,
            message_mid,
            comparison_after_lock.conversation_version,
            target_version,
            len(history_items),
            time.monotonic() - started_monotonic,
        )
        return {
            "ok": True,
            "upgraded": True,
            "reason": "ai_version_upgraded",
            "ai_user": ai_user,
            "version": target_version,
            "conversation": active_conversation,
            "ai_result": ai_result,
            "init_result": init_result,
            "history_count": len(history_items),
            "history_reason": history_reason,
            "comparison": comparison_after_lock,
        }
