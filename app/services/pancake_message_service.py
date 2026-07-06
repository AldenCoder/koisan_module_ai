from __future__ import annotations

import asyncio
import json
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional

import httpx

from app.core.config import settings
from logs.logging_config import logger


PANCAKE_PUBLIC_API_BASE_URL = "https://pages.fm/api/public_api/v1"
PANCAKE_REPLY_INBOX_ACTION = "reply_inbox"
PANCAKE_REPLY_COMMENT_ACTION = "reply_comment"
PANCAKE_NON_RETRYABLE_STATUS_CODES = {400, 401, 403, 404}
PANCAKE_MISSING_PAGE_ACCESS_TOKENS_REASON = "missing_pancake_page_access_tokens_by_page_id"
PANCAKE_INVALID_PAGE_ACCESS_TOKENS_REASON = "invalid_pancake_page_access_tokens_by_page_id"
PANCAKE_MISSING_PAGE_ACCESS_TOKEN_FOR_PAGE_REASON = "missing_pancake_page_access_token_for_page"
PANCAKE_INTERNAL_ARTIFACT_WARNING_MARKER = "\u26a0"


class PancakePageAccessTokenConfigError(Exception):
    def __init__(self, reason: str, *, page_id: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.page_id = page_id


@contextmanager
def _suppress_httpx_info_logs():
    httpx_logger = logging.getLogger("httpx")
    original_level = httpx_logger.level
    if original_level == logging.NOTSET or original_level < logging.WARNING:
        httpx_logger.setLevel(logging.WARNING)
    try:
        yield
    finally:
        httpx_logger.setLevel(original_level)


def build_pancake_messages_api_url(*, page_id: str, conversation_id: str) -> str:
    normalized_page_id = str(page_id or "").strip()
    normalized_conversation_id = str(conversation_id or "").strip()
    return (
        f"{PANCAKE_PUBLIC_API_BASE_URL}/pages/{normalized_page_id}"
        f"/conversations/{normalized_conversation_id}/messages"
    )


def build_pancake_upload_contents_api_url(*, page_id: str) -> str:
    normalized_page_id = str(page_id or "").strip()
    return f"{PANCAKE_PUBLIC_API_BASE_URL}/pages/{normalized_page_id}/upload_contents"


def sanitize_pancake_outgoing_message(message: Any) -> str:
    text = str(message or "")
    warning_index = text.find(PANCAKE_INTERNAL_ARTIFACT_WARNING_MARKER)
    if warning_index >= 0:
        text = text[:warning_index].rstrip()

    return text.replace("*", "")


def _sanitize_pancake_reply_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if "message" not in payload:
        return payload
    return {
        **payload,
        "message": sanitize_pancake_outgoing_message(payload.get("message")),
    }


def build_pancake_reply_payload(*, message: str, action: str = PANCAKE_REPLY_INBOX_ACTION) -> dict[str, Any]:
    return {
        "action": action,
        "message": sanitize_pancake_outgoing_message(message),
    }


def build_pancake_comment_reply_payload(
    *,
    comment_message_id: str,
    message: str,
) -> dict[str, Any]:
    return {
        "action": PANCAKE_REPLY_COMMENT_ACTION,
        "message_id": str(comment_message_id or ""),
        "message": sanitize_pancake_outgoing_message(message),
    }


def build_pancake_comment_content_ids_payload(
    *,
    comment_message_id: str,
    content_ids: list[str],
) -> dict[str, Any]:
    return {
        "action": PANCAKE_REPLY_COMMENT_ACTION,
        "message_id": str(comment_message_id or ""),
        "content_ids": [str(content_id) for content_id in content_ids],
    }


def build_pancake_content_ids_payload(
    *,
    content_ids: list[str],
    action: str = PANCAKE_REPLY_INBOX_ACTION,
) -> dict[str, Any]:
    return {
        "action": action,
        "content_ids": [str(content_id) for content_id in content_ids],
    }


def _get_pancake_page_access_tokens_by_page_id() -> dict[str, str]:
    raw_tokens = getattr(settings, "pancake_page_access_tokens_by_page_id", None)
    if raw_tokens is None or str(raw_tokens).strip() == "":
        raise PancakePageAccessTokenConfigError(PANCAKE_MISSING_PAGE_ACCESS_TOKENS_REASON)

    try:
        parsed_tokens = json.loads(raw_tokens) if isinstance(raw_tokens, str) else raw_tokens
    except json.JSONDecodeError as exc:
        raise PancakePageAccessTokenConfigError(PANCAKE_INVALID_PAGE_ACCESS_TOKENS_REASON) from exc

    if not isinstance(parsed_tokens, dict):
        raise PancakePageAccessTokenConfigError(PANCAKE_INVALID_PAGE_ACCESS_TOKENS_REASON)

    tokens_by_page_id: dict[str, str] = {}
    for raw_page_id, raw_token in parsed_tokens.items():
        if not isinstance(raw_page_id, str) or not isinstance(raw_token, str):
            raise PancakePageAccessTokenConfigError(PANCAKE_INVALID_PAGE_ACCESS_TOKENS_REASON)
        page_id = raw_page_id.strip()
        token = raw_token.strip()
        if page_id and token:
            tokens_by_page_id[page_id] = token

    return tokens_by_page_id


def _pancake_page_token_error_result(
    error: PancakePageAccessTokenConfigError,
    *,
    operation: str,
    page_id: str | None = None,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": False,
        "reason": error.reason,
        "non_retryable": True,
    }
    normalized_page_id = str(error.page_id or page_id or "").strip()
    normalized_conversation_id = str(conversation_id or "").strip()
    if normalized_page_id:
        result["page_id"] = normalized_page_id
    logger.warning(
        "PANCAKE_PAGE_ACCESS_TOKEN_CONFIG_ERROR operation=%s page_id=%s conversation_id=%s reason=%s",
        operation,
        normalized_page_id or None,
        normalized_conversation_id or None,
        error.reason,
    )
    return result


def _get_pancake_page_access_token_for_page(*, page_id: str) -> str:
    normalized_page_id = str(page_id or "").strip()
    if not normalized_page_id:
        raise PancakePageAccessTokenConfigError("missing_page_id")

    tokens_by_page_id = _get_pancake_page_access_tokens_by_page_id()
    token = str(tokens_by_page_id.get(normalized_page_id) or "").strip()
    if not token:
        raise PancakePageAccessTokenConfigError(
            PANCAKE_MISSING_PAGE_ACCESS_TOKEN_FOR_PAGE_REASON,
            page_id=normalized_page_id,
        )
    return token


def _get_pancake_api_timeout_seconds(timeout: Optional[float] = None) -> float:
    raw = timeout if timeout is not None else getattr(settings, "pancake_api_timeout_seconds", 30.0)
    try:
        value = float(raw or 30.0)
    except (TypeError, ValueError):
        value = 30.0
    return max(0.1, value)


def _get_pancake_image_upload_timeout_seconds(timeout: Optional[float] = None) -> float:
    raw = timeout if timeout is not None else getattr(settings, "pancake_image_upload_timeout_seconds", 30.0)
    try:
        value = float(raw or 30.0)
    except (TypeError, ValueError):
        value = 30.0
    return max(0.1, value)


def _get_pancake_api_retry_attempts(retry_attempts: Optional[int] = None) -> int:
    raw = retry_attempts if retry_attempts is not None else getattr(settings, "pancake_api_retry_attempts", 3)
    try:
        value = int(raw or 3)
    except (TypeError, ValueError):
        value = 3
    return max(1, value)


def _get_pancake_api_retry_backoff_seconds(retry_backoff_seconds: Optional[float] = None) -> float:
    raw = retry_backoff_seconds if retry_backoff_seconds is not None else getattr(settings, "pancake_api_retry_backoff_seconds", 1.0)
    try:
        value = float(raw or 1.0)
    except (TypeError, ValueError):
        value = 1.0
    return max(0.0, value)


def _classify_pancake_error(*, status_code: Optional[int], error_body: Any = None) -> dict[str, Any]:
    non_retryable = status_code in PANCAKE_NON_RETRYABLE_STATUS_CODES if status_code is not None else False
    reason = "pancake_api_error"
    if status_code in {401, 403}:
        reason = "pancake_auth_error"
    elif status_code == 404:
        reason = "pancake_conversation_not_found"
    elif status_code == 400:
        reason = "pancake_payload_error"

    return {
        "reason": reason,
        "non_retryable": non_retryable,
        "status_code": status_code,
        "error": error_body,
    }


def _extract_pancake_content_id(response_data: Any) -> str | None:
    if not isinstance(response_data, dict):
        return None

    candidates: list[Any] = [
        response_data.get("content_id"),
        response_data.get("contentId"),
        response_data.get("id"),
    ]
    for key in ("data", "content"):
        nested = response_data.get(key)
        if isinstance(nested, dict):
            candidates.extend(
                [
                    nested.get("content_id"),
                    nested.get("contentId"),
                    nested.get("id"),
                ]
            )

    for candidate in candidates:
        normalized = str(candidate or "").strip()
        if normalized:
            return normalized
    return None


def _preview_pancake_response(value: Any, *, limit: int = 500) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        text = str(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...(truncated)"


async def _post_pancake_reply_payload(
    *,
    page_access_token: str,
    page_id: str,
    conversation_id: str,
    payload: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    url = build_pancake_messages_api_url(page_id=page_id, conversation_id=conversation_id)
    payload = _sanitize_pancake_reply_payload(payload)
    with _suppress_httpx_info_logs():
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                url,
                params={"page_access_token": page_access_token},
                json=payload,
            )

    try:
        response_data = response.json()
    except Exception:
        response_data = response.text

    if isinstance(payload.get("content_ids"), list):
        payload_kind = "content_ids"
    elif str(payload.get("content_url") or "").strip():
        payload_kind = "content_url"
    else:
        payload_kind = "message"
    payload_action = str(payload.get("action") or "").strip() or None
    content_id_count = len(payload.get("content_ids") or []) if payload_kind == "content_ids" else 0
    message_field_present = "message" in payload
    message_present = bool(str(payload.get("message") or "").strip())

    response_success = (
        response_data.get("success")
        if isinstance(response_data, dict)
        else None
    )
    if 200 <= response.status_code < 300 and response_success is not False:
        logger.info(
            "PANCAKE_POST_REPLY_PAYLOAD_OK page_id=%s conversation_id=%s status_code=%s payload_kind=%s payload_action=%s content_id_count=%s message_field_present=%s message_present=%s response=%s",
            page_id,
            conversation_id,
            response.status_code,
            payload_kind,
            payload_action,
            content_id_count,
            message_field_present,
            message_present,
            _preview_pancake_response(response_data),
        )
        return {
            "ok": True,
            "status_code": response.status_code,
            "response_data": response_data,
        }

    error = _classify_pancake_error(status_code=response.status_code, error_body=response_data)
    if response_success is False:
        error.update(
            {
                "reason": "pancake_api_unsuccessful_response",
                "non_retryable": True,
            }
        )
    logger.warning(
        "PANCAKE_POST_REPLY_PAYLOAD_FAILED page_id=%s conversation_id=%s status_code=%s reason=%s payload_kind=%s payload_action=%s content_id_count=%s message_field_present=%s message_present=%s response=%s",
        page_id,
        conversation_id,
        response.status_code,
        error.get("reason"),
        payload_kind,
        payload_action,
        content_id_count,
        message_field_present,
        message_present,
        _preview_pancake_response(response_data),
    )
    return {
        "ok": False,
        **error,
        "response_data": response_data,
    }


async def _get_pancake_conversation_messages(
    *,
    page_access_token: str,
    page_id: str,
    conversation_id: str,
    timeout: float,
) -> dict[str, Any]:
    url = build_pancake_messages_api_url(page_id=page_id, conversation_id=conversation_id)
    with _suppress_httpx_info_logs():
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                url,
                params={"page_access_token": page_access_token},
            )

    try:
        response_data = response.json()
    except Exception:
        response_data = response.text

    if 200 <= response.status_code < 300:
        logger.info(
            "PANCAKE_FETCH_CONVERSATION_MESSAGES_OK page_id=%s conversation_id=%s status_code=%s",
            page_id,
            conversation_id,
            response.status_code,
        )
        return {
            "ok": True,
            "status_code": response.status_code,
            "response_data": response_data,
        }

    error = _classify_pancake_error(status_code=response.status_code, error_body=response_data)
    logger.warning(
        "PANCAKE_FETCH_CONVERSATION_MESSAGES_FAILED page_id=%s conversation_id=%s status_code=%s reason=%s response=%s",
        page_id,
        conversation_id,
        response.status_code,
        error.get("reason"),
        _preview_pancake_response(response_data),
    )
    return {
        "ok": False,
        **error,
    }


async def _post_pancake_upload_content(
    *,
    page_access_token: str,
    page_id: str,
    file_path: Path,
    timeout: float,
) -> dict[str, Any]:
    url = build_pancake_upload_contents_api_url(page_id=page_id)
    try:
        file_size_bytes: Optional[int] = file_path.stat().st_size
    except OSError:
        file_size_bytes = None
    with file_path.open("rb") as file_obj:
        files = {"file": (file_path.name, file_obj)}
        with _suppress_httpx_info_logs():
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    url,
                    params={"page_access_token": page_access_token},
                    files=files,
                )

    try:
        response_data = response.json()
    except Exception:
        response_data = response.text

    if 200 <= response.status_code < 300:
        content_id = _extract_pancake_content_id(response_data)
        if content_id:
            logger.info(
                "PANCAKE_UPLOAD_CONTENT_OK page_id=%s file_name=%s file_size_bytes=%s status_code=%s content_id=%s",
                page_id,
                file_path.name,
                file_size_bytes,
                response.status_code,
                content_id,
            )
            return {
                "ok": True,
                "status_code": response.status_code,
                "content_id": content_id,
                "response_data": response_data,
            }
        logger.warning(
            "PANCAKE_UPLOAD_CONTENT_MISSING_ID page_id=%s file_name=%s file_size_bytes=%s status_code=%s response=%s",
            page_id,
            file_path.name,
            file_size_bytes,
            response.status_code,
            _preview_pancake_response(response_data),
        )
        return {
            "ok": False,
            "reason": "missing_pancake_content_id",
            "non_retryable": True,
            "status_code": response.status_code,
            "response_data": response_data,
        }

    error = _classify_pancake_error(status_code=response.status_code, error_body=response_data)
    logger.warning(
        "PANCAKE_UPLOAD_CONTENT_FAILED page_id=%s file_name=%s file_size_bytes=%s status_code=%s reason=%s response=%s",
        page_id,
        file_path.name,
        file_size_bytes,
        response.status_code,
        error.get("reason"),
        _preview_pancake_response(response_data),
    )
    return {
        "ok": False,
        **error,
    }


