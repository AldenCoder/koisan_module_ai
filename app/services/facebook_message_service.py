"""Facebook Messenger Send API payload helpers."""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from logs.logging_config import logger


FACEBOOK_GRAPH_API_VERSION = "v21.0"
FACEBOOK_SEND_API_URL_FALLBACK = f"https://graph.facebook.com/{FACEBOOK_GRAPH_API_VERSION}/me/messages"
MAX_FACEBOOK_IMAGE_ATTACHMENTS = 30
MAX_FACEBOOK_PRODUCT_IMAGES = 3
FACEBOOK_BULK_RETRY_DELAY_SECONDS = 2.0
_URL_PATTERN = re.compile(r"https://[^\s<>\]\[\"']+", re.IGNORECASE)
_TRAILING_URL_PUNCTUATION = ".,;!?)}}]"
_ALLOWED_IMAGE_HOSTS = {"lh3.googleusercontent.com"}
_FACEBOOK_PERMISSION_ERROR_CODES = {10, 200, 230, 2500}
_FACEBOOK_PAGE_ERROR_PHRASES = (
    "unsupported post request",
    "object with id",
    "does not exist",
    "cannot be loaded",
    "does not support this operation",
)


@dataclass(frozen=True)
class ImageUrlSplitResult:
    text: str
    image_urls: list[str]
    skipped_count: int = 0
    truncated_count: int = 0


def _shorten_url_for_log(url: str) -> str:
    parsed = urlparse(str(url or ""))
    path = parsed.path or ""
    if len(path) > 32:
        path = f"{path[:16]}...{path[-12:]}"
    return f"{parsed.netloc}{path}" if parsed.netloc else str(url or "")[:48]


def _preview_error_for_log(value: Any, *, limit: int = 500) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...(truncated)"


def _parse_facebook_error_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        error = value.get("error")
        return error if isinstance(error, dict) else {}
    if not isinstance(value, str):
        return {}
    try:
        data = json.loads(value)
    except ValueError:
        return {}
    error = data.get("error") if isinstance(data, dict) else None
    return error if isinstance(error, dict) else {}


def _classify_facebook_api_error(*, status_code: Optional[int], error_body: Any) -> dict[str, Any]:
    error = _parse_facebook_error_payload(error_body)
    message = str(error.get("message") or "").lower()
    error_type = str(error.get("type") or "")

    try:
        code = int(error.get("code")) if error.get("code") is not None else None
    except (TypeError, ValueError):
        code = None

    if status_code == 401 or code == 190:
        return {
            "reason": "facebook_auth_error",
            "non_retryable": True,
            "facebook_error_code": code,
            "facebook_error_type": error_type,
        }

    if code in _FACEBOOK_PERMISSION_ERROR_CODES:
        return {
            "reason": "facebook_permission_error",
            "non_retryable": True,
            "facebook_error_code": code,
            "facebook_error_type": error_type,
        }

    if code == 100 and any(phrase in message for phrase in _FACEBOOK_PAGE_ERROR_PHRASES):
        return {
            "reason": "facebook_page_error",
            "non_retryable": True,
            "facebook_error_code": code,
            "facebook_error_type": error_type,
        }

    if status_code == 403:
        return {
            "reason": "facebook_permission_error",
            "non_retryable": True,
            "facebook_error_code": code,
            "facebook_error_type": error_type,
        }

    return {
        "reason": "facebook_api_error",
        "non_retryable": False,
        "facebook_error_code": code,
        "facebook_error_type": error_type,
    }


def _result_has_non_retryable_error(value: Any) -> bool:
    if isinstance(value, dict):
        if bool(value.get("non_retryable")):
            return True
        return any(_result_has_non_retryable_error(item) for item in value.values())
    if isinstance(value, list):
        return any(_result_has_non_retryable_error(item) for item in value)
    return False


def _trim_url(url: str) -> str:
    trimmed = str(url or "").strip()
    while trimmed and trimmed[-1] in _TRAILING_URL_PUNCTUATION:
        trimmed = trimmed[:-1]
    return trimmed


