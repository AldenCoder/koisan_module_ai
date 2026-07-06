import asyncio
import csv
from io import BytesIO
from unittest.mock import Mock

import pytest
from fastapi import UploadFile
from PIL import Image
from starlette.datastructures import Headers

from app.api.dependencies.error_codes import ErrorCode
from app.core.config import settings
from app.services.chroma_crop_aware_index import ChromaCropAwareIndexUpdate
from app.services.foreground_common import CropAwareImageSearchError
from app.services.image_search_source_service import (
    delete_image_search_source_service,
    get_image_search_source_service,
    import_image_search_sources_service,
    list_image_search_sources_service,
    update_image_search_source_service,
)


def _image_bytes(image_format="JPEG", size=(16, 12)):
    image = Image.new("RGB", size, (120, 70, 20))
    output = BytesIO()
    image.save(output, format=image_format)
    return output.getvalue()


def _noisy_image_bytes(image_format="JPEG", size=(1400, 1000)):
    width, height = size
    pixels = bytes(
        (index * 37 + index // 13) % 256 for index in range(width * height * 3)
    )
    image = Image.frombytes("RGB", size, pixels)
    output = BytesIO()
    image.save(output, format=image_format, quality=95)
    return output.getvalue()


def _transparent_png_bytes(size=(80, 80)):
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    for x in range(20, 60):
        for y in range(20, 60):
            image.putpixel((x, y), (180, 40, 30, 255))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _upload(content, content_type="image/jpeg", filename="source.jpg"):
    return UploadFile(
        file=BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


def _index_result(tmp_path, *, created_index=True, added_view_count=5):
    return ChromaCropAwareIndexUpdate(
        output=f"{tmp_path / 'chroma'}#image_search_crop_views_v1",
        source_count=1,
        added_view_count=added_view_count,
        total_view_count=added_view_count,
        created_index=created_index,
        foreground_cache_hits=0,
        foreground_cache_misses=1,
    )


def _write_metadata(path, rows):
    fieldnames = [
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
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _metadata_row(code, path, *, description="", updated_at="2026-06-15T00:00:00+00:00"):
    file_path = str(path).replace("\\", "/")
    return {
        "product_id": code,
        "description": description,
        "source_image_path": file_path,
        "file_name": path.name,
        "original_filename": path.name,
        "content_type": "image/jpeg",
        "size_bytes": "123",
        "width": "16",
        "height": "12",
        "created_at": updated_at,
        "updated_at": updated_at,
    }


def test_import_image_search_sources_stores_resized_source_metadata_and_updates_index(
    tmp_path,
    monkeypatch,
):
    source_dir = tmp_path / "source_images"
    metadata_path = tmp_path / "source_images_metadata.csv"
    content = _image_bytes()
    append_mock = Mock(return_value=_index_result(tmp_path))
    monkeypatch.setattr(
        "app.services.image_search_source_service.upsert_sources_to_chroma_index_service",
        append_mock,
    )

    result = asyncio.run(
        import_image_search_sources_service(
            code=" s12345 ",
            description="  Ao dai do  ",
            uploads=[_upload(content)],
            source_dir=source_dir,
            metadata_path=metadata_path,
        )
    )

    assert result.code == "S12345"
    assert result.description == "Ao dai do"
    assert result.imported_count == 1
    assert result.index_updated is True
    assert result.index is not None
    assert result.index.added_view_count == 5
    assert result.index.created_index is True
    stored = result.files[0]
    assert stored.file_name.startswith("S12345_")
    assert stored.file_name.endswith(".jpg")
    assert stored.width == 16
    assert stored.height == 12
    stored_path = source_dir / "S12345" / stored.file_name
    assert stored.size_bytes == stored_path.stat().st_size
    with Image.open(stored_path) as image:
        assert image.size == (16, 12)
        assert image.format == "JPEG"

    with metadata_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 1
    assert rows[0]["product_id"] == "S12345"
    assert rows[0]["description"] == "Ao dai do"
    assert rows[0]["source_image_path"] == stored.source_image_path
    assert rows[0]["width"] == "16"
    assert rows[0]["height"] == "12"
    append_mock.assert_called_once()
    append_kwargs = append_mock.call_args.kwargs
    assert append_kwargs["rows"] == [
        {
            "product_id": "S12345",
            "source_image_path": stored.source_image_path,
        }
    ]
    assert append_kwargs["cache_foregrounds"] is False


def test_import_optimizes_public_file_after_index_uses_index_ready_image(
    tmp_path,
    monkeypatch,
):
    source_dir = tmp_path / "source_images"
    metadata_path = tmp_path / "source_images_metadata.csv"
    captured = {}

    def _fake_upsert(*, rows, **kwargs):
        del kwargs
        source_path = source_dir / "S12345" / rows[0]["source_image_path"].split("/")[-1]
        captured["source_path"] = source_path
        captured["upsert_size_bytes"] = source_path.stat().st_size
        with Image.open(source_path) as image:
            captured["upsert_size"] = image.size
            captured["upsert_format"] = image.format
        return _index_result(tmp_path)

    monkeypatch.setattr(
        "app.services.image_search_source_service.upsert_sources_to_chroma_index_service",
        _fake_upsert,
    )

    result = asyncio.run(
        import_image_search_sources_service(
            code="S12345",
            description=None,
            uploads=[_upload(_noisy_image_bytes())],
            source_dir=source_dir,
            metadata_path=metadata_path,
        )
    )

    stored = result.files[0]
    stored_path = source_dir / "S12345" / stored.file_name
    assert captured["upsert_format"] == "JPEG"
    assert captured["upsert_size"] == (1280, 914)
    assert captured["upsert_size_bytes"] > stored.size_bytes
    assert stored.size_bytes <= 100_000
    assert stored.size_bytes == stored_path.stat().st_size
    assert stored.content_type == "image/jpeg"
    with Image.open(stored_path) as image:
        assert image.format == "JPEG"
        assert max(image.size) <= 512

    with metadata_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["source_image_path"] == stored.source_image_path
    assert rows[0]["file_name"] == stored.file_name
    assert rows[0]["content_type"] == "image/jpeg"
    assert rows[0]["size_bytes"] == str(stored.size_bytes)
    assert rows[0]["width"] == str(stored.width)
    assert rows[0]["height"] == str(stored.height)


def test_import_png_alpha_becomes_jpeg_thumbnail_with_f2f2f2_background(
    tmp_path,
    monkeypatch,
):
    source_dir = tmp_path / "source_images"
    metadata_path = tmp_path / "source_images_metadata.csv"
    append_mock = Mock(return_value=_index_result(tmp_path))
    monkeypatch.setattr(
        "app.services.image_search_source_service.upsert_sources_to_chroma_index_service",
        append_mock,
    )

    result = asyncio.run(
        import_image_search_sources_service(
            code="S12345",
            description=None,
            uploads=[
                _upload(
                    _transparent_png_bytes(),
                    content_type="image/png",
                    filename="source.png",
                )
            ],
            source_dir=source_dir,
            metadata_path=metadata_path,
        )
    )

    stored = result.files[0]
    stored_path = source_dir / "S12345" / stored.file_name
    assert stored.file_name.endswith(".jpg")
    assert stored.content_type == "image/jpeg"
    assert stored.size_bytes <= 100_000
    with Image.open(stored_path) as image:
        assert image.format == "JPEG"
        assert image.mode == "RGB"
        corner = image.getpixel((0, 0))
    assert all(235 <= channel <= 250 for channel in corner)
    assert append_mock.call_args.kwargs["rows"][0]["source_image_path"].endswith(".jpg")


def test_import_image_search_sources_resizes_large_source_to_max_side(
    tmp_path,
    monkeypatch,
):
    source_dir = tmp_path / "source_images"
    metadata_path = tmp_path / "source_images_metadata.csv"
    append_mock = Mock(return_value=_index_result(tmp_path))
    monkeypatch.setattr(settings, "clip_crop_aware_max_side", 20)
    monkeypatch.setattr(
        "app.services.image_search_source_service.upsert_sources_to_chroma_index_service",
        append_mock,
    )

    result = asyncio.run(
        import_image_search_sources_service(
            code="S12345",
            description=None,
            uploads=[_upload(_image_bytes(size=(40, 10)))],
            source_dir=source_dir,
            metadata_path=metadata_path,
        )
    )

    stored = result.files[0]
    stored_path = source_dir / "S12345" / stored.file_name
    assert stored.width == 20
    assert stored.height == 5
    assert stored.size_bytes == stored_path.stat().st_size
    with Image.open(stored_path) as image:
        assert image.size == (20, 5)

    with metadata_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["width"] == "20"
    assert rows[0]["height"] == "5"


def test_import_image_search_sources_rejects_invalid_uploads(tmp_path, monkeypatch):
    append_mock = Mock(return_value=_index_result(tmp_path))
    monkeypatch.setattr(
        "app.services.image_search_source_service.upsert_sources_to_chroma_index_service",
        append_mock,
    )

    with pytest.raises(CropAwareImageSearchError) as type_error:
        asyncio.run(
            import_image_search_sources_service(
                code="S12345",
                description=None,
                uploads=[_upload(b"text", content_type="text/plain")],
                source_dir=tmp_path / "source_images",
                metadata_path=tmp_path / "metadata.csv",
            )
        )
    assert type_error.value.error_code == ErrorCode.IMAGE_SEARCH_FILE_TYPE_NOT_ALLOWED
    assert type_error.value.status_code == 415

    with pytest.raises(CropAwareImageSearchError) as image_error:
        asyncio.run(
            import_image_search_sources_service(
                code="S12345",
                description=None,
                uploads=[_upload(b"not-an-image")],
                source_dir=tmp_path / "source_images",
                metadata_path=tmp_path / "metadata.csv",
            )
        )
    assert image_error.value.error_code == ErrorCode.IMAGE_SEARCH_INVALID_IMAGE
    assert image_error.value.status_code == 422
    append_mock.assert_not_called()


def test_import_image_search_sources_rolls_back_files_when_metadata_fails(tmp_path):
    source_dir = tmp_path / "source_images"
    metadata_path = tmp_path / "metadata.csv"
    metadata_path.mkdir()

    with pytest.raises(CropAwareImageSearchError):
        asyncio.run(
            import_image_search_sources_service(
                code="S12345",
                description=None,
                uploads=[_upload(_image_bytes())],
                source_dir=source_dir,
                metadata_path=metadata_path,
            )
        )

    assert not list(source_dir.rglob("*.jpg"))


def test_import_image_search_sources_rolls_back_when_index_update_fails(
    tmp_path,
    monkeypatch,
):
    source_dir = tmp_path / "source_images"
    metadata_path = tmp_path / "source_images_metadata.csv"
    append_mock = Mock(
        side_effect=CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_PROCESSING_FAILED,
            500,
        )
    )
    monkeypatch.setattr(
        "app.services.image_search_source_service.upsert_sources_to_chroma_index_service",
        append_mock,
    )

    with pytest.raises(CropAwareImageSearchError):
        asyncio.run(
            import_image_search_sources_service(
                code="S12345",
                description=None,
                uploads=[_upload(_image_bytes())],
                source_dir=source_dir,
                metadata_path=metadata_path,
            )
        )

    assert not list(source_dir.rglob("*.jpg"))
    with metadata_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == []


def test_import_thumbnail_optimize_failure_removes_public_file_and_metadata(
    tmp_path,
    monkeypatch,
):
    source_dir = tmp_path / "source_images"
    metadata_path = tmp_path / "source_images_metadata.csv"
    append_mock = Mock(return_value=_index_result(tmp_path))

    def _raise_optimize_error(content):
        del content
        raise CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_PROCESSING_FAILED,
            500,
        )

    monkeypatch.setattr(
        "app.services.image_search_source_service.upsert_sources_to_chroma_index_service",
        append_mock,
    )
    monkeypatch.setattr(
        "app.services.image_search_source_service._build_source_thumbnail",
        _raise_optimize_error,
    )

    with pytest.raises(CropAwareImageSearchError):
        asyncio.run(
            import_image_search_sources_service(
                code="S12345",
                description=None,
                uploads=[_upload(_noisy_image_bytes())],
                source_dir=source_dir,
                metadata_path=metadata_path,
            )
        )

    append_mock.assert_called_once()
    assert not list(source_dir.rglob("*.jpg"))
    with metadata_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == []


def test_list_and_get_image_search_sources_read_metadata(tmp_path):
    metadata_path = tmp_path / "source_images_metadata.csv"
    s123_path = tmp_path / "source_images" / "S123" / "S123_a.jpg"
    s456_path = tmp_path / "source_images" / "S456" / "S456_a.jpg"
    _write_metadata(
        metadata_path,
        [
            _metadata_row(
                "S123",
                s123_path,
                description="First",
                updated_at="2026-06-15T00:00:00+00:00",
            ),
            _metadata_row(
                "S456",
                s456_path,
                description="Second",
                updated_at="2026-06-16T00:00:00+00:00",
            ),
        ],
    )

    listing = list_image_search_sources_service(metadata_path=metadata_path)
    detail = get_image_search_source_service(
        code="s123",
        source_dir=tmp_path / "source_images",
        metadata_path=metadata_path,
    )

    assert listing.total == 2
    assert listing.page == 1
    assert listing.size == 20
    assert [item.code for item in listing.items] == ["S456", "S123"]
    assert listing.items[0].description == "Second"

    paged = list_image_search_sources_service(
        metadata_path=metadata_path,
        page=2,
        size=1,
    )
    assert paged.total == 2
    assert paged.page == 2
    assert paged.size == 1
    assert [item.code for item in paged.items] == ["S123"]

    filtered = list_image_search_sources_service(
        metadata_path=metadata_path,
        keyword="second",
    )
    assert filtered.total == 1
    assert [item.code for item in filtered.items] == ["S456"]

    assert detail.code == "S123"
    assert detail.description == "First"
    assert detail.image_count == 1
    assert detail.images[0].file_name == "S123_a.jpg"


def test_update_image_search_source_updates_description_without_chroma(
    tmp_path,
    monkeypatch,
):
    metadata_path = tmp_path / "source_images_metadata.csv"
    source_path = tmp_path / "source_images" / "S123" / "S123_a.jpg"
    _write_metadata(
        metadata_path,
        [_metadata_row("S123", source_path, description="Old")],
    )
    upsert_mock = Mock(return_value=_index_result(tmp_path))
    delete_mock = Mock()
    monkeypatch.setattr(
        "app.services.image_search_source_service.upsert_sources_to_chroma_index_service",
        upsert_mock,
    )
    monkeypatch.setattr(
        "app.services.image_search_source_service.delete_sources_from_chroma_index_service",
        delete_mock,
    )

    result = asyncio.run(
        update_image_search_source_service(
            code="S123",
            description="New description",
            description_provided=True,
            source_dir=tmp_path / "source_images",
            metadata_path=metadata_path,
        )
    )

    assert result.description == "New description"
    assert result.added_count == 0
    assert result.deleted_count == 0
    assert result.index_updated is False
    upsert_mock.assert_not_called()
    delete_mock.assert_not_called()
    with metadata_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["description"] == "New description"
    assert rows[0]["updated_at"] != rows[0]["created_at"]


def test_update_image_search_source_adds_and_deletes_images(
    tmp_path,
    monkeypatch,
):
    source_dir = tmp_path / "source_images"
    code_dir = source_dir / "S123"
    code_dir.mkdir(parents=True)
    old_path = code_dir / "S123_old.jpg"
    old_path.write_bytes(_image_bytes())
    metadata_path = tmp_path / "source_images_metadata.csv"
    _write_metadata(
        metadata_path,
        [_metadata_row("S123", old_path, description="Keep")],
    )
    upsert_mock = Mock(return_value=_index_result(tmp_path, created_index=False))
    delete_mock = Mock()
    monkeypatch.setattr(
        "app.services.image_search_source_service.upsert_sources_to_chroma_index_service",
        upsert_mock,
    )
    monkeypatch.setattr(
        "app.services.image_search_source_service.delete_sources_from_chroma_index_service",
        delete_mock,
    )

    result = asyncio.run(
        update_image_search_source_service(
            code="S123",
            description=None,
            description_provided=False,
            add_uploads=[_upload(_image_bytes(), filename="new.jpg")],
            delete_file_names=["S123_old.jpg"],
            source_dir=source_dir,
            metadata_path=metadata_path,
        )
    )

    assert result.added_count == 1
    assert result.deleted_count == 1
    assert result.index_updated is True
    assert result.image_count == 1
    assert result.images[0].file_name.startswith("S123_")
    assert not old_path.exists()
    delete_mock.assert_called_once()
    assert delete_mock.call_args.kwargs["source_image_paths"] == [
        str(old_path).replace("\\", "/")
    ]
    upsert_mock.assert_called_once()
    with metadata_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["file_name"] == result.images[0].file_name
    assert rows[0]["description"] == "Keep"


def test_delete_image_search_source_removes_metadata_files_and_chroma(
    tmp_path,
    monkeypatch,
):
    source_dir = tmp_path / "source_images"
    s123_dir = source_dir / "S123"
    s123_dir.mkdir(parents=True)
    first = s123_dir / "S123_a.jpg"
    second = s123_dir / "S123_b.jpg"
    other = source_dir / "S456" / "S456_a.jpg"
    other.parent.mkdir(parents=True)
    for path in (first, second, other):
        path.write_bytes(_image_bytes())
    metadata_path = tmp_path / "source_images_metadata.csv"
    _write_metadata(
        metadata_path,
        [
            _metadata_row("S123", first),
            _metadata_row("S123", second),
            _metadata_row("S456", other),
        ],
    )
    delete_mock = Mock()
    monkeypatch.setattr(
        "app.services.image_search_source_service.delete_sources_from_chroma_index_service",
        delete_mock,
    )

    result = asyncio.run(
        delete_image_search_source_service(
            code="s123",
            source_dir=source_dir,
            metadata_path=metadata_path,
        )
    )

    assert result.code == "S123"
    assert result.deleted_count == 2
    assert result.index_updated is True
    assert not s123_dir.exists()
    assert other.exists()
    delete_mock.assert_called_once()
    assert delete_mock.call_args.kwargs["source_image_paths"] == [
        str(first).replace("\\", "/"),
        str(second).replace("\\", "/"),
    ]
    with metadata_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["product_id"] == "S456"
