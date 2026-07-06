from __future__ import annotations

import ipaddress
import logging
import math
from dataclasses import dataclass
from io import BytesIO
from typing import Optional
from urllib.parse import urlparse

from fastapi import UploadFile
import httpx
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers

from app.api.dependencies.error_codes import ErrorCode
from app.api.schemas.image_search import (
    PublicImageCropCoordinates,
    PublicImageCropSearchRequest,
    PublicImageCropSearchResponse,
)
from app.core.config import settings
from app.services.chroma_crop_aware_index import search_chroma_crop_aware_image_service
from app.services.foreground_common import (
    ALLOWED_IMAGE_CONTENT_TYPES,
    CropAwareImageSearchError,
)

logger = logging.getLogger(__name__)

PUBLIC_IMAGE_CROP_REASON_INVALID_IMAGE_URL = "invalid_image_url"
PUBLIC_IMAGE_CROP_REASON_INVALID_CROP = "invalid_crop"
PUBLIC_IMAGE_CROP_REASON_IMAGE_SEARCH_INDEX_NOT_FOUND = "image_search_index_not_found"
PUBLIC_IMAGE_CROP_REASON_IMAGE_SEARCH_FAILED = "image_search_failed"

_MIN_CROP_SIDE_PX = 2
_MAX_IMAGE_URL_LENGTH = 2048
_SOURCE_FORMAT_UPLOADS = {
    "JPEG": ("jpg", "image/jpeg"),
    "PNG": ("png", "image/png"),
    "WEBP": ("webp", "image/webp"),
}


class PublicImageCropSearchError(ValueError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class PublicImageCropResult:
    content: bytes
    extension: str
    content_type: str


def _error_response(reason: str) -> PublicImageCropSearchResponse:
    return PublicImageCropSearchResponse(
        success=False,
        status="error",
        reason=reason,
    )


def _not_found_response() -> PublicImageCropSearchResponse:
    return PublicImageCropSearchResponse(
        success=True,
        status="not_found",
        reason="low_confidence",
    )


def _found_response(*, sku: str, confidence: float) -> PublicImageCropSearchResponse:
    return PublicImageCropSearchResponse(
        success=True,
        status="found",
        sku=sku,
        confidence=round(float(confidence), 4),
    )


def _is_private_or_local_host(hostname: str) -> bool:
    normalized = hostname.strip().strip("[]").rstrip(".").lower()
    if not normalized:
        return True
    if normalized in {"localhost", "0.0.0.0"} or normalized.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return any(
        (
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_reserved,
            address.is_multicast,
            address.is_unspecified,
        )
    )


def _validate_public_image_url(value: str) -> str:
    url = str(value or "").strip()
    if len(url) > _MAX_IMAGE_URL_LENGTH:
        raise PublicImageCropSearchError(PUBLIC_IMAGE_CROP_REASON_INVALID_IMAGE_URL)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise PublicImageCropSearchError(PUBLIC_IMAGE_CROP_REASON_INVALID_IMAGE_URL)
    if not parsed.hostname:
        raise PublicImageCropSearchError(PUBLIC_IMAGE_CROP_REASON_INVALID_IMAGE_URL)
    if _is_private_or_local_host(parsed.hostname):
        raise PublicImageCropSearchError(PUBLIC_IMAGE_CROP_REASON_INVALID_IMAGE_URL)
    return url


def _content_type_allowed(content_type: Optional[str]) -> bool:
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    return media_type in ALLOWED_IMAGE_CONTENT_TYPES


def _configured_timeout(timeout: Optional[float] = None) -> float:
    raw = timeout if timeout is not None else settings.public_image_crop_search_timeout_seconds
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 15.0
    return value if value > 0 else 15.0


def _configured_max_bytes(max_bytes: Optional[int] = None) -> int:
    raw = max_bytes if max_bytes is not None else settings.public_image_crop_search_max_bytes
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 10 * 1024 * 1024
    return value if value > 0 else 10 * 1024 * 1024


def _configured_min_confidence(min_confidence: Optional[float] = None) -> float:
    raw = (
        min_confidence
        if min_confidence is not None
        else settings.public_image_crop_search_min_confidence
    )
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.9
    return value if value >= 0 else 0.9


async def fetch_public_image_bytes(
    image_url: str,
    *,
    timeout_seconds: Optional[float] = None,
    max_bytes: Optional[int] = None,
) -> bytes:
    url = _validate_public_image_url(image_url)
    limit = _configured_max_bytes(max_bytes)
    timeout = _configured_timeout(timeout_seconds)

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
        ) as client:
            async with client.stream("GET", url) as response:
                final_url = str(response.url)
                _validate_public_image_url(final_url)
                if response.status_code < 200 or response.status_code >= 300:
                    raise PublicImageCropSearchError(
                        PUBLIC_IMAGE_CROP_REASON_INVALID_IMAGE_URL
                    )
                if not _content_type_allowed(response.headers.get("content-type")):
                    raise PublicImageCropSearchError(
                        PUBLIC_IMAGE_CROP_REASON_INVALID_IMAGE_URL
                    )
                content_length = response.headers.get("content-length")
                if content_length is not None:
                    try:
                        if int(content_length) > limit:
                            raise PublicImageCropSearchError(
                                PUBLIC_IMAGE_CROP_REASON_INVALID_IMAGE_URL
                            )
                    except ValueError:
                        pass

                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > limit:
                        raise PublicImageCropSearchError(
                            PUBLIC_IMAGE_CROP_REASON_INVALID_IMAGE_URL
                        )
                    chunks.append(chunk)
    except PublicImageCropSearchError:
        raise
    except httpx.HTTPError as exc:
        raise PublicImageCropSearchError(
            PUBLIC_IMAGE_CROP_REASON_INVALID_IMAGE_URL
        ) from exc

    content = b"".join(chunks)
    if not content:
        raise PublicImageCropSearchError(PUBLIC_IMAGE_CROP_REASON_INVALID_IMAGE_URL)
    return content


