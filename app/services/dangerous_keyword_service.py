from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any


DANGEROUS_KEYWORD_MATCHED_REASON = "dangerous_keyword_matched"
DANGEROUS_KEYWORD_FILE_MISSING_REASON = "dangerous_keyword_file_missing"
DANGEROUS_KEYWORD_LOAD_FAILED_REASON = "dangerous_keyword_load_failed"
DANGEROUS_KEYWORDS_PATH = Path(__file__).resolve().parents[2] / "docs" / "dangerous_keywords.md"

_cache_lock = Lock()
_cached_path: Path | None = None
_cached_mtime_ns: int | None = None
_cached_keywords: list[str] | None = None


class DangerousKeywordLoadError(Exception):
    def __init__(self, reason: str, *, path: Path) -> None:
        super().__init__(reason)
        self.reason = reason
        self.path = path


def reset_dangerous_keyword_cache() -> None:
    global _cached_path, _cached_mtime_ns, _cached_keywords
    with _cache_lock:
        _cached_path = None
        _cached_mtime_ns = None
        _cached_keywords = None


def _dedupe_keywords(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    keywords: list[str] = []
    for line in lines:
        keyword = line.strip()
        if not keyword or keyword in seen:
            continue
        seen.add(keyword)
        keywords.append(keyword)
    return keywords


def _is_word_char(value: str) -> bool:
    return value == "_" or value.isalnum()


def _keyword_matches(text: str, keyword: str) -> bool:
    if not keyword:
        return False

    start_index = 0
    keyword_starts_with_word = _is_word_char(keyword[0])
    keyword_ends_with_word = _is_word_char(keyword[-1])

    while True:
        index = text.find(keyword, start_index)
        if index < 0:
            return False

        before_index = index - 1
        after_index = index + len(keyword)
        before_is_word = before_index >= 0 and _is_word_char(text[before_index])
        after_is_word = after_index < len(text) and _is_word_char(text[after_index])

        if keyword_starts_with_word and before_is_word:
            start_index = index + 1
            continue
        if keyword_ends_with_word and after_is_word:
            start_index = index + 1
            continue
        return True


def load_dangerous_keywords(path: Path | str | None = None) -> list[str]:
    global _cached_path, _cached_mtime_ns, _cached_keywords

    keyword_path = Path(path) if path is not None else DANGEROUS_KEYWORDS_PATH
    try:
        stat = keyword_path.stat()
    except FileNotFoundError as exc:
        raise DangerousKeywordLoadError(DANGEROUS_KEYWORD_FILE_MISSING_REASON, path=keyword_path) from exc
    except OSError as exc:
        raise DangerousKeywordLoadError(DANGEROUS_KEYWORD_LOAD_FAILED_REASON, path=keyword_path) from exc

    mtime_ns = stat.st_mtime_ns
    with _cache_lock:
        if (
            _cached_path == keyword_path
            and _cached_mtime_ns == mtime_ns
            and _cached_keywords is not None
        ):
            return list(_cached_keywords)

        try:
            text = keyword_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise DangerousKeywordLoadError(DANGEROUS_KEYWORD_LOAD_FAILED_REASON, path=keyword_path) from exc

        keywords = _dedupe_keywords(text.splitlines())
        _cached_path = keyword_path
        _cached_mtime_ns = mtime_ns
        _cached_keywords = keywords
        return list(keywords)


def check_dangerous_keyword(
    text: Any,
    *,
    path: Path | str | None = None,
) -> dict[str, Any]:
    message_text = "" if text is None else str(text)
    if not message_text:
        return {
            "blocked": False,
            "reason": None,
            "matched_keyword": None,
        }

    for keyword in load_dangerous_keywords(path):
        if _keyword_matches(message_text, keyword):
            return {
                "blocked": True,
                "reason": DANGEROUS_KEYWORD_MATCHED_REASON,
                "matched_keyword": keyword,
            }

    return {
        "blocked": False,
        "reason": None,
        "matched_keyword": None,
    }