async def send_pancake_reply(
    *,
    page_id: str,
    conversation_id: str,
    message: str,
    action: str = PANCAKE_REPLY_INBOX_ACTION,
    timeout: Optional[float] = None,
    retry_attempts: Optional[int] = None,
    retry_backoff_seconds: Optional[float] = None,
) -> dict[str, Any]:
    normalized_page_id = str(page_id or "").strip()
    normalized_conversation_id = str(conversation_id or "").strip()
    normalized_message = sanitize_pancake_outgoing_message(message).strip()

    if not normalized_page_id:
        return {"ok": False, "reason": "missing_page_id", "non_retryable": True}
    if not normalized_conversation_id:
        return {"ok": False, "reason": "missing_pancake_conversation_id", "non_retryable": True}
    if not normalized_message:
        return {"ok": False, "reason": "missing_reply_message", "non_retryable": True}
    try:
        token = _get_pancake_page_access_token_for_page(page_id=normalized_page_id)
    except PancakePageAccessTokenConfigError as exc:
        return _pancake_page_token_error_result(
            exc,
            operation="send_reply",
            page_id=normalized_page_id,
            conversation_id=normalized_conversation_id,
        )

    payload = build_pancake_reply_payload(message=normalized_message, action=action)
    attempts = _get_pancake_api_retry_attempts(retry_attempts)
    timeout_seconds = _get_pancake_api_timeout_seconds(timeout)
    backoff_seconds = _get_pancake_api_retry_backoff_seconds(retry_backoff_seconds)
    last_result: dict[str, Any] = {}

    for attempt in range(1, attempts + 1):
        try:
            result = await _post_pancake_reply_payload(
                page_access_token=token,
                page_id=normalized_page_id,
                conversation_id=normalized_conversation_id,
                payload=payload,
                timeout=timeout_seconds,
            )
        except Exception as exc:
            logger.exception(
                "PANCAKE_SEND_REPLY_EXCEPTION page_id=%s conversation_id=%s attempt=%s error=%s",
                normalized_page_id,
                normalized_conversation_id,
                attempt,
                exc,
            )
            result = {
                "ok": False,
                "reason": "pancake_request_failed",
                "non_retryable": False,
                "error": str(exc),
            }

        last_result = result
        if bool(result.get("ok")):
            return result
        if bool(result.get("non_retryable")):
            return result
        if attempt < attempts:
            await asyncio.sleep(backoff_seconds * attempt)

    return last_result or {"ok": False, "reason": "pancake_send_failed", "non_retryable": False}


