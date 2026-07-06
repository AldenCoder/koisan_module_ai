import logging
import os
import re
import secrets
import string
import tempfile
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path, PurePath
from typing import Iterable, List, Optional, Sequence, Tuple
from urllib.parse import unquote, urlsplit

from bson import ObjectId
from fastapi import FastAPI, UploadFile
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError
from pymongo.errors import DuplicateKeyError

from app.api.dependencies.time import now_vn
from app.api.dependencies.error_codes import ErrorCode
from app.api.schemas.image_asset import (
    ImageAssetListResponse,
    ImageAssetResponse,
    normalize_image_asset_code,
    normalize_image_asset_description,
    normalize_remove_image_file_names,
)
from app.core.config import settings
from app.models.image_assets import ImageAsset

logger = logging.getLogger(__name__)

PREFERRED_IMAGE_TARGET_BYTES = 500_000
IMAGE_MAX_WIDTH = 2048
IMAGE_MAX_HEIGHT = 2048
JPEG_START_QUALITY = 90
ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
}
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
FILENAME_RANDOM_ID_LENGTH = 20
MIN_JPEG_QUALITY = 55
MIN_IMAGE_DIMENSION = 320
DIMENSION_REDUCTION_FACTOR = 0.85
UNSET = object()


class ImageAssetProcessingError(ValueError):
    def __init__(self, error_code: ErrorCode, status_code: int):
        self.error_code = error_code
        self.status_code = status_code
        super().__init__(error_code.value)


@dataclass(frozen=True)
class OptimizedImage:
    content: bytes
    width: int
    height: int
    preferred_target_met: bool


@dataclass(frozen=True)
class StoredImage:
    file_name: str
    local_path: Path
    public_url: str
    original_size: int
    stored_size: int
    width: int
    height: int
    preferred_target_met: bool


@dataclass(frozen=True)
class RenamedImage:
    old_file_name: str
    new_file_name: str
    old_path: Path
    new_path: Path


def normalize_public_path(public_path: str) -> str:
    normalized = f"/{public_path.strip().strip('/')}"
    if normalized == "/":
        raise ValueError("RAG_IMAGE_PUBLIC_PATH must not be empty")
    return normalized


def resolve_storage_root(storage_dir: Optional[str | Path] = None) -> Path:
    configured_dir = storage_dir if storage_dir is not None else settings.rag_image_storage_dir
    return Path(configured_dir).expanduser().resolve()


def ensure_storage_directory(storage_dir: Optional[str | Path] = None) -> Path:
    storage_root = resolve_storage_root(storage_dir)
    try:
        storage_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(
            f"Unable to create RAG image storage directory: {storage_root}"
        ) from exc

    if not storage_root.is_dir():
        raise RuntimeError(f"RAG image storage path is not a directory: {storage_root}")
    if not os.access(storage_root, os.W_OK):
        raise RuntimeError(f"RAG image storage directory is not writable: {storage_root}")
    return storage_root


def mount_rag_image_storage(
    app: FastAPI,
    *,
    storage_dir: Optional[str | Path] = None,
    public_path: Optional[str] = None,
) -> Path:
    storage_root = ensure_storage_directory(storage_dir)
    route_path = normalize_public_path(public_path or settings.rag_image_public_path)
    app.mount(
        route_path,
        StaticFiles(directory=str(storage_root), check_dir=True),
        name="rag-images",
    )
    return storage_root


def normalize_code_for_filename(code: str, *, max_length: int = 100) -> str:
    normalized_code = normalize_image_asset_code(code)
    safe_prefix = re.sub(r"[^A-Z0-9_-]+", "_", normalized_code)
    safe_prefix = re.sub(r"_+", "_", safe_prefix).strip("_")
    safe_prefix = safe_prefix[:max_length].rstrip("_")
    if not safe_prefix:
        raise ValueError("code does not contain filename-safe characters")
    return safe_prefix


def _new_random_id() -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(FILENAME_RANDOM_ID_LENGTH))


