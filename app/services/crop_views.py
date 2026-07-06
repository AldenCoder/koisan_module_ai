from __future__ import annotations

from dataclasses import dataclass

from PIL import Image


@dataclass(frozen=True)
class CropView:
    name: str
    y0: float
    y1: float
    x_pad: float = 0.04


DEFAULT_VIEWS = (
    CropView("full", 0.00, 1.00, 0.02),
    CropView("upper_65", 0.00, 0.65, 0.06),
    CropView("upper_50", 0.00, 0.50, 0.08),
    CropView("neck_40", 0.00, 0.40, 0.10),
    CropView("torso_15_75", 0.15, 0.75, 0.08),
)


def alpha_bbox(image: Image.Image) -> tuple[int, int, int, int] | None:
    return image.convert("RGBA").getchannel("A").getbbox()


def crop_alpha_view(image: Image.Image, view: CropView) -> Image.Image:
    image = image.convert("RGBA")
    bbox = alpha_bbox(image)
    if not bbox:
        return image

    left, top, right, bottom = bbox
    width = right - left
    height = bottom - top
    crop_top = top + round(height * view.y0)
    crop_bottom = top + round(height * view.y1)
    pad_x = round(width * view.x_pad)

    crop_left = max(0, left - pad_x)
    crop_right = min(image.width, right + pad_x)
    crop_top = max(0, crop_top)
    crop_bottom = min(image.height, max(crop_top + 1, crop_bottom))
    return image.crop((crop_left, crop_top, crop_right, crop_bottom))