async def send_pancake_comment_reply(
    *,
    page_id: str,
    conversation_id: str,
    comment_message_id: str,
    message: str,
    timeout: Optional[float] = None,
    retry_attempts: Optional[int] = None,
    retry_backoff_seconds: Optional[float] = None,
) -> dict[str, Any]:
    normalized_page_id = str(page_id or "").strip()
    normalized_conversation_id = str(conversation_id or "").strip()
    normalized_comment_message_id = str(comment_message_id or "").strip()
    normalized_message = sanitize_pancake_outgoing_message(message).strip()

    if not normalized_page_id:
        return {"ok": False, "reason": "missing_page_id", "non_retryable": True}
    if not normalized_conversation_id:
        return {
            "ok": False,
            "reason": "missing_pancake_conversation_id",
            "non_retryable": True,
        }
    if not normalized_comment_message_id:
        return {
            "ok": False,
            "reason": "missing_pancake_comment_message_id",
            "non_retryable": True,
        }
    if not normalized_message:
        return {"ok": False, "reason": "missing_reply_message", "non_retryable": True}

    try:
        token = _get_pancake_page_access_token_for_page(page_id=normalized_page_id)
    except PancakePageAccessTokenConfigError as exc:
        return _pancake_page_token_error_result(
            exc,
            operation="send_comment_reply",
            page_id=normalized_page_id,
            conversation_id=normalized_conversation_id,
        )

    payload = build_pancake_comment_reply_payload(
        comment_message_id=normalized_comment_message_id,
        message=normalized_message,
    )
    attempts = _get_pancake_api_retry_attempts(retry_attempts)
    timeout_seconds = _get_pancake_api_timeout_seconds(timeout)
    backoff_seconds = _get_pancake_api_retry_backoff_seconds(retry_backoff_seconds)
    last_result: dict[str, Any] = {}

    for attempt in range(1, attempts + 1):
        try:
            result = await _post_pancake_reply_payload(
                page_access_token=token,
                page_id=normalized_page_id,
                conversation_id=normalized_conversation_id,
                payload=payload,
                timeout=timeout_seconds,
            )
        except Exception as exc:
            logger.exception(
                "PANCAKE_SEND_COMMENT_REPLY_EXCEPTION page_id=%s conversation_id=%s comment_message_id=%s attempt=%s error=%s",
                normalized_page_id,
                normalized_conversation_id,
                normalized_comment_message_id,
                attempt,
                exc,
            )
            result = {
                "ok": False,
                "reason": "pancake_request_failed",
                "non_retryable": False,
                "error": str(exc),
            }

        last_result = result
        if bool(result.get("ok")):
            return result
        if bool(result.get("non_retryable")):
            return result
        if attempt < attempts:
            await asyncio.sleep(backoff_seconds * attempt)

    return last_result or {
        "ok": False,
        "reason": "pancake_send_failed",
        "non_retryable": False,
    }