def generate_unique_file_name(
    code: str,
    *,
    storage_dir: Optional[str | Path] = None,
    max_attempts: int = 100,
) -> str:
    storage_root = ensure_storage_directory(storage_dir)
    code_prefix = normalize_code_for_filename(code)
    for _ in range(max_attempts):
        file_name = f"{code_prefix}_{_new_random_id()}.jpg"
        if not (storage_root / file_name).exists():
            return file_name
    raise ImageAssetProcessingError(ErrorCode.IMAGE_ASSET_STORAGE_ERROR, 500)


def split_stored_file_name(file_name: str) -> Tuple[str, str, str]:
    match = re.fullmatch(
        rf"(?P<code>.+)_(?P<random>[a-z0-9]{{{FILENAME_RANDOM_ID_LENGTH}}})(?P<ext>\.jpg)",
        file_name,
    )
    if match is None:
        raise ValueError("invalid stored image filename")
    return match.group("code"), match.group("random"), match.group("ext")


def resolve_storage_file(
    file_name: str,
    *,
    storage_dir: Optional[str | Path] = None,
) -> Path:
    if (
        not file_name
        or Path(file_name).is_absolute()
        or PurePath(file_name).name != file_name
        or "/" in file_name
        or "\\" in file_name
    ):
        raise ValueError("filename must be a basename")

    storage_root = ensure_storage_directory(storage_dir)
    candidate = storage_root / file_name
    if candidate.is_symlink():
        raise ValueError("symlinks are not allowed in image storage")

    resolved_candidate = candidate.resolve(strict=False)
    if resolved_candidate.parent != storage_root:
        raise ValueError("resolved path escapes image storage")
    return resolved_candidate


def build_public_url(
    file_name: str,
    *,
    base_url: Optional[str] = None,
    public_path: Optional[str] = None,
) -> str:
    safe_file_name = PurePath(file_name).name
    if safe_file_name != file_name or "/" in file_name or "\\" in file_name:
        raise ValueError("filename must be a basename")

    route_path = normalize_public_path(public_path or settings.rag_image_public_path)
    configured_base_url = base_url if base_url is not None else settings.base_url
    relative_url = f"{route_path}/{safe_file_name}"
    if not configured_base_url:
        return relative_url
    return f"{configured_base_url.rstrip('/')}{relative_url}"


def file_name_from_public_url(url: str) -> str:
    path = unquote(urlsplit(url).path)
    public_prefix = f"{normalize_public_path(settings.rag_image_public_path)}/"
    if not path.startswith(public_prefix):
        raise ValueError("image URL does not use the configured public path")
    file_name = path.removeprefix(public_prefix)
    if (
        not file_name
        or file_name in {".", ".."}
        or PurePath(file_name).name != file_name
        or "/" in file_name
        or "\\" in file_name
    ):
        raise ValueError("invalid image URL")
    return file_name


def _quality_steps(start_quality: int) -> List[int]:
    bounded_start = min(95, max(MIN_JPEG_QUALITY, start_quality))
    qualities = list(range(bounded_start, MIN_JPEG_QUALITY - 1, -5))
    if qualities[-1] != MIN_JPEG_QUALITY:
        qualities.append(MIN_JPEG_QUALITY)
    return qualities


def _resize_within_bounds(image: Image.Image, max_width: int, max_height: int) -> Image.Image:
    if image.width <= max_width and image.height <= max_height:
        return image.copy()
    resized = image.copy()
    resized.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
    return resized


def _normalize_image_mode(image: Image.Image) -> Image.Image:
    has_transparency = image.mode in {"RGBA", "LA"} or (
        image.mode == "P" and "transparency" in image.info
    )
    if has_transparency:
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        return Image.alpha_composite(background, rgba).convert("RGB")
    return image.convert("RGB")


def _encode_jpeg(image: Image.Image, quality: int) -> bytes:
    output = BytesIO()
    image.save(
        output,
        format="JPEG",
        quality=quality,
        optimize=True,
        progressive=True,
    )
    return output.getvalue()


