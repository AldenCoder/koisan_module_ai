"""Google Drive folder image lookup helpers."""
from __future__ import annotations

import logging
import random
import re
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Optional
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.services.pancake_drive_image_color_service import (
    name_matches_color_terms,
    normalize_color_terms,
    parse_drive_file_color_from_name,
    parse_drive_folder_color_from_name,
)
from logs.logging_config import logger


GOOGLE_DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
GOOGLE_DRIVE_FIELDS = "nextPageToken,files(id,name,mimeType,size)"
GOOGLE_DRIVE_IMAGE_BASE_URL = "https://lh3.googleusercontent.com/d"
GOOGLE_DRIVE_IMAGE_MIME_TYPES = {"image/jpeg", "image/png"}
GOOGLE_DRIVE_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
GOOGLE_DRIVE_PAGE_SIZE = 1000
GOOGLE_DRIVE_FOLDER_HOSTS = {"drive.google.com"}
GOOGLE_DRIVE_FOLDER_LOOKUP_MAX_DEPTH_LIMIT = 3
GOOGLE_DRIVE_FOLDER_BLOCKED_NAME_KEYWORDS = ("Video",)
PANCAKE_DRIVE_IMAGE_SELECTION_STRATEGY_COLOR_DIVERSE = "color_diverse"
PANCAKE_DRIVE_IMAGE_SELECTION_STRATEGY_SINGLE_BRANCH_RANDOM = "single_branch_random"
PANCAKE_DRIVE_COLOR_FOLDER_MAX_COUNT_DEFAULT = 5
_DRIVE_URL_PATTERN = re.compile(r"https?://[^\s<>\]\[\"']+", re.IGNORECASE)
_DRIVE_FOLDER_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


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


@dataclass(frozen=True)
class DriveImageResult:
    id: str
    imageUrl: str
    name: Optional[str] = None
    mimeType: Optional[str] = None
    size: Optional[str] = None
    drive_file_color: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "imageUrl": self.imageUrl,
            "id": self.id,
        }
        if self.name is not None:
            data["name"] = self.name
        if self.mimeType is not None:
            data["mimeType"] = self.mimeType
        if self.size is not None:
            data["size"] = self.size
        if self.drive_file_color is not None:
            data["drive_file_color"] = self.drive_file_color
        return data


@dataclass(frozen=True)
class DriveFolderImageResult:
    folder_url: str
    folder_id: Optional[str]
    images: list[DriveImageResult]
    error: Optional[str] = None
    lookup_depth: Optional[int] = None
    visited_folder_ids: list[str] = field(default_factory=list)
    selected_child_folder_ids: list[str] = field(default_factory=list)
    page_truncated: bool = False
    requested_color: Optional[str] = None
    requested_color_terms: list[str] = field(default_factory=list)
    selected_group: Optional[str] = None
    root_selected_group: Optional[str] = None
    color_fallback_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "folder_url": self.folder_url,
            "folder_id": self.folder_id,
            "images": [image.to_dict() for image in self.images],
        }
        if self.error:
            data["error"] = self.error
        if self.lookup_depth is not None:
            data["lookup_depth"] = self.lookup_depth
        if self.visited_folder_ids:
            data["visited_folder_ids"] = list(self.visited_folder_ids)
        if self.selected_child_folder_ids:
            data["selected_child_folder_ids"] = list(self.selected_child_folder_ids)
        if self.page_truncated:
            data["page_truncated"] = True
        if self.requested_color:
            data["requested_color"] = self.requested_color
        if self.requested_color_terms:
            data["requested_color_terms"] = list(self.requested_color_terms)
        if self.selected_group:
            data["selected_group"] = self.selected_group
        if self.root_selected_group:
            data["root_selected_group"] = self.root_selected_group
        if self.color_fallback_used:
            data["color_fallback_used"] = True
        return data


class GoogleDriveImageLookupError(RuntimeError):
    """Raised when Google Drive lookup fails for a single folder."""


@dataclass(frozen=True)
class DriveFolderChildResult:
    id: str
    name: Optional[str] = None
    drive_folder_color: Optional[str] = None


@dataclass(frozen=True)
class DriveFolderChildrenPageResult:
    images: list[DriveImageResult]
    child_folders: list[DriveFolderChildResult]
    page_truncated: bool = False


@dataclass(frozen=True)
class DriveFolderUrlSplitResult:
    text: str
    drive_folder_urls: list[str]
    skipped_count: int = 0


def parse_drive_folder_id(folder_url: str) -> str:
    """Extract a Google Drive folder id from a standard folder URL."""
    normalized_url = str(folder_url or "").strip()
    if not normalized_url:
        raise ValueError("drive_folder_url_empty")

    parsed = urlparse(normalized_url)
    if parsed.scheme.lower() != "https":
        raise ValueError("drive_folder_url_invalid_scheme")
    if parsed.netloc.lower() not in GOOGLE_DRIVE_FOLDER_HOSTS:
        raise ValueError("drive_folder_url_invalid_host")

    path_parts = [part for part in parsed.path.split("/") if part]

    folder_id: Optional[str] = None
    for index, part in enumerate(path_parts):
        if part == "folders" and index + 1 < len(path_parts):
            folder_id = path_parts[index + 1].strip()
            break

    if not folder_id:
        raise ValueError("drive_folder_id_not_found")

    if not _DRIVE_FOLDER_ID_PATTERN.fullmatch(folder_id):
        raise ValueError("drive_folder_id_invalid")

    return folder_id


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


