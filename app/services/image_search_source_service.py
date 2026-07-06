from __future__ import annotations

import csv
import logging
import os
import re
import secrets
import shutil
import string
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Optional, Sequence

from fastapi import FastAPI, UploadFile
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from app.api.dependencies.error_codes import ErrorCode
from app.api.schemas.image_asset import (
    normalize_image_asset_code,
    normalize_image_asset_description,
    normalize_remove_image_file_names,
)
from app.api.schemas.image_search_source import (
    ImageSearchSourceDeleteResponse,
    ImageSearchSourceDetailResponse,
    ImageSearchSourceFile,
    ImageSearchSourceIndexUpdate,
    ImageSearchSourceImportResponse,
    ImageSearchSourceListItem,
    ImageSearchSourceListResponse,
    ImageSearchSourceUpdateResponse,
)
from app.core.config import settings
from app.services.chroma_crop_aware_index import (
    delete_sources_from_chroma_index_service,
    upsert_sources_to_chroma_index_service,
)
from app.services.foreground_common import (
    ALLOWED_IMAGE_CONTENT_TYPES,
    ALLOWED_IMAGE_FORMATS,
    CropAwareImageSearchError,
    resize_max_side,
)

SOURCE_METADATA_FIELDS = [
    "product_id",
    "description",
    "source_image_path",
    "file_name",
    "original_filename",
    "content_type",
    "size_bytes",
    "width",
    "height",
    "created_at",
    "updated_at",
]
FILENAME_RANDOM_ID_LENGTH = 20
SOURCE_IMAGES_PUBLIC_PATH = "/data/source_images"
SOURCE_IMAGE_STORAGE_FORMAT = "JPEG"
SOURCE_IMAGE_STORAGE_CONTENT_TYPE = "image/jpeg"
SOURCE_THUMBNAIL_BACKGROUND = (242, 242, 242)
SOURCE_THUMBNAIL_MAX_BYTES = 100_000
SOURCE_THUMBNAIL_INITIAL_MAX_SIDE = 512
SOURCE_THUMBNAIL_QUALITY_LEVELS = (85, 80, 75, 70, 65, 60, 55, 50, 45)
SOURCE_THUMBNAIL_MAX_SIDE_LEVELS = (
    512,
    448,
    384,
    320,
    256,
    224,
    192,
    160,
    128,
    96,
    80,
    64,
    48,
    32,
    24,
    16,
    8,
    4,
    2,
    1,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreparedSourceImage:
    content: bytes
    image_format: str
    width: int
    height: int


@dataclass(frozen=True)
class StoredSourceImage:
    file_name: str
    original_filename: Optional[str]
    source_image_path: str
    local_path: Path
    content_type: str
    size_bytes: int
    width: int
    height: int


@dataclass(frozen=True)
class OptimizedSourceThumbnail:
    content: bytes
    size_bytes: int
    width: int
    height: int


def _resolve_source_root(source_dir: Optional[str | Path] = None) -> Path:
    configured_dir = source_dir if source_dir is not None else settings.clip_crop_aware_source_dir
    root = Path(configured_dir).expanduser().resolve()
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_PROCESSING_FAILED,
            500,
        ) from exc
    if not root.is_dir():
        raise CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_PROCESSING_FAILED,
            500,
        )
    return root


def _normalize_source_public_path(public_path: str = SOURCE_IMAGES_PUBLIC_PATH) -> str:
    normalized = f"/{public_path.strip().strip('/')}"
    if normalized == "/":
        raise ValueError("source image public path must not be empty")
    return normalized


def mount_image_search_source_storage(
    app: FastAPI,
    *,
    source_dir: Optional[str | Path] = None,
    public_path: str = SOURCE_IMAGES_PUBLIC_PATH,
) -> Path:
    source_root = _resolve_source_root(source_dir)
    app.mount(
        _normalize_source_public_path(public_path),
        StaticFiles(directory=str(source_root), check_dir=True),
        name="image-search-source-images",
    )
    return source_root


def _safe_code_path_segment(code: str) -> str:
    safe = re.sub(r"[^A-Z0-9_-]+", "_", normalize_image_asset_code(code))
    safe = re.sub(r"_+", "_", safe).strip("_")
    if not safe:
        raise ValueError("code does not contain filename-safe characters")
    return safe


