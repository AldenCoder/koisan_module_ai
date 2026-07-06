import re
import unicodedata
from typing import Any, Dict, Pattern


HANDOVER_DETECTED_REASON = "ai_reply_handover_keyword"

HANDOVER_REPLY_PATTERNS: tuple[tuple[str, Pattern[str]], ...] = (
    (
        "chuyen bo phan phu trach",
        re.compile(r"\b(?:em\s+)?chuyen\s+bo\s+phan\s+phu\s+trach\b"),
    ),
    ("em chuyen sale", re.compile(r"\bem\s+chuyen\s+sale\b")),
    ("da em xin loi", re.compile(r"\bda\s+em\s+xin\s+loi\b")),
    (
        "can bo phan phu trach kiem tra",
        re.compile(r"\bcan\s+bo\s+phan\s+phu\s+trach\s+kiem\s+tra\b"),
    ),
    ("em chuyen xu ly", re.compile(r"\bem\s+chuyen\s+xu\s+ly\b")),
    (
        "cho em 1 lat em check",
        re.compile(
            r"\b(?:(?:anh|chi|minh|ban)\s+)?cho\s+em\s+"
            r"(?:(?:1|mot)\s+)?(?:lat|chut|xiu)\b.*"
            r"\bem\s+(?:check|kiem\s+tra)\b"
        ),
    ),
)


def normalize_handover_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""

    text = text.replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", text)
    without_marks = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    normalized = unicodedata.normalize("NFC", without_marks)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def detect_handover_reply(value: Any) -> Dict[str, Any]:
    normalized_text = normalize_handover_text(value)
    if not normalized_text:
        return {
            "detected": False,
            "reason": None,
            "matched_pattern": None,
        }

    for pattern_name, pattern in HANDOVER_REPLY_PATTERNS:
        if pattern.search(normalized_text):
            return {
                "detected": True,
                "reason": HANDOVER_DETECTED_REASON,
                "matched_pattern": pattern_name,
            }

    return {
        "detected": False,
        "reason": None,
        "matched_pattern": None,
    }