def _normalize_folder_name(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _folder_name_has_blocked_keyword(folder_name: Any) -> bool:
    normalized_name = _normalize_folder_name(folder_name)
    if not normalized_name:
        return False

    return any(
        _normalize_folder_name(keyword) in normalized_name
        for keyword in GOOGLE_DRIVE_FOLDER_BLOCKED_NAME_KEYWORDS
        if str(keyword).strip()
    )


def split_text_and_drive_folder_urls(message_text: str) -> DriveFolderUrlSplitResult:
    """Remove Drive folder URLs from text and return them separately."""
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
            candidate_url = _trim_drive_folder_url(match.group(0))
            try:
                parse_drive_folder_id(candidate_url)
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

    return DriveFolderUrlSplitResult(
        text=_normalize_text_preserving_paragraphs("\n".join(cleaned_lines)),
        drive_folder_urls=accepted_urls,
        skipped_count=skipped_count,
    )


def extract_drive_folder_urls_from_text(message_text: str) -> list[str]:
    return split_text_and_drive_folder_urls(message_text).drive_folder_urls


def build_drive_image_url(file_id: str) -> str:
    normalized_file_id = str(file_id or "").strip()
    if not normalized_file_id:
        raise ValueError("drive_file_id_empty")
    return f"{GOOGLE_DRIVE_IMAGE_BASE_URL}/{normalized_file_id}"


def build_drive_files_query(folder_id: str) -> str:
    normalized_folder_id = str(folder_id or "").strip()
    if not normalized_folder_id:
        raise ValueError("drive_folder_id_empty")
    return (
        f"'{normalized_folder_id}' in parents and trashed=false "
        "and (mimeType='image/jpeg' or mimeType='image/png')"
    )


def build_drive_folder_children_query(folder_id: str) -> str:
    normalized_folder_id = str(folder_id or "").strip()
    if not normalized_folder_id:
        raise ValueError("drive_folder_id_empty")
    return (
        f"'{normalized_folder_id}' in parents and trashed=false "
        "and (mimeType='image/jpeg' or mimeType='image/png' "
        f"or mimeType='{GOOGLE_DRIVE_FOLDER_MIME_TYPE}')"
    )


def _preview_error(value: Any, *, limit: int = 300) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...(truncated)"


def _image_from_drive_file(file_data: dict[str, Any]) -> Optional[DriveImageResult]:
    file_id = str(file_data.get("id") or "").strip()
    mime_type = str(file_data.get("mimeType") or "").strip()
    if not file_id or mime_type not in GOOGLE_DRIVE_IMAGE_MIME_TYPES:
        return None

    return DriveImageResult(
        id=file_id,
        imageUrl=build_drive_image_url(file_id),
        name=str(file_data.get("name")) if file_data.get("name") is not None else None,
        mimeType=mime_type,
        size=str(file_data.get("size")) if file_data.get("size") is not None else None,
        drive_file_color=parse_drive_file_color_from_name(file_data.get("name")),
    )


def _child_folder_from_drive_file(file_data: dict[str, Any]) -> Optional[DriveFolderChildResult]:
    folder_id = str(file_data.get("id") or "").strip()
    mime_type = str(file_data.get("mimeType") or "").strip()
    if not folder_id or mime_type != GOOGLE_DRIVE_FOLDER_MIME_TYPE:
        return None
    return DriveFolderChildResult(
        id=folder_id,
        name=str(file_data.get("name")) if file_data.get("name") is not None else None,
        drive_folder_color=parse_drive_folder_color_from_name(file_data.get("name")),
    )


def _normalize_folder_lookup_max_depth(max_depth: Optional[int]) -> int:
    try:
        value = int(max_depth if max_depth is not None else GOOGLE_DRIVE_FOLDER_LOOKUP_MAX_DEPTH_LIMIT)
    except (TypeError, ValueError):
        value = GOOGLE_DRIVE_FOLDER_LOOKUP_MAX_DEPTH_LIMIT
    return max(1, min(value, GOOGLE_DRIVE_FOLDER_LOOKUP_MAX_DEPTH_LIMIT))


def _is_color_diverse_drive_selection_enabled() -> bool:
    strategy = str(
        getattr(
            settings,
            "pancake_drive_image_selection_strategy",
            PANCAKE_DRIVE_IMAGE_SELECTION_STRATEGY_COLOR_DIVERSE,
        )
        or ""
    ).strip().lower()
    if not strategy:
        strategy = PANCAKE_DRIVE_IMAGE_SELECTION_STRATEGY_COLOR_DIVERSE
    return strategy != PANCAKE_DRIVE_IMAGE_SELECTION_STRATEGY_SINGLE_BRANCH_RANDOM


def _get_pancake_drive_color_folder_max_count() -> int:
    raw_value = getattr(
        settings,
        "pancake_drive_color_folder_max_count",
        PANCAKE_DRIVE_COLOR_FOLDER_MAX_COUNT_DEFAULT,
    )
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = PANCAKE_DRIVE_COLOR_FOLDER_MAX_COUNT_DEFAULT
    return max(1, value)


def _image_effective_color(image: DriveImageResult, inherited_color: Optional[str]) -> Optional[str]:
    return image.drive_file_color or inherited_color


def _child_folder_effective_color(
    child_folder: DriveFolderChildResult,
    inherited_color: Optional[str],
) -> Optional[str]:
    return child_folder.drive_folder_color or inherited_color


def _color_value_matches_request(
    color_value: Optional[str],
    *,
    requested_color: Optional[str],
    requested_color_terms: Iterable[str] | None,
) -> bool:
    normalized_color_value = str(color_value or "").strip()
    if not normalized_color_value:
        return False
    if requested_color and normalized_color_value == requested_color:
        return True
    return name_matches_color_terms(normalized_color_value, requested_color_terms)


def _with_inherited_image_color(
    image: DriveImageResult,
    inherited_color: Optional[str],
) -> DriveImageResult:
    if image.drive_file_color or not inherited_color:
        return image
    return replace(image, drive_file_color=inherited_color)


def _images_with_inherited_color(
    images: list[DriveImageResult],
    inherited_color: Optional[str],
) -> list[DriveImageResult]:
    return [_with_inherited_image_color(image, inherited_color) for image in images]


def _with_requested_image_color(
    image: DriveImageResult,
    *,
    inherited_color: Optional[str],
    requested_color: Optional[str],
    requested_color_terms: Iterable[str] | None,
) -> DriveImageResult:
    if image.drive_file_color:
        return image
    if inherited_color:
        return replace(image, drive_file_color=inherited_color)
    if requested_color and name_matches_color_terms(image.name, requested_color_terms):
        return replace(image, drive_file_color=requested_color)
    return image


def _image_matches_requested_color(
    image: DriveImageResult,
    *,
    requested_color: Optional[str],
    requested_color_terms: Iterable[str] | None,
    inherited_color: Optional[str],
) -> bool:
    effective_color = _image_effective_color(image, inherited_color)
    if _color_value_matches_request(
        effective_color,
        requested_color=requested_color,
        requested_color_terms=requested_color_terms,
    ):
        return True
    return name_matches_color_terms(image.name, requested_color_terms)


def _child_folder_matches_requested_color(
    child_folder: DriveFolderChildResult,
    *,
    requested_color: Optional[str],
    requested_color_terms: Iterable[str] | None,
    inherited_color: Optional[str],
) -> bool:
    effective_color = _child_folder_effective_color(child_folder, inherited_color)
    if _color_value_matches_request(
        effective_color,
        requested_color=requested_color,
        requested_color_terms=requested_color_terms,
    ):
        return True
    return name_matches_color_terms(child_folder.name, requested_color_terms)


def _selected_child_folder_color(
    child_folder: DriveFolderChildResult,
    *,
    requested_color: Optional[str],
    requested_color_terms: Iterable[str] | None,
    inherited_color: Optional[str],
) -> Optional[str]:
    effective_color = _child_folder_effective_color(child_folder, inherited_color)
    if effective_color:
        return effective_color
    if requested_color and name_matches_color_terms(child_folder.name, requested_color_terms):
        return requested_color
    return None


def _images_matching_color(
    images: list[DriveImageResult],
    *,
    requested_color: Optional[str],
    requested_color_terms: Iterable[str] | None,
    inherited_color: Optional[str],
) -> list[DriveImageResult]:
    return [
        _with_requested_image_color(
            image,
            inherited_color=inherited_color,
            requested_color=requested_color,
            requested_color_terms=requested_color_terms,
        )
        for image in images
        if _image_matches_requested_color(
            image,
            requested_color=requested_color,
            requested_color_terms=requested_color_terms,
            inherited_color=inherited_color,
        )
    ]


def _child_folders_matching_color(
    child_folders: list[DriveFolderChildResult],
    *,
    requested_color: Optional[str],
    requested_color_terms: Iterable[str] | None,
    inherited_color: Optional[str],
) -> list[DriveFolderChildResult]:
    return [
        child_folder
        for child_folder in child_folders
        if _child_folder_matches_requested_color(
            child_folder,
            requested_color=requested_color,
            requested_color_terms=requested_color_terms,
            inherited_color=inherited_color,
        )
    ]


def _child_folders_without_blocked_keywords(
    child_folders: list[DriveFolderChildResult],
) -> list[DriveFolderChildResult]:
    return [
        child_folder
        for child_folder in child_folders
        if not _folder_name_has_blocked_keyword(child_folder.name)
    ]


def _child_folders_with_detected_color(
    child_folders: list[DriveFolderChildResult],
    inherited_color: Optional[str],
) -> list[DriveFolderChildResult]:
    return [
        child_folder
        for child_folder in child_folders
        if _child_folder_effective_color(child_folder, inherited_color)
    ]


def _append_unique_images(
    target: list[DriveImageResult],
    images: list[DriveImageResult],
) -> None:
    existing_ids = {image.id for image in target}
    for image in images:
        if image.id in existing_ids:
            continue
        target.append(image)
        existing_ids.add(image.id)


class GoogleDriveImageService:
    """Fetch image metadata from public Google Drive folders."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
        timeout: float = 10.0,
    ) -> None:
        configured_key = api_key if api_key is not None else getattr(settings, "google_drive_api_key", None)
        self.api_key = str(configured_key or "").strip()
        self.client = client
        self.timeout = timeout

    async def lookup_folder_images(self, drive_folder_urls: Iterable[str]) -> list[DriveFolderImageResult]:
        urls = [str(url or "").strip() for url in drive_folder_urls]
        if self.client is not None:
            return [await self.lookup_single_folder(url, self.client) for url in urls]

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            return [await self.lookup_single_folder(url, client) for url in urls]

    async def lookup_folder_images_nested(
        self,
        drive_folder_urls: Iterable[str],
        *,
        max_depth: Optional[int] = None,
        requested_color: Optional[str] = None,
        requested_color_terms: Iterable[str] | None = None,
    ) -> list[DriveFolderImageResult]:
        urls = [str(url or "").strip() for url in drive_folder_urls]
        normalized_max_depth = _normalize_folder_lookup_max_depth(max_depth)
        normalized_requested_color = str(requested_color or "").strip() or None
        normalized_requested_color_terms = normalize_color_terms(requested_color_terms)
        if self.client is not None:
            return [
                await self.lookup_single_folder_nested(
                    url,
                    self.client,
                    max_depth=normalized_max_depth,
                    requested_color=normalized_requested_color,
                    requested_color_terms=normalized_requested_color_terms,
                )
                for url in urls
            ]

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            return [
                await self.lookup_single_folder_nested(
                    url,
                    client,
                    max_depth=normalized_max_depth,
                    requested_color=normalized_requested_color,
                    requested_color_terms=normalized_requested_color_terms,
                )
                for url in urls
            ]

    async def lookup_single_folder(
        self,
        folder_url: str,
        client: httpx.AsyncClient,
    ) -> DriveFolderImageResult:
        try:
            folder_id = parse_drive_folder_id(folder_url)
        except ValueError as exc:
            reason = str(exc) or "invalid_drive_folder_url"
            logger.warning("GOOGLE_DRIVE_FOLDER_URL_INVALID reason=%s", reason)
            return DriveFolderImageResult(
                folder_url=folder_url,
                folder_id=None,
                images=[],
                error=reason,
            )

        if not self.api_key:
            logger.error("GOOGLE_DRIVE_LOOKUP_SKIPPED missing_google_drive_api_key folder_id=%s", folder_id)
            return DriveFolderImageResult(
                folder_url=folder_url,
                folder_id=folder_id,
                images=[],
                error="missing_google_drive_api_key",
            )

        try:
            files = await self._fetch_files_for_folder(client=client, folder_id=folder_id)
            images = [
                image
                for image in (_image_from_drive_file(file_data) for file_data in files)
                if image is not None
            ]
            return DriveFolderImageResult(
                folder_url=folder_url,
                folder_id=folder_id,
                images=images,
            )
        except GoogleDriveImageLookupError as exc:
            logger.warning(
                "GOOGLE_DRIVE_LOOKUP_FOLDER_FAILED folder_id=%s reason=%s",
                folder_id,
                _preview_error(exc),
            )
            return DriveFolderImageResult(
                folder_url=folder_url,
                folder_id=folder_id,
                images=[],
                error=str(exc) or "drive_lookup_failed",
            )
        except Exception as exc:
            logger.exception(
                "GOOGLE_DRIVE_LOOKUP_FOLDER_EXCEPTION folder_id=%s error=%s",
                folder_id,
                exc,
            )
            return DriveFolderImageResult(
                folder_url=folder_url,
                folder_id=folder_id,
                images=[],
                error="drive_lookup_failed",
            )

    async def lookup_single_folder_nested(
        self,
        folder_url: str,
        client: httpx.AsyncClient,
        *,
        max_depth: Optional[int] = None,
        requested_color: Optional[str] = None,
        requested_color_terms: Iterable[str] | None = None,
    ) -> DriveFolderImageResult:
        try:
            folder_id = parse_drive_folder_id(folder_url)
        except ValueError as exc:
            reason = str(exc) or "invalid_drive_folder_url"
            logger.warning("GOOGLE_DRIVE_FOLDER_URL_INVALID reason=%s", reason)
            return DriveFolderImageResult(
                folder_url=folder_url,
                folder_id=None,
                images=[],
                error=reason,
            )

        if not self.api_key:
            logger.error("GOOGLE_DRIVE_LOOKUP_SKIPPED missing_google_drive_api_key folder_id=%s", folder_id)
            return DriveFolderImageResult(
                folder_url=folder_url,
                folder_id=folder_id,
                images=[],
                error="missing_google_drive_api_key",
            )

        try:
            return await self._lookup_nested_folder_images(
                client=client,
                folder_url=folder_url,
                root_folder_id=folder_id,
                max_depth=_normalize_folder_lookup_max_depth(max_depth),
                requested_color=str(requested_color or "").strip() or None,
                requested_color_terms=normalize_color_terms(requested_color_terms),
            )
        except GoogleDriveImageLookupError as exc:
            logger.warning(
                "GOOGLE_DRIVE_LOOKUP_FOLDER_FAILED folder_id=%s reason=%s",
                folder_id,
                _preview_error(exc),
            )
            return DriveFolderImageResult(
                folder_url=folder_url,
                folder_id=folder_id,
                images=[],
                error=str(exc) or "drive_lookup_failed",
            )
        except Exception as exc:
            logger.exception(
                "GOOGLE_DRIVE_LOOKUP_FOLDER_EXCEPTION folder_id=%s error=%s",
                folder_id,
                exc,
            )
            return DriveFolderImageResult(
                folder_url=folder_url,
                folder_id=folder_id,
                images=[],
                error="drive_lookup_failed",
            )

    async def _lookup_nested_folder_images(
        self,
        *,
        client: httpx.AsyncClient,
        folder_url: str,
        root_folder_id: str,
        max_depth: int,
        requested_color: Optional[str] = None,
        requested_color_terms: Iterable[str] | None = None,
    ) -> DriveFolderImageResult:
        current_folder_id = root_folder_id
        current_folder_color: Optional[str] = None
        visited_folder_ids: list[str] = []
        selected_child_folder_ids: list[str] = []
        fallback_images: list[DriveImageResult] = []
        page_truncated = False
        root_selected_group: Optional[str] = None
        normalized_requested_color_terms = normalize_color_terms(requested_color_terms)
        color_filter_active = bool(requested_color or normalized_requested_color_terms)

        def result(
            *,
            images: list[DriveImageResult],
            depth: int,
            error: Optional[str] = None,
            selected_group: Optional[str] = None,
            color_fallback_used: bool = False,
        ) -> DriveFolderImageResult:
            return DriveFolderImageResult(
                folder_url=folder_url,
                folder_id=root_folder_id,
                images=images,
                error=error,
                lookup_depth=depth,
                visited_folder_ids=visited_folder_ids,
                selected_child_folder_ids=selected_child_folder_ids,
                page_truncated=page_truncated,
                requested_color=requested_color,
                requested_color_terms=normalized_requested_color_terms,
                selected_group=selected_group,
                root_selected_group=root_selected_group,
                color_fallback_used=color_fallback_used,
            )

        for depth in range(1, max_depth + 1):
            visited_folder_ids.append(current_folder_id)
            page = await self._fetch_first_children_page_for_folder(
                client=client,
                folder_id=current_folder_id,
            )
            page_truncated = page_truncated or page.page_truncated
            visible_child_folders = _child_folders_without_blocked_keywords(page.child_folders)
            images_with_folder_color = _images_with_inherited_color(page.images, current_folder_color)
            if color_filter_active:
                _append_unique_images(fallback_images, images_with_folder_color)
                matched_images = _images_matching_color(
                    page.images,
                    requested_color=requested_color,
                    requested_color_terms=normalized_requested_color_terms,
                    inherited_color=current_folder_color,
                )
                matched_child_folders = _child_folders_matching_color(
                    visible_child_folders,
                    requested_color=requested_color,
                    requested_color_terms=normalized_requested_color_terms,
                    inherited_color=current_folder_color,
                )
            else:
                matched_images = []
                matched_child_folders = []

            logger.info(
                "GOOGLE_DRIVE_FOLDER_DEPTH_RESULT root_folder_id=%s current_folder_id=%s depth=%s image_count=%s child_folder_count=%s requested_color=%s current_folder_color=%s matched_image_count=%s matched_child_folder_count=%s page_truncated=%s",
                root_folder_id,
                current_folder_id,
                depth,
                len(page.images),
                len(visible_child_folders),
                requested_color,
                current_folder_color,
                len(matched_images),
                len(matched_child_folders),
                page.page_truncated,
            )

            if not color_filter_active:
                color_child_folders = _child_folders_with_detected_color(
                    visible_child_folders,
                    current_folder_color,
                )
                if (
                    depth == 1
                    and color_child_folders
                    and depth < max_depth
                    and _is_color_diverse_drive_selection_enabled()
                ):
                    root_selected_group = "color_folders"
                    max_color_folder_count = _get_pancake_drive_color_folder_max_count()
                    selected_color_child_folders = color_child_folders[:max_color_folder_count]
                    color_folder_scan_truncated = len(color_child_folders) > len(selected_color_child_folders)
                    color_folder_images: list[DriveImageResult] = []
                    root_fill_images = list(images_with_folder_color)
                    opened_color_folder_ids: list[str] = []
                    covered_color_keys: list[str] = []

                    for child_folder in selected_color_child_folders:
                        child_folder_color = _child_folder_effective_color(
                            child_folder,
                            current_folder_color,
                        )
                        visited_folder_ids.append(child_folder.id)
                        opened_color_folder_ids.append(child_folder.id)
                        child_page = await self._fetch_first_children_page_for_folder(
                            client=client,
                            folder_id=child_folder.id,
                        )
                        page_truncated = page_truncated or child_page.page_truncated
                        child_images = _images_with_inherited_color(
                            child_page.images,
                            child_folder_color,
                        )
                        if not child_images:
                            logger.info(
                                "GOOGLE_DRIVE_FOLDER_COLOR_CHILD_EMPTY root_folder_id=%s child_folder_id=%s child_folder_name=%s child_folder_color=%s page_truncated=%s",
                                root_folder_id,
                                child_folder.id,
                                child_folder.name,
                                child_folder_color,
                                child_page.page_truncated,
                            )
                            continue

                        selected_child_folder_ids.append(child_folder.id)
                        _append_unique_images(color_folder_images, child_images)
                        if child_folder_color and child_folder_color not in covered_color_keys:
                            covered_color_keys.append(child_folder_color)

                    combined_images: list[DriveImageResult] = []
                    _append_unique_images(combined_images, color_folder_images)
                    _append_unique_images(combined_images, root_fill_images)

                    logger.info(
                        "GOOGLE_DRIVE_FOLDER_COLOR_DIVERSE_RESULT root_folder_id=%s color_folder_count=%s opened_color_folder_count=%s selected_color_folder_count=%s covered_colors=%s root_image_count=%s image_count=%s color_folder_scan_truncated=%s",
                        root_folder_id,
                        len(color_child_folders),
                        len(opened_color_folder_ids),
                        len(selected_child_folder_ids),
                        covered_color_keys,
                        len(root_fill_images),
                        len(combined_images),
                        color_folder_scan_truncated,
                    )

                    if combined_images:
                        return result(
                            images=combined_images,
                            depth=2,
                            selected_group="color_diverse_images",
                        )

                    return result(
                        images=[],
                        error="drive_folder_no_images",
                        depth=2,
                        selected_group="color_diverse_images",
                    )

                if depth == 1 and page.images and visible_child_folders:
                    selected_group = random.choice(["images", "child_folders"])
                    root_selected_group = selected_group
                    logger.info(
                        "GOOGLE_DRIVE_FOLDER_ROOT_GROUP_SELECTED root_folder_id=%s selected_group=%s requested_color=%s",
                        root_folder_id,
                        selected_group,
                        requested_color,
                    )
                    if selected_group == "images":
                        return result(
                            images=images_with_folder_color,
                            depth=depth,
                            selected_group="root_images",
                        )

                    selected_child = random.choice(visible_child_folders)
                    selected_child_folder_ids.append(selected_child.id)
                    current_folder_color = _child_folder_effective_color(
                        selected_child,
                        current_folder_color,
                    )
                    logger.info(
                        "GOOGLE_DRIVE_FOLDER_CHILD_SELECTED root_folder_id=%s current_folder_id=%s depth=%s selected_child_folder_id=%s selected_child_folder_name=%s selected_child_folder_color=%s selected_group=%s",
                        root_folder_id,
                        current_folder_id,
                        depth,
                        selected_child.id,
                        selected_child.name,
                        selected_child.drive_folder_color,
                        "root_child_folders",
                    )
                    current_folder_id = selected_child.id
                    continue

                if page.images:
                    return result(
                        images=images_with_folder_color,
                        depth=depth,
                        selected_group="images",
                    )

                if not visible_child_folders:
                    return result(
                        images=[],
                        error="drive_folder_no_images",
                        depth=depth,
                    )

                if depth >= max_depth:
                    return result(
                        images=[],
                        error="drive_folder_no_images_within_depth_limit",
                        depth=depth,
                    )

                selected_child = random.choice(visible_child_folders)
                selected_child_folder_ids.append(selected_child.id)
                current_folder_color = _child_folder_effective_color(
                    selected_child,
                    current_folder_color,
                )
                logger.info(
                    "GOOGLE_DRIVE_FOLDER_CHILD_SELECTED root_folder_id=%s current_folder_id=%s depth=%s selected_child_folder_id=%s selected_child_folder_name=%s selected_child_folder_color=%s selected_group=%s",
                    root_folder_id,
                    current_folder_id,
                    depth,
                    selected_child.id,
                    selected_child.name,
                    selected_child.drive_folder_color,
                    "child_folders",
                )
                current_folder_id = selected_child.id
                continue

            if depth == 1 and page.images and visible_child_folders:
                if matched_images and not matched_child_folders:
                    return result(
                        images=matched_images,
                        depth=depth,
                        selected_group="root_color_images",
                    )

                if matched_child_folders and not matched_images:
                    selected_child = random.choice(matched_child_folders)
                    selected_child_folder_ids.append(selected_child.id)
                    current_folder_color = _selected_child_folder_color(
                        selected_child,
                        requested_color=requested_color,
                        requested_color_terms=normalized_requested_color_terms,
                        inherited_color=current_folder_color,
                    )
                    logger.info(
                        "GOOGLE_DRIVE_FOLDER_CHILD_SELECTED root_folder_id=%s current_folder_id=%s depth=%s selected_child_folder_id=%s selected_child_folder_name=%s selected_child_folder_color=%s selected_group=%s",
                        root_folder_id,
                        current_folder_id,
                        depth,
                        selected_child.id,
                        selected_child.name,
                        selected_child.drive_folder_color,
                        "root_color_child_folders",
                    )
                    current_folder_id = selected_child.id
                    continue

                if matched_images and matched_child_folders:
                    selected_group = random.choice(["images", "child_folders"])
                    root_selected_group = selected_group
                    logger.info(
                        "GOOGLE_DRIVE_FOLDER_ROOT_GROUP_SELECTED root_folder_id=%s selected_group=%s requested_color=%s",
                        root_folder_id,
                        selected_group,
                        requested_color,
                    )
                    if selected_group == "images":
                        return result(
                            images=matched_images,
                            depth=depth,
                            selected_group="root_color_images",
                        )

                    selected_child = random.choice(matched_child_folders)
                    selected_child_folder_ids.append(selected_child.id)
                    current_folder_color = _selected_child_folder_color(
                        selected_child,
                        requested_color=requested_color,
                        requested_color_terms=normalized_requested_color_terms,
                        inherited_color=current_folder_color,
                    )
                    logger.info(
                        "GOOGLE_DRIVE_FOLDER_CHILD_SELECTED root_folder_id=%s current_folder_id=%s depth=%s selected_child_folder_id=%s selected_child_folder_name=%s selected_child_folder_color=%s selected_group=%s",
                        root_folder_id,
                        current_folder_id,
                        depth,
                        selected_child.id,
                        selected_child.name,
                        selected_child.drive_folder_color,
                        "root_color_child_folders",
                    )
                    current_folder_id = selected_child.id
                    continue

                selected_group = random.choice(["images", "child_folders"])
                root_selected_group = selected_group
                logger.info(
                    "GOOGLE_DRIVE_FOLDER_ROOT_GROUP_SELECTED root_folder_id=%s selected_group=%s requested_color=%s fallback_candidates=%s",
                    root_folder_id,
                    selected_group,
                    requested_color,
                    len(fallback_images),
                )
                if selected_group == "images":
                    return result(
                        images=images_with_folder_color,
                        depth=depth,
                        selected_group="root_fallback_images",
                        color_fallback_used=True,
                    )

                selected_child = random.choice(visible_child_folders)
                selected_child_folder_ids.append(selected_child.id)
                current_folder_color = _selected_child_folder_color(
                    selected_child,
                    requested_color=requested_color,
                    requested_color_terms=normalized_requested_color_terms,
                    inherited_color=current_folder_color,
                )
                logger.info(
                    "GOOGLE_DRIVE_FOLDER_CHILD_SELECTED root_folder_id=%s current_folder_id=%s depth=%s selected_child_folder_id=%s selected_child_folder_name=%s selected_child_folder_color=%s selected_group=%s",
                    root_folder_id,
                    current_folder_id,
                    depth,
                    selected_child.id,
                    selected_child.name,
                    selected_child.drive_folder_color,
                    "root_child_folders",
                )
                current_folder_id = selected_child.id
                continue

            if matched_images:
                return result(
                    images=matched_images,
                    depth=depth,
                    selected_group="color_images",
                )

            if matched_child_folders and depth < max_depth:
                selected_child = random.choice(matched_child_folders)
                selected_child_folder_ids.append(selected_child.id)
                current_folder_color = _selected_child_folder_color(
                    selected_child,
                    requested_color=requested_color,
                    requested_color_terms=normalized_requested_color_terms,
                    inherited_color=current_folder_color,
                )
                logger.info(
                    "GOOGLE_DRIVE_FOLDER_CHILD_SELECTED root_folder_id=%s current_folder_id=%s depth=%s selected_child_folder_id=%s selected_child_folder_name=%s selected_child_folder_color=%s selected_group=%s",
                    root_folder_id,
                    current_folder_id,
                    depth,
                    selected_child.id,
                    selected_child.name,
                    selected_child.drive_folder_color,
                    "color_child_folders",
                )
                current_folder_id = selected_child.id
                continue

            if visible_child_folders and depth < max_depth:
                selected_child = random.choice(visible_child_folders)
                selected_child_folder_ids.append(selected_child.id)
                current_folder_color = _selected_child_folder_color(
                    selected_child,
                    requested_color=requested_color,
                    requested_color_terms=normalized_requested_color_terms,
                    inherited_color=current_folder_color,
                )
                logger.info(
                    "GOOGLE_DRIVE_FOLDER_CHILD_SELECTED root_folder_id=%s current_folder_id=%s depth=%s selected_child_folder_id=%s selected_child_folder_name=%s selected_child_folder_color=%s selected_group=%s",
                    root_folder_id,
                    current_folder_id,
                    depth,
                    selected_child.id,
                    selected_child.name,
                    selected_child.drive_folder_color,
                    "fallback_child_folders",
                )
                current_folder_id = selected_child.id
                continue

            if fallback_images:
                logger.warning(
                    "GOOGLE_DRIVE_FOLDER_COLOR_FALLBACK root_folder_id=%s requested_color=%s fallback_image_count=%s visited_folder_ids=%s",
                    root_folder_id,
                    requested_color,
                    len(fallback_images),
                    visited_folder_ids,
                )
                return result(
                    images=list(fallback_images),
                    depth=depth,
                    selected_group="fallback_images",
                    color_fallback_used=True,
                )

            if visible_child_folders and depth >= max_depth:
                return result(
                    images=[],
                    error="drive_folder_no_images_within_depth_limit",
                    depth=depth,
                )

            return result(
                images=[],
                error="drive_folder_no_images",
                depth=depth,
            )

        if fallback_images and color_filter_active:
            return DriveFolderImageResult(
                folder_url=folder_url,
                folder_id=root_folder_id,
                images=list(fallback_images),
                lookup_depth=max_depth,
                visited_folder_ids=visited_folder_ids,
                selected_child_folder_ids=selected_child_folder_ids,
                page_truncated=page_truncated,
                requested_color=requested_color,
                requested_color_terms=normalized_requested_color_terms,
                selected_group="fallback_images",
                root_selected_group=root_selected_group,
                color_fallback_used=True,
            )

        return DriveFolderImageResult(
            folder_url=folder_url,
            folder_id=root_folder_id,
            images=[],
            error="drive_folder_no_images_within_depth_limit",
            lookup_depth=max_depth,
            visited_folder_ids=visited_folder_ids,
            selected_child_folder_ids=selected_child_folder_ids,
            page_truncated=page_truncated,
            requested_color=requested_color,
            requested_color_terms=normalized_requested_color_terms,
            root_selected_group=root_selected_group,
        )

    async def _fetch_files_for_folder(
        self,
        *,
        client: httpx.AsyncClient,
        folder_id: str,
    ) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []
        page_token: Optional[str] = None

        while True:
            params: dict[str, Any] = {
                "q": build_drive_files_query(folder_id),
                "fields": GOOGLE_DRIVE_FIELDS,
                "pageSize": GOOGLE_DRIVE_PAGE_SIZE,
                "key": self.api_key,
            }
            if page_token:
                params["pageToken"] = page_token

            try:
                with _suppress_httpx_info_logs():
                    response = await client.get(GOOGLE_DRIVE_FILES_URL, params=params)
            except httpx.TimeoutException as exc:
                raise GoogleDriveImageLookupError("drive_api_timeout") from exc
            except httpx.RequestError as exc:
                raise GoogleDriveImageLookupError("drive_api_request_failed") from exc

            if response.status_code >= 400:
                raise GoogleDriveImageLookupError(f"drive_api_http_{response.status_code}")

            try:
                data = response.json()
            except ValueError as exc:
                raise GoogleDriveImageLookupError("drive_api_invalid_json") from exc

            raw_files = data.get("files") if isinstance(data, dict) else None
            if isinstance(raw_files, list):
                files.extend(item for item in raw_files if isinstance(item, dict))

            next_page_token = data.get("nextPageToken") if isinstance(data, dict) else None
            page_token = str(next_page_token).strip() if next_page_token else None
            if not page_token:
                return files

    async def _fetch_first_children_page_for_folder(
        self,
        *,
        client: httpx.AsyncClient,
        folder_id: str,
    ) -> DriveFolderChildrenPageResult:
        params: dict[str, Any] = {
            "q": build_drive_folder_children_query(folder_id),
            "fields": GOOGLE_DRIVE_FIELDS,
            "pageSize": GOOGLE_DRIVE_PAGE_SIZE,
            "key": self.api_key,
        }

        try:
            with _suppress_httpx_info_logs():
                response = await client.get(GOOGLE_DRIVE_FILES_URL, params=params)
        except httpx.TimeoutException as exc:
            raise GoogleDriveImageLookupError("drive_api_timeout") from exc
        except httpx.RequestError as exc:
            raise GoogleDriveImageLookupError("drive_api_request_failed") from exc

        if response.status_code >= 400:
            raise GoogleDriveImageLookupError(f"drive_api_http_{response.status_code}")

        try:
            data = response.json()
        except ValueError as exc:
            raise GoogleDriveImageLookupError("drive_api_invalid_json") from exc

        raw_files = data.get("files") if isinstance(data, dict) else None
        files = [item for item in raw_files if isinstance(item, dict)] if isinstance(raw_files, list) else []
        images = [
            image
            for image in (_image_from_drive_file(file_data) for file_data in files)
            if image is not None
        ]
        child_folders = [
            child_folder
            for child_folder in (_child_folder_from_drive_file(file_data) for file_data in files)
            if child_folder is not None
        ]
        next_page_token = data.get("nextPageToken") if isinstance(data, dict) else None
        page_truncated = bool(str(next_page_token or "").strip())
        if page_truncated:
            logger.info("GOOGLE_DRIVE_FOLDER_PAGE_TRUNCATED folder_id=%s", folder_id)

        return DriveFolderChildrenPageResult(
            images=images,
            child_folders=child_folders,
            page_truncated=page_truncated,
        )