def build_source_image_public_url(
    *,
    code: str,
    file_name: str,
    base_url: Optional[str] = None,
    public_path: str = SOURCE_IMAGES_PUBLIC_PATH,
) -> str:
    safe_file_name = Path(file_name).name
    if safe_file_name != file_name or "/" in file_name or "\\" in file_name:
        raise ValueError("file_name must be a basename")

    relative_url = (
        f"{_normalize_source_public_path(public_path)}"
        f"/{_safe_code_path_segment(code)}/{safe_file_name}"
    )
    configured_base_url = base_url if base_url is not None else settings.base_url
    if not configured_base_url:
        return relative_url
    return f"{configured_base_url.rstrip('/')}{relative_url}"


def _code_source_dir(code: str, *, source_dir: Optional[str | Path] = None) -> Path:
    root = _resolve_source_root(source_dir)
    code_dir = (root / _safe_code_path_segment(code)).resolve()
    if code_dir.parent != root:
        raise CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_PROCESSING_FAILED,
            500,
        )
    try:
        code_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_PROCESSING_FAILED,
            500,
        ) from exc
    return code_dir


def _extension_for_image_format(image_format: str) -> str:
    normalized = image_format.upper()
    if normalized == "JPEG":
        return ".jpg"
    if normalized == "PNG":
        return ".png"
    if normalized == "WEBP":
        return ".webp"
    raise CropAwareImageSearchError(
        ErrorCode.IMAGE_SEARCH_FILE_TYPE_NOT_ALLOWED,
        415,
    )


def _new_random_id() -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(FILENAME_RANDOM_ID_LENGTH))


def _new_source_file_name(code: str, image_format: str, code_dir: Path) -> str:
    prefix = _safe_code_path_segment(code)
    extension = _extension_for_image_format(image_format)
    for _ in range(100):
        file_name = f"{prefix}_{_new_random_id()}{extension}"
        if not (code_dir / file_name).exists():
            return file_name
    raise CropAwareImageSearchError(
        ErrorCode.IMAGE_SEARCH_PROCESSING_FAILED,
        500,
    )


def _path_for_metadata(path: Path) -> str:
    resolved = path.resolve()
    try:
        value = resolved.relative_to(Path.cwd().resolve())
    except ValueError:
        value = resolved
    return str(value).replace("\\", "/")


async def _read_source_upload(upload: UploadFile) -> bytes:
    if upload.content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_FILE_TYPE_NOT_ALLOWED,
            415,
        )

    content = await upload.read()
    if not content:
        raise CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_FILE_REQUIRED,
            422,
        )
    return content


def _flatten_image_for_jpeg(image: Image.Image) -> Image.Image:
    has_alpha = image.mode in {"RGBA", "LA"} or (
        image.mode == "P" and "transparency" in image.info
    )
    if has_alpha:
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (*SOURCE_THUMBNAIL_BACKGROUND, 255))
        background.alpha_composite(rgba)
        return background.convert("RGB")
    if image.mode != "RGB":
        return image.convert("RGB")
    return image


def _save_prepared_source_image(image: Image.Image, image_format: str) -> bytes:
    output = BytesIO()
    normalized_format = image_format.upper()
    save_kwargs: dict[str, object] = {}

    if normalized_format == "JPEG":
        image = _flatten_image_for_jpeg(image)
        save_kwargs = {"quality": 95, "optimize": True}
    elif normalized_format == "PNG":
        save_kwargs = {"optimize": True}
    elif normalized_format == "WEBP":
        if image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGB")
        save_kwargs = {"quality": 95, "method": 6}

    image.save(output, format=normalized_format, **save_kwargs)
    return output.getvalue()


def _prepare_source_image_for_storage(
    content: bytes,
    *,
    max_side: Optional[int] = None,
) -> PreparedSourceImage:
    try:
        with Image.open(BytesIO(content)) as source:
            source.verify()
        with Image.open(BytesIO(content)) as source:
            image_format = (source.format or "").upper()
            if image_format not in ALLOWED_IMAGE_FORMATS:
                raise CropAwareImageSearchError(
                    ErrorCode.IMAGE_SEARCH_FILE_TYPE_NOT_ALLOWED,
                    415,
                )
            image = ImageOps.exif_transpose(source)
            image.load()
            image = resize_max_side(
                image,
                max_side or settings.clip_crop_aware_max_side,
            )
            stored_content = _save_prepared_source_image(
                image,
                SOURCE_IMAGE_STORAGE_FORMAT,
            )
            width, height = image.size
    except CropAwareImageSearchError:
        raise
    except (
        Image.DecompressionBombError,
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
    ) as exc:
        raise CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_INVALID_IMAGE,
            422,
        ) from exc
    except Exception as exc:
        raise CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_PROCESSING_FAILED,
            500,
        ) from exc

    return PreparedSourceImage(
        content=stored_content,
        image_format=SOURCE_IMAGE_STORAGE_FORMAT,
        width=width,
        height=height,
    )


