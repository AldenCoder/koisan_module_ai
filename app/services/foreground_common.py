from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from app.api.dependencies.error_codes import ErrorCode
from app.core.config import settings

ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
}
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}

_RUNTIME_CACHE_LOCK = Lock()
_RUNTIME_CACHE: Dict[tuple[str, str], "ClipCropAwareRuntime"] = {}


class CropAwareImageSearchError(ValueError):
    def __init__(self, error_code: ErrorCode, status_code: int):
        self.error_code = error_code
        self.status_code = status_code
        super().__init__(error_code.value)


@dataclass(frozen=True)
class ClipCropAwareRuntime:
    np: Any
    torch: Any
    remove: Any
    processor: Any
    model: Any
    rembg_session: Any


def parse_color(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#")
    if len(value) != 6:
        raise ValueError("Color must be a hex value like #f2f2f2")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


def resize_max_side(image: Image.Image, max_side: int) -> Image.Image:
    if max_side < 1:
        raise ValueError("max_side must be positive")
    if max(image.size) <= max_side:
        return image
    scale = max_side / max(image.size)
    size = (round(image.width * scale), round(image.height * scale))
    return image.resize(size, Image.Resampling.LANCZOS)


def prepare_rgba_for_clip(
    image: Image.Image,
    *,
    background: tuple[int, int, int] = (242, 242, 242),
    crop_alpha: bool = True,
) -> Image.Image:
    image = image.convert("RGBA")
    if crop_alpha:
        bbox = image.getchannel("A").getbbox()
        if bbox:
            image = image.crop(bbox)
    canvas = Image.new("RGBA", image.size, (*background, 255))
    canvas.alpha_composite(image)
    return canvas.convert("RGB")


def _load_ml_dependencies() -> tuple[Any, Any, Any, Any, Any]:
    try:
        import numpy as np
        import torch
        from rembg import new_session, remove
        from transformers import CLIPModel, CLIPProcessor
    except ImportError as exc:
        raise CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_DEPENDENCY_MISSING,
            503,
        ) from exc
    return np, torch, new_session, remove, (CLIPModel, CLIPProcessor)


def get_clip_crop_aware_runtime(
    *,
    clip_model: Optional[str] = None,
    rembg_model: Optional[str] = None,
) -> ClipCropAwareRuntime:
    resolved_clip_model = clip_model or settings.clip_crop_aware_clip_model
    resolved_rembg_model = rembg_model or settings.clip_crop_aware_rembg_model
    cache_key = (resolved_clip_model, resolved_rembg_model)

    with _RUNTIME_CACHE_LOCK:
        cached = _RUNTIME_CACHE.get(cache_key)
        if cached is not None:
            return cached

        np, torch, new_session, remove, clip_classes = _load_ml_dependencies()
        clip_model_class, clip_processor_class = clip_classes
        try:
            processor = clip_processor_class.from_pretrained(resolved_clip_model)
            model = clip_model_class.from_pretrained(resolved_clip_model)
            model.eval()
            rembg_session = new_session(resolved_rembg_model)
        except Exception as exc:
            raise CropAwareImageSearchError(
                ErrorCode.IMAGE_SEARCH_PROCESSING_FAILED,
                500,
            ) from exc

        runtime = ClipCropAwareRuntime(
            np=np,
            torch=torch,
            remove=remove,
            processor=processor,
            model=model,
            rembg_session=rembg_session,
        )
        _RUNTIME_CACHE[cache_key] = runtime
        return runtime


def clear_clip_crop_aware_runtime_cache() -> None:
    with _RUNTIME_CACHE_LOCK:
        _RUNTIME_CACHE.clear()


def embed_prepared_images(
    images: list[Image.Image],
    *,
    runtime: ClipCropAwareRuntime,
) -> Any:
    inputs = runtime.processor(images=images, return_tensors="pt", padding=True)
    with runtime.torch.no_grad():
        features = runtime.model.get_image_features(**inputs)
    if not isinstance(features, runtime.torch.Tensor):
        if hasattr(features, "image_embeds"):
            features = features.image_embeds
        elif hasattr(features, "pooler_output") and hasattr(runtime.model, "visual_projection"):
            features = features.pooler_output
            in_features = getattr(runtime.model.visual_projection, "in_features", None)
            if in_features == features.shape[-1]:
                features = runtime.model.visual_projection(features)
        elif hasattr(features, "pooler_output"):
            features = features.pooler_output
        else:
            raise CropAwareImageSearchError(
                ErrorCode.IMAGE_SEARCH_PROCESSING_FAILED,
                500,
            )
    features = features / features.norm(dim=-1, keepdim=True)
    return features.cpu().numpy().astype("float32")


def validate_image_content(content: bytes) -> None:
    if not content:
        raise CropAwareImageSearchError(ErrorCode.IMAGE_SEARCH_FILE_REQUIRED, 422)
    try:
        with Image.open(BytesIO(content)) as source:
            if (source.format or "").upper() not in ALLOWED_IMAGE_FORMATS:
                raise CropAwareImageSearchError(
                    ErrorCode.IMAGE_SEARCH_FILE_TYPE_NOT_ALLOWED,
                    415,
                )
            source.verify()
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


def extract_foreground_from_content(
    content: bytes,
    *,
    runtime: ClipCropAwareRuntime,
    max_side: int,
) -> Image.Image:
    validate_image_content(content)
    try:
        with Image.open(BytesIO(content)) as source:
            image = source.convert("RGBA")
        image = resize_max_side(image, max_side)
        return runtime.remove(image, session=runtime.rembg_session).convert("RGBA")
    except CropAwareImageSearchError:
        raise
    except Exception as exc:
        raise CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_PROCESSING_FAILED,
            500,
        ) from exc


def extract_foreground_from_path(
    image_path: Path,
    *,
    runtime: ClipCropAwareRuntime,
    max_side: int,
) -> Image.Image:
    try:
        content = image_path.read_bytes()
    except OSError as exc:
        raise CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_INVALID_IMAGE,
            422,
        ) from exc
    return extract_foreground_from_content(
        content,
        runtime=runtime,
        max_side=max_side,
    )


async def read_image_search_upload(upload: UploadFile) -> bytes:
    if upload.content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        await upload.close()
        raise CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_FILE_TYPE_NOT_ALLOWED,
            415,
        )
    try:
        content = await upload.read()
    finally:
        await upload.close()
    if not content:
        raise CropAwareImageSearchError(ErrorCode.IMAGE_SEARCH_FILE_REQUIRED, 422)
    return content