async def send_pancake_comment_content_ids(
    *,
    page_id: str,
    conversation_id: str,
    comment_message_id: str,
    content_ids: list[str],
    timeout: Optional[float] = None,
    retry_attempts: Optional[int] = None,
    retry_backoff_seconds: Optional[float] = None,
) -> dict[str, Any]:
    normalized_page_id = str(page_id or "").strip()
    normalized_conversation_id = str(conversation_id or "").strip()
    normalized_comment_message_id = str(comment_message_id or "").strip()
    normalized_content_ids = [
        str(content_id or "").strip()
        for content_id in content_ids
        if str(content_id or "").strip()
    ]

    if not normalized_page_id:
        return {"ok": False, "reason": "missing_page_id", "non_retryable": True}
    if not normalized_conversation_id:
        return {
            "ok": False,
            "reason": "missing_pancake_conversation_id",
            "non_retryable": True,
        }
    if not normalized_comment_message_id:
        return {
            "ok": False,
            "reason": "missing_pancake_comment_message_id",
            "non_retryable": True,
        }
    if not normalized_content_ids:
        return {
            "ok": False,
            "reason": "missing_pancake_content_ids",
            "non_retryable": True,
        }

    try:
        token = _get_pancake_page_access_token_for_page(page_id=normalized_page_id)
    except PancakePageAccessTokenConfigError as exc:
        return _pancake_page_token_error_result(
            exc,
            operation="send_comment_content_ids",
            page_id=normalized_page_id,
            conversation_id=normalized_conversation_id,
        )

    payload = build_pancake_comment_content_ids_payload(
        comment_message_id=normalized_comment_message_id,
        content_ids=normalized_content_ids,
    )
    attempts = _get_pancake_api_retry_attempts(retry_attempts)
    timeout_seconds = _get_pancake_api_timeout_seconds(timeout)
    backoff_seconds = _get_pancake_api_retry_backoff_seconds(retry_backoff_seconds)
    last_result: dict[str, Any] = {}

    for attempt in range(1, attempts + 1):
        try:
            result = await _post_pancake_reply_payload(
                page_access_token=token,
                page_id=normalized_page_id,
                conversation_id=normalized_conversation_id,
                payload=payload,
                timeout=timeout_seconds,
            )
        except Exception as exc:
            logger.exception(
                "PANCAKE_SEND_COMMENT_CONTENT_IDS_EXCEPTION page_id=%s conversation_id=%s comment_message_id=%s attempt=%s error=%s",
                normalized_page_id,
                normalized_conversation_id,
                normalized_comment_message_id,
                attempt,
                exc,
            )
            result = {
                "ok": False,
                "reason": "pancake_comment_content_ids_request_failed",
                "non_retryable": False,
                "error": str(exc),
            }

        last_result = result
        if bool(result.get("ok")):
            return result
        if bool(result.get("non_retryable")):
            return result
        if attempt < attempts:
            await asyncio.sleep(backoff_seconds * attempt)

    return last_result or {
        "ok": False,
        "reason": "pancake_send_comment_content_ids_failed",
        "non_retryable": False,
    }