def optimize_image(
    content: bytes,
    *,
    hard_limit_bytes: Optional[int] = None,
    max_width: Optional[int] = None,
    max_height: Optional[int] = None,
    jpeg_quality: Optional[int] = None,
) -> OptimizedImage:
    hard_limit = hard_limit_bytes or settings.rag_image_target_max_bytes
    if hard_limit < PREFERRED_IMAGE_TARGET_BYTES:
        raise ValueError(
            "RAG_IMAGE_TARGET_MAX_BYTES must be at least 500000 bytes"
        )

    target_width = max_width or IMAGE_MAX_WIDTH
    target_height = max_height or IMAGE_MAX_HEIGHT
    start_quality = jpeg_quality or JPEG_START_QUALITY
    if target_width < 1 or target_height < 1:
        raise ValueError("image dimensions must be positive")

    try:
        with Image.open(BytesIO(content)) as source:
            source.verify()
        with Image.open(BytesIO(content)) as source:
            if (source.format or "").upper() not in ALLOWED_IMAGE_FORMATS:
                raise ImageAssetProcessingError(
                    ErrorCode.IMAGE_ASSET_FILE_TYPE_NOT_ALLOWED,
                    415,
                )
            source.load()
            oriented = ImageOps.exif_transpose(source)
            normalized = _normalize_image_mode(oriented)
    except ImageAssetProcessingError:
        raise
    except (
        Image.DecompressionBombError,
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
    ) as exc:
        raise ImageAssetProcessingError(
            ErrorCode.IMAGE_ASSET_IMAGE_OPTIMIZE_FAILED,
            422,
        ) from exc

    current = _resize_within_bounds(normalized, target_width, target_height)
    fallback: Optional[OptimizedImage] = None

    while True:
        for quality in _quality_steps(start_quality):
            try:
                encoded = _encode_jpeg(current, quality)
            except (OSError, ValueError) as exc:
                raise ImageAssetProcessingError(
                    ErrorCode.IMAGE_ASSET_IMAGE_OPTIMIZE_FAILED,
                    422,
                ) from exc
            candidate = OptimizedImage(
                content=encoded,
                width=current.width,
                height=current.height,
                preferred_target_met=len(encoded) <= PREFERRED_IMAGE_TARGET_BYTES,
            )
            if len(encoded) <= PREFERRED_IMAGE_TARGET_BYTES:
                return candidate
            if fallback is None and len(encoded) <= hard_limit:
                fallback = candidate

        if max(current.size) <= MIN_IMAGE_DIMENSION:
            break

        next_width = max(1, int(current.width * DIMENSION_REDUCTION_FACTOR))
        next_height = max(1, int(current.height * DIMENSION_REDUCTION_FACTOR))
        if max(next_width, next_height) < MIN_IMAGE_DIMENSION:
            scale = MIN_IMAGE_DIMENSION / max(current.size)
            next_width = max(1, int(current.width * scale))
            next_height = max(1, int(current.height * scale))
        if (next_width, next_height) == current.size:
            break
        current = current.resize(
            (next_width, next_height),
            Image.Resampling.LANCZOS,
        )

    if fallback is not None:
        return fallback

    raise ImageAssetProcessingError(
        ErrorCode.IMAGE_ASSET_IMAGE_OPTIMIZE_FAILED,
        422,
    )


async def read_upload_content(upload: UploadFile) -> bytes:
    if upload.content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise ImageAssetProcessingError(
            ErrorCode.IMAGE_ASSET_FILE_TYPE_NOT_ALLOWED,
            415,
        )

    content = await upload.read()
    if not content:
        raise ImageAssetProcessingError(ErrorCode.IMAGE_ASSET_FILE_REQUIRED, 422)
    return content


