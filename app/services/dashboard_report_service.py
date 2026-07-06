from __future__ import annotations

import re
from io import BytesIO
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.api.dependencies.time import VN_TZ, now_vn
from app.models.conversations import Conversation, ConversationStatus
from app.models.messages import Message
from app.services.dashboard_report_excel import build_dashboard_report_workbook
from logs.logging_config import logger


DEFAULT_DASHBOARD_ALERT_LIMIT = 20
MAX_DASHBOARD_ALERT_LIMIT = 100
MAX_DASHBOARD_REPORT_RANGE_DAYS = 366
EXCEL_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_IMAGE_CONTENT_URL_PATTERN = (
    r"^https?://\S+\.(?:jpg|jpeg|png|webp|gif|bmp|svg|avif|heic|heif)(?:[?#].*)?$"
)
_IMAGE_CONTENT_URL_RE = re.compile(_IMAGE_CONTENT_URL_PATTERN, re.IGNORECASE)
_MESSAGE_TYPE_BY_THREAD_TYPE = {
    "inbox": "INBOX",
    "comment": "COMMENT",
}


def _to_int_or_default(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


def _clean_optional_text(value: Optional[Any]) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _is_image_content(value: Optional[Any]) -> bool:
    normalized = _clean_optional_text(value)
    if not normalized:
        return False
    return bool(_IMAGE_CONTENT_URL_RE.match(normalized))


def _is_text_content(value: Optional[Any]) -> bool:
    normalized = _clean_optional_text(value)
    if not normalized:
        return False
    return not _is_image_content(normalized)


def _normalize_thread_type(value: Optional[Any]) -> Optional[str]:
    normalized = _clean_optional_text(value)
    if not normalized:
        return None
    lowered = normalized.lower()
    if lowered not in _MESSAGE_TYPE_BY_THREAD_TYPE:
        raise ValueError("invalid_thread_type")
    return lowered


def _normalize_role(value: Optional[Any]) -> Optional[str]:
    normalized = _clean_optional_text(value)
    if not normalized:
        return None
    lowered = normalized.lower()
    if lowered not in {"user", "staff", "bot", "system"}:
        raise ValueError("invalid_role")
    return lowered


def _normalize_alert_limit(value: Optional[Any]) -> int:
    normalized = _to_int_or_default(value, DEFAULT_DASHBOARD_ALERT_LIMIT)
    return min(MAX_DASHBOARD_ALERT_LIMIT, max(1, normalized))


def _to_vn_aware_datetime(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(VN_TZ)


def _parse_date_input(value: Optional[Any], *, field_name: str) -> tuple[datetime, bool]:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError(f"{field_name}_required")

    if _DATE_ONLY_RE.match(raw):
        parsed_date = date.fromisoformat(raw)
        return (
            datetime(
                parsed_date.year,
                parsed_date.month,
                parsed_date.day,
                tzinfo=VN_TZ,
            ),
            True,
        )

    try:
        parsed_dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid_{field_name}") from exc

    if parsed_dt.tzinfo is None:
        parsed_dt = parsed_dt.replace(tzinfo=VN_TZ)
    else:
        parsed_dt = parsed_dt.astimezone(VN_TZ)
    return parsed_dt, False


def _normalize_date_range(
    *,
    from_date: Optional[Any],
    to_date: Optional[Any],
) -> tuple[datetime, datetime, datetime]:
    start, _ = _parse_date_input(from_date, field_name="from_date")
    raw_end, to_date_only = _parse_date_input(to_date, field_name="to_date")

    if to_date_only:
        query_end = raw_end + timedelta(days=1)
        display_end = query_end - timedelta(microseconds=1)
    else:
        query_end = raw_end
        display_end = raw_end

    if start > display_end:
        raise ValueError("from_date_must_be_before_to_date")

    if query_end - start > timedelta(days=MAX_DASHBOARD_REPORT_RANGE_DAYS):
        raise ValueError("date_range_too_large")

    return start, query_end, display_end


def _status_to_str(value: Any) -> str:
    raw = getattr(value, "value", value)
    normalized = str(raw or "").strip()
    return normalized or ConversationStatus.NEW.value


def _base_message_match(
    *,
    start: datetime,
    end: datetime,
    page_id: Optional[str],
    thread_type: Optional[str],
    role: Optional[str],
) -> Dict[str, Any]:
    match: Dict[str, Any] = {"created_at": {"$gte": start, "$lt": end}}
    if page_id:
        match["meta.page_id"] = page_id
    if thread_type:
        match["meta.message_type"] = _MESSAGE_TYPE_BY_THREAD_TYPE[thread_type]
    if role:
        match["role"] = role
    return match


def _base_conversation_match(
    *,
    page_id: Optional[str],
    thread_type: Optional[str],
    include_inactive: bool,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> Dict[str, Any]:
    match: Dict[str, Any] = {}
    if not include_inactive:
        match["is_active"] = True
    if page_id:
        match["pancake_page_id"] = page_id
    if thread_type:
        match["pancake_thread_type"] = thread_type
    if start is not None and end is not None:
        match["created_at"] = {"$gte": start, "$lt": end}
    return match


def _message_projection_stage() -> Dict[str, Any]:
    trimmed_content = {"$trim": {"input": {"$ifNull": ["$content", ""]}}}
    is_image_content = {
        "$regexMatch": {
            "input": trimmed_content,
            "regex": _IMAGE_CONTENT_URL_PATTERN,
            "options": "i",
        }
    }
    return {
        "$project": {
            "role": 1,
            "day": {
                "$dateToString": {
                    "format": "%Y-%m-%d",
                    "date": "$created_at",
                    "timezone": "+07:00",
                }
            },
            "has_text": {
                "$and": [
                    {"$gt": [{"$strLenCP": trimmed_content}, 0]},
                    {"$not": [is_image_content]},
                ]
            },
            "has_image": is_image_content,
        }
    }


async def _aggregate_message_report(match_query: Dict[str, Any]) -> tuple[Dict[str, int], List[Dict[str, Any]]]:
    pipeline = [
        {"$match": match_query},
        _message_projection_stage(),
        {
            "$facet": {
                "summary": [
                    {
                        "$group": {
                            "_id": None,
                            "total_messages": {"$sum": 1},
                            "text_messages": {"$sum": {"$cond": ["$has_text", 1, 0]}},
                            "image_messages": {"$sum": {"$cond": ["$has_image", 1, 0]}},
                            "user_messages": {
                                "$sum": {"$cond": [{"$eq": ["$role", "user"]}, 1, 0]}
                            },
                            "staff_messages": {
                                "$sum": {"$cond": [{"$eq": ["$role", "staff"]}, 1, 0]}
                            },
                            "bot_messages": {
                                "$sum": {"$cond": [{"$eq": ["$role", "bot"]}, 1, 0]}
                            },
                        }
                    }
                ],
                "by_day": [
                    {
                        "$group": {
                            "_id": "$day",
                            "total": {"$sum": 1},
                            "text": {"$sum": {"$cond": ["$has_text", 1, 0]}},
                            "image": {"$sum": {"$cond": ["$has_image", 1, 0]}},
                            "user": {
                                "$sum": {"$cond": [{"$eq": ["$role", "user"]}, 1, 0]}
                            },
                            "staff": {
                                "$sum": {"$cond": [{"$eq": ["$role", "staff"]}, 1, 0]}
                            },
                            "bot": {
                                "$sum": {"$cond": [{"$eq": ["$role", "bot"]}, 1, 0]}
                            },
                        }
                    },
                    {"$sort": {"_id": 1}},
                ],
            }
        },
    ]
    rows = await Message.aggregate(pipeline).to_list()
    data = rows[0] if rows else {}
    summary_rows = data.get("summary") or []
    raw_summary = summary_rows[0] if summary_rows else {}
    summary = {
        "total_messages": max(0, _to_int_or_default(raw_summary.get("total_messages"), 0)),
        "text_messages": max(0, _to_int_or_default(raw_summary.get("text_messages"), 0)),
        "image_messages": max(0, _to_int_or_default(raw_summary.get("image_messages"), 0)),
        "user_messages": max(0, _to_int_or_default(raw_summary.get("user_messages"), 0)),
        "staff_messages": max(0, _to_int_or_default(raw_summary.get("staff_messages"), 0)),
        "bot_messages": max(0, _to_int_or_default(raw_summary.get("bot_messages"), 0)),
    }

    by_day: List[Dict[str, Any]] = []
    for row in data.get("by_day") or []:
        if not isinstance(row, dict):
            continue
        by_day.append(
            {
                "date": str(row.get("_id") or ""),
                "total": max(0, _to_int_or_default(row.get("total"), 0)),
                "text": max(0, _to_int_or_default(row.get("text"), 0)),
                "image": max(0, _to_int_or_default(row.get("image"), 0)),
                "user": max(0, _to_int_or_default(row.get("user"), 0)),
                "staff": max(0, _to_int_or_default(row.get("staff"), 0)),
                "bot": max(0, _to_int_or_default(row.get("bot"), 0)),
            }
        )
    return summary, by_day


async def _aggregate_conversation_status(match_query: Dict[str, Any]) -> tuple[Dict[str, int], List[Dict[str, Any]]]:
    pipeline = [
        {"$match": match_query},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    rows = await Conversation.aggregate(pipeline).to_list()
    status_counts = {status.value: 0 for status in ConversationStatus}
    for row in rows:
        if not isinstance(row, dict):
            continue
        status_value = _status_to_str(row.get("_id"))
        if status_value in status_counts:
            status_counts[status_value] = max(0, _to_int_or_default(row.get("count"), 0))

    conversation_status = [
        {"status": status.value, "count": status_counts[status.value]}
        for status in ConversationStatus
    ]
    return status_counts, conversation_status


def _alert_lookup_stages(limit: int) -> List[Dict[str, Any]]:
    return [
        {"$limit": limit},
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
                "customer_name": 1,
                "customer_id": 1,
                "status": 1,
                "pancake_page_id": 1,
                "pancake_conversation_id": 1,
                "pancake_info_url": 1,
                "order_note": 1,
                "bot_paused_until": 1,
                "updated_at": 1,
                "message_count": 1,
            }
        },
    ]


async def _aggregate_alert_rows(match_query: Dict[str, Any], *, limit: int) -> tuple[List[Dict[str, Any]], int]:
    pipeline = [
        {"$match": match_query},
        {"$sort": {"updated_at": -1}},
        {
            "$facet": {
                "items": _alert_lookup_stages(limit),
                "total": [{"$count": "count"}],
            }
        },
    ]
    rows = await Conversation.aggregate(pipeline).to_list()
    data = rows[0] if rows else {}
    total_rows = data.get("total") or []
    total = 0
    if total_rows and isinstance(total_rows[0], dict):
        total = max(0, _to_int_or_default(total_rows[0].get("count"), 0))
    items = [row for row in data.get("items") or [] if isinstance(row, dict)]
    return items, total


async def _aggregate_conversation_page_ids(*, include_inactive: bool) -> List[Dict[str, Any]]:
    match_query: Dict[str, Any] = {
        "pancake_page_id": {"$exists": True, "$nin": [None, ""]}
    }
    if not include_inactive:
        match_query["is_active"] = True

    pipeline = [
        {"$match": match_query},
        {
            "$group": {
                "_id": "$pancake_page_id",
                "conversation_count": {"$sum": 1},
                "latest_activity_at": {"$max": "$updated_at"},
            }
        },
        {"$sort": {"latest_activity_at": -1, "_id": 1}},
    ]
    rows = await Conversation.aggregate(pipeline).to_list()
    return [row for row in rows if isinstance(row, dict)]


async def _aggregate_message_page_ids() -> List[Dict[str, Any]]:
    pipeline = [
        {"$match": {"meta.page_id": {"$exists": True, "$nin": [None, ""]}}},
        {
            "$group": {
                "_id": "$meta.page_id",
                "message_count": {"$sum": 1},
                "latest_activity_at": {"$max": "$created_at"},
            }
        },
        {"$sort": {"latest_activity_at": -1, "_id": 1}},
    ]
    rows = await Message.aggregate(pipeline).to_list()
    return [row for row in rows if isinstance(row, dict)]


def _latest_datetime(left: Any, right: Any) -> Optional[datetime]:
    left_dt = _to_vn_aware_datetime(left)
    right_dt = _to_vn_aware_datetime(right)
    if left_dt is None:
        return right_dt
    if right_dt is None:
        return left_dt
    return max(left_dt, right_dt)


def _sort_page_id_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items.sort(key=lambda item: item["page_id"])
    items.sort(
        key=lambda item: item.get("latest_activity_at")
        or datetime.min.replace(tzinfo=VN_TZ),
        reverse=True,
    )
    return items


def _support_reason(row: Dict[str, Any], *, now: datetime) -> str:
    status = _status_to_str(row.get("status"))
    if status == ConversationStatus.APILIMIT.value:
        return "apilimit"
    if status == ConversationStatus.HANDOVER.value:
        return "handover"
    paused_until = _to_vn_aware_datetime(row.get("bot_paused_until"))
    if paused_until is not None and paused_until > now:
        return "bot_paused"
    return "needs_support"


def _serialize_alert_base(row: Dict[str, Any]) -> Dict[str, Any]:
    raw_id = row.get("_id")
    return {
        "conversation_id": str(raw_id) if raw_id is not None else "",
        "customer_name": row.get("customer_name"),
        "customer_id": row.get("customer_id"),
        "status": _status_to_str(row.get("status")),
        "pancake_page_id": row.get("pancake_page_id"),
        "pancake_conversation_id": row.get("pancake_conversation_id"),
        "pancake_info_url": row.get("pancake_info_url"),
        "order_note": row.get("order_note"),
        "updated_at": _to_vn_aware_datetime(row.get("updated_at")),
        "message_count": max(0, _to_int_or_default(row.get("message_count"), 0)),
    }


def _serialize_needs_support_alert(row: Dict[str, Any], *, now: datetime) -> Dict[str, Any]:
    data = _serialize_alert_base(row)
    data.update(
        {
            "reason": _support_reason(row, now=now),
            "bot_paused_until": _to_vn_aware_datetime(row.get("bot_paused_until")),
        }
    )
    return data


def _serialize_order_alert(row: Dict[str, Any]) -> Dict[str, Any]:
    data = _serialize_alert_base(row)
    data.pop("bot_paused_until", None)
    return data


def _export_message_image_urls(content: Any, meta: Dict[str, Any]) -> str:
    urls: List[str] = []
    normalized_content = _clean_optional_text(content)
    if normalized_content and _is_image_content(normalized_content):
        urls.append(normalized_content)

    raw_image_urls = meta.get("image_urls") or []
    if isinstance(raw_image_urls, (list, tuple, set)):
        candidates = raw_image_urls
    else:
        candidates = [raw_image_urls]
    for value in candidates:
        normalized = _clean_optional_text(value)
        if normalized and normalized not in urls:
            urls.append(normalized)
    return "\n".join(urls)


def _serialize_export_message(row: Dict[str, Any]) -> Dict[str, Any]:
    meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
    content = row.get("content")
    if _is_image_content(content):
        content_type = "image"
    elif _is_text_content(content):
        content_type = "text"
    else:
        content_type = "other"

    sender_id = (
        meta.get("sender_id")
        or meta.get("platform_sender_id")
        or meta.get("message_from_id")
        or meta.get("customer_id")
    )
    sender_name = (
        meta.get("conversation_sender_name")
        or meta.get("message_from_admin_name")
        or meta.get("sender_name")
    )
    return {
        "message_id": str(row.get("_id") or ""),
        "message_mid": row.get("message_mid"),
        "conversation_id": str(row.get("conversation_id") or ""),
        "content_type": content_type,
        "role": _clean_optional_text(row.get("role")) or "",
        "content": content,
        "image_urls": _export_message_image_urls(content, meta),
        "page_id": meta.get("page_id"),
        "thread_type": meta.get("message_type") or meta.get("conversation_type"),
        "source": meta.get("source"),
        "sender_id": sender_id,
        "sender_name": sender_name,
        "pancake_conversation_id": meta.get("pancake_conversation_id"),
        "created_at": _to_vn_aware_datetime(row.get("created_at")),
        "updated_at": _to_vn_aware_datetime(row.get("updated_at")),
        "meta": meta,
    }


def _serialize_export_conversation(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "conversation_id": str(row.get("_id") or ""),
        "channel": row.get("channel"),
        "customer_name": row.get("customer_name"),
        "customer_id": row.get("customer_id"),
        "pancake_page_id": row.get("pancake_page_id"),
        "pancake_conversation_id": row.get("pancake_conversation_id"),
        "pancake_thread_type": row.get("pancake_thread_type"),
        "pancake_info_url": row.get("pancake_info_url"),
        "order_note": row.get("order_note"),
        "is_active": bool(row.get("is_active", True)),
        "status": _status_to_str(row.get("status")),
        "summaries": row.get("summaries") or [],
        "fb_ai_initialized": bool(row.get("fb_ai_initialized", False)),
        "fb_ai_initialized_at": _to_vn_aware_datetime(row.get("fb_ai_initialized_at")),
        "bot_paused_until": _to_vn_aware_datetime(row.get("bot_paused_until")),
        "bot_paused_at": _to_vn_aware_datetime(row.get("bot_paused_at")),
        "bot_paused_reason": row.get("bot_paused_reason"),
        "bot_paused_by": row.get("bot_paused_by"),
        "created_at": _to_vn_aware_datetime(row.get("created_at")),
        "updated_at": _to_vn_aware_datetime(row.get("updated_at")),
        "message_count": max(0, _to_int_or_default(row.get("message_count"), 0)),
    }


async def _list_export_messages(match_query: Dict[str, Any]) -> List[Dict[str, Any]]:
    pipeline = [
        {"$match": match_query},
        {"$sort": {"created_at": -1, "_id": -1}},
    ]
    rows = await Message.aggregate(pipeline).to_list()
    return [
        _serialize_export_message(row)
        for row in rows
        if isinstance(row, dict)
    ]


async def _list_export_conversations(match_query: Dict[str, Any]) -> List[Dict[str, Any]]:
    pipeline = [
        {"$match": match_query},
        {"$sort": {"updated_at": -1, "_id": -1}},
        {
            "$lookup": {
                "from": Message.Settings.name,
                "let": {"conversation_id": "$_id"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {"$eq": ["$conversation_id", "$$conversation_id"]}
                        }
                    },
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
    ]
    rows = await Conversation.aggregate(pipeline).to_list()
    return [
        _serialize_export_conversation(row)
        for row in rows
        if isinstance(row, dict)
    ]


async def _collect_dashboard_report_export_details(
    *,
    from_date: Optional[Any],
    to_date: Optional[Any],
    page_id: Optional[str],
    thread_type: Optional[str],
    role: Optional[str],
    include_inactive: bool,
    as_of: Optional[datetime] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    start, query_end, _ = _normalize_date_range(
        from_date=from_date,
        to_date=to_date,
    )
    normalized_page_id = _clean_optional_text(page_id)
    normalized_thread_type = _normalize_thread_type(thread_type)
    normalized_role = _normalize_role(role)

    message_match = _base_message_match(
        start=start,
        end=query_end,
        page_id=normalized_page_id,
        thread_type=normalized_thread_type,
        role=normalized_role,
    )
    new_conversation_match = _base_conversation_match(
        start=start,
        end=query_end,
        page_id=normalized_page_id,
        thread_type=normalized_thread_type,
        include_inactive=include_inactive,
    )
    alert_base_match = _base_conversation_match(
        page_id=normalized_page_id,
        thread_type=normalized_thread_type,
        include_inactive=include_inactive,
    )
    now = _to_vn_aware_datetime(as_of) or now_vn()
    needs_support_match = {
        **alert_base_match,
        "$or": [
            {"status": ConversationStatus.HANDOVER.value},
            {"status": ConversationStatus.APILIMIT.value},
            {"bot_paused_until": {"$gt": now}},
        ],
    }
    order_match = {
        **alert_base_match,
        "$or": [
            {"status": ConversationStatus.ORDER_PENDING.value},
            {"order_note": {"$exists": True, "$nin": [None, ""]}},
        ],
    }

    messages = await _list_export_messages(message_match)
    new_conversations = await _list_export_conversations(new_conversation_match)
    needs_support = await _list_export_conversations(needs_support_match)
    for row in needs_support:
        row["support_reason"] = _support_reason(row, now=now)
    orders = await _list_export_conversations(order_match)
    return {
        "messages": messages,
        "new_conversations": new_conversations,
        "needs_support": needs_support,
        "orders": orders,
    }


def _synchronize_export_report_with_details(
    report: Dict[str, Any],
    details: Dict[str, List[Dict[str, Any]]],
) -> None:
    messages = details.get("messages") or []
    conversations = details.get("new_conversations") or []
    needs_support = details.get("needs_support") or []
    orders = details.get("orders") or []

    message_counts = {
        "total_messages": len(messages),
        "text_messages": 0,
        "image_messages": 0,
        "user_messages": 0,
        "staff_messages": 0,
        "bot_messages": 0,
    }
    messages_by_day: Dict[str, Dict[str, Any]] = {}
    for message in messages:
        content_type = str(message.get("content_type") or "").lower()
        role = str(message.get("role") or "").lower()
        if content_type == "text":
            message_counts["text_messages"] += 1
        elif content_type == "image":
            message_counts["image_messages"] += 1
        if role in {"user", "staff", "bot"}:
            message_counts[f"{role}_messages"] += 1

        created_at = _to_vn_aware_datetime(message.get("created_at"))
        if created_at is None:
            continue
        day = created_at.date().isoformat()
        daily = messages_by_day.setdefault(
            day,
            {
                "date": day,
                "total": 0,
                "text": 0,
                "image": 0,
                "user": 0,
                "staff": 0,
                "bot": 0,
            },
        )
        daily["total"] += 1
        if content_type in {"text", "image"}:
            daily[content_type] += 1
        if role in {"user", "staff", "bot"}:
            daily[role] += 1

    status_counts = {status.value: 0 for status in ConversationStatus}
    for conversation in conversations:
        status_value = _status_to_str(conversation.get("status"))
        if status_value in status_counts:
            status_counts[status_value] += 1

    summary = report.setdefault("summary", {})
    summary.update(message_counts)
    summary.update(
        {
            "total_conversations": len(conversations),
            "new_conversations": status_counts[ConversationStatus.NEW.value],
            "confirmed_conversations": status_counts[ConversationStatus.CONFIRMED.value],
            "handover_conversations": status_counts[ConversationStatus.HANDOVER.value],
            "apilimit_conversations": status_counts[ConversationStatus.APILIMIT.value],
            "order_pending_conversations": status_counts[
                ConversationStatus.ORDER_PENDING.value
            ],
            "needs_support_count": len(needs_support),
            "order_alert_count": len(orders),
        }
    )
    report["messages_by_day"] = [messages_by_day[day] for day in sorted(messages_by_day)]
    report["conversation_status"] = [
        {"status": status.value, "count": status_counts[status.value]}
        for status in ConversationStatus
    ]


async def list_dashboard_report_page_ids_service(
    *,
    include_inactive: bool = False,
) -> Dict[str, Any]:
    logger.info(
        "DASHBOARD_REPORT_PAGE_IDS_REQUEST include_inactive=%s",
        bool(include_inactive),
    )

    conversation_rows = await _aggregate_conversation_page_ids(
        include_inactive=include_inactive,
    )
    message_rows = await _aggregate_message_page_ids()

    items_by_page_id: Dict[str, Dict[str, Any]] = {}

    for row in conversation_rows:
        page_id = _clean_optional_text(row.get("_id"))
        if not page_id:
            continue
        item = items_by_page_id.setdefault(
            page_id,
            {
                "page_id": page_id,
                "conversation_count": 0,
                "message_count": 0,
                "latest_activity_at": None,
            },
        )
        item["conversation_count"] += max(
            0,
            _to_int_or_default(row.get("conversation_count"), 0),
        )
        item["latest_activity_at"] = _latest_datetime(
            item.get("latest_activity_at"),
            row.get("latest_activity_at"),
        )

    for row in message_rows:
        page_id = _clean_optional_text(row.get("_id"))
        if not page_id:
            continue
        item = items_by_page_id.setdefault(
            page_id,
            {
                "page_id": page_id,
                "conversation_count": 0,
                "message_count": 0,
                "latest_activity_at": None,
            },
        )
        item["message_count"] += max(
            0,
            _to_int_or_default(row.get("message_count"), 0),
        )
        item["latest_activity_at"] = _latest_datetime(
            item.get("latest_activity_at"),
            row.get("latest_activity_at"),
        )

    items = _sort_page_id_items(list(items_by_page_id.values()))
    logger.info("DASHBOARD_REPORT_PAGE_IDS_DONE count=%s", len(items))
    return {"items": items}


async def get_dashboard_report_service(
    *,
    from_date: Optional[Any],
    to_date: Optional[Any],
    page_id: Optional[str] = None,
    thread_type: Optional[str] = None,
    role: Optional[str] = None,
    include_inactive: bool = False,
    alert_limit: Optional[int] = None,
) -> Dict[str, Any]:
    start, query_end, display_end = _normalize_date_range(
        from_date=from_date,
        to_date=to_date,
    )
    normalized_page_id = _clean_optional_text(page_id)
    normalized_thread_type = _normalize_thread_type(thread_type)
    normalized_role = _normalize_role(role)
    normalized_alert_limit = _normalize_alert_limit(alert_limit)

    logger.info(
        "DASHBOARD_REPORT_REQUEST from_date=%s to_date=%s page_id=%s thread_type=%s role=%s",
        start.isoformat(),
        display_end.isoformat(),
        normalized_page_id,
        normalized_thread_type,
        normalized_role,
    )

    message_match = _base_message_match(
        start=start,
        end=query_end,
        page_id=normalized_page_id,
        thread_type=normalized_thread_type,
        role=normalized_role,
    )
    message_summary, messages_by_day = await _aggregate_message_report(message_match)

    conversation_match = _base_conversation_match(
        start=start,
        end=query_end,
        page_id=normalized_page_id,
        thread_type=normalized_thread_type,
        include_inactive=include_inactive,
    )
    status_counts, conversation_status = await _aggregate_conversation_status(conversation_match)

    alert_base_match = _base_conversation_match(
        page_id=normalized_page_id,
        thread_type=normalized_thread_type,
        include_inactive=include_inactive,
    )
    now = now_vn()
    needs_support_match = {
        **alert_base_match,
        "$or": [
            {"status": ConversationStatus.HANDOVER.value},
            {"status": ConversationStatus.APILIMIT.value},
            {"bot_paused_until": {"$gt": now}},
        ],
    }
    order_match = {
        **alert_base_match,
        "$or": [
            {"status": ConversationStatus.ORDER_PENDING.value},
            {"order_note": {"$exists": True, "$nin": [None, ""]}},
        ],
    }

    needs_support_rows, needs_support_count = await _aggregate_alert_rows(
        needs_support_match,
        limit=normalized_alert_limit,
    )
    order_rows, order_alert_count = await _aggregate_alert_rows(
        order_match,
        limit=normalized_alert_limit,
    )

    summary = {
        **message_summary,
        "total_conversations": sum(status_counts.values()),
        "new_conversations": status_counts[ConversationStatus.NEW.value],
        "confirmed_conversations": status_counts[ConversationStatus.CONFIRMED.value],
        "handover_conversations": status_counts[ConversationStatus.HANDOVER.value],
        "apilimit_conversations": status_counts[ConversationStatus.APILIMIT.value],
        "order_pending_conversations": status_counts[ConversationStatus.ORDER_PENDING.value],
        "needs_support_count": needs_support_count,
        "order_alert_count": order_alert_count,
    }

    logger.info(
        "DASHBOARD_REPORT_DONE total_messages=%s total_conversations=%s needs_support_count=%s order_alert_count=%s",
        summary["total_messages"],
        summary["total_conversations"],
        needs_support_count,
        order_alert_count,
    )

    return {
        "generated_at": now,
        "filters": {
            "from_date": start,
            "to_date": display_end,
            "page_id": normalized_page_id,
            "thread_type": normalized_thread_type,
            "role": normalized_role,
            "include_inactive": bool(include_inactive),
            "alert_limit": normalized_alert_limit,
        },
        "summary": summary,
        "messages_by_day": messages_by_day,
        "conversation_status": conversation_status,
        "alerts": {
            "needs_support": [
                _serialize_needs_support_alert(row, now=now)
                for row in needs_support_rows
            ],
            "orders": [_serialize_order_alert(row) for row in order_rows],
        },
    }


def _dashboard_report_filename(report: Dict[str, Any]) -> str:
    filters = report.get("filters") or {}
    start = _to_vn_aware_datetime(filters.get("from_date"))
    end = _to_vn_aware_datetime(filters.get("to_date"))
    start_text = start.date().isoformat() if start else "from"
    end_text = end.date().isoformat() if end else "to"
    return f"bao-cao-du-lieu-{start_text}-den-{end_text}.xlsx"


async def export_dashboard_report_excel_service(
    *,
    from_date: Optional[Any],
    to_date: Optional[Any],
    page_id: Optional[str] = None,
    thread_type: Optional[str] = None,
    role: Optional[str] = None,
    include_inactive: bool = False,
    alert_limit: Optional[int] = None,
) -> tuple[bytes, str]:
    logger.info(
        "DASHBOARD_REPORT_EXPORT_REQUEST from_date=%s to_date=%s page_id=%s thread_type=%s role=%s",
        from_date,
        to_date,
        _clean_optional_text(page_id),
        _clean_optional_text(thread_type),
        _clean_optional_text(role),
    )

    report = await get_dashboard_report_service(
        from_date=from_date,
        to_date=to_date,
        page_id=page_id,
        thread_type=thread_type,
        role=role,
        include_inactive=include_inactive,
        alert_limit=alert_limit,
    )
    export_details = await _collect_dashboard_report_export_details(
        from_date=from_date,
        to_date=to_date,
        page_id=page_id,
        thread_type=thread_type,
        role=role,
        include_inactive=include_inactive,
        as_of=report.get("generated_at"),
    )
    _synchronize_export_report_with_details(report, export_details)
    report["export_details"] = export_details
    report["exported_at"] = now_vn()
    workbook = build_dashboard_report_workbook(report)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue(), _dashboard_report_filename(report)