def _write_file_atomically(content: bytes, destination: Path) -> None:
    temp_path: Optional[Path] = None
    try:
        descriptor, raw_temp_path = tempfile.mkstemp(
            prefix=".image-search-source-",
            suffix=".tmp",
            dir=str(destination.parent),
        )
        temp_path = Path(raw_temp_path)
        with os.fdopen(descriptor, "wb") as temp_file:
            temp_file.write(content)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.link(temp_path, destination)
    except FileExistsError:
        raise
    except OSError as exc:
        raise CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_PROCESSING_FAILED,
            500,
        ) from exc
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _replace_file_atomically(content: bytes, destination: Path) -> None:
    temp_path: Optional[Path] = None
    try:
        descriptor, raw_temp_path = tempfile.mkstemp(
            prefix=".image-search-source-",
            suffix=".tmp",
            dir=str(destination.parent),
        )
        temp_path = Path(raw_temp_path)
        with os.fdopen(descriptor, "wb") as temp_file:
            temp_file.write(content)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, destination)
        temp_path = None
    except OSError as exc:
        raise CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_PROCESSING_FAILED,
            500,
        ) from exc
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _thumbnail_max_side_candidates(image: Image.Image) -> list[int]:
    start = min(max(image.size), SOURCE_THUMBNAIL_INITIAL_MAX_SIDE)
    candidates = [start]
    candidates.extend(
        side for side in SOURCE_THUMBNAIL_MAX_SIDE_LEVELS if side < start
    )
    return list(dict.fromkeys(side for side in candidates if side >= 1))


def _encode_jpeg_thumbnail(image: Image.Image, *, quality: int) -> bytes:
    output = BytesIO()
    image.save(output, format="JPEG", quality=quality, optimize=True)
    return output.getvalue()


def _build_source_thumbnail(content: bytes) -> OptimizedSourceThumbnail:
    try:
        with Image.open(BytesIO(content)) as source:
            image = ImageOps.exif_transpose(source)
            image.load()

        for max_side in _thumbnail_max_side_candidates(image):
            resized = resize_max_side(image, max_side)
            jpeg_image = _flatten_image_for_jpeg(resized)
            for quality in SOURCE_THUMBNAIL_QUALITY_LEVELS:
                encoded = _encode_jpeg_thumbnail(jpeg_image, quality=quality)
                if len(encoded) <= SOURCE_THUMBNAIL_MAX_BYTES:
                    width, height = jpeg_image.size
                    return OptimizedSourceThumbnail(
                        content=encoded,
                        size_bytes=len(encoded),
                        width=width,
                        height=height,
                    )
    except CropAwareImageSearchError:
        raise
    except Exception as exc:
        raise CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_PROCESSING_FAILED,
            500,
        ) from exc

    raise CropAwareImageSearchError(
        ErrorCode.IMAGE_SEARCH_PROCESSING_FAILED,
        500,
    )


def _optimize_stored_source_thumbnail(
    image: StoredSourceImage,
    *,
    code: str,
) -> StoredSourceImage:
    try:
        original_size_bytes = image.local_path.stat().st_size
        content = image.local_path.read_bytes()
        thumbnail = _build_source_thumbnail(content)
        _replace_file_atomically(thumbnail.content, image.local_path)
    except CropAwareImageSearchError:
        logger.exception(
            "IMAGE_SEARCH_IMPORT_THUMBNAIL_OPTIMIZE_FAILED code=%s file=%s",
            code,
            image.file_name,
        )
        raise
    except OSError as exc:
        logger.exception(
            "IMAGE_SEARCH_IMPORT_THUMBNAIL_OPTIMIZE_FAILED code=%s file=%s",
            code,
            image.file_name,
        )
        raise CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_PROCESSING_FAILED,
            500,
        ) from exc

    logger.info(
        "IMAGE_SEARCH_IMPORT_THUMBNAIL_OPTIMIZED code=%s file=%s before_bytes=%s "
        "after_bytes=%s width=%s height=%s",
        code,
        image.file_name,
        original_size_bytes,
        thumbnail.size_bytes,
        thumbnail.width,
        thumbnail.height,
    )
    return StoredSourceImage(
        file_name=image.file_name,
        original_filename=image.original_filename,
        source_image_path=image.source_image_path,
        local_path=image.local_path,
        content_type=SOURCE_IMAGE_STORAGE_CONTENT_TYPE,
        size_bytes=thumbnail.size_bytes,
        width=thumbnail.width,
        height=thumbnail.height,
    )


