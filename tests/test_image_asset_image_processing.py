import asyncio
from io import BytesIO

import pytest
from fastapi import UploadFile
from PIL import Image
from starlette.datastructures import Headers

from app.api.dependencies.error_codes import ErrorCode
from app.services import image_asset_service
from app.services.image_asset_service import (
    ImageAssetProcessingError,
    optimize_image,
    read_upload_content,
    store_upload_batch,
)


def _image_bytes(
    image_format="JPEG",
    *,
    size=(120, 80),
    mode="RGB",
    color=(40, 80, 120),
    exif=None,
):
    image = Image.new(mode, size, color)
    output = BytesIO()
    save_kwargs = {"exif": exif} if exif is not None else {}
    image.save(output, format=image_format, **save_kwargs)
    return output.getvalue()


def _upload(content, content_type="image/jpeg", filename="image.jpg"):
    return UploadFile(
        file=BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


@pytest.mark.parametrize(
    ("image_format", "content_type", "mode", "color"),
    [
        ("JPEG", "image/jpeg", "RGB", (40, 80, 120)),
        ("PNG", "image/png", "RGB", (40, 80, 120)),
        ("WEBP", "image/webp", "RGB", (40, 80, 120)),
    ],
)
def test_optimize_supported_images_to_jpeg(image_format, content_type, mode, color):
    del content_type
    result = optimize_image(
        _image_bytes(image_format, mode=mode, color=color),
        hard_limit_bytes=1_000_000,
    )

    with Image.open(BytesIO(result.content)) as stored:
        assert stored.format == "JPEG"
        assert stored.mode == "RGB"
    assert len(result.content) <= 1_000_000


def test_read_upload_rejects_empty_and_unsupported_files():
    with pytest.raises(ImageAssetProcessingError) as empty_error:
        asyncio.run(read_upload_content(_upload(b"")))
    assert empty_error.value.error_code == ErrorCode.IMAGE_ASSET_FILE_REQUIRED

    with pytest.raises(ImageAssetProcessingError) as type_error:
        asyncio.run(
            read_upload_content(
                _upload(b"text", content_type="text/plain"),
            )
        )
    assert type_error.value.error_code == ErrorCode.IMAGE_ASSET_FILE_TYPE_NOT_ALLOWED

    content = b"x" * 11
    assert asyncio.run(read_upload_content(_upload(content))) == content


def test_optimize_rejects_fake_and_corrupt_images():
    with pytest.raises(ImageAssetProcessingError):
        optimize_image(b"not-an-image")

    valid = _image_bytes("JPEG")
    with pytest.raises(ImageAssetProcessingError):
        optimize_image(valid[:20])


def test_optimize_rejects_decodable_but_unsupported_format():
    gif_content = _image_bytes("GIF")

    with pytest.raises(ImageAssetProcessingError) as exc:
        optimize_image(gif_content)

    assert exc.value.error_code == ErrorCode.IMAGE_ASSET_FILE_TYPE_NOT_ALLOWED


def test_exif_orientation_is_applied_before_resize():
    exif = Image.Exif()
    exif[274] = 6
    content = _image_bytes("JPEG", size=(40, 20), exif=exif)

    result = optimize_image(content, max_width=100, max_height=100)

    assert (result.width, result.height) == (20, 40)


def test_transparency_is_flattened_on_white_background():
    content = _image_bytes(
        "PNG",
        size=(4, 4),
        mode="RGBA",
        color=(0, 0, 0, 0),
    )

    result = optimize_image(content)

    with Image.open(BytesIO(result.content)) as stored:
        red, green, blue = stored.convert("RGB").getpixel((0, 0))
    assert red > 245 and green > 245 and blue > 245


def test_optimize_does_not_upscale_and_keeps_aspect_ratio():
    result = optimize_image(
        _image_bytes("PNG", size=(100, 50)),
        max_width=500,
        max_height=500,
    )

    assert (result.width, result.height) == (100, 50)
    assert result.width / result.height == 2


def test_optimize_prefers_target_under_500kb():
    width, height = 1200, 900
    pixels = bytes((index * 37 + index // 13) % 256 for index in range(width * height * 3))
    image = Image.frombytes("RGB", (width, height), pixels)
    output = BytesIO()
    image.save(output, format="PNG")

    result = optimize_image(output.getvalue(), hard_limit_bytes=1_000_000)

    assert result.preferred_target_met is True
    assert len(result.content) <= 500_000


def test_optimize_stops_after_first_candidate_meets_preferred_target(monkeypatch):
    calls = []

    def encode_under_target(image, quality):
        calls.append((image.size, quality))
        return b"x" * 400_000

    monkeypatch.setattr(image_asset_service, "_encode_jpeg", encode_under_target)

    result = optimize_image(_image_bytes("JPEG"), hard_limit_bytes=1_000_000)

    assert result.preferred_target_met is True
    assert len(calls) == 1


def test_optimize_uses_fallback_candidate_when_target_is_unreachable(monkeypatch):
    monkeypatch.setattr(
        image_asset_service,
        "_encode_jpeg",
        lambda image, quality: b"x" * 600_000,
    )

    result = optimize_image(
        _image_bytes("JPEG", size=(320, 240)),
        hard_limit_bytes=1_000_000,
    )

    assert result.preferred_target_met is False
    assert len(result.content) == 600_000


def test_optimize_rejects_when_every_candidate_exceeds_hard_limit(monkeypatch):
    monkeypatch.setattr(
        image_asset_service,
        "_encode_jpeg",
        lambda image, quality: b"x" * 1_000_001,
    )

    with pytest.raises(ImageAssetProcessingError) as exc:
        optimize_image(
            _image_bytes("JPEG", size=(320, 240)),
            hard_limit_bytes=1_000_000,
        )

    assert exc.value.error_code == ErrorCode.IMAGE_ASSET_IMAGE_OPTIMIZE_FAILED


def test_store_upload_batch_keeps_order_and_closes_uploads(tmp_path):
    first = _upload(_image_bytes("JPEG", color=(255, 0, 0)), filename="first.jpg")
    second = _upload(
        _image_bytes("PNG", color=(0, 255, 0)),
        content_type="image/png",
        filename="second.png",
    )

    stored = asyncio.run(
        store_upload_batch(" s678657 ", [first, second], storage_dir=tmp_path)
    )

    assert len(stored) == 2
    assert stored[0].file_name.startswith("S678657_")
    assert stored[1].file_name.startswith("S678657_")
    assert stored[0].file_name != stored[1].file_name
    assert all(item.local_path.exists() for item in stored)
    assert all(item.local_path.suffix == ".jpg" for item in stored)
    assert stored[0].original_size > 0
    assert stored[0].stored_size == stored[0].local_path.stat().st_size
    assert stored[0].width == 120
    assert stored[0].height == 80
    assert first.file.closed is True
    assert second.file.closed is True
    assert not list(tmp_path.glob("*.tmp"))


def test_store_upload_batch_accepts_one_image(tmp_path):
    upload = _upload(_image_bytes("JPEG"))

    stored = asyncio.run(
        store_upload_batch("CODE", [upload], storage_dir=tmp_path)
    )

    assert len(stored) == 1
    assert stored[0].local_path.exists()


def test_store_upload_batch_rolls_back_when_one_image_fails(tmp_path):
    valid = _upload(_image_bytes("JPEG"), filename="valid.jpg")
    invalid = _upload(b"not-an-image", filename="invalid.jpg")

    with pytest.raises(ImageAssetProcessingError):
        asyncio.run(
            store_upload_batch("CODE", [valid, invalid], storage_dir=tmp_path)
        )

    assert not list(tmp_path.glob("*.jpg"))
    assert not list(tmp_path.glob("*.tmp"))
    assert valid.file.closed is True
    assert invalid.file.closed is True


def test_store_upload_removes_written_file_when_public_url_build_fails(
    tmp_path,
    monkeypatch,
):
    upload = _upload(_image_bytes("JPEG"))
    monkeypatch.setattr(
        image_asset_service,
        "build_public_url",
        lambda file_name: (_ for _ in ()).throw(ValueError("invalid public path")),
    )

    with pytest.raises(ValueError):
        asyncio.run(store_upload_batch("CODE", [upload], storage_dir=tmp_path))

    assert not list(tmp_path.glob("*.jpg"))
    assert not list(tmp_path.glob("*.tmp"))