async def fetch_pancake_conversation_messages(
    *,
    page_id: str,
    conversation_id: str,
    timeout: Optional[float] = None,
    retry_attempts: Optional[int] = None,
    retry_backoff_seconds: Optional[float] = None,
) -> dict[str, Any]:
    normalized_page_id = str(page_id or "").strip()
    normalized_conversation_id = str(conversation_id or "").strip()

    if not normalized_page_id:
        return {"ok": False, "reason": "missing_page_id", "non_retryable": True}
    if not normalized_conversation_id:
        return {"ok": False, "reason": "missing_pancake_conversation_id", "non_retryable": True}
    try:
        token = _get_pancake_page_access_token_for_page(page_id=normalized_page_id)
    except PancakePageAccessTokenConfigError as exc:
        return _pancake_page_token_error_result(
            exc,
            operation="fetch_conversation_messages",
            page_id=normalized_page_id,
            conversation_id=normalized_conversation_id,
        )

    attempts = _get_pancake_api_retry_attempts(retry_attempts)
    timeout_seconds = _get_pancake_api_timeout_seconds(timeout)
    backoff_seconds = _get_pancake_api_retry_backoff_seconds(retry_backoff_seconds)
    last_result: dict[str, Any] = {}

    for attempt in range(1, attempts + 1):
        try:
            result = await _get_pancake_conversation_messages(
                page_access_token=token,
                page_id=normalized_page_id,
                conversation_id=normalized_conversation_id,
                timeout=timeout_seconds,
            )
        except Exception as exc:
            logger.exception(
                "PANCAKE_FETCH_CONVERSATION_MESSAGES_EXCEPTION page_id=%s conversation_id=%s attempt=%s error=%s",
                normalized_page_id,
                normalized_conversation_id,
                attempt,
                exc,
            )
            result = {
                "ok": False,
                "reason": "pancake_request_failed",
                "non_retryable": False,
                "error": str(exc),
            }

        last_result = result
        if bool(result.get("ok")):
            return result
        if bool(result.get("non_retryable")):
            return result
        if attempt < attempts:
            await asyncio.sleep(backoff_seconds * attempt)

    return last_result or {"ok": False, "reason": "pancake_fetch_failed", "non_retryable": False}