def _optimize_stored_source_thumbnails(
    images: Sequence[StoredSourceImage],
    *,
    code: str,
) -> list[StoredSourceImage]:
    return [
        _optimize_stored_source_thumbnail(image, code=code)
        for image in images
    ]


async def _store_source_upload(
    code: str,
    upload: UploadFile,
    *,
    source_dir: Optional[str | Path] = None,
) -> StoredSourceImage:
    content = await _read_source_upload(upload)
    prepared = _prepare_source_image_for_storage(content)
    code_dir = _code_source_dir(code, source_dir=source_dir)

    for _ in range(100):
        file_name = _new_source_file_name(code, prepared.image_format, code_dir)
        local_path = code_dir / file_name
        try:
            _write_file_atomically(prepared.content, local_path)
            break
        except FileExistsError:
            continue
    else:
        raise CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_PROCESSING_FAILED,
            500,
        )

    return StoredSourceImage(
        file_name=file_name,
        original_filename=upload.filename,
        source_image_path=_path_for_metadata(local_path),
        local_path=local_path,
        content_type=SOURCE_IMAGE_STORAGE_CONTENT_TYPE,
        size_bytes=len(prepared.content),
        width=prepared.width,
        height=prepared.height,
    )


def _metadata_path(metadata_path: Optional[str | Path] = None) -> Path:
    configured_path = (
        metadata_path
        if metadata_path is not None
        else settings.clip_crop_aware_metadata_path
    )
    return Path(configured_path).expanduser().resolve()


def _read_existing_metadata_fields(path: Path) -> Optional[list[str]]:
    if not path.exists() or path.stat().st_size == 0:
        return None
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        try:
            fields = next(reader)
        except StopIteration:
            return None
    required = {"product_id", "source_image_path"}
    if not required.issubset(set(fields)):
        raise CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_PROCESSING_FAILED,
            500,
        )
    return fields


def _metadata_fields_for_write(existing_fields: Optional[Sequence[str]] = None) -> list[str]:
    fields = list(existing_fields or SOURCE_METADATA_FIELDS)
    for field in SOURCE_METADATA_FIELDS:
        if field not in fields:
            fields.append(field)
    return fields


def _read_metadata_rows(
    metadata_path: Optional[str | Path] = None,
) -> tuple[list[str], list[dict[str, str]]]:
    path = _metadata_path(metadata_path)
    if not path.exists() or path.stat().st_size == 0:
        return SOURCE_METADATA_FIELDS.copy(), []

    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames or []
            required = {"product_id", "source_image_path"}
            if not required.issubset(set(fieldnames)):
                raise CropAwareImageSearchError(
                    ErrorCode.IMAGE_SEARCH_PROCESSING_FAILED,
                    500,
                )
            fields = _metadata_fields_for_write(fieldnames)
            rows = []
            for row in reader:
                rows.append({field: row.get(field, "") or "" for field in fields})
    except CropAwareImageSearchError:
        raise
    except OSError as exc:
        raise CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_PROCESSING_FAILED,
            500,
        ) from exc
    return fields, rows


def _write_metadata_rows(
    rows: Sequence[dict[str, str]],
    *,
    metadata_path: Optional[str | Path] = None,
    fields: Optional[Sequence[str]] = None,
) -> Path:
    path = _metadata_path(metadata_path)
    fieldnames = _metadata_fields_for_write(fields)
    temp_path: Optional[Path] = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, raw_temp_path = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=str(path.parent),
        )
        temp_path = Path(raw_temp_path)
        with os.fdopen(descriptor, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=fieldnames,
                extrasaction="ignore",
            )
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        temp_path = None
    except OSError as exc:
        raise CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_PROCESSING_FAILED,
            500,
        ) from exc
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return path