def is_allowed_facebook_image_url(url: str) -> bool:
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme.lower() != "https":
        return False
    if parsed.netloc.lower() not in _ALLOWED_IMAGE_HOSTS:
        return False
    path_parts = [part for part in parsed.path.split("/") if part]
    return len(path_parts) >= 2 and path_parts[0] == "d" and bool(path_parts[1].strip())


def split_text_and_image_urls(message_text: str) -> ImageUrlSplitResult:
    """Remove allowed image URLs from a text response and return them separately."""
    source_text = str(message_text or "")
    accepted_urls: list[str] = []
    accepted_set: set[str] = set()
    skipped_count = 0
    cleaned_lines: list[str] = []

    for line in source_text.splitlines():
        cleaned_parts: list[str] = []
        cursor = 0
        line_had_image_url = False

        for match in _URL_PATTERN.finditer(line):
            raw_url = match.group(0)
            image_url = _trim_url(raw_url)
            if is_allowed_facebook_image_url(image_url):
                line_had_image_url = True
                cleaned_parts.append(line[cursor:match.start()])
                cursor = match.end()
                if image_url not in accepted_set:
                    accepted_set.add(image_url)
                    accepted_urls.append(image_url)
                else:
                    skipped_count += 1
                continue

            skipped_count += 1

        cleaned_parts.append(line[cursor:])
        cleaned_line = "".join(cleaned_parts).strip()
        if line_had_image_url and not _line_has_readable_text(cleaned_line):
            continue
        cleaned_lines.append(cleaned_line)

    cleaned_text = _normalize_cleaned_text("\n".join(cleaned_lines))

    truncated_count = max(0, len(accepted_urls) - MAX_FACEBOOK_IMAGE_ATTACHMENTS)
    image_urls = accepted_urls[:MAX_FACEBOOK_IMAGE_ATTACHMENTS]
    return ImageUrlSplitResult(
        text=cleaned_text,
        image_urls=image_urls,
        skipped_count=skipped_count,
        truncated_count=truncated_count,
    )


def _normalize_cleaned_text(text: str) -> str:
    normalized_lines: list[str] = []
    previous_blank = False

    for raw_line in str(text or "").splitlines():
        line = " ".join(raw_line.split())
        if line:
            normalized_lines.append(line)
            previous_blank = False
            continue

        if normalized_lines and not previous_blank:
            normalized_lines.append("")
            previous_blank = True

    while normalized_lines and normalized_lines[-1] == "":
        normalized_lines.pop()

    return "\n".join(normalized_lines).strip()


def _line_has_readable_text(value: str) -> bool:
    return any(char.isalnum() for char in str(value or ""))