async def upload_pancake_content(
    *,
    page_id: str,
    file_path: str,
    timeout: Optional[float] = None,
    retry_attempts: Optional[int] = None,
    retry_backoff_seconds: Optional[float] = None,
) -> dict[str, Any]:
    normalized_page_id = str(page_id or "").strip()
    normalized_file_path = Path(str(file_path or "").strip())

    if not normalized_page_id:
        return {"ok": False, "reason": "missing_page_id", "non_retryable": True}
    if not str(normalized_file_path):
        return {"ok": False, "reason": "missing_file_path", "non_retryable": True}
    try:
        token = _get_pancake_page_access_token_for_page(page_id=normalized_page_id)
    except PancakePageAccessTokenConfigError as exc:
        return _pancake_page_token_error_result(
            exc,
            operation="upload_content",
            page_id=normalized_page_id,
        )
    if not normalized_file_path.is_file():
        return {"ok": False, "reason": "pancake_upload_file_not_found", "non_retryable": True}

    attempts = _get_pancake_api_retry_attempts(retry_attempts)
    timeout_seconds = _get_pancake_image_upload_timeout_seconds(timeout)
    backoff_seconds = _get_pancake_api_retry_backoff_seconds(retry_backoff_seconds)
    last_result: dict[str, Any] = {}

    for attempt in range(1, attempts + 1):
        try:
            result = await _post_pancake_upload_content(
                page_access_token=token,
                page_id=normalized_page_id,
                file_path=normalized_file_path,
                timeout=timeout_seconds,
            )
        except Exception as exc:
            logger.exception(
                "PANCAKE_UPLOAD_CONTENT_EXCEPTION page_id=%s file_path=%s attempt=%s error=%s",
                normalized_page_id,
                normalized_file_path,
                attempt,
                exc,
            )
            result = {
                "ok": False,
                "reason": "pancake_upload_request_failed",
                "non_retryable": False,
                "error": str(exc),
            }

        last_result = result
        if bool(result.get("ok")):
            return result
        if bool(result.get("non_retryable")):
            return result
        if attempt < attempts:
            await asyncio.sleep(backoff_seconds * attempt)

    return last_result or {"ok": False, "reason": "pancake_upload_failed", "non_retryable": False}