def _metadata_row_for_image(
    *,
    code: str,
    description: Optional[str],
    image: StoredSourceImage,
    timestamp: str,
) -> dict[str, str]:
    return {
        "product_id": code,
        "description": description or "",
        "source_image_path": image.source_image_path,
        "file_name": image.file_name,
        "original_filename": image.original_filename or "",
        "content_type": image.content_type,
        "size_bytes": str(image.size_bytes),
        "width": str(image.width),
        "height": str(image.height),
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def _append_metadata_rows(
    *,
    code: str,
    description: Optional[str],
    images: Sequence[StoredSourceImage],
    metadata_path: Optional[str | Path] = None,
) -> Path:
    path = _metadata_path(metadata_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        existing_fields = _read_existing_metadata_fields(path)
        fields = existing_fields or SOURCE_METADATA_FIELDS
        should_write_header = existing_fields is None
        now = datetime.now(timezone.utc).isoformat()
        with path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            if should_write_header:
                writer.writeheader()
            for image in images:
                writer.writerow(
                    _metadata_row_for_image(
                        code=code,
                        description=description,
                        image=image,
                        timestamp=now,
                    )
                )
    except CropAwareImageSearchError:
        raise
    except OSError as exc:
        raise CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_PROCESSING_FAILED,
            500,
        ) from exc
    return path


def _refresh_metadata_rows_for_images(
    *,
    images: Sequence[StoredSourceImage],
    metadata_path: Optional[str | Path] = None,
) -> Path:
    if not images:
        return _metadata_path(metadata_path)

    fields, rows = _read_metadata_rows(metadata_path)
    images_by_path = {image.source_image_path: image for image in images}
    refreshed_rows: list[dict[str, str]] = []
    for row in rows:
        image = images_by_path.get(row.get("source_image_path") or "")
        if image is None:
            refreshed_rows.append(row)
            continue

        refreshed = dict(row)
        refreshed.update(
            {
                "source_image_path": image.source_image_path,
                "file_name": image.file_name,
                "content_type": image.content_type,
                "size_bytes": str(image.size_bytes),
                "width": str(image.width),
                "height": str(image.height),
            }
        )
        refreshed_rows.append(refreshed)

    return _write_metadata_rows(
        refreshed_rows,
        metadata_path=metadata_path,
        fields=fields,
    )


def _remove_metadata_rows(
    *,
    source_image_paths: Sequence[str],
    metadata_path: Optional[str | Path] = None,
) -> None:
    path = _metadata_path(metadata_path)
    if not path.exists():
        return

    remove_set = set(source_image_paths)
    temp_path: Optional[Path] = None
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames
            if not fieldnames:
                return
            rows = [
                row
                for row in reader
                if row.get("source_image_path") not in remove_set
            ]

        descriptor, raw_temp_path = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=str(path.parent),
        )
        temp_path = Path(raw_temp_path)
        with os.fdopen(descriptor, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        temp_path = None
    except OSError:
        return
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _index_rows_for_sources(
    code: str,
    images: Sequence[StoredSourceImage],
) -> list[dict[str, str]]:
    return [
        {
            "product_id": code,
            "source_image_path": image.source_image_path,
        }
        for image in images
    ]


def _index_update_from_chroma_result(index_result) -> ImageSearchSourceIndexUpdate:
    return ImageSearchSourceIndexUpdate(
        index_path=_path_for_metadata(Path(index_result.output)),
        source_count=index_result.source_count,
        added_view_count=index_result.added_view_count,
        total_view_count=index_result.total_view_count,
        created_index=index_result.created_index,
        foreground_cache_hits=index_result.foreground_cache_hits,
        foreground_cache_misses=index_result.foreground_cache_misses,
    )


def _row_timestamp(row: dict[str, str]) -> str:
    return row.get("updated_at") or row.get("created_at") or ""


def _latest_timestamp(rows: Sequence[dict[str, str]]) -> Optional[str]:
    timestamps = [timestamp for row in rows if (timestamp := _row_timestamp(row))]
    if not timestamps:
        return None
    return max(timestamps)


def _description_from_rows(rows: Sequence[dict[str, str]]) -> Optional[str]:
    if not rows:
        return None
    latest = max(rows, key=_row_timestamp)
    description = (latest.get("description") or "").strip()
    if description:
        return description
    for row in rows:
        description = (row.get("description") or "").strip()
        if description:
            return description
    return None


def _int_from_row(row: dict[str, str], field: str) -> int:
    try:
        return int(row.get(field) or 0)
    except (TypeError, ValueError):
        return 0


def _file_from_row(row: dict[str, str]) -> ImageSearchSourceFile:
    source_image_path = row.get("source_image_path") or ""
    file_name = row.get("file_name") or Path(source_image_path).name
    code = row.get("product_id") or ""
    return ImageSearchSourceFile(
        file_name=file_name,
        original_filename=row.get("original_filename") or None,
        source_image_path=source_image_path,
        public_url=build_source_image_public_url(code=code, file_name=file_name),
        content_type=row.get("content_type") or "",
        size_bytes=_int_from_row(row, "size_bytes"),
        width=_int_from_row(row, "width"),
        height=_int_from_row(row, "height"),
    )


def _code_rows(
    rows: Sequence[dict[str, str]],
    code: str,
) -> list[dict[str, str]]:
    return [row for row in rows if row.get("product_id") == code]


def _source_dir_response(source_dir: Optional[str | Path] = None) -> str:
    return _path_for_metadata(_resolve_source_root(source_dir))


def _metadata_path_response(metadata_path: Optional[str | Path] = None) -> str:
    return _path_for_metadata(_metadata_path(metadata_path))


def _detail_response_from_rows(
    *,
    code: str,
    rows: Sequence[dict[str, str]],
    source_dir: Optional[str | Path] = None,
    metadata_path: Optional[str | Path] = None,
) -> ImageSearchSourceDetailResponse:
    code_rows = sorted(rows, key=_row_timestamp, reverse=True)
    return ImageSearchSourceDetailResponse(
        code=code,
        description=_description_from_rows(code_rows),
        source_dir=_source_dir_response(source_dir),
        metadata_path=_metadata_path_response(metadata_path),
        image_count=len(code_rows),
        updated_at=_latest_timestamp(code_rows),
        images=[_file_from_row(row) for row in code_rows],
    )


def _raise_not_found() -> None:
    raise CropAwareImageSearchError(ErrorCode.IMAGE_ASSET_NOT_FOUND, 404)


def _delete_source_files(rows: Sequence[dict[str, str]]) -> None:
    for row in rows:
        path = Path(row.get("source_image_path") or "").expanduser()
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            raise CropAwareImageSearchError(
                ErrorCode.IMAGE_SEARCH_PROCESSING_FAILED,
                500,
            ) from exc


def _delete_code_source_dir(code: str, *, source_dir: Optional[str | Path] = None) -> None:
    root = _resolve_source_root(source_dir)
    code_dir = (root / _safe_code_path_segment(code)).resolve()
    if code_dir.parent != root:
        raise CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_PROCESSING_FAILED,
            500,
        )
    if not code_dir.exists():
        return
    if not code_dir.is_dir():
        raise CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_PROCESSING_FAILED,
            500,
        )
    try:
        shutil.rmtree(code_dir)
    except OSError as exc:
        raise CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_PROCESSING_FAILED,
            500,
        ) from exc


