import asyncio
import json
from io import BytesIO

from PIL import Image

from app.services.pancake_drive_image_service import (
    PancakeDriveImageService,
    build_drive_file_download_url,
    parse_drive_file_id,
    prepare_pancake_drive_reply,
    split_text_and_pancake_drive_urls,
    split_text_and_drive_file_urls,
)


class _FakeDownloadResponse:
    def __init__(self, *, status_code=200, headers=None, content=b"image-bytes"):
        self.status_code = status_code
        self.headers = headers if headers is not None else {"content-type": "image/jpeg"}
        self.content = content


class _FakeDownloadClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.call_kwargs = []

    async def get(self, url, **kwargs):
        self.calls.append(url)
        self.call_kwargs.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class _FailingDownloadClient:
    async def get(self, url):  # pragma: no cover - defensive
        raise AssertionError(f"download should not be called: {url}")


def _make_large_test_image_bytes(*, image_format="PNG") -> bytes:
    width = 900
    height = 700
    raw_pixels = bytearray(width * height * 3)
    for index in range(len(raw_pixels)):
        raw_pixels[index] = (index * 37 + index // 11) % 256

    image = Image.frombytes("RGB", (width, height), bytes(raw_pixels))
    buffer = BytesIO()
    image.save(buffer, format=image_format, quality=95)
    return buffer.getvalue()


def test_parse_drive_file_id_supports_file_url():
    drive_file_id = parse_drive_file_id(
        "https://drive.google.com/file/d/1ab3fsmJdVXLXL2wbbzB-NcNWo2PyqKuk/view?usp=drive_link"
    )

    assert drive_file_id == "1ab3fsmJdVXLXL2wbbzB-NcNWo2PyqKuk"


def test_parse_drive_file_id_supports_direct_download_url():
    drive_file_id = parse_drive_file_id(
        "https://drive.google.com/uc?export=download&id=1ab3fsmJdVXLXL2wbbzB-NcNWo2PyqKuk"
    )

    assert drive_file_id == "1ab3fsmJdVXLXL2wbbzB-NcNWo2PyqKuk"


def test_parse_drive_file_id_supports_open_url():
    drive_file_id = parse_drive_file_id(
        "https://drive.google.com/open?id=1ab3fsmJdVXLXL2wbbzB-NcNWo2PyqKuk"
    )

    assert drive_file_id == "1ab3fsmJdVXLXL2wbbzB-NcNWo2PyqKuk"


def test_parse_drive_file_id_rejects_non_drive_host():
    try:
        parse_drive_file_id("https://example.com/file/d/not-drive/view")
    except ValueError as exc:
        assert str(exc) == "drive_file_url_invalid_host"
    else:  # pragma: no cover - defensive
        raise AssertionError("non-drive URL should raise ValueError")


def test_split_text_and_drive_file_urls_removes_drive_link():
    result = split_text_and_drive_file_urls(
        "Dạ mẫu này còn hàng, em gửi ảnh anh/chị xem ạ.\n"
        "https://drive.google.com/file/d/1ab3fsmJdVXLXL2wbbzB-NcNWo2PyqKuk/view?usp=drive_link\n"
        "Anh/chị cần thêm size nào ạ?"
    )

    assert result.text == (
        "Dạ mẫu này còn hàng, em gửi ảnh anh/chị xem ạ.\n"
        "Anh/chị cần thêm size nào ạ?"
    )
    assert result.drive_file_urls == [
        "https://drive.google.com/file/d/1ab3fsmJdVXLXL2wbbzB-NcNWo2PyqKuk/view?usp=drive_link"
    ]


def test_prepare_pancake_drive_reply_deduplicates_drive_files_and_keeps_folder_image_limit():
    result = prepare_pancake_drive_reply(
        "Ảnh 1 https://drive.google.com/file/d/drive_file_1/view\n"
        "Ảnh 1 lặp https://drive.google.com/file/d/drive_file_1/view\n"
        "Ảnh 2 https://drive.google.com/file/d/drive_file_2/view\n"
        "Ảnh 3 https://drive.google.com/file/d/drive_file_3/view",
        image_limit=2,
    )

    assert result.text == "Ảnh 1\nẢnh 1 lặp\nẢnh 2\nẢnh 3"
    assert result.drive_file_ids == ["drive_file_1", "drive_file_2", "drive_file_3"]
    assert result.drive_file_urls == [
        "https://drive.google.com/file/d/drive_file_1/view",
        "https://drive.google.com/file/d/drive_file_2/view",
        "https://drive.google.com/file/d/drive_file_3/view",
    ]
    assert result.image_limit == 2


def test_split_text_and_pancake_drive_urls_removes_file_and_folder_links():
    result = split_text_and_pancake_drive_urls(
        "Em gửi anh/chị album tham khảo:\n"
        "https://drive.google.com/drive/folders/folder_1?usp=sharing\n"
        "Ảnh riêng https://drive.google.com/file/d/drive_file_1/view?usp=drive_link"
    )

    assert result.text == "Em gửi anh/chị album tham khảo:\nẢnh riêng"
    assert result.drive_folder_urls == ["https://drive.google.com/drive/folders/folder_1?usp=sharing"]
    assert result.drive_file_urls == ["https://drive.google.com/file/d/drive_file_1/view?usp=drive_link"]


def test_prepare_pancake_drive_reply_includes_drive_folder_urls():
    result = prepare_pancake_drive_reply(
        "Album https://drive.google.com/drive/folders/folder_1\n"
        "Anh/chị xem giúp em ạ."
    )

    assert result.text == "Album\nAnh/chị xem giúp em ạ."
    assert result.drive_file_ids == []
    assert result.drive_folder_urls == ["https://drive.google.com/drive/folders/folder_1"]


def test_build_drive_file_download_url_uses_expected_format():
    assert build_drive_file_download_url("drive_file_1") == (
        "https://drive.google.com/uc?export=download&id=drive_file_1"
    )


def test_ensure_local_images_uses_existing_local_file_without_download(tmp_path):
    drive_file_id = "drive_file_1"
    storage_dir = tmp_path / "pancake_images"
    local_path = storage_dir / f"{drive_file_id}.jpg"
    local_path.parent.mkdir(parents=True)
    local_path.write_bytes(b"existing-image")
    cache_path = tmp_path / "pancake_image_cache.json"
    service = PancakeDriveImageService(
        cache_path=cache_path,
        storage_dir=storage_dir,
        client=_FailingDownloadClient(),
    )

    result = asyncio.run(
        service.ensure_local_images([f"https://drive.google.com/file/d/{drive_file_id}/view"])
    )

    assert result.errors == []
    assert result.images[0].cache_hit is True
    assert result.images[0].downloaded is False
    assert result.images[0].size_bytes == len(b"existing-image")

    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    assert cache["items"][drive_file_id]["local_path"].endswith(f"{drive_file_id}.jpg")
    assert cache["items"][drive_file_id]["size_bytes"] == len(b"existing-image")


def test_ensure_local_images_optimizes_existing_large_local_file(tmp_path):
    drive_file_id = "drive_file_1"
    storage_max_bytes = 50_000
    storage_dir = tmp_path / "pancake_images"
    local_path = storage_dir / f"{drive_file_id}.jpg"
    local_path.parent.mkdir(parents=True)
    original_content = _make_large_test_image_bytes(image_format="JPEG")
    local_path.write_bytes(original_content)
    cache_path = tmp_path / "pancake_image_cache.json"
    service = PancakeDriveImageService(
        cache_path=cache_path,
        storage_dir=storage_dir,
        client=_FailingDownloadClient(),
        storage_max_bytes=storage_max_bytes,
    )

    result = asyncio.run(
        service.ensure_local_images([f"https://drive.google.com/file/d/{drive_file_id}/view"])
    )

    stored_content = local_path.read_bytes()
    assert result.errors == []
    assert result.images[0].cache_hit is True
    assert result.images[0].downloaded is False
    assert result.images[0].optimized is True
    assert result.images[0].original_size_bytes == len(original_content)
    assert result.images[0].mime_type == "image/jpeg"
    assert result.images[0].size_bytes == len(stored_content)
    assert len(stored_content) <= storage_max_bytes

    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    entry = cache["items"][drive_file_id]
    assert entry["mime_type"] == "image/jpeg"
    assert entry["optimized"] is True
    assert entry["original_size_bytes"] == len(original_content)
    assert entry["size_bytes"] == len(stored_content)
    assert entry["storage_max_bytes"] == storage_max_bytes


def test_ensure_local_images_redownloads_when_existing_large_local_file_is_invalid(tmp_path):
    drive_file_id = "drive_file_1"
    storage_max_bytes = 50_000
    storage_dir = tmp_path / "pancake_images"
    local_path = storage_dir / f"{drive_file_id}.jpg"
    local_path.parent.mkdir(parents=True)
    local_path.write_bytes(b"x" * (storage_max_bytes + 1))
    cache_path = tmp_path / "pancake_image_cache.json"
    original_content = _make_large_test_image_bytes(image_format="JPEG")
    client = _FakeDownloadClient(
        [_FakeDownloadResponse(headers={"content-type": "image/jpeg"}, content=original_content)]
    )
    service = PancakeDriveImageService(
        cache_path=cache_path,
        storage_dir=storage_dir,
        client=client,
        storage_max_bytes=storage_max_bytes,
    )

    result = asyncio.run(
        service.ensure_local_images([f"https://drive.google.com/file/d/{drive_file_id}/view"])
    )

    stored_content = local_path.read_bytes()
    assert client.calls == [f"https://drive.google.com/uc?export=download&id={drive_file_id}"]
    assert result.errors == []
    assert result.images[0].cache_hit is False
    assert result.images[0].downloaded is True
    assert result.images[0].optimized is True
    assert stored_content != b"x" * (storage_max_bytes + 1)
    assert len(stored_content) <= storage_max_bytes


def test_ensure_local_images_downloads_missing_file_and_updates_cache(tmp_path):
    drive_file_id = "drive_file_1"
    storage_dir = tmp_path / "pancake_images"
    cache_path = tmp_path / "pancake_image_cache.json"
    client = _FakeDownloadClient(
        [_FakeDownloadResponse(headers={"content-type": "image/jpeg"}, content=b"new-image")]
    )
    service = PancakeDriveImageService(
        cache_path=cache_path,
        storage_dir=storage_dir,
        client=client,
    )

    result = asyncio.run(
        service.ensure_local_images([f"https://drive.google.com/file/d/{drive_file_id}/view"])
    )

    assert client.calls == [f"https://drive.google.com/uc?export=download&id={drive_file_id}"]
    assert client.call_kwargs == [{"follow_redirects": True}]
    assert result.errors == []
    assert result.images[0].cache_hit is False
    assert result.images[0].downloaded is True
    assert result.images[0].mime_type == "image/jpeg"
    assert (storage_dir / f"{drive_file_id}.jpg").read_bytes() == b"new-image"

    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    entry = cache["items"][drive_file_id]
    assert entry["drive_file_id"] == drive_file_id
    assert entry["direct_download_url"] == f"https://drive.google.com/uc?export=download&id={drive_file_id}"
    assert entry["mime_type"] == "image/jpeg"
    assert entry["size_bytes"] == len(b"new-image")


def test_ensure_local_images_stores_drive_file_name_and_color_metadata(tmp_path):
    drive_file_id = "drive_file_1"
    storage_dir = tmp_path / "pancake_images"
    cache_path = tmp_path / "pancake_image_cache.json"
    client = _FakeDownloadClient(
        [_FakeDownloadResponse(headers={"content-type": "image/jpeg"}, content=b"new-image")]
    )
    service = PancakeDriveImageService(
        cache_path=cache_path,
        storage_dir=storage_dir,
        client=client,
    )

    result = asyncio.run(
        service.ensure_local_images(
            [f"https://drive.google.com/file/d/{drive_file_id}/view"],
            drive_file_metadata={
                drive_file_id: {
                    "drive_file_name": "vay_da_hoi_do.jpg",
                    "drive_file_color": "do",
                }
            },
        )
    )

    assert result.errors == []
    assert result.images[0].drive_file_name == "vay_da_hoi_do.jpg"
    assert result.images[0].drive_file_color == "do"

    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    entry = cache["items"][drive_file_id]
    assert entry["drive_file_name"] == "vay_da_hoi_do.jpg"
    assert entry["drive_file_color"] == "do"


def test_ensure_local_images_reuses_cached_content_id_without_local_file_or_download(tmp_path):
    drive_file_id = "drive_file_1"
    storage_dir = tmp_path / "pancake_images"
    cache_path = tmp_path / "pancake_image_cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "version": 1,
                "items": {
                    drive_file_id: {
                        "drive_file_id": drive_file_id,
                        "content_id": "cached-content-1",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    service = PancakeDriveImageService(
        cache_path=cache_path,
        storage_dir=storage_dir,
        client=_FailingDownloadClient(),
    )

    result = asyncio.run(
        service.ensure_local_images(
            [f"https://drive.google.com/file/d/{drive_file_id}/view"],
            reuse_uploaded_content_id=True,
        )
    )

    assert result.errors == []
    assert result.images[0].cache_hit is True
    assert result.images[0].downloaded is False
    assert result.images[0].content_id == "cached-content-1"
    assert not (storage_dir / f"{drive_file_id}.jpg").exists()


def test_ensure_local_images_removes_old_cache_without_metadata_when_color_required(tmp_path):
    drive_file_id = "drive_file_1"
    storage_dir = tmp_path / "pancake_images"
    local_path = storage_dir / f"{drive_file_id}.jpg"
    local_path.parent.mkdir(parents=True)
    local_path.write_bytes(b"old-local-image")
    cache_path = tmp_path / "pancake_image_cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "version": 1,
                "items": {
                    drive_file_id: {
                        "drive_file_id": drive_file_id,
                        "content_id": "cached-content-1",
                        "local_path": local_path.as_posix(),
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    client = _FakeDownloadClient(
        [_FakeDownloadResponse(headers={"content-type": "image/jpeg"}, content=b"new-image")]
    )
    service = PancakeDriveImageService(
        cache_path=cache_path,
        storage_dir=storage_dir,
        client=client,
    )

    result = asyncio.run(
        service.ensure_local_images(
            [f"https://drive.google.com/file/d/{drive_file_id}/view"],
            reuse_uploaded_content_id=True,
            require_color_metadata=True,
            drive_file_metadata={
                drive_file_id: {
                    "drive_file_name": "vay_da_hoi_do.jpg",
                    "drive_file_color": "do",
                }
            },
        )
    )

    assert client.calls == [f"https://drive.google.com/uc?export=download&id={drive_file_id}"]
    assert result.errors == []
    assert result.images[0].cache_entry_removed is True
    assert result.images[0].downloaded is True
    assert result.images[0].content_id is None
    assert local_path.read_bytes() == b"new-image"

    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    entry = cache["items"][drive_file_id]
    assert "content_id" not in entry
    assert entry["drive_file_name"] == "vay_da_hoi_do.jpg"
    assert entry["drive_file_color"] == "do"


def test_ensure_local_images_downloads_missing_file_when_content_id_reuse_disabled(tmp_path):
    drive_file_id = "drive_file_1"
    storage_dir = tmp_path / "pancake_images"
    cache_path = tmp_path / "pancake_image_cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "version": 1,
                "items": {
                    drive_file_id: {
                        "drive_file_id": drive_file_id,
                        "content_id": "cached-content-1",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    client = _FakeDownloadClient(
        [_FakeDownloadResponse(headers={"content-type": "image/jpeg"}, content=b"new-image")]
    )
    service = PancakeDriveImageService(
        cache_path=cache_path,
        storage_dir=storage_dir,
        client=client,
    )

    result = asyncio.run(
        service.ensure_local_images(
            [f"https://drive.google.com/file/d/{drive_file_id}/view"],
            reuse_uploaded_content_id=False,
        )
    )

    assert client.calls == [f"https://drive.google.com/uc?export=download&id={drive_file_id}"]
    assert result.errors == []
    assert result.images[0].downloaded is True
    assert result.images[0].content_id == "cached-content-1"
    assert (storage_dir / f"{drive_file_id}.jpg").read_bytes() == b"new-image"


def test_ensure_local_images_optimizes_large_download_before_local_save(tmp_path):
    drive_file_id = "drive_file_1"
    storage_max_bytes = 50_000
    original_content = _make_large_test_image_bytes(image_format="PNG")
    storage_dir = tmp_path / "pancake_images"
    cache_path = tmp_path / "pancake_image_cache.json"
    client = _FakeDownloadClient(
        [_FakeDownloadResponse(headers={"content-type": "image/png"}, content=original_content)]
    )
    service = PancakeDriveImageService(
        cache_path=cache_path,
        storage_dir=storage_dir,
        client=client,
        storage_max_bytes=storage_max_bytes,
    )

    result = asyncio.run(
        service.ensure_local_images([f"https://drive.google.com/file/d/{drive_file_id}/view"])
    )

    local_path = storage_dir / f"{drive_file_id}.jpg"
    stored_content = local_path.read_bytes()
    assert result.errors == []
    assert result.images[0].cache_hit is False
    assert result.images[0].downloaded is True
    assert result.images[0].optimized is True
    assert result.images[0].original_size_bytes == len(original_content)
    assert result.images[0].mime_type == "image/jpeg"
    assert result.images[0].size_bytes == len(stored_content)
    assert len(stored_content) <= storage_max_bytes

    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    entry = cache["items"][drive_file_id]
    assert entry["mime_type"] == "image/jpeg"
    assert entry["optimized"] is True
    assert entry["original_size_bytes"] == len(original_content)
    assert entry["size_bytes"] == len(stored_content)
    assert entry["storage_max_bytes"] == storage_max_bytes


def test_record_uploaded_content_id_updates_cache(tmp_path):
    drive_file_id = "drive_file_1"
    storage_dir = tmp_path / "pancake_images"
    cache_path = tmp_path / "pancake_image_cache.json"
    service = PancakeDriveImageService(cache_path=cache_path, storage_dir=storage_dir)

    service.record_uploaded_content_id(drive_file_id=drive_file_id, content_id="content-1")

    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    entry = cache["items"][drive_file_id]
    assert entry["drive_file_id"] == drive_file_id
    assert entry["content_id"] == "content-1"
    assert entry["uploaded_at"]


def test_record_uploaded_content_id_preserves_drive_file_metadata(tmp_path):
    drive_file_id = "drive_file_1"
    storage_dir = tmp_path / "pancake_images"
    cache_path = tmp_path / "pancake_image_cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "version": 1,
                "items": {
                    drive_file_id: {
                        "drive_file_id": drive_file_id,
                        "drive_file_name": "vay_da_hoi_do.jpg",
                        "drive_file_color": "do",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    service = PancakeDriveImageService(cache_path=cache_path, storage_dir=storage_dir)

    service.record_uploaded_content_id(drive_file_id=drive_file_id, content_id="content-1")

    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    entry = cache["items"][drive_file_id]
    assert entry["content_id"] == "content-1"
    assert entry["drive_file_name"] == "vay_da_hoi_do.jpg"
    assert entry["drive_file_color"] == "do"


def test_remove_local_image_for_drive_file_id_deletes_file_and_marks_cache(tmp_path):
    drive_file_id = "drive_file_1"
    storage_dir = tmp_path / "pancake_images"
    local_path = storage_dir / f"{drive_file_id}.jpg"
    local_path.parent.mkdir(parents=True)
    local_path.write_bytes(b"existing-image")
    cache_path = tmp_path / "pancake_image_cache.json"
    service = PancakeDriveImageService(cache_path=cache_path, storage_dir=storage_dir)

    assert service.remove_local_image_for_drive_file_id(drive_file_id) is True

    assert not local_path.exists()
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    entry = cache["items"][drive_file_id]
    assert entry["drive_file_id"] == drive_file_id
    assert entry["local_present"] is False
    assert entry["local_removed_at"]


def test_remove_local_image_for_drive_file_id_preserves_drive_file_metadata(tmp_path):
    drive_file_id = "drive_file_1"
    storage_dir = tmp_path / "pancake_images"
    local_path = storage_dir / f"{drive_file_id}.jpg"
    local_path.parent.mkdir(parents=True)
    local_path.write_bytes(b"existing-image")
    cache_path = tmp_path / "pancake_image_cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "version": 1,
                "items": {
                    drive_file_id: {
                        "drive_file_id": drive_file_id,
                        "drive_file_name": "vay_da_hoi_do.jpg",
                        "drive_file_color": "do",
                        "local_path": local_path.as_posix(),
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    service = PancakeDriveImageService(cache_path=cache_path, storage_dir=storage_dir)

    assert service.remove_local_image_for_drive_file_id(drive_file_id) is True

    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    entry = cache["items"][drive_file_id]
    assert entry["drive_file_name"] == "vay_da_hoi_do.jpg"
    assert entry["drive_file_color"] == "do"
    assert entry["local_present"] is False


def test_ensure_local_images_rejects_non_image_response(tmp_path):
    drive_file_id = "drive_file_1"
    storage_dir = tmp_path / "pancake_images"
    cache_path = tmp_path / "pancake_image_cache.json"
    client = _FakeDownloadClient(
        [_FakeDownloadResponse(headers={"content-type": "text/html"}, content=b"<html></html>")]
    )
    service = PancakeDriveImageService(
        cache_path=cache_path,
        storage_dir=storage_dir,
        client=client,
    )

    result = asyncio.run(
        service.ensure_local_images([f"https://drive.google.com/file/d/{drive_file_id}/view"])
    )

    assert result.errors == [
        {
            "drive_url": f"https://drive.google.com/file/d/{drive_file_id}/view",
            "drive_file_id": drive_file_id,
            "reason": "drive_download_invalid_content_type",
        }
    ]
    assert result.images[0].error == "drive_download_invalid_content_type"
    assert not (storage_dir / f"{drive_file_id}.jpg").exists()
