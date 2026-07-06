import asyncio
from io import BytesIO

import pytest
from fastapi import UploadFile
from PIL import Image
from starlette.datastructures import Headers

from app.api.dependencies.error_codes import ErrorCode
from app.services import chroma_crop_aware_index as search_service
from app.services.crop_aware_index_common import aggregate_image_matches
from app.services.foreground_common import (
    CropAwareImageSearchError,
    parse_color,
    read_image_search_upload,
    validate_image_content,
)


def _image_bytes(image_format="JPEG"):
    image = Image.new("RGB", (16, 16), (20, 80, 140))
    output = BytesIO()
    image.save(output, format=image_format)
    return output.getvalue()


def _upload(content, content_type="image/jpeg", filename="query.jpg"):
    return UploadFile(
        file=BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


def test_parse_color_accepts_hex_with_or_without_hash():
    assert parse_color("#f2f2f2") == (242, 242, 242)
    assert parse_color("000102") == (0, 1, 2)


def test_aggregate_image_matches_scores_by_product_top_k_mean():
    matches = [
        {
            "product_id": "A",
            "score": 0.9,
            "source_image_path": "a-1.jpg",
            "index_view": "full",
            "query_view": "upper_50",
        },
        {
            "product_id": "A",
            "score": 0.7,
            "source_image_path": "a-2.jpg",
            "index_view": "upper_65",
            "query_view": "full",
        },
        {
            "product_id": "B",
            "score": 0.8,
            "source_image_path": "b-1.jpg",
            "index_view": "neck_40",
            "query_view": "neck_40",
        },
    ]

    result = aggregate_image_matches(matches, aggregate_k=2)

    assert [item["product_id"] for item in result] == ["A", "B"]
    assert result[0]["score"] == pytest.approx(0.8)
    assert result[0]["best_score"] == pytest.approx(0.9)
    assert result[0]["best_image_path"] == "a-1.jpg"
    assert result[0]["top_image_scores"] == [0.9, 0.7]


def test_read_image_search_upload_validates_type_and_empty_content():
    valid = asyncio.run(read_image_search_upload(_upload(_image_bytes())))
    assert valid

    with pytest.raises(CropAwareImageSearchError) as type_error:
        asyncio.run(
            read_image_search_upload(
                _upload(b"text", content_type="text/plain"),
            )
        )
    assert type_error.value.error_code == ErrorCode.IMAGE_SEARCH_FILE_TYPE_NOT_ALLOWED
    assert type_error.value.status_code == 415

    with pytest.raises(CropAwareImageSearchError) as empty_error:
        asyncio.run(read_image_search_upload(_upload(b"")))
    assert empty_error.value.error_code == ErrorCode.IMAGE_SEARCH_FILE_REQUIRED
    assert empty_error.value.status_code == 422


def test_validate_image_content_rejects_corrupt_and_unsupported_images():
    validate_image_content(_image_bytes("PNG"))

    with pytest.raises(CropAwareImageSearchError) as corrupt_error:
        validate_image_content(b"not-an-image")
    assert corrupt_error.value.error_code == ErrorCode.IMAGE_SEARCH_INVALID_IMAGE
    assert corrupt_error.value.status_code == 422

    with pytest.raises(CropAwareImageSearchError) as type_error:
        validate_image_content(_image_bytes("GIF"))
    assert type_error.value.error_code == ErrorCode.IMAGE_SEARCH_FILE_TYPE_NOT_ALLOWED
    assert type_error.value.status_code == 415


def test_search_service_does_not_persist_query_debug_images(monkeypatch):
    captured = {}

    def fake_search(**kwargs):
        captured.update(kwargs)
        return {
            "query": kwargs["filename"],
            "query_foreground": None,
            "query_views": {},
            "index_path": "data/chroma#image_search_crop_views_v1",
            "top_k": kwargs["top_k"],
            "aggregate_k": kwargs["aggregate_k"],
            "ranking": [],
            "top_images": [],
        }

    monkeypatch.setattr(
        search_service,
        "search_chroma_crop_aware_image_bytes",
        fake_search,
    )

    result = asyncio.run(
        search_service.search_chroma_crop_aware_image_service(
            upload=_upload(_image_bytes()),
            top_k=3,
            aggregate_k=2,
        )
    )

    assert result["query_foreground"] is None
    assert result["query_views"] == {}
    assert captured["save_debug_images"] is False