async def _close_uploads(uploads: Sequence[UploadFile]) -> None:
    for upload in uploads:
        try:
            await upload.close()
        except Exception:
            continue


def _delete_stored_sources(images: Sequence[StoredSourceImage]) -> None:
    for image in images:
        image.local_path.unlink(missing_ok=True)


async def import_image_search_sources_service(
    *,
    code: str,
    description: Optional[str],
    uploads: Sequence[UploadFile],
    source_dir: Optional[str | Path] = None,
    metadata_path: Optional[str | Path] = None,
    foreground_dir: Optional[str | Path] = None,
) -> ImageSearchSourceImportResponse:
    stored_images: list[StoredSourceImage] = []
    written_metadata_path: Optional[Path] = None
    try:
        if not uploads:
            raise CropAwareImageSearchError(
                ErrorCode.IMAGE_SEARCH_FILE_REQUIRED,
                422,
            )

        normalized_code = normalize_image_asset_code(code)
        normalized_description = normalize_image_asset_description(description)
        for upload in uploads:
            stored_images.append(
                await _store_source_upload(
                    normalized_code,
                    upload,
                    source_dir=source_dir,
                )
            )

        written_metadata_path = _append_metadata_rows(
            code=normalized_code,
            description=normalized_description,
            images=stored_images,
            metadata_path=metadata_path,
        )
        index_result = await run_in_threadpool(
            upsert_sources_to_chroma_index_service,
            rows=_index_rows_for_sources(normalized_code, stored_images),
            foreground_dir=foreground_dir,
            cache_foregrounds=False,
        )
        stored_images = await run_in_threadpool(
            _optimize_stored_source_thumbnails,
            stored_images,
            code=normalized_code,
        )
        _refresh_metadata_rows_for_images(
            images=stored_images,
            metadata_path=written_metadata_path,
        )
        source_root = _resolve_source_root(source_dir)
        return ImageSearchSourceImportResponse(
            code=normalized_code,
            description=normalized_description,
            source_dir=_path_for_metadata(source_root),
            metadata_path=_path_for_metadata(written_metadata_path),
            imported_count=len(stored_images),
            index_updated=True,
            index=_index_update_from_chroma_result(index_result),
            files=[
                ImageSearchSourceFile(
                    file_name=image.file_name,
                    original_filename=image.original_filename,
                    source_image_path=image.source_image_path,
                    public_url=build_source_image_public_url(
                        code=normalized_code,
                        file_name=image.file_name,
                    ),
                    content_type=image.content_type,
                    size_bytes=image.size_bytes,
                    width=image.width,
                    height=image.height,
                )
                for image in stored_images
            ],
        )
    except Exception:
        if written_metadata_path is not None:
            _remove_metadata_rows(
                source_image_paths=[image.source_image_path for image in stored_images],
                metadata_path=written_metadata_path,
            )
        _delete_stored_sources(stored_images)
        raise
    finally:
        await _close_uploads(uploads)


