"""Helpers for Pancake image replies backed by Google Drive file links."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Any, Iterable, Optional
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import settings
from app.services.pancake_drive_image_color_service import build_requested_color_match
from app.services.google_drive_image_service import parse_drive_folder_id
from logs.logging_config import logger


PANCAKE_DRIVE_FILE_HOSTS = {"drive.google.com"}
PANCAKE_DRIVE_IMAGE_CACHE_VERSION = 1
PANCAKE_DRIVE_IMAGE_MIME_TYPES = {"image/jpeg", "image/png"}
PANCAKE_DRIVE_DIRECT_DOWNLOAD_BASE_URL = "https://drive.google.com/uc"
PANCAKE_DRIVE_DEFAULT_IMAGE_LIMIT = 3
PANCAKE_DRIVE_DEFAULT_STORAGE_MAX_BYTES = 500_000
PANCAKE_DRIVE_MAX_OPTIMIZE_DIMENSION = 1600
PANCAKE_DRIVE_IMAGE_SCALE_STEPS = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.25, 0.2, 0.15, 0.1)
PANCAKE_DRIVE_JPEG_QUALITY_STEPS = (85, 80, 75, 70, 65, 60, 55, 50, 45, 40, 35, 30)
_DRIVE_URL_PATTERN = re.compile(r"https?://[^\s<>\]\[\"']+", re.IGNORECASE)
_DRIVE_FILE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_cache_write_lock = Lock()


class PancakeDriveImageOptimizationError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class PancakeDriveFileUrlSplitResult:
    text: str
    drive_file_urls: list[str]
    skipped_count: int = 0


@dataclass(frozen=True)
class PancakeDriveUrlSplitResult:
    text: str
    drive_file_urls: list[str]
    drive_folder_urls: list[str]
    skipped_count: int = 0


@dataclass(frozen=True)
class PreparedPancakeDriveReply:
    text: str
    drive_file_urls: list[str]
    drive_file_ids: list[str]
    image_limit: int
    requested_color: Optional[str] = None
    requested_color_phrases: list[str] = field(default_factory=list)
    requested_color_terms: list[str] = field(default_factory=list)
    color_filter_applied: bool = False
    color_filter_reason: Optional[str] = None
    drive_file_metadata: dict[str, dict[str, Any]] = field(default_factory=dict)
    selected_drive_file_ids: list[str] = field(default_factory=list)
    drive_folder_urls: list[str] = field(default_factory=list)
    drive_folder_results: list[dict[str, Any]] = field(default_factory=list)
    drive_folder_error_count: int = 0
    content_ids: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    skipped_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "drive_file_urls": list(self.drive_file_urls),
            "drive_file_ids": list(self.drive_file_ids),
            "image_limit": self.image_limit,
            "requested_color": self.requested_color,
            "requested_color_phrases": list(self.requested_color_phrases),
            "requested_color_terms": list(self.requested_color_terms),
            "color_filter_applied": self.color_filter_applied,
            "color_filter_reason": self.color_filter_reason,
            "drive_file_metadata": dict(self.drive_file_metadata),
            "selected_drive_file_ids": list(self.selected_drive_file_ids),
            "drive_folder_urls": list(self.drive_folder_urls),
            "drive_folder_results": list(self.drive_folder_results),
            "drive_folder_error_count": self.drive_folder_error_count,
            "content_ids": list(self.content_ids),
            "errors": list(self.errors),
            "skipped_count": self.skipped_count,
        }


@dataclass(frozen=True)
class PancakeDriveLocalImageResult:
    drive_file_id: str
    drive_url: str
    direct_download_url: str
    local_path: str
    cache_hit: bool = False
    downloaded: bool = False
    content_id: Optional[str] = None
    drive_file_name: Optional[str] = None
    drive_file_color: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    local_present: Optional[bool] = None
    optimized: bool = False
    original_size_bytes: Optional[int] = None
    cache_entry_removed: bool = False
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "drive_file_id": self.drive_file_id,
            "drive_url": self.drive_url,
            "direct_download_url": self.direct_download_url,
            "local_path": self.local_path,
            "cache_hit": self.cache_hit,
            "downloaded": self.downloaded,
        }
        if self.content_id:
            data["content_id"] = self.content_id
        if self.drive_file_name:
            data["drive_file_name"] = self.drive_file_name
        if self.drive_file_color:
            data["drive_file_color"] = self.drive_file_color
        if self.mime_type:
            data["mime_type"] = self.mime_type
        if self.size_bytes is not None:
            data["size_bytes"] = self.size_bytes
        if self.local_present is not None:
            data["local_present"] = self.local_present
        if self.optimized:
            data["optimized"] = True
        if self.original_size_bytes is not None:
            data["original_size_bytes"] = self.original_size_bytes
        if self.cache_entry_removed:
            data["cache_entry_removed"] = True
        if self.error:
            data["error"] = self.error
        return data


@dataclass(frozen=True)
class PancakeDriveLocalImageBatchResult:
    images: list[PancakeDriveLocalImageResult]
    errors: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "images": [image.to_dict() for image in self.images],
            "errors": list(self.errors),
        }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_optional_metadata_text(value: Any) -> Optional[str]:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized or None


def _normalize_text_preserving_paragraphs(text: str) -> str:
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


def _get_configured_image_limit(image_limit: Optional[int] = None) -> int:
    raw = image_limit if image_limit is not None else PANCAKE_DRIVE_DEFAULT_IMAGE_LIMIT
    if raw is None:
        raw = PANCAKE_DRIVE_DEFAULT_IMAGE_LIMIT
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = PANCAKE_DRIVE_DEFAULT_IMAGE_LIMIT
    return max(1, value)


def _get_configured_download_timeout(timeout: Optional[float] = None) -> float:
    raw = timeout if timeout is not None else getattr(settings, "pancake_image_download_timeout_seconds", 15.0)
    try:
        value = float(raw or 15.0)
    except (TypeError, ValueError):
        value = 15.0
    return max(0.1, value)


def _get_configured_max_bytes(max_bytes: Optional[int] = None) -> int:
    raw = max_bytes if max_bytes is not None else getattr(settings, "pancake_image_max_bytes", 10 * 1024 * 1024)
    try:
        value = int(raw or 10 * 1024 * 1024)
    except (TypeError, ValueError):
        value = 10 * 1024 * 1024
    return max(1, value)


def _get_configured_storage_max_bytes(storage_max_bytes: Optional[int] = None) -> int:
    raw = (
        storage_max_bytes
        if storage_max_bytes is not None
        else getattr(settings, "pancake_image_storage_max_bytes", PANCAKE_DRIVE_DEFAULT_STORAGE_MAX_BYTES)
    )
    try:
        value = int(raw or PANCAKE_DRIVE_DEFAULT_STORAGE_MAX_BYTES)
    except (TypeError, ValueError):
        value = PANCAKE_DRIVE_DEFAULT_STORAGE_MAX_BYTES
    return max(1, value)


def _get_configured_reuse_uploaded_content_id(reuse_uploaded_content_id: Optional[bool] = None) -> bool:
    raw = (
        reuse_uploaded_content_id
        if reuse_uploaded_content_id is not None
        else getattr(settings, "pancake_reuse_uploaded_content_id", True)
    )
    if isinstance(raw, bool):
        return raw
    return str(raw or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_drive_file_id(drive_url: str) -> str:
    normalized_url = str(drive_url or "").strip()
    if not normalized_url:
        raise ValueError("drive_file_url_empty")

    parsed = urlparse(normalized_url)
    if parsed.scheme.lower() != "https":
        raise ValueError("drive_file_url_invalid_scheme")
    if parsed.netloc.lower() not in PANCAKE_DRIVE_FILE_HOSTS:
        raise ValueError("drive_file_url_invalid_host")

    path_parts = [part for part in parsed.path.split("/") if part]
    drive_file_id: Optional[str] = None

    for index, part in enumerate(path_parts):
        if part == "file" and index + 2 < len(path_parts) and path_parts[index + 1] == "d":
            drive_file_id = path_parts[index + 2].strip()
            break

    if not drive_file_id:
        query_id = parse_qs(parsed.query).get("id")
        if query_id:
            drive_file_id = str(query_id[0] or "").strip()

    if not drive_file_id:
        raise ValueError("drive_file_id_not_found")
    if not _DRIVE_FILE_ID_PATTERN.fullmatch(drive_file_id):
        raise ValueError("drive_file_id_invalid")

    return drive_file_id


def build_drive_file_download_url(drive_file_id: str) -> str:
    normalized_file_id = str(drive_file_id or "").strip()
    if not normalized_file_id:
        raise ValueError("drive_file_id_empty")
    return f"{PANCAKE_DRIVE_DIRECT_DOWNLOAD_BASE_URL}?{urlencode({'export': 'download', 'id': normalized_file_id})}"


def build_drive_file_view_url(drive_file_id: str) -> str:
    normalized_file_id = str(drive_file_id or "").strip()
    if not normalized_file_id:
        raise ValueError("drive_file_id_empty")
    return f"https://drive.google.com/file/d/{normalized_file_id}/view"


def _trim_drive_file_url(raw_url: str) -> str:
    trimmed = str(raw_url or "").strip()
    while trimmed:
        try:
            parse_drive_file_id(trimmed)
            return trimmed
        except ValueError:
            if trimmed[-1].isalnum() or trimmed[-1] in "_-":
                return trimmed
            trimmed = trimmed[:-1].rstrip()
    return trimmed


def _trim_drive_folder_url(raw_url: str) -> str:
    trimmed = str(raw_url or "").strip()
    while trimmed:
        try:
            parse_drive_folder_id(trimmed)
            return trimmed
        except ValueError:
            if trimmed[-1].isalnum() or trimmed[-1] in "_-":
                return trimmed
            trimmed = trimmed[:-1].rstrip()
    return trimmed


def split_text_and_pancake_drive_urls(message_text: str) -> PancakeDriveUrlSplitResult:
    source_text = str(message_text or "")
    accepted_file_urls: list[str] = []
    accepted_folder_urls: list[str] = []
    accepted_file_set: set[str] = set()
    accepted_folder_set: set[str] = set()
    skipped_count = 0
    cleaned_lines: list[str] = []

    for line in source_text.splitlines():
        cleaned_parts: list[str] = []
        cursor = 0
        line_had_drive_url = False

        for match in _DRIVE_URL_PATTERN.finditer(line):
            raw_url = match.group(0)
            file_url = _trim_drive_file_url(raw_url)
            folder_url = _trim_drive_folder_url(raw_url)
            url_kind: Optional[str] = None
            normalized_url = ""

            try:
                parse_drive_file_id(file_url)
                url_kind = "file"
                normalized_url = file_url
            except ValueError:
                try:
                    parse_drive_folder_id(folder_url)
                    url_kind = "folder"
                    normalized_url = folder_url
                except ValueError:
                    skipped_count += 1
                    continue

            line_had_drive_url = True
            cleaned_parts.append(line[cursor:match.start()])
            cursor = match.end()

            if url_kind == "file":
                if normalized_url not in accepted_file_set:
                    accepted_file_set.add(normalized_url)
                    accepted_file_urls.append(normalized_url)
                else:
                    skipped_count += 1
                continue

            if normalized_url not in accepted_folder_set:
                accepted_folder_set.add(normalized_url)
                accepted_folder_urls.append(normalized_url)
            else:
                skipped_count += 1

        cleaned_parts.append(line[cursor:])
        cleaned_line = "".join(cleaned_parts).strip()
        if line_had_drive_url and not _line_has_readable_text(cleaned_line):
            continue
        cleaned_lines.append(cleaned_line)

    return PancakeDriveUrlSplitResult(
        text=_normalize_text_preserving_paragraphs("\n".join(cleaned_lines)),
        drive_file_urls=accepted_file_urls,
        drive_folder_urls=accepted_folder_urls,
        skipped_count=skipped_count,
    )


def split_text_and_drive_file_urls(message_text: str) -> PancakeDriveFileUrlSplitResult:
    source_text = str(message_text or "")
    accepted_urls: list[str] = []
    accepted_set: set[str] = set()
    skipped_count = 0
    cleaned_lines: list[str] = []

    for line in source_text.splitlines():
        cleaned_parts: list[str] = []
        cursor = 0
        line_had_drive_url = False

        for match in _DRIVE_URL_PATTERN.finditer(line):
            candidate_url = _trim_drive_file_url(match.group(0))
            try:
                parse_drive_file_id(candidate_url)
            except ValueError:
                skipped_count += 1
                continue

            line_had_drive_url = True
            cleaned_parts.append(line[cursor:match.start()])
            cursor = match.end()
            if candidate_url not in accepted_set:
                accepted_set.add(candidate_url)
                accepted_urls.append(candidate_url)
            else:
                skipped_count += 1

        cleaned_parts.append(line[cursor:])
        cleaned_line = "".join(cleaned_parts).strip()
        if line_had_drive_url and not _line_has_readable_text(cleaned_line):
            continue
        cleaned_lines.append(cleaned_line)

    return PancakeDriveFileUrlSplitResult(
        text=_normalize_text_preserving_paragraphs("\n".join(cleaned_lines)),
        drive_file_urls=accepted_urls,
        skipped_count=skipped_count,
    )


def extract_drive_file_urls_from_text(message_text: str) -> list[str]:
    return split_text_and_drive_file_urls(message_text).drive_file_urls


def prepare_pancake_drive_reply(
    message_text: str,
    *,
    image_limit: Optional[int] = None,
) -> PreparedPancakeDriveReply:
    split_result = split_text_and_pancake_drive_urls(message_text)
    limit = _get_configured_image_limit(image_limit)
    drive_file_urls: list[str] = []
    drive_file_ids: list[str] = []
    accepted_ids: set[str] = set()
    errors: list[dict[str, Any]] = []
    has_drive_link = bool(split_result.drive_file_urls or split_result.drive_folder_urls)
    requested_color_match = build_requested_color_match(split_result.text, has_drive_link=has_drive_link)
    requested_color = requested_color_match.primary
    requested_color_terms = list(requested_color_match.terms)

    for drive_url in split_result.drive_file_urls:
        try:
            drive_file_id = parse_drive_file_id(drive_url)
        except ValueError as exc:
            errors.append({"drive_url": drive_url, "reason": str(exc) or "invalid_drive_file_url"})
            continue

        if drive_file_id in accepted_ids:
            continue
        accepted_ids.add(drive_file_id)
        drive_file_urls.append(drive_url)
        drive_file_ids.append(drive_file_id)

    selected_drive_file_ids = list(drive_file_ids)
    return PreparedPancakeDriveReply(
        text=split_result.text,
        drive_file_urls=drive_file_urls,
        drive_file_ids=drive_file_ids,
        image_limit=limit,
        requested_color=requested_color,
        requested_color_phrases=list(requested_color_match.phrases),
        requested_color_terms=requested_color_terms,
        color_filter_applied=bool(requested_color_terms),
        color_filter_reason=None if requested_color_terms else ("no_requested_color" if has_drive_link else "no_drive_link"),
        selected_drive_file_ids=selected_drive_file_ids,
        drive_folder_urls=split_result.drive_folder_urls,
        errors=errors,
        skipped_count=split_result.skipped_count,
    )


class PancakeDriveImageService:
    def __init__(
        self,
        *,
        cache_path: Optional[str | Path] = None,
        storage_dir: Optional[str | Path] = None,
        client: Optional[httpx.AsyncClient] = None,
        download_timeout: Optional[float] = None,
        max_bytes: Optional[int] = None,
        storage_max_bytes: Optional[int] = None,
    ) -> None:
        self.cache_path = Path(
            cache_path
            if cache_path is not None
            else getattr(settings, "pancake_image_cache_path", "storage/pancake_image_cache.json")
        )
        self.storage_dir = Path(
            storage_dir
            if storage_dir is not None
            else getattr(settings, "pancake_image_storage_dir", "storage/pancake_images")
        )
        self.client = client
        self.download_timeout = _get_configured_download_timeout(download_timeout)
        self.max_bytes = _get_configured_max_bytes(max_bytes)
        self.storage_max_bytes = _get_configured_storage_max_bytes(storage_max_bytes)

    async def ensure_local_images(
        self,
        drive_file_urls: Iterable[str],
        *,
        image_limit: Optional[int] = None,
        reuse_uploaded_content_id: Optional[bool] = None,
        drive_file_metadata: Optional[dict[str, dict[str, Any]]] = None,
        require_color_metadata: bool = False,
    ) -> PancakeDriveLocalImageBatchResult:
        limit = _get_configured_image_limit(image_limit)
        reuse_content_ids = _get_configured_reuse_uploaded_content_id(reuse_uploaded_content_id)
        metadata_by_id = drive_file_metadata if isinstance(drive_file_metadata, dict) else {}
        images: list[PancakeDriveLocalImageResult] = []
        errors: list[dict[str, Any]] = []
        accepted_ids: set[str] = set()

        for drive_url in [str(url or "").strip() for url in drive_file_urls]:
            if len(accepted_ids) >= limit:
                break

            try:
                drive_file_id = parse_drive_file_id(drive_url)
            except ValueError as exc:
                reason = str(exc) or "invalid_drive_file_url"
                errors.append({"drive_url": drive_url, "reason": reason})
                continue

            if drive_file_id in accepted_ids:
                continue
            accepted_ids.add(drive_file_id)

            result = await self.ensure_local_image(
                drive_url=drive_url,
                drive_file_id=drive_file_id,
                reuse_uploaded_content_id=reuse_content_ids,
                drive_file_metadata=metadata_by_id.get(drive_file_id),
                require_color_metadata=require_color_metadata,
            )
            images.append(result)
            if result.error:
                errors.append(
                    {
                        "drive_url": drive_url,
                        "drive_file_id": drive_file_id,
                        "reason": result.error,
                    }
                )

        return PancakeDriveLocalImageBatchResult(images=images, errors=errors)

    async def ensure_local_image(
        self,
        *,
        drive_url: str,
        drive_file_id: str,
        reuse_uploaded_content_id: Optional[bool] = None,
        drive_file_metadata: Optional[dict[str, Any]] = None,
        require_color_metadata: bool = False,
    ) -> PancakeDriveLocalImageResult:
        direct_download_url = build_drive_file_download_url(drive_file_id)
        local_path = self._local_image_path(drive_file_id)
        cached_entry = self._get_cache_entry(drive_file_id)
        metadata = drive_file_metadata if isinstance(drive_file_metadata, dict) else {}
        metadata_name = _normalize_optional_metadata_text(
            metadata.get("drive_file_name") or metadata.get("name") or cached_entry.get("drive_file_name")
        )
        metadata_color = _normalize_optional_metadata_text(
            metadata.get("drive_file_color") or cached_entry.get("drive_file_color")
        )
        cache_entry_removed = False
        if require_color_metadata and cached_entry and (
            not cached_entry.get("drive_file_name") or not cached_entry.get("drive_file_color")
        ):
            self.remove_cache_entry_for_drive_file_id(drive_file_id)
            self._remove_local_image(local_path)
            cached_entry = {}
            cache_entry_removed = True

        content_id = str(cached_entry.get("content_id") or "").strip() or None
        if _get_configured_reuse_uploaded_content_id(reuse_uploaded_content_id) and content_id:
            if metadata_name or metadata_color:
                self._update_cache_entry(
                    drive_file_id,
                    {
                        "drive_file_id": drive_file_id,
                        "drive_file_name": metadata_name,
                        "drive_file_color": metadata_color,
                    },
                )
            logger.info(
                "PANCAKE_DRIVE_IMAGE_CONTENT_ID_CACHE_HIT drive_file_id=%s local_download_skipped=true",
                drive_file_id,
            )
            return PancakeDriveLocalImageResult(
                drive_file_id=drive_file_id,
                drive_url=drive_url,
                direct_download_url=direct_download_url,
                local_path=self._public_path(local_path),
                cache_hit=True,
                downloaded=False,
                content_id=content_id,
                drive_file_name=metadata_name,
                drive_file_color=metadata_color,
                mime_type=str(cached_entry.get("mime_type") or "").strip() or None,
                size_bytes=(
                    cached_entry.get("size_bytes")
                    if isinstance(cached_entry.get("size_bytes"), int)
                    else None
                ),
                local_present=False,
                cache_entry_removed=cache_entry_removed,
            )

        if self._is_existing_local_image(local_path):
            size_bytes = local_path.stat().st_size
            mime_type = str(cached_entry.get("mime_type") or "").strip() or "image/jpeg"
            optimized = False
            original_size_bytes: Optional[int] = None

            if size_bytes > self.storage_max_bytes:
                original_size_bytes = size_bytes
                try:
                    stored_content = local_path.read_bytes()
                    optimized_content, mime_type, optimized = self._prepare_image_for_storage(
                        stored_content,
                        content_type=mime_type,
                    )
                    self._write_local_image(local_path, optimized_content)
                    size_bytes = len(optimized_content)
                    logger.info(
                        "PANCAKE_DRIVE_IMAGE_LOCAL_OPTIMIZED drive_file_id=%s original_size_bytes=%s size_bytes=%s",
                        drive_file_id,
                        original_size_bytes,
                        size_bytes,
                    )
                except PancakeDriveImageOptimizationError as exc:
                    logger.warning(
                        "PANCAKE_DRIVE_IMAGE_LOCAL_OPTIMIZE_FAILED drive_file_id=%s reason=%s fallback=redownload",
                        drive_file_id,
                        exc.reason,
                    )
                    self._remove_local_image(local_path)
                    return await self._download_local_image(
                        drive_url=drive_url,
                        drive_file_id=drive_file_id,
                        direct_download_url=direct_download_url,
                        local_path=local_path,
                        content_id=content_id,
                        drive_file_name=metadata_name,
                        drive_file_color=metadata_color,
                        cache_entry_removed=cache_entry_removed,
                    )
                except Exception as exc:
                    logger.exception(
                        "PANCAKE_DRIVE_IMAGE_LOCAL_OPTIMIZE_EXCEPTION drive_file_id=%s error=%s",
                        drive_file_id,
                        exc,
                    )
                    self._remove_local_image(local_path)
                    return await self._download_local_image(
                        drive_url=drive_url,
                        drive_file_id=drive_file_id,
                        direct_download_url=direct_download_url,
                        local_path=local_path,
                        content_id=content_id,
                        drive_file_name=metadata_name,
                        drive_file_color=metadata_color,
                        cache_entry_removed=cache_entry_removed,
                    )

            self._update_cache_entry(
                drive_file_id,
                {
                    "drive_file_id": drive_file_id,
                    "drive_url": drive_url,
                    "drive_file_name": metadata_name,
                    "drive_file_color": metadata_color,
                    "direct_download_url": direct_download_url,
                    "local_path": self._public_path(local_path),
                    "content_id": content_id,
                    "mime_type": mime_type,
                    "size_bytes": size_bytes,
                    "local_present": True,
                    "storage_max_bytes": self.storage_max_bytes,
                    "optimized": optimized or None,
                    "optimized_at": _utc_now_iso() if optimized else None,
                    "original_size_bytes": original_size_bytes,
                },
            )
            return PancakeDriveLocalImageResult(
                drive_file_id=drive_file_id,
                drive_url=drive_url,
                direct_download_url=direct_download_url,
                local_path=self._public_path(local_path),
                cache_hit=True,
                downloaded=False,
                content_id=content_id,
                drive_file_name=metadata_name,
                drive_file_color=metadata_color,
                mime_type=mime_type,
                size_bytes=size_bytes,
                local_present=True,
                optimized=optimized,
                original_size_bytes=original_size_bytes,
                cache_entry_removed=cache_entry_removed,
            )

        return await self._download_local_image(
            drive_url=drive_url,
            drive_file_id=drive_file_id,
            direct_download_url=direct_download_url,
            local_path=local_path,
            content_id=content_id,
            drive_file_name=metadata_name,
            drive_file_color=metadata_color,
            cache_entry_removed=cache_entry_removed,
        )

    def _local_image_path(self, drive_file_id: str) -> Path:
        return self.storage_dir / f"{drive_file_id}.jpg"

    def _public_path(self, path: Path) -> str:
        return path.as_posix()

    def _empty_cache(self) -> dict[str, Any]:
        return {"version": PANCAKE_DRIVE_IMAGE_CACHE_VERSION, "items": {}}

    def _load_cache_unlocked(self) -> dict[str, Any]:
        if not self.cache_path.exists():
            return self._empty_cache()
        try:
            with self.cache_path.open("r", encoding="utf-8") as file_obj:
                cache = json.load(file_obj)
        except Exception as exc:
            logger.warning(
                "PANCAKE_DRIVE_IMAGE_CACHE_READ_FAILED cache_path=%s reason=%s",
                self.cache_path,
                exc,
            )
            return self._empty_cache()

        if not isinstance(cache, dict) or not isinstance(cache.get("items"), dict):
            logger.warning("PANCAKE_DRIVE_IMAGE_CACHE_INVALID cache_path=%s", self.cache_path)
            return self._empty_cache()
        cache.setdefault("version", PANCAKE_DRIVE_IMAGE_CACHE_VERSION)
        return cache

    def _get_cache_entry(self, drive_file_id: str) -> dict[str, Any]:
        with _cache_write_lock:
            cache = self._load_cache_unlocked()
        entry = cache.get("items", {}).get(drive_file_id)
        return entry if isinstance(entry, dict) else {}

    def record_uploaded_content_id(self, *, drive_file_id: str, content_id: str) -> None:
        normalized_drive_file_id = str(drive_file_id or "").strip()
        normalized_content_id = str(content_id or "").strip()
        if not normalized_drive_file_id or not normalized_content_id:
            return
        self._update_cache_entry(
            normalized_drive_file_id,
            {
                "drive_file_id": normalized_drive_file_id,
                "content_id": normalized_content_id,
                "uploaded_at": _utc_now_iso(),
            },
        )

    def remove_local_image_for_drive_file_id(self, drive_file_id: str) -> bool:
        normalized_drive_file_id = str(drive_file_id or "").strip()
        if not normalized_drive_file_id:
            return False

        local_path = self._local_image_path(normalized_drive_file_id)
        removed = self._remove_local_image(local_path)
        if removed or not self._is_existing_local_image(local_path):
            self._update_cache_entry(
                normalized_drive_file_id,
                {
                    "drive_file_id": normalized_drive_file_id,
                    "local_present": False,
                    "local_removed_at": _utc_now_iso() if removed else None,
                },
            )
        return removed

    def remove_cache_entry_for_drive_file_id(self, drive_file_id: str) -> bool:
        normalized_drive_file_id = str(drive_file_id or "").strip()
        if not normalized_drive_file_id:
            return False

        with _cache_write_lock:
            cache = self._load_cache_unlocked()
            items = cache.setdefault("items", {})
            if normalized_drive_file_id not in items:
                return False
            items.pop(normalized_drive_file_id, None)
            self._write_cache_unlocked(cache)

        logger.info("PANCAKE_DRIVE_IMAGE_CACHE_ENTRY_REMOVED drive_file_id=%s", normalized_drive_file_id)
        return True

    def _update_cache_entry(self, drive_file_id: str, updates: dict[str, Any]) -> None:
        clean_updates = {key: value for key, value in updates.items() if value is not None}
        with _cache_write_lock:
            cache = self._load_cache_unlocked()
            items = cache.setdefault("items", {})
            current_entry = items.get(drive_file_id)
            if not isinstance(current_entry, dict):
                current_entry = {}
            current_entry.update(clean_updates)
            items[drive_file_id] = current_entry
            self._write_cache_unlocked(cache)

    def _write_cache_unlocked(self, cache: dict[str, Any]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.cache_path.with_suffix(f"{self.cache_path.suffix}.tmp")
        with temp_path.open("w", encoding="utf-8") as file_obj:
            json.dump(cache, file_obj, ensure_ascii=False, indent=2, sort_keys=True)
            file_obj.write("\n")
        os.replace(temp_path, self.cache_path)

    def _is_existing_local_image(self, local_path: Path) -> bool:
        try:
            return local_path.is_file() and local_path.stat().st_size > 0
        except OSError:
            return False

    def _remove_local_image(self, local_path: Path) -> bool:
        try:
            if local_path.is_file():
                local_path.unlink()
                return True
        except OSError as exc:
            logger.warning(
                "PANCAKE_DRIVE_IMAGE_LOCAL_REMOVE_FAILED local_path=%s reason=%s",
                self._public_path(local_path),
                exc,
            )
        return False

    async def _download_local_image(
        self,
        *,
        drive_url: str,
        drive_file_id: str,
        direct_download_url: str,
        local_path: Path,
        content_id: Optional[str],
        drive_file_name: Optional[str] = None,
        drive_file_color: Optional[str] = None,
        cache_entry_removed: bool = False,
    ) -> PancakeDriveLocalImageResult:
        try:
            response = await self._get_download_response(direct_download_url)
        except httpx.TimeoutException:
            return self._failed_image_result(
                drive_url=drive_url,
                drive_file_id=drive_file_id,
                direct_download_url=direct_download_url,
                local_path=local_path,
                content_id=content_id,
                drive_file_name=drive_file_name,
                drive_file_color=drive_file_color,
                cache_entry_removed=cache_entry_removed,
                error="drive_download_timeout",
            )
        except httpx.RequestError:
            return self._failed_image_result(
                drive_url=drive_url,
                drive_file_id=drive_file_id,
                direct_download_url=direct_download_url,
                local_path=local_path,
                content_id=content_id,
                drive_file_name=drive_file_name,
                drive_file_color=drive_file_color,
                cache_entry_removed=cache_entry_removed,
                error="drive_download_request_failed",
            )
        except Exception as exc:
            logger.exception(
                "PANCAKE_DRIVE_IMAGE_DOWNLOAD_EXCEPTION drive_file_id=%s error=%s",
                drive_file_id,
                exc,
            )
            return self._failed_image_result(
                drive_url=drive_url,
                drive_file_id=drive_file_id,
                direct_download_url=direct_download_url,
                local_path=local_path,
                content_id=content_id,
                drive_file_name=drive_file_name,
                drive_file_color=drive_file_color,
                cache_entry_removed=cache_entry_removed,
                error="drive_download_failed",
            )

        status_code = int(getattr(response, "status_code", 0) or 0)
        if status_code >= 400:
            return self._failed_image_result(
                drive_url=drive_url,
                drive_file_id=drive_file_id,
                direct_download_url=direct_download_url,
                local_path=local_path,
                content_id=content_id,
                drive_file_name=drive_file_name,
                drive_file_color=drive_file_color,
                cache_entry_removed=cache_entry_removed,
                error=f"drive_download_http_{status_code}",
            )

        headers = getattr(response, "headers", {}) or {}
        content_type = str(headers.get("content-type") or headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if content_type not in PANCAKE_DRIVE_IMAGE_MIME_TYPES:
            return self._failed_image_result(
                drive_url=drive_url,
                drive_file_id=drive_file_id,
                direct_download_url=direct_download_url,
                local_path=local_path,
                content_id=content_id,
                drive_file_name=drive_file_name,
                drive_file_color=drive_file_color,
                cache_entry_removed=cache_entry_removed,
                error="drive_download_invalid_content_type",
            )

        content = bytes(getattr(response, "content", b"") or b"")
        if not content:
            return self._failed_image_result(
                drive_url=drive_url,
                drive_file_id=drive_file_id,
                direct_download_url=direct_download_url,
                local_path=local_path,
                content_id=content_id,
                drive_file_name=drive_file_name,
                drive_file_color=drive_file_color,
                cache_entry_removed=cache_entry_removed,
                error="drive_download_empty",
            )
        if len(content) > self.max_bytes:
            return self._failed_image_result(
                drive_url=drive_url,
                drive_file_id=drive_file_id,
                direct_download_url=direct_download_url,
                local_path=local_path,
                content_id=content_id,
                drive_file_name=drive_file_name,
                drive_file_color=drive_file_color,
                cache_entry_removed=cache_entry_removed,
                error="drive_download_too_large",
            )

        original_size_bytes = len(content)
        try:
            stored_content, stored_mime_type, optimized = self._prepare_image_for_storage(
                content,
                content_type=content_type,
            )
        except PancakeDriveImageOptimizationError as exc:
            return self._failed_image_result(
                drive_url=drive_url,
                drive_file_id=drive_file_id,
                direct_download_url=direct_download_url,
                local_path=local_path,
                content_id=content_id,
                drive_file_name=drive_file_name,
                drive_file_color=drive_file_color,
                cache_entry_removed=cache_entry_removed,
                error=exc.reason,
            )
        except Exception as exc:
            logger.exception(
                "PANCAKE_DRIVE_IMAGE_OPTIMIZE_EXCEPTION drive_file_id=%s error=%s",
                drive_file_id,
                exc,
            )
            return self._failed_image_result(
                drive_url=drive_url,
                drive_file_id=drive_file_id,
                direct_download_url=direct_download_url,
                local_path=local_path,
                content_id=content_id,
                drive_file_name=drive_file_name,
                drive_file_color=drive_file_color,
                cache_entry_removed=cache_entry_removed,
                error="pancake_image_optimize_failed",
            )

        self._write_local_image(local_path, stored_content)
        self._update_cache_entry(
            drive_file_id,
            {
                "drive_file_id": drive_file_id,
                "drive_url": drive_url,
                "drive_file_name": drive_file_name,
                "drive_file_color": drive_file_color,
                "direct_download_url": direct_download_url,
                "local_path": self._public_path(local_path),
                "content_id": content_id,
                "downloaded_at": _utc_now_iso(),
                "mime_type": stored_mime_type,
                "size_bytes": len(stored_content),
                "local_present": True,
                "storage_max_bytes": self.storage_max_bytes,
                "optimized": optimized or None,
                "original_size_bytes": original_size_bytes if optimized else None,
            },
        )
        logger.info(
            "PANCAKE_DRIVE_IMAGE_DOWNLOADED drive_file_id=%s original_size_bytes=%s size_bytes=%s mime_type=%s optimized=%s",
            drive_file_id,
            original_size_bytes,
            len(stored_content),
            stored_mime_type,
            optimized,
        )
        return PancakeDriveLocalImageResult(
            drive_file_id=drive_file_id,
            drive_url=drive_url,
            direct_download_url=direct_download_url,
            local_path=self._public_path(local_path),
            cache_hit=False,
            downloaded=True,
            content_id=content_id,
            drive_file_name=drive_file_name,
            drive_file_color=drive_file_color,
            mime_type=stored_mime_type,
            size_bytes=len(stored_content),
            local_present=True,
            optimized=optimized,
            original_size_bytes=original_size_bytes if optimized else None,
            cache_entry_removed=cache_entry_removed,
        )

    def _prepare_image_for_storage(self, content: bytes, *, content_type: Optional[str]) -> tuple[bytes, str, bool]:
        normalized_content_type = str(content_type or "").split(";")[0].strip().lower()
        if normalized_content_type == "image/jpeg" and len(content) <= self.storage_max_bytes:
            return content, "image/jpeg", False

        optimized_content = self._optimize_image_for_storage(content)
        if len(optimized_content) > self.storage_max_bytes:
            raise PancakeDriveImageOptimizationError("pancake_image_optimize_too_large")
        return optimized_content, "image/jpeg", True

    def _optimize_image_for_storage(self, content: bytes) -> bytes:
        try:
            with Image.open(BytesIO(content)) as image:
                image.load()
                source_image = self._normalize_pillow_image(image)
        except UnidentifiedImageError as exc:
            raise PancakeDriveImageOptimizationError("pancake_image_optimize_invalid_image") from exc
        except OSError as exc:
            raise PancakeDriveImageOptimizationError("pancake_image_optimize_invalid_image") from exc

        base_width, base_height = source_image.size
        if base_width <= 0 or base_height <= 0:
            raise PancakeDriveImageOptimizationError("pancake_image_optimize_invalid_image")

        initial_scale = min(1.0, PANCAKE_DRIVE_MAX_OPTIMIZE_DIMENSION / max(base_width, base_height))
        candidate_sizes: list[tuple[int, int]] = []
        for scale in PANCAKE_DRIVE_IMAGE_SCALE_STEPS:
            width = max(1, int(base_width * initial_scale * scale))
            height = max(1, int(base_height * initial_scale * scale))
            candidate_size = (width, height)
            if candidate_size not in candidate_sizes:
                candidate_sizes.append(candidate_size)

        smallest_candidate: Optional[bytes] = None
        resampling_filter = getattr(Image.Resampling, "LANCZOS", Image.Resampling.BICUBIC)
        for candidate_size in candidate_sizes:
            if candidate_size == source_image.size:
                candidate_image = source_image
            else:
                candidate_image = source_image.resize(candidate_size, resampling_filter)

            for quality in PANCAKE_DRIVE_JPEG_QUALITY_STEPS:
                buffer = BytesIO()
                candidate_image.save(
                    buffer,
                    format="JPEG",
                    quality=quality,
                    optimize=True,
                    progressive=True,
                )
                candidate_content = buffer.getvalue()
                if len(candidate_content) <= self.storage_max_bytes:
                    return candidate_content
                if smallest_candidate is None or len(candidate_content) < len(smallest_candidate):
                    smallest_candidate = candidate_content

        logger.warning(
            "PANCAKE_DRIVE_IMAGE_OPTIMIZE_TOO_LARGE storage_max_bytes=%s smallest_size_bytes=%s",
            self.storage_max_bytes,
            len(smallest_candidate or b""),
        )
        raise PancakeDriveImageOptimizationError("pancake_image_optimize_too_large")

    def _normalize_pillow_image(self, image: Image.Image) -> Image.Image:
        transposed = ImageOps.exif_transpose(image)
        if transposed.mode in {"RGBA", "LA"} or (transposed.mode == "P" and "transparency" in transposed.info):
            rgba_image = transposed.convert("RGBA")
            background = Image.new("RGB", rgba_image.size, (255, 255, 255))
            background.paste(rgba_image, mask=rgba_image.getchannel("A"))
            return background
        if transposed.mode != "RGB":
            return transposed.convert("RGB")
        return transposed.copy()

    async def _get_download_response(self, url: str) -> Any:
        if self.client is not None:
            return await self.client.get(url, follow_redirects=True)
        async with httpx.AsyncClient(timeout=self.download_timeout, follow_redirects=True) as client:
            return await client.get(url)

    def _write_local_image(self, local_path: Path, content: bytes) -> None:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = local_path.with_suffix(f"{local_path.suffix}.tmp")
        with temp_path.open("wb") as file_obj:
            file_obj.write(content)
        os.replace(temp_path, local_path)

    def _failed_image_result(
        self,
        *,
        drive_url: str,
        drive_file_id: str,
        direct_download_url: str,
        local_path: Path,
        content_id: Optional[str],
        error: str,
        drive_file_name: Optional[str] = None,
        drive_file_color: Optional[str] = None,
        cache_entry_removed: bool = False,
    ) -> PancakeDriveLocalImageResult:
        logger.warning(
            "PANCAKE_DRIVE_IMAGE_LOCAL_FAILED drive_file_id=%s reason=%s",
            drive_file_id,
            error,
        )
        return PancakeDriveLocalImageResult(
            drive_file_id=drive_file_id,
            drive_url=drive_url,
            direct_download_url=direct_download_url,
            local_path=self._public_path(local_path),
            cache_hit=False,
            downloaded=False,
            content_id=content_id,
            drive_file_name=drive_file_name,
            drive_file_color=drive_file_color,
            cache_entry_removed=cache_entry_removed,
            error=error,
        )