def _write_file_atomically(content: bytes, destination: Path) -> None:
    temp_path: Optional[Path] = None
    try:
        descriptor, raw_temp_path = tempfile.mkstemp(
            prefix=".rag-image-",
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
        raise ImageAssetProcessingError(
            ErrorCode.IMAGE_ASSET_STORAGE_ERROR,
            500,
        ) from exc
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def delete_stored_images(images: Iterable[StoredImage]) -> None:
    for image in images:
        try:
            image.local_path.unlink(missing_ok=True)
            logger.info(
                "IMAGE_ASSET_FILE_ROLLBACK file_name=%s",
                image.file_name,
            )
        except OSError:
            logger.warning(
                "IMAGE_ASSET_FILE_ROLLBACK file_name=%s",
                image.file_name,
                exc_info=True,
            )


async def _store_upload(
    code: str,
    upload: UploadFile,
    *,
    storage_dir: Optional[str | Path] = None,
) -> StoredImage:
    content = await read_upload_content(upload)
    original_size = len(content)
    optimized = optimize_image(content)
    storage_root = ensure_storage_directory(storage_dir)
    local_path: Optional[Path] = None

    try:
        for _ in range(100):
            file_name = generate_unique_file_name(code, storage_dir=storage_root)
            local_path = resolve_storage_file(file_name, storage_dir=storage_root)
            try:
                _write_file_atomically(optimized.content, local_path)
                break
            except FileExistsError:
                local_path = None
                continue
        else:
            raise ImageAssetProcessingError(ErrorCode.IMAGE_ASSET_STORAGE_ERROR, 500)

        if local_path.stat().st_size != len(optimized.content):
            raise ImageAssetProcessingError(ErrorCode.IMAGE_ASSET_STORAGE_ERROR, 500)

        stored = StoredImage(
            file_name=file_name,
            local_path=local_path,
            public_url=build_public_url(file_name),
            original_size=original_size,
            stored_size=len(optimized.content),
            width=optimized.width,
            height=optimized.height,
            preferred_target_met=optimized.preferred_target_met,
        )
    except Exception:
        if local_path is not None:
            local_path.unlink(missing_ok=True)
        raise
    logger.info(
        "IMAGE_ASSET_FILE_SAVED code=%s file_name=%s original_size=%s "
        "stored_size=%s width=%s height=%s preferred_target_met=%s",
        normalize_image_asset_code(code),
        stored.file_name,
        stored.original_size,
        stored.stored_size,
        stored.width,
        stored.height,
        stored.preferred_target_met,
    )
    return stored


async def store_upload_batch(
    code: str,
    uploads: Sequence[UploadFile],
    *,
    storage_dir: Optional[str | Path] = None,
) -> List[StoredImage]:
    stored_images: List[StoredImage] = []
    try:
        if not uploads:
            raise ImageAssetProcessingError(ErrorCode.IMAGE_ASSET_FILE_REQUIRED, 422)

        normalized_code = normalize_image_asset_code(code)
        for upload in uploads:
            stored_images.append(
                await _store_upload(
                    normalized_code,
                    upload,
                    storage_dir=storage_dir,
                )
            )
        return stored_images
    except Exception as exc:
        delete_stored_images(stored_images)
        error_code = getattr(exc, "error_code", ErrorCode.INTERNAL_SERVER_ERROR)
        logger.warning(
            "IMAGE_ASSET_IMAGE_PROCESSING_FAILED code=%s error_code=%s",
            code,
            getattr(error_code, "value", str(error_code)),
        )
        raise
    finally:
        for upload in uploads:
            await upload.close()


async def _close_uploads(uploads: Sequence[UploadFile]) -> None:
    for upload in uploads:
        close = getattr(upload, "close", None)
        if close is None:
            continue
        try:
            await close()
        except Exception:
            logger.warning("IMAGE_ASSET_UPLOAD_CLOSE_FAILED", exc_info=True)


def serialize_image_asset(image_asset: ImageAsset) -> ImageAssetResponse:
    return ImageAssetResponse(
        id=str(image_asset.id),
        code=image_asset.code,
        description=image_asset.description,
        url_images=list(image_asset.url_images),
        created_at=image_asset.created_at,
        updated_at=image_asset.updated_at,
    )


def parse_image_asset_id(image_asset_id: str) -> ObjectId:
    if not ObjectId.is_valid(image_asset_id):
        raise ImageAssetProcessingError(ErrorCode.IMAGE_ASSET_INVALID_ID, 400)
    return ObjectId(image_asset_id)


async def find_image_asset_by_id(image_asset_id: str) -> ImageAsset:
    object_id = parse_image_asset_id(image_asset_id)
    image_asset = await ImageAsset.find_one({"_id": object_id})
    if image_asset is None:
        raise ImageAssetProcessingError(ErrorCode.IMAGE_ASSET_NOT_FOUND, 404)
    return image_asset


async def find_image_asset_by_code(code: str) -> ImageAsset:
    normalized_code = normalize_image_asset_code(code)
    image_asset = await ImageAsset.find_one({"code": normalized_code})
    if image_asset is None:
        raise ImageAssetProcessingError(ErrorCode.IMAGE_ASSET_NOT_FOUND, 404)
    return image_asset


async def _create_image_asset_service_impl(
    *,
    code: str,
    description: Optional[str],
    uploads: Sequence[UploadFile],
    storage_dir: Optional[str | Path] = None,
) -> ImageAssetResponse:
    normalized_code = normalize_image_asset_code(code)
    normalized_description = normalize_image_asset_description(description)
    existing = await ImageAsset.find_one({"code": normalized_code})
    if existing is not None:
        logger.warning("IMAGE_ASSET_CREATE_DUPLICATE_CODE code=%s", normalized_code)
        raise ImageAssetProcessingError(ErrorCode.IMAGE_ASSET_CODE_EXISTS, 409)

    stored_images = await store_upload_batch(
        normalized_code,
        uploads,
        storage_dir=storage_dir,
    )
    try:
        image_asset = ImageAsset(
            code=normalized_code,
            description=normalized_description,
            url_images=[image.public_url for image in stored_images],
        )
        await image_asset.insert()
    except DuplicateKeyError as exc:
        delete_stored_images(stored_images)
        logger.warning("IMAGE_ASSET_CREATE_DUPLICATE_CODE code=%s", normalized_code)
        raise ImageAssetProcessingError(
            ErrorCode.IMAGE_ASSET_CODE_EXISTS,
            409,
        ) from exc
    except Exception as exc:
        delete_stored_images(stored_images)
        logger.exception("IMAGE_ASSET_CREATE_DATABASE_FAILED code=%s", normalized_code)
        raise ImageAssetProcessingError(
            ErrorCode.IMAGE_ASSET_STORAGE_ERROR,
            500,
        ) from exc

    logger.info(
        "IMAGE_ASSET_CREATE_SUCCESS image_asset_id=%s code=%s image_count=%s",
        image_asset.id,
        normalized_code,
        len(stored_images),
    )
    return serialize_image_asset(image_asset)


async def create_image_asset_service(
    *,
    code: str,
    description: Optional[str],
    uploads: Sequence[UploadFile],
    storage_dir: Optional[str | Path] = None,
) -> ImageAssetResponse:
    try:
        return await _create_image_asset_service_impl(
            code=code,
            description=description,
            uploads=uploads,
            storage_dir=storage_dir,
        )
    finally:
        await _close_uploads(uploads)


async def list_image_assets_service(
    *,
    page: int = 1,
    size: int = 10,
    code: Optional[str] = None,
    keyword: Optional[str] = None,
) -> ImageAssetListResponse:
    if page < 1 or size < 1 or size > 100:
        raise ImageAssetProcessingError(ErrorCode.INVALID_INPUT_DATA, 422)

    filters = {}
    if code is not None:
        filters["code"] = normalize_image_asset_code(code)
    normalized_keyword = (keyword or "").strip()
    if normalized_keyword:
        escaped_keyword = re.escape(normalized_keyword)
        filters["$or"] = [
            {"code": {"$regex": escaped_keyword, "$options": "i"}},
            {"description": {"$regex": escaped_keyword, "$options": "i"}},
        ]

    query = ImageAsset.find(filters)
    total = await query.count()
    documents = await (
        query.sort("-updated_at")
        .skip((page - 1) * size)
        .limit(size)
        .to_list()
    )
    logger.info(
        "IMAGE_ASSET_LIST page=%s size=%s code=%s has_keyword=%s total=%s",
        page,
        size,
        code,
        bool(normalized_keyword),
        total,
    )
    return ImageAssetListResponse(
        items=[serialize_image_asset(document) for document in documents],
        total=total,
        page=page,
        size=size,
    )


async def get_image_asset_service(image_asset_id: str) -> ImageAssetResponse:
    return serialize_image_asset(await find_image_asset_by_id(image_asset_id))


async def get_image_asset_by_code_service(code: str) -> ImageAssetResponse:
    return serialize_image_asset(await find_image_asset_by_code(code))


def _rename_image_files(
    image_urls: Sequence[str],
    *,
    new_code: str,
    storage_dir: Optional[str | Path] = None,
) -> Tuple[List[RenamedImage], dict[str, str]]:
    renamed_images: List[RenamedImage] = []
    renamed_urls: dict[str, str] = {}
    new_prefix = normalize_code_for_filename(new_code)

    try:
        for image_url in image_urls:
            old_file_name = file_name_from_public_url(image_url)
            _, random_id, extension = split_stored_file_name(old_file_name)
            new_file_name = f"{new_prefix}_{random_id}{extension}"
            if old_file_name == new_file_name:
                renamed_urls[image_url] = image_url
                continue

            old_path = resolve_storage_file(old_file_name, storage_dir=storage_dir)
            new_path = resolve_storage_file(new_file_name, storage_dir=storage_dir)
            if not old_path.is_file() or new_path.exists():
                raise ImageAssetProcessingError(
                    ErrorCode.IMAGE_ASSET_STORAGE_ERROR,
                    500,
                )
            old_path.rename(new_path)
            renamed_images.append(
                RenamedImage(
                    old_file_name=old_file_name,
                    new_file_name=new_file_name,
                    old_path=old_path,
                    new_path=new_path,
                )
            )
            renamed_urls[image_url] = build_public_url(new_file_name)
    except Exception:
        _rollback_renamed_images(renamed_images)
        raise

    return renamed_images, renamed_urls


def _rollback_renamed_images(renamed_images: Sequence[RenamedImage]) -> None:
    for renamed in reversed(renamed_images):
        try:
            if renamed.new_path.exists() and not renamed.old_path.exists():
                renamed.new_path.rename(renamed.old_path)
                logger.info(
                    "IMAGE_ASSET_RENAME_ROLLBACK old_file_name=%s new_file_name=%s",
                    renamed.old_file_name,
                    renamed.new_file_name,
                )
        except OSError:
            logger.critical(
                "IMAGE_ASSET_RENAME_ROLLBACK_FAILED old_file_name=%s new_file_name=%s",
                renamed.old_file_name,
                renamed.new_file_name,
                exc_info=True,
            )


def _cleanup_file_names(
    file_names: Iterable[str],
    *,
    storage_dir: Optional[str | Path] = None,
) -> None:
    for file_name in file_names:
        try:
            resolve_storage_file(file_name, storage_dir=storage_dir).unlink(missing_ok=True)
        except (OSError, ValueError):
            logger.warning(
                "IMAGE_ASSET_IMAGE_DELETE_FAILED file_name=%s",
                file_name,
                exc_info=True,
            )


async def _update_image_asset_service_impl(
    image_asset_id: str,
    *,
    code: object = UNSET,
    description: object = UNSET,
    uploads: Sequence[UploadFile] = (),
    remove_image_file_names: Optional[Sequence[str]] = None,
    storage_dir: Optional[str | Path] = None,
) -> ImageAssetResponse:
    image_asset = await find_image_asset_by_id(image_asset_id)
    has_code = code is not UNSET
    has_description = description is not UNSET
    normalized_remove_names = normalize_remove_image_file_names(
        list(remove_image_file_names) if remove_image_file_names is not None else None
    ) or []
    if not has_code and not has_description and not uploads and not normalized_remove_names:
        raise ImageAssetProcessingError(ErrorCode.IMAGE_ASSET_EMPTY_UPDATE, 400)

    final_code = (
        normalize_image_asset_code(str(code))
        if has_code
        else image_asset.code
    )
    final_description = (
        normalize_image_asset_description(
            None if description is None else str(description)
        )
        if has_description
        else image_asset.description
    )
    if final_code != image_asset.code:
        duplicate = await ImageAsset.find_one(
            {"code": final_code, "_id": {"$ne": image_asset.id}}
        )
        if duplicate is not None:
            logger.warning(
                "IMAGE_ASSET_UPDATE_DUPLICATE_CODE image_asset_id=%s code=%s",
                image_asset.id,
                final_code,
            )
            raise ImageAssetProcessingError(ErrorCode.IMAGE_ASSET_CODE_EXISTS, 409)

    current_entries = [
        (url, file_name_from_public_url(url))
        for url in image_asset.url_images
    ]
    current_file_names = {file_name for _, file_name in current_entries}
    unknown_remove_names = set(normalized_remove_names) - current_file_names
    if unknown_remove_names:
        raise ImageAssetProcessingError(ErrorCode.IMAGE_ASSET_IMAGE_NOT_FOUND, 400)

    remove_name_set = set(normalized_remove_names)
    kept_entries = [
        (url, file_name)
        for url, file_name in current_entries
        if file_name not in remove_name_set
    ]
    final_image_count = len(kept_entries) + len(uploads)
    if final_image_count < 1:
        raise ImageAssetProcessingError(ErrorCode.INVALID_INPUT_DATA, 422)

    stored_images: List[StoredImage] = []
    renamed_images: List[RenamedImage] = []
    renamed_urls: dict[str, str] = {}
    original_code = image_asset.code
    original_description = image_asset.description
    original_urls = list(image_asset.url_images)
    original_updated_at = image_asset.updated_at

    try:
        if uploads:
            stored_images = await store_upload_batch(
                final_code,
                uploads,
                storage_dir=storage_dir,
            )

        if final_code != original_code:
            renamed_images, renamed_urls = _rename_image_files(
                [url for url, _ in kept_entries],
                new_code=final_code,
                storage_dir=storage_dir,
            )
            logger.info(
                "IMAGE_ASSET_CODE_RENAMED image_asset_id=%s old_code=%s new_code=%s file_count=%s",
                image_asset.id,
                original_code,
                final_code,
                len(renamed_images),
            )

        final_urls = [
            renamed_urls.get(url, url)
            for url, _ in kept_entries
        ]
        final_urls.extend(image.public_url for image in stored_images)

        image_asset.code = final_code
        image_asset.description = final_description
        image_asset.url_images = final_urls
        image_asset.updated_at = now_vn()
        try:
            await image_asset.save()
        except DuplicateKeyError as exc:
            logger.warning(
                "IMAGE_ASSET_UPDATE_DUPLICATE_CODE image_asset_id=%s code=%s",
                image_asset.id,
                final_code,
            )
            raise ImageAssetProcessingError(
                ErrorCode.IMAGE_ASSET_CODE_EXISTS,
                409,
            ) from exc
    except Exception:
        image_asset.code = original_code
        image_asset.description = original_description
        image_asset.url_images = original_urls
        image_asset.updated_at = original_updated_at
        _rollback_renamed_images(renamed_images)
        delete_stored_images(stored_images)
        logger.warning(
            "IMAGE_ASSET_UPDATE_ROLLBACK image_asset_id=%s new_file_count=%s renamed_file_count=%s",
            image_asset_id,
            len(stored_images),
            len(renamed_images),
        )
        raise

    _cleanup_file_names(normalized_remove_names, storage_dir=storage_dir)
    logger.info(
        "IMAGE_ASSET_UPDATE_SUCCESS image_asset_id=%s code=%s added=%s removed=%s",
        image_asset.id,
        image_asset.code,
        len(stored_images),
        len(normalized_remove_names),
    )
    return serialize_image_asset(image_asset)


async def update_image_asset_service(
    image_asset_id: str,
    *,
    code: object = UNSET,
    description: object = UNSET,
    uploads: Sequence[UploadFile] = (),
    remove_image_file_names: Optional[Sequence[str]] = None,
    storage_dir: Optional[str | Path] = None,
) -> ImageAssetResponse:
    try:
        return await _update_image_asset_service_impl(
            image_asset_id,
            code=code,
            description=description,
            uploads=uploads,
            remove_image_file_names=remove_image_file_names,
            storage_dir=storage_dir,
        )
    finally:
        await _close_uploads(uploads)


async def delete_image_asset_service(
    image_asset_id: str,
    *,
    storage_dir: Optional[str | Path] = None,
) -> None:
    image_asset = await find_image_asset_by_id(image_asset_id)
    file_names = [
        file_name_from_public_url(url)
        for url in image_asset.url_images
    ]
    await image_asset.delete()
    _cleanup_file_names(file_names, storage_dir=storage_dir)
    logger.info(
        "IMAGE_ASSET_DELETE_SUCCESS image_asset_id=%s code=%s image_count=%s",
        image_asset.id,
        image_asset.code,
        len(file_names),
    )