def list_image_search_sources_service(
    *,
    page: int = 1,
    size: int = 20,
    keyword: Optional[str] = None,
    metadata_path: Optional[str | Path] = None,
) -> ImageSearchSourceListResponse:
    if page < 1 or size < 1:
        raise ValueError("page and size must be greater than 0")

    _, rows = _read_metadata_rows(metadata_path)
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        code = row.get("product_id") or ""
        if code:
            grouped.setdefault(code, []).append(row)

    items = [
        ImageSearchSourceListItem(
            code=code,
            description=_description_from_rows(code_rows),
            image_count=len(code_rows),
            updated_at=_latest_timestamp(code_rows),
        )
        for code, code_rows in grouped.items()
    ]
    items.sort(key=lambda item: item.updated_at or "", reverse=True)
    normalized_keyword = (keyword or "").strip().lower()
    if normalized_keyword:
        items = [
            item
            for item in items
            if normalized_keyword in item.code.lower()
            or normalized_keyword in (item.description or "").lower()
        ]

    total = len(items)
    start = (page - 1) * size
    end = start + size
    return ImageSearchSourceListResponse(
        items=items[start:end],
        total=total,
        page=page,
        size=size,
    )


def get_image_search_source_service(
    *,
    code: str,
    source_dir: Optional[str | Path] = None,
    metadata_path: Optional[str | Path] = None,
) -> ImageSearchSourceDetailResponse:
    normalized_code = normalize_image_asset_code(code)
    _, rows = _read_metadata_rows(metadata_path)
    selected_rows = _code_rows(rows, normalized_code)
    if not selected_rows:
        _raise_not_found()
    return _detail_response_from_rows(
        code=normalized_code,
        rows=selected_rows,
        source_dir=source_dir,
        metadata_path=metadata_path,
    )


