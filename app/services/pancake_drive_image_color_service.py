"""Color helpers for Pancake Drive image selection."""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from app.core.config import settings
from logs.logging_config import logger


DEFAULT_PANCAKE_IMAGE_COLOR_MAP: dict[str, list[str]] = {
    "be": ["be", "beige"],
    "cam": ["cam"],
    "den": ["den", "đen"],
    "do": ["do", "đỏ"],
    "ghi": ["ghi"],
    "hong": ["hong", "hồng"],
    "kem": ["kem"],
    "nau": ["nau", "nâu"],
    "tim": ["tim", "tím"],
    "trang": ["trang", "trắng"],
    "vang": ["vang", "vàng"],
    "xam": ["xam", "xám"],
    "xanh": ["xanh"],
    "xanhbien": ["xanh bien", "xanh biển", "xanhbien"],
    "xanhda": ["xanh da", "xanh đá", "xanhda"],
    "xanhduong": ["xanh duong", "xanh dương", "xanhduong"],
    "xanhla": ["xanh la", "xanh lá", "xanhla"],
    "xanhngoc": ["xanh ngoc", "xanh ngọc", "xanhngoc"],
    "xanhreu": ["xanh reu", "xanh rêu", "xanhreu"],
}

_TRIGGER_PATTERN = re.compile(r"(?<![0-9A-Za-zÀ-ỹ_])màu\s+", re.IGNORECASE)
_PHRASE_TERMINATOR_PATTERN = re.compile(r"https?://|[\r\n.!?:]", re.IGNORECASE)
_MARKDOWN_CHARS_PATTERN = re.compile(r"[*`~]+")
_COLOR_SPLIT_PATTERN = re.compile(r"\s*(?:,|/|\bvà\b)\s*", re.IGNORECASE)
_COLOR_TRAILING_WORDS = {
    "a",
    "ạ",
    "nha",
    "nhé",
    "nhe",
}
_NON_COLOR_LEADING_WORDS = {
    "gi",
    "nao",
    "nào",
}


@dataclass(frozen=True)
class RequestedColorMatch:
    primary: Optional[str] = None
    phrases: list[str] = field(default_factory=list)
    terms: list[str] = field(default_factory=list)


def _strip_vietnamese_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", str(value or ""))
    without_marks = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return without_marks.replace("đ", "d").replace("Đ", "D")