async def send_pancake_content_ids(
    *,
    page_id: str,
    conversation_id: str,
    content_ids: list[str],
    action: str = PANCAKE_REPLY_INBOX_ACTION,
    timeout: Optional[float] = None,
    retry_attempts: Optional[int] = None,
    retry_backoff_seconds: Optional[float] = None,
) -> dict[str, Any]:
    normalized_page_id = str(page_id or "").strip()
    normalized_conversation_id = str(conversation_id or "").strip()
    normalized_content_ids = [str(content_id or "").strip() for content_id in content_ids if str(content_id or "").strip()]

    if not normalized_page_id:
        return {"ok": False, "reason": "missing_page_id", "non_retryable": True}
    if not normalized_conversation_id:
        return {"ok": False, "reason": "missing_pancake_conversation_id", "non_retryable": True}
    if not normalized_content_ids:
        return {"ok": False, "reason": "missing_pancake_content_ids", "non_retryable": True}
    try:
        token = _get_pancake_page_access_token_for_page(page_id=normalized_page_id)
    except PancakePageAccessTokenConfigError as exc:
        return _pancake_page_token_error_result(
            exc,
            operation="send_content_ids",
            page_id=normalized_page_id,
            conversation_id=normalized_conversation_id,
        )

    payload = build_pancake_content_ids_payload(content_ids=normalized_content_ids, action=action)
    attempts = _get_pancake_api_retry_attempts(retry_attempts)
    timeout_seconds = _get_pancake_api_timeout_seconds(timeout)
    backoff_seconds = _get_pancake_api_retry_backoff_seconds(retry_backoff_seconds)
    last_result: dict[str, Any] = {}

    for attempt in range(1, attempts + 1):
        try:
            result = await _post_pancake_reply_payload(
                page_access_token=token,
                page_id=normalized_page_id,
                conversation_id=normalized_conversation_id,
                payload=payload,
                timeout=timeout_seconds,
            )
        except Exception as exc:
            logger.exception(
                "PANCAKE_SEND_CONTENT_IDS_EXCEPTION page_id=%s conversation_id=%s attempt=%s error=%s",
                normalized_page_id,
                normalized_conversation_id,
                attempt,
                exc,
            )
            result = {
                "ok": False,
                "reason": "pancake_content_ids_request_failed",
                "non_retryable": False,
                "error": str(exc),
            }

        last_result = result
        if bool(result.get("ok")):
            return result
        if bool(result.get("non_retryable")):
            return result
        if attempt < attempts:
            await asyncio.sleep(backoff_seconds * attempt)

    return last_result or {"ok": False, "reason": "pancake_send_content_ids_failed", "non_retryable": False}