async def update_image_search_source_service(
    *,
    code: str,
    description: Optional[str],
    description_provided: bool,
    add_uploads: Optional[Sequence[UploadFile]] = None,
    delete_file_names: Optional[Sequence[str]] = None,
    source_dir: Optional[str | Path] = None,
    metadata_path: Optional[str | Path] = None,
    foreground_dir: Optional[str | Path] = None,
) -> ImageSearchSourceUpdateResponse:
    normalized_code = normalize_image_asset_code(code)
    normalized_description = (
        normalize_image_asset_description(description)
        if description_provided
        else None
    )
    normalized_delete_names = normalize_remove_image_file_names(
        list(delete_file_names) if delete_file_names is not None else None
    ) or []
    uploads = list(add_uploads or [])
    stored_images: list[StoredSourceImage] = []
    metadata_written = False
    fields, original_rows = _read_metadata_rows(metadata_path)
    selected_rows = _code_rows(original_rows, normalized_code)
    if not selected_rows:
        await _close_uploads(uploads)
        _raise_not_found()

    delete_by_file_name = {
        row.get("file_name") or Path(row.get("source_image_path") or "").name: row
        for row in selected_rows
    }
    missing_delete_names = [
        file_name
        for file_name in normalized_delete_names
        if file_name not in delete_by_file_name
    ]
    if missing_delete_names:
        await _close_uploads(uploads)
        raise CropAwareImageSearchError(ErrorCode.IMAGE_ASSET_IMAGE_NOT_FOUND, 404)

    delete_rows = [delete_by_file_name[file_name] for file_name in normalized_delete_names]
    delete_source_paths = {row.get("source_image_path") or "" for row in delete_rows}
    touch_code = description_provided or bool(uploads) or bool(delete_rows)
    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        for upload in uploads:
            stored_images.append(
                await _store_source_upload(
                    normalized_code,
                    upload,
                    source_dir=source_dir,
                )
            )

        updated_rows: list[dict[str, str]] = []
        for row in original_rows:
            if row.get("source_image_path") in delete_source_paths:
                continue
            if row.get("product_id") == normalized_code and touch_code:
                row = dict(row)
                if description_provided:
                    row["description"] = normalized_description or ""
                row["updated_at"] = timestamp
            updated_rows.append(row)

        description_for_new_images = (
            normalized_description
            if description_provided
            else _description_from_rows(selected_rows)
        )
        for image in stored_images:
            updated_rows.append(
                _metadata_row_for_image(
                    code=normalized_code,
                    description=description_for_new_images,
                    image=image,
                    timestamp=timestamp,
                )
            )

        if touch_code:
            _write_metadata_rows(
                updated_rows,
                metadata_path=metadata_path,
                fields=fields,
            )
            metadata_written = True

        if delete_source_paths:
            await run_in_threadpool(
                delete_sources_from_chroma_index_service,
                source_image_paths=list(delete_source_paths),
            )

        index_result = None
        if stored_images:
            index_result = await run_in_threadpool(
                upsert_sources_to_chroma_index_service,
                rows=_index_rows_for_sources(normalized_code, stored_images),
                foreground_dir=foreground_dir,
                cache_foregrounds=False,
            )
            stored_images = await run_in_threadpool(
                _optimize_stored_source_thumbnails,
                stored_images,
                code=normalized_code,
            )
            _refresh_metadata_rows_for_images(
                images=stored_images,
                metadata_path=metadata_path,
            )
            _, updated_rows = _read_metadata_rows(metadata_path)

        _delete_source_files(delete_rows)
        selected_after_update = _code_rows(updated_rows, normalized_code)
        detail = _detail_response_from_rows(
            code=normalized_code,
            rows=selected_after_update,
            source_dir=source_dir,
            metadata_path=metadata_path,
        )
        return ImageSearchSourceUpdateResponse(
            code=detail.code,
            description=detail.description,
            source_dir=detail.source_dir,
            metadata_path=detail.metadata_path,
            image_count=detail.image_count,
            updated_at=detail.updated_at,
            added_count=len(stored_images),
            deleted_count=len(delete_rows),
            index_updated=bool(delete_rows or stored_images),
            index=(
                _index_update_from_chroma_result(index_result)
                if index_result is not None
                else None
            ),
            images=detail.images,
        )
    except Exception:
        if metadata_written:
            _write_metadata_rows(
                original_rows,
                metadata_path=metadata_path,
                fields=fields,
            )
        _delete_stored_sources(stored_images)
        raise
    finally:
        await _close_uploads(uploads)


async def delete_image_search_source_service(
    *,
    code: str,
    source_dir: Optional[str | Path] = None,
    metadata_path: Optional[str | Path] = None,
) -> ImageSearchSourceDeleteResponse:
    normalized_code = normalize_image_asset_code(code)
    fields, original_rows = _read_metadata_rows(metadata_path)
    selected_rows = _code_rows(original_rows, normalized_code)
    if not selected_rows:
        _raise_not_found()

    updated_rows = [
        row for row in original_rows if row.get("product_id") != normalized_code
    ]
    _write_metadata_rows(
        updated_rows,
        metadata_path=metadata_path,
        fields=fields,
    )
    try:
        await run_in_threadpool(
            delete_sources_from_chroma_index_service,
            source_image_paths=[
                row.get("source_image_path") or "" for row in selected_rows
            ],
        )
        _delete_code_source_dir(normalized_code, source_dir=source_dir)
    except Exception:
        _write_metadata_rows(
            original_rows,
            metadata_path=metadata_path,
            fields=fields,
        )
        raise

    return ImageSearchSourceDeleteResponse(
        code=normalized_code,
        source_dir=_source_dir_response(source_dir),
        metadata_path=_metadata_path_response(metadata_path),
        deleted_count=len(selected_rows),
        index_updated=True,
    )