def _normalize_spaces(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def normalize_color_text(value: Any) -> str:
    text = _strip_vietnamese_accents(str(value or "")).lower()
    text = re.sub(r"[^0-9a-z]+", " ", text)
    return _normalize_spaces(text)


def normalize_color_key(value: Any) -> Optional[str]:
    normalized = normalize_color_text(value).replace(" ", "")
    return normalized or None


def _normalize_color_map(raw_map: dict[str, Any]) -> dict[str, list[str]]:
    normalized_map: dict[str, list[str]] = {}
    for raw_key, raw_aliases in raw_map.items():
        color_key = normalize_color_key(raw_key)
        if not color_key:
            continue

        aliases: list[Any]
        if isinstance(raw_aliases, list):
            aliases = list(raw_aliases)
        else:
            aliases = [raw_aliases]
        aliases.append(raw_key)

        normalized_aliases: list[str] = []
        for alias in aliases:
            normalized_alias = normalize_color_text(alias)
            if normalized_alias and normalized_alias not in normalized_aliases:
                normalized_aliases.append(normalized_alias)

        if normalized_aliases:
            normalized_map[color_key] = normalized_aliases

    return normalized_map


def _color_alias_candidates(color_map: dict[str, list[str]]) -> list[tuple[str, str]]:
    alias_candidates: list[tuple[str, str]] = []
    for color_key, aliases in color_map.items():
        for alias in aliases:
            normalized_alias = normalize_color_text(alias)
            if normalized_alias:
                alias_candidates.append((color_key, normalized_alias))
    alias_candidates.sort(key=lambda item: (len(item[1].split()), len(item[1])), reverse=True)
    return alias_candidates


def _append_unique(target: list[str], values: Iterable[Any]) -> None:
    existing = set(target)
    for value in values:
        normalized = _normalize_spaces(str(value or "")).lower()
        if not normalized or normalized in existing:
            continue
        target.append(normalized)
        existing.add(normalized)


def _strip_phrase_wrappers(value: str) -> str:
    text = str(value or "")
    text = _MARKDOWN_CHARS_PATTERN.sub("", text)
    text = text.replace("<", " ").replace(">", " ")
    text = text.replace("[", " ").replace("]", " ")
    text = text.replace("(", " ").replace(")", " ")
    text = _normalize_spaces(text)
    return text.strip(" \t\r\n,;:-")


def _strip_trailing_color_words(value: str) -> str:
    words = _strip_phrase_wrappers(value).split()
    while words:
        normalized_last_word = normalize_color_key(words[-1])
        if normalized_last_word not in _COLOR_TRAILING_WORDS:
            break
        words.pop()
    return _strip_phrase_wrappers(" ".join(words))


def _is_probable_color_phrase(value: str) -> bool:
    normalized = normalize_color_text(value)
    if not normalized:
        return False
    first_word = normalized.split()[0]
    return first_word not in _NON_COLOR_LEADING_WORDS


def _extract_phrase_after_trigger(text: str, start: int) -> str:
    remainder = str(text or "")[start:]
    terminator = _PHRASE_TERMINATOR_PATTERN.search(remainder)
    if terminator:
        remainder = remainder[: terminator.start()]
    return _strip_phrase_wrappers(remainder)


def extract_requested_color_phrases(
    text: str,
    *,
    has_drive_link: bool,
    enabled: Optional[bool] = None,
) -> list[str]:
    if not has_drive_link:
        return []
    if not is_pancake_image_color_filter_enabled(enabled):
        return []

    source = str(text or "")
    if not source.strip():
        return []

    phrases: list[str] = []
    seen: set[str] = set()
    for match in _TRIGGER_PATTERN.finditer(source):
        raw_phrase = _extract_phrase_after_trigger(source, match.end())
        if not raw_phrase:
            continue
        if not _is_probable_color_phrase(raw_phrase):
            continue

        for part in _COLOR_SPLIT_PATTERN.split(raw_phrase):
            phrase = _strip_trailing_color_words(part)
            phrase_key = normalize_color_key(phrase)
            if not phrase_key or phrase_key in seen:
                continue
            if not _is_probable_color_phrase(phrase):
                continue
            phrases.append(phrase)
            seen.add(phrase_key)

    return phrases


def _exact_color_key_for_phrase(
    phrase: str,
    color_map: dict[str, list[str]],
) -> Optional[str]:
    normalized_phrase = normalize_color_text(phrase)
    phrase_key = normalize_color_key(phrase)
    if not normalized_phrase or not phrase_key:
        return None

    for color_key, aliases in color_map.items():
        if phrase_key == color_key:
            return color_key
        for alias in aliases:
            normalized_alias = normalize_color_text(alias)
            if normalized_phrase == normalized_alias:
                return color_key
    return None


def _terms_for_color_phrase(phrase: str) -> list[str]:
    cleaned_phrase = _strip_phrase_wrappers(phrase).lower()
    raw_words = [word for word in cleaned_phrase.split() if word]
    normalized_phrase = normalize_color_text(cleaned_phrase)
    normalized_words = normalized_phrase.split()

    terms: list[str] = []
    _append_unique(terms, [cleaned_phrase, normalized_phrase])
    if normalized_words:
        _append_unique(terms, ["".join(normalized_words), "_".join(normalized_words), "-".join(normalized_words)])
    if raw_words:
        _append_unique(terms, ["_".join(raw_words), "-".join(raw_words)])
    _append_unique(terms, raw_words)
    _append_unique(terms, normalized_words)
    return terms


def build_color_match_terms(
    phrases: Iterable[str],
    *,
    color_map: Optional[dict[str, list[str]]] = None,
) -> list[str]:
    resolved_color_map = color_map or get_pancake_image_color_map()
    terms: list[str] = []

    for phrase in phrases:
        cleaned_phrase = _strip_trailing_color_words(str(phrase or ""))
        if not cleaned_phrase:
            continue

        phrase_terms = _terms_for_color_phrase(cleaned_phrase)
        color_key = _exact_color_key_for_phrase(cleaned_phrase, resolved_color_map)
        if color_key:
            aliases = resolved_color_map.get(color_key, [])
            phrase_terms.extend([color_key, *aliases])
        _append_unique(terms, phrase_terms)

    return terms


def normalize_color_terms(terms: Iterable[Any] | None) -> list[str]:
    normalized_terms: list[str] = []
    _append_unique(normalized_terms, terms or [])
    return normalized_terms


def build_requested_color_match(
    text: str,
    *,
    has_drive_link: bool,
    enabled: Optional[bool] = None,
    color_map: Optional[dict[str, list[str]]] = None,
) -> RequestedColorMatch:
    phrases = extract_requested_color_phrases(text, has_drive_link=has_drive_link, enabled=enabled)
    if not phrases:
        return RequestedColorMatch()

    resolved_color_map = color_map or get_pancake_image_color_map()
    terms = build_color_match_terms(phrases, color_map=resolved_color_map)

    primary: Optional[str] = None
    for phrase in phrases:
        color_key = _exact_color_key_for_phrase(phrase, resolved_color_map)
        if color_key:
            primary = color_key
            break

    if not primary:
        primary = normalize_color_key(phrases[0])

    return RequestedColorMatch(
        primary=primary,
        phrases=list(phrases),
        terms=terms,
    )


def _normalized_text_contains_term(normalized_text: str, normalized_term: str) -> bool:
    if not normalized_text or not normalized_term:
        return False

    if " " in normalized_term:
        compact_text = normalized_text.replace(" ", "")
        compact_term = normalized_term.replace(" ", "")
        return (
            normalized_text == normalized_term
            or normalized_text.startswith(f"{normalized_term} ")
            or normalized_text.endswith(f" {normalized_term}")
            or f" {normalized_term} " in normalized_text
            or bool(compact_term and compact_term in compact_text)
        )

    return normalized_term in normalized_text.split()


def name_matches_color_terms(name: Any, terms: Iterable[Any] | None) -> bool:
    normalized_name = normalize_color_text(name)
    if not normalized_name:
        return False

    for term in normalize_color_terms(terms):
        normalized_term = normalize_color_text(term)
        if _normalized_text_contains_term(normalized_name, normalized_term):
            return True
    return False


def get_pancake_image_color_map(raw: Optional[Any] = None) -> dict[str, list[str]]:
    configured = raw if raw is not None else getattr(settings, "pancake_image_color_map", None)
    if not configured:
        return _normalize_color_map(DEFAULT_PANCAKE_IMAGE_COLOR_MAP)

    parsed: Any = configured
    if isinstance(configured, str):
        text = configured.strip()
        try:
            if text.startswith("{"):
                parsed = json.loads(text)
            else:
                path = Path(text)
                if path.is_file():
                    parsed = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("PANCAKE_IMAGE_COLOR_MAP_INVALID reason=%s", exc)
            return _normalize_color_map(DEFAULT_PANCAKE_IMAGE_COLOR_MAP)

    if not isinstance(parsed, dict):
        logger.warning("PANCAKE_IMAGE_COLOR_MAP_INVALID reason=not_dict")
        return _normalize_color_map(DEFAULT_PANCAKE_IMAGE_COLOR_MAP)

    return _normalize_color_map(parsed)


def is_pancake_image_color_filter_enabled(raw: Optional[Any] = None) -> bool:
    value = raw if raw is not None else getattr(settings, "pancake_image_color_filter_enabled", True)
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def detect_requested_color(
    text: str,
    *,
    has_drive_link: bool,
    enabled: Optional[bool] = None,
    color_map: Optional[dict[str, list[str]]] = None,
) -> Optional[str]:
    return build_requested_color_match(
        text,
        has_drive_link=has_drive_link,
        enabled=enabled,
        color_map=color_map,
    ).primary


def parse_drive_file_color_from_name(
    file_name: Any,
    *,
    color_map: Optional[dict[str, list[str]]] = None,
) -> Optional[str]:
    normalized_name = _normalize_spaces(str(file_name or ""))
    if not normalized_name:
        return None

    stem = Path(normalized_name).stem
    if not stem:
        return None

    parts = [part for part in stem.lower().split("_") if part]
    if not parts:
        return None

    candidate_key = normalize_color_key(parts[-1])
    if not candidate_key:
        return None

    resolved_color_map = color_map or get_pancake_image_color_map()
    return candidate_key if candidate_key in resolved_color_map else None


def parse_drive_folder_color_from_name(
    folder_name: Any,
    *,
    color_map: Optional[dict[str, list[str]]] = None,
) -> Optional[str]:
    normalized_name = normalize_color_text(folder_name)
    if not normalized_name:
        return None

    resolved_color_map = color_map or get_pancake_image_color_map()
    for color_key, alias in _color_alias_candidates(resolved_color_map):
        if (
            normalized_name == alias
            or normalized_name.startswith(f"{alias} ")
            or normalized_name.endswith(f" {alias}")
            or f" {alias} " in normalized_name
        ):
            return color_key
    return None