def _validate_crop(crop: PublicImageCropCoordinates) -> None:
    values = (crop.x1, crop.y1, crop.x2, crop.y2)
    if not all(math.isfinite(value) for value in values):
        raise PublicImageCropSearchError(PUBLIC_IMAGE_CROP_REASON_INVALID_CROP)
    if not (0 <= crop.x1 < crop.x2 <= 1):
        raise PublicImageCropSearchError(PUBLIC_IMAGE_CROP_REASON_INVALID_CROP)
    if not (0 <= crop.y1 < crop.y2 <= 1):
        raise PublicImageCropSearchError(PUBLIC_IMAGE_CROP_REASON_INVALID_CROP)


def _crop_box_for_image(
    crop: PublicImageCropCoordinates,
    *,
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    left = math.floor(crop.x1 * width)
    top = math.floor(crop.y1 * height)
    right = math.ceil(crop.x2 * width)
    bottom = math.ceil(crop.y2 * height)

    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        raise PublicImageCropSearchError(PUBLIC_IMAGE_CROP_REASON_INVALID_CROP)
    if right - left < _MIN_CROP_SIDE_PX or bottom - top < _MIN_CROP_SIDE_PX:
        raise PublicImageCropSearchError(PUBLIC_IMAGE_CROP_REASON_INVALID_CROP)
    return left, top, right, bottom


def crop_public_image_to_source_format_bytes(
    content: bytes,
    crop: PublicImageCropCoordinates,
) -> PublicImageCropResult:
    _validate_crop(crop)
    try:
        with Image.open(BytesIO(content)) as source:
            source_format = (source.format or "").upper()
            upload_info = _SOURCE_FORMAT_UPLOADS.get(source_format)
            if upload_info is None:
                raise PublicImageCropSearchError(
                    PUBLIC_IMAGE_CROP_REASON_INVALID_IMAGE_URL
                )
            image = ImageOps.exif_transpose(source).copy()
    except (
        Image.DecompressionBombError,
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
    ) as exc:
        raise PublicImageCropSearchError(
            PUBLIC_IMAGE_CROP_REASON_INVALID_IMAGE_URL
        ) from exc

    width, height = image.size
    box = _crop_box_for_image(crop, width=width, height=height)
    extension, content_type = upload_info
    if box == (0, 0, width, height):
        return PublicImageCropResult(
            content=content,
            extension=extension,
            content_type=content_type,
        )

    cropped = image.crop(box)
    output = BytesIO()
    if source_format == "JPEG":
        cropped.save(output, format="JPEG", quality=95, optimize=True)
    elif source_format == "WEBP":
        cropped.save(output, format="WEBP", quality=95, method=6)
    else:
        cropped.save(output, format=source_format, optimize=True)
    return PublicImageCropResult(
        content=output.getvalue(),
        extension=extension,
        content_type=content_type,
    )


async def search_public_image_crop_service(
    request: PublicImageCropSearchRequest,
    *,
    min_confidence: Optional[float] = None,
) -> PublicImageCropSearchResponse:
    try:
        logger.info(
            "PUBLIC_IMAGE_CROP_SEARCH_REQUEST_RECEIVED conversation_id=%s",
            request.conversation_id,
        )
        source_content = await fetch_public_image_bytes(request.image_url)
        crop_result = await run_in_threadpool(
            crop_public_image_to_source_format_bytes,
            source_content,
            request.crop,
        )
    except PublicImageCropSearchError as exc:
        logger.warning(
            "PUBLIC_IMAGE_CROP_SEARCH_PREP_FAILED conversation_id=%s reason=%s",
            request.conversation_id,
            exc.reason,
        )
        return _error_response(exc.reason)

    try:
        logger.info(
            "PUBLIC_IMAGE_CROP_SEARCH_SEARCH_START conversation_id=%s",
            request.conversation_id,
        )
        upload = UploadFile(
            file=BytesIO(crop_result.content),
            filename=f"public_crop_{request.conversation_id}.{crop_result.extension}",
            headers=Headers({"content-type": crop_result.content_type}),
        )
        try:
            search_response = await search_chroma_crop_aware_image_service(
                upload=upload,
                top_k=10,
                aggregate_k=1,
            )
        finally:
            await upload.close()
    except CropAwareImageSearchError as exc:
        reason = (
            PUBLIC_IMAGE_CROP_REASON_IMAGE_SEARCH_INDEX_NOT_FOUND
            if exc.error_code == ErrorCode.IMAGE_SEARCH_INDEX_NOT_FOUND
            else PUBLIC_IMAGE_CROP_REASON_IMAGE_SEARCH_FAILED
        )
        logger.warning(
            "PUBLIC_IMAGE_CROP_SEARCH_SEARCH_FAILED conversation_id=%s reason=%s",
            request.conversation_id,
            reason,
        )
        return _error_response(reason)
    except Exception:
        logger.exception(
            "PUBLIC_IMAGE_CROP_SEARCH_SEARCH_FAILED conversation_id=%s reason=%s",
            request.conversation_id,
            PUBLIC_IMAGE_CROP_REASON_IMAGE_SEARCH_FAILED,
        )
        return _error_response(PUBLIC_IMAGE_CROP_REASON_IMAGE_SEARCH_FAILED)

    ranking = search_response.ranking
    if not ranking:
        logger.info(
            "PUBLIC_IMAGE_CROP_SEARCH_NOT_FOUND conversation_id=%s reason=empty_ranking",
            request.conversation_id,
        )
        return _not_found_response()

    best = ranking[0]
    confidence = float(best.score)
    threshold = _configured_min_confidence(min_confidence)
    if confidence < threshold:
        logger.info(
            "PUBLIC_IMAGE_CROP_SEARCH_NOT_FOUND conversation_id=%s sku=%s confidence=%s threshold=%s",
            request.conversation_id,
            best.product_id,
            confidence,
            threshold,
        )
        return _not_found_response()

    logger.info(
        "PUBLIC_IMAGE_CROP_SEARCH_FOUND conversation_id=%s sku=%s confidence=%s",
        request.conversation_id,
        best.product_id,
        confidence,
    )
    return _found_response(sku=best.product_id, confidence=confidence)
