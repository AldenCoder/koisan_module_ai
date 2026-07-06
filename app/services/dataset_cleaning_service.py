from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


SYSTEM_ASSISTANT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*Đã đặt giai đoạn", re.IGNORECASE),
    re.compile(r"^\s*Đã thêm nhãn tự động", re.IGNORECASE),
    re.compile(r"^\s*Tác nhân AI sẽ phản hồi\.?\s*$", re.IGNORECASE),
    re.compile(r"^\s*Đã tạo", re.IGNORECASE),
    re.compile(r"^\s*Đã cập nhật", re.IGNORECASE),
    re.compile(r"^\s*Đã chuyển", re.IGNORECASE),
    re.compile(r"^\s*Đã gán", re.IGNORECASE),
)


def _artifacts_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "artifacts" / "training_data"


def _sanitize_filename(filename: str) -> str:
    safe_name = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in filename)
    return safe_name or "uploaded.jsonl"


def _is_system_like_assistant_message(content: str) -> bool:
    normalized = (content or "").strip()
    if not normalized:
        return True
    return any(pattern.search(normalized) for pattern in SYSTEM_ASSISTANT_PATTERNS)


def _validate_record(record: Dict[str, Any]) -> Tuple[bool, str]:
    messages = record.get("messages")
    if not isinstance(messages, list) or len(messages) != 2:
        return False, "invalid_message_shape"

    user_message, assistant_message = messages
    if not isinstance(user_message, dict) or not isinstance(assistant_message, dict):
        return False, "invalid_message_shape"

    if user_message.get("role") != "user" or assistant_message.get("role") != "assistant":
        return False, "invalid_role_order"

    user_content = str(user_message.get("content") or "").strip()
    assistant_content = str(assistant_message.get("content") or "").strip()

    if not user_content:
        return False, "empty_user_content"
    if not assistant_content:
        return False, "empty_assistant_content"
    if _is_system_like_assistant_message(assistant_content):
        return False, "system_like_assistant"

    return True, "kept"


def _rejection_sample(line_number: int, reason: str, record: Dict[str, Any]) -> Dict[str, str]:
    messages = record.get("messages")
    user_preview = ""
    assistant_preview = ""
    if isinstance(messages, list) and len(messages) >= 1 and isinstance(messages[0], dict):
        user_preview = str(messages[0].get("content") or "")[:160]
    if isinstance(messages, list) and len(messages) >= 2 and isinstance(messages[1], dict):
        assistant_preview = str(messages[1].get("content") or "")[:160]

    return {
        "line_number": str(line_number),
        "reason": reason,
        "user_preview": user_preview,
        "assistant_preview": assistant_preview,
    }


def clean_training_pairs_jsonl(
    *,
    source_name: str,
    content_bytes: bytes,
    sample_limit: int = 10,
) -> Dict[str, Any]:
    decoded = content_bytes.decode("utf-8-sig")
    lines = decoded.splitlines()

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    artifacts_dir = _artifacts_dir()
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    safe_source_name = _sanitize_filename(source_name)
    base_name = safe_source_name[:-6] if safe_source_name.endswith(".jsonl") else safe_source_name
    cleaned_path = artifacts_dir / f"{base_name}_cleaned_{timestamp}.jsonl"
    rejected_path = artifacts_dir / f"{base_name}_rejected_{timestamp}.jsonl"

    total_records = 0
    cleaned_records = 0
    rejected_records = 0
    rejection_reasons: Counter[str] = Counter()
    sample_rejections: List[Dict[str, str]] = []

    with cleaned_path.open("w", encoding="utf-8") as cleaned_file, rejected_path.open(
        "w", encoding="utf-8"
    ) as rejected_file:
        for line_number, raw_line in enumerate(lines, start=1):
            if not raw_line.strip():
                continue

            total_records += 1

            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError:
                rejected_records += 1
                rejection_reasons["invalid_json"] += 1
                rejected_file.write(
                    json.dumps(
                        {
                            "line_number": line_number,
                            "reason": "invalid_json",
                            "raw_line": raw_line,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                if len(sample_rejections) < sample_limit:
                    sample_rejections.append(
                        {
                            "line_number": str(line_number),
                            "reason": "invalid_json",
                            "user_preview": "",
                            "assistant_preview": raw_line[:160],
                        }
                    )
                continue

            if not isinstance(record, dict):
                rejected_records += 1
                rejection_reasons["invalid_record_type"] += 1
                rejected_file.write(
                    json.dumps(
                        {
                            "line_number": line_number,
                            "reason": "invalid_record_type",
                            "record": record,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                if len(sample_rejections) < sample_limit:
                    sample_rejections.append(
                        {
                            "line_number": str(line_number),
                            "reason": "invalid_record_type",
                            "user_preview": "",
                            "assistant_preview": str(record)[:160],
                        }
                    )
                continue

            is_valid, reason = _validate_record(record)
            if is_valid:
                cleaned_records += 1
                cleaned_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                continue

            rejected_records += 1
            rejection_reasons[reason] += 1
            rejected_file.write(
                json.dumps(
                    {
                        "line_number": line_number,
                        "reason": reason,
                        "record": record,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            if len(sample_rejections) < sample_limit:
                sample_rejections.append(_rejection_sample(line_number, reason, record))

    return {
        "original_filename": source_name,
        "cleaned_file_path": str(cleaned_path),
        "rejected_file_path": str(rejected_path),
        "total_records": total_records,
        "cleaned_records": cleaned_records,
        "rejected_records": rejected_records,
        "rejection_reasons": dict(sorted(rejection_reasons.items())),
        "sample_rejections": sample_rejections,
    }