def _merge_unique_image_urls(*url_groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for url_group in url_groups:
        for raw_url in url_group:
            image_url = _trim_url(raw_url)
            if image_url in seen:
                continue
            seen.add(image_url)
            merged.append(image_url)
    return merged


def build_facebook_send_api_url(*, page_id: Optional[str] = None) -> str:
    normalized_page_id = str(page_id or "").strip()
    if normalized_page_id:
        return f"https://graph.facebook.com/{FACEBOOK_GRAPH_API_VERSION}/{normalized_page_id}/messages"
    return FACEBOOK_SEND_API_URL_FALLBACK


def build_facebook_text_payload(
    *,
    recipient_id: str,
    message_text: str,
    reply_to_mid: Optional[str] = None,
    messaging_type: str = "RESPONSE",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "messaging_type": messaging_type,
        "recipient": {"id": recipient_id},
        "message": {"text": message_text},
    }
    if reply_to_mid:
        payload["message"]["metadata"] = f"source_mid:{reply_to_mid}"
    return payload


def build_facebook_image_attachments_payload(
    *,
    recipient_id: str,
    image_urls: list[str],
    messaging_type: str = "RESPONSE",
) -> dict[str, Any]:
    urls = image_urls[:MAX_FACEBOOK_IMAGE_ATTACHMENTS]
    return {
        "messaging_type": messaging_type,
        "recipient": {"id": recipient_id},
        "message": {
            "attachments": [
                {
                    "type": "image",
                    "payload": {"url": image_url},
                }
                for image_url in urls
            ]
        },
    }


def build_facebook_single_image_payload(
    *,
    recipient_id: str,
    image_url: str,
    messaging_type: str = "RESPONSE",
) -> dict[str, Any]:
    return {
        "messaging_type": messaging_type,
        "recipient": {"id": recipient_id},
        "message": {
            "attachment": {
                "type": "image",
                "payload": {"url": image_url},
            }
        },
    }


async def _post_facebook_message_payload(
    *,
    page_access_token: str,
    payload: dict[str, Any],
    page_id: Optional[str] = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    params = {"access_token": page_access_token}
    send_api_url = build_facebook_send_api_url(page_id=page_id)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(send_api_url, params=params, json=payload)
    except Exception as exc:
        return {"ok": False, "reason": "facebook_send_request_failed", "error": str(exc)}

    if response.status_code >= 400:
        classification = _classify_facebook_api_error(
            status_code=response.status_code,
            error_body=response.text,
        )
        return {
            "ok": False,
            "reason": classification["reason"],
            "non_retryable": classification["non_retryable"],
            "facebook_error_code": classification["facebook_error_code"],
            "facebook_error_type": classification["facebook_error_type"],
            "status_code": response.status_code,
            "error": response.text,
        }

    try:
        data = response.json()
    except ValueError:
        data = response.text
    return {
        "ok": True,
        "data": data if isinstance(data, dict) else {"data": data},
    }


async def send_facebook_images(
    *,
    recipient_id: str,
    image_urls: list[str],
    page_access_token: str,
    page_id: Optional[str] = None,
) -> dict[str, Any]:
    valid_urls: list[str] = []
    skipped_count = 0
    seen_urls: set[str] = set()

    for url in image_urls:
        normalized_url = _trim_url(url)
        if not is_allowed_facebook_image_url(normalized_url):
            skipped_count += 1
            logger.info(
                "FB_IMAGE_URL_SKIPPED reason=invalid_or_disallowed url=%s",
                _shorten_url_for_log(normalized_url),
            )
            continue
        if normalized_url in seen_urls:
            skipped_count += 1
            continue
        seen_urls.add(normalized_url)
        valid_urls.append(normalized_url)

    truncated_count = max(0, len(valid_urls) - MAX_FACEBOOK_IMAGE_ATTACHMENTS)
    valid_urls = valid_urls[:MAX_FACEBOOK_IMAGE_ATTACHMENTS]

    if not valid_urls:
        return {
            "ok": skipped_count > 0,
            "sent_count": 0,
            "skipped_count": skipped_count,
            "failed_count": 0,
            "truncated_count": truncated_count,
            "bulk_attempted": False,
            "bulk_succeeded": False,
            "results": [],
        }

    if len(valid_urls) == 1:
        single_payload = build_facebook_single_image_payload(
            recipient_id=recipient_id,
            image_url=valid_urls[0],
        )
        single_result = await _post_facebook_message_payload(
            page_access_token=page_access_token,
            page_id=page_id,
            payload=single_payload,
        )
        sent_count = 1 if bool(single_result.get("ok")) else 0
        failed_count = 0 if sent_count else 1
        if not sent_count:
            logger.warning(
                "FB_IMAGE_SINGLE_SEND_FAILED recipient_id=%s image_url=%s reason=%s status_code=%s non_retryable=%s",
                recipient_id,
                _shorten_url_for_log(valid_urls[0]),
                single_result.get("reason") or "facebook_api_error",
                single_result.get("status_code"),
                bool(single_result.get("non_retryable")),
            )
        return {
            "ok": bool(sent_count),
            "reason": None if sent_count else single_result.get("reason") or "facebook_api_error",
            "non_retryable": bool(single_result.get("non_retryable")) if not sent_count else False,
            "sent_count": sent_count,
            "skipped_count": skipped_count,
            "failed_count": failed_count,
            "truncated_count": truncated_count,
            "bulk_attempted": False,
            "bulk_succeeded": False,
            "results": [single_result],
        }

    bulk_payload = build_facebook_image_attachments_payload(
        recipient_id=recipient_id,
        image_urls=valid_urls,
    )
    bulk_result = await _post_facebook_message_payload(
        page_access_token=page_access_token,
        page_id=page_id,
        payload=bulk_payload,
    )
    if bool(bulk_result.get("ok")):
        logger.info(
            "FB_IMAGE_BULK_SEND_OK recipient_id=%s image_count=%s skipped_count=%s truncated_count=%s",
            recipient_id,
            len(valid_urls),
            skipped_count,
            truncated_count,
        )
        return {
            "ok": True,
            "sent_count": len(valid_urls),
            "skipped_count": skipped_count,
            "failed_count": 0,
            "truncated_count": truncated_count,
            "bulk_attempted": True,
            "bulk_succeeded": True,
            "bulk_attempt_count": 1,
            "bulk_result": bulk_result,
            "results": [],
        }

    logger.warning(
        "FB_IMAGE_BULK_SEND_FAILED recipient_id=%s image_count=%s attempt=1 reason=%s status_code=%s non_retryable=%s error=%s",
        recipient_id,
        len(valid_urls),
        bulk_result.get("reason") or "facebook_api_error",
        bulk_result.get("status_code"),
        bool(bulk_result.get("non_retryable")),
        _preview_error_for_log(bulk_result.get("error")),
    )

    if bool(bulk_result.get("non_retryable")):
        return {
            "ok": False,
            "reason": bulk_result.get("reason") or "facebook_api_error",
            "non_retryable": True,
            "sent_count": 0,
            "skipped_count": skipped_count,
            "failed_count": len(valid_urls),
            "truncated_count": truncated_count,
            "bulk_attempted": True,
            "bulk_succeeded": False,
            "bulk_attempt_count": 1,
            "bulk_result": bulk_result,
            "bulk_results": [bulk_result],
            "results": [],
        }

    await asyncio.sleep(FACEBOOK_BULK_RETRY_DELAY_SECONDS)
    bulk_retry_result = await _post_facebook_message_payload(
        page_access_token=page_access_token,
        page_id=page_id,
        payload=bulk_payload,
    )
    if bool(bulk_retry_result.get("ok")):
        logger.info(
            "FB_IMAGE_BULK_SEND_OK recipient_id=%s image_count=%s skipped_count=%s truncated_count=%s attempt=2",
            recipient_id,
            len(valid_urls),
            skipped_count,
            truncated_count,
        )
        return {
            "ok": True,
            "sent_count": len(valid_urls),
            "skipped_count": skipped_count,
            "failed_count": 0,
            "truncated_count": truncated_count,
            "bulk_attempted": True,
            "bulk_succeeded": True,
            "bulk_attempt_count": 2,
            "bulk_result": bulk_retry_result,
            "bulk_results": [bulk_result, bulk_retry_result],
            "results": [],
        }

    logger.warning(
        "FB_IMAGE_BULK_SEND_FAILED recipient_id=%s image_count=%s attempt=2 reason=%s status_code=%s non_retryable=%s error=%s",
        recipient_id,
        len(valid_urls),
        bulk_retry_result.get("reason") or "facebook_api_error",
        bulk_retry_result.get("status_code"),
        bool(bulk_retry_result.get("non_retryable")),
        _preview_error_for_log(bulk_retry_result.get("error")),
    )

    if bool(bulk_retry_result.get("non_retryable")):
        return {
            "ok": False,
            "reason": bulk_retry_result.get("reason") or "facebook_api_error",
            "non_retryable": True,
            "sent_count": 0,
            "skipped_count": skipped_count,
            "failed_count": len(valid_urls),
            "truncated_count": truncated_count,
            "bulk_attempted": True,
            "bulk_succeeded": False,
            "bulk_attempt_count": 2,
            "bulk_result": bulk_retry_result,
            "bulk_results": [bulk_result, bulk_retry_result],
            "results": [],
        }

    results: list[dict[str, Any]] = []
    sent_count = 0
    failed_count = 0
    non_retryable = False
    failure_reason: Optional[str] = None
    for image_url in valid_urls:
        single_payload = build_facebook_single_image_payload(
            recipient_id=recipient_id,
            image_url=image_url,
        )
        single_result = await _post_facebook_message_payload(
            page_access_token=page_access_token,
            page_id=page_id,
            payload=single_payload,
        )
        if bool(single_result.get("ok")):
            sent_count += 1
        else:
            failed_count += 1
            failure_reason = single_result.get("reason") or "facebook_api_error"
            non_retryable = bool(single_result.get("non_retryable"))
            logger.warning(
                "FB_IMAGE_SINGLE_SEND_FAILED recipient_id=%s image_url=%s reason=%s status_code=%s non_retryable=%s",
                recipient_id,
                _shorten_url_for_log(image_url),
                failure_reason,
                single_result.get("status_code"),
                non_retryable,
            )
        results.append(single_result)
        if non_retryable:
            break

    return {
        "ok": sent_count > 0,
        "reason": failure_reason if not sent_count else None,
        "non_retryable": non_retryable and sent_count == 0,
        "sent_count": sent_count,
        "skipped_count": skipped_count,
        "failed_count": failed_count,
        "truncated_count": truncated_count,
        "bulk_attempted": True,
        "bulk_succeeded": False,
        "bulk_attempt_count": 2,
        "bulk_result": bulk_retry_result,
        "bulk_results": [bulk_result, bulk_retry_result],
        "results": results,
    }


async def send_facebook_text_and_images(
    *,
    recipient_id: str,
    message_text: str,
    page_access_token: str,
    reply_to_mid: Optional[str] = None,
    image_urls: Optional[list[str]] = None,
    max_image_count: int = MAX_FACEBOOK_PRODUCT_IMAGES,
    page_id: Optional[str] = None,
) -> dict[str, Any]:
    split_result = split_text_and_image_urls(message_text)
    requested_image_urls = image_urls or []
    combined_image_urls = _merge_unique_image_urls(split_result.image_urls, requested_image_urls)
    normalized_limit = max(0, min(int(max_image_count or 0), MAX_FACEBOOK_IMAGE_ATTACHMENTS))
    if normalized_limit:
        truncated_count = split_result.truncated_count + max(0, len(combined_image_urls) - normalized_limit)
        combined_image_urls = combined_image_urls[:normalized_limit]
    else:
        truncated_count = split_result.truncated_count
        combined_image_urls = []

    if not page_access_token:
        return {"ok": False, "reason": "missing_fb_page_access_token", "non_retryable": True}
    if not recipient_id:
        return {"ok": False, "reason": "missing_recipient", "non_retryable": True}
    if not split_result.text and not combined_image_urls:
        return {"ok": False, "reason": "missing_message_text_or_image", "non_retryable": True}

    text_result: Optional[dict[str, Any]] = None
    if split_result.text:
        text_payload = build_facebook_text_payload(
            recipient_id=recipient_id,
            message_text=split_result.text,
            reply_to_mid=reply_to_mid,
        )
        text_result = await _post_facebook_message_payload(
            page_access_token=page_access_token,
            page_id=page_id,
            payload=text_payload,
        )
        if not bool(text_result.get("ok")):
            return {
                "ok": False,
                "reason": "facebook_text_send_failed",
                "non_retryable": bool(text_result.get("non_retryable")),
                "text": split_result.text,
                "image_urls": combined_image_urls,
                "skipped_image_url_count": split_result.skipped_count,
                "truncated_image_url_count": truncated_count,
                "text_result": text_result,
            }

    image_result: Optional[dict[str, Any]] = None
    if combined_image_urls:
        image_result = await send_facebook_images(
            recipient_id=recipient_id,
            image_urls=combined_image_urls,
            page_access_token=page_access_token,
            page_id=page_id,
        )

    ok = bool(text_result and text_result.get("ok"))
    if image_result:
        ok = ok or bool(image_result.get("ok"))

    return {
        "ok": ok,
        "non_retryable": _result_has_non_retryable_error(
            {
                "text_result": text_result,
                "image_result": image_result,
            }
        ),
        "text": split_result.text,
        "image_urls": combined_image_urls,
        "skipped_image_url_count": split_result.skipped_count,
        "truncated_image_url_count": truncated_count,
        "text_result": text_result,
        "image_result": image_result,
    }
