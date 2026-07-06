from io import BytesIO

import anyio
import pytest
from PIL import Image

from app.api.dependencies.error_codes import ErrorCode
from app.api.schemas.image_search import (
    CropAwareImageSearchResponse,
    PublicImageCropCoordinates,
    PublicImageCropSearchRequest,
)
from app.services import public_image_crop_search_service as service
from app.services.foreground_common import CropAwareImageSearchError


@pytest.fixture(autouse=True)
def isolate_public_image_crop_settings(monkeypatch):
    monkeypatch.setattr(service.settings, "public_image_crop_search_min_confidence", 0.9)


def _image_bytes(
    *,
    size=(100, 50),
    mode="RGB",
    color=(255, 0, 0),
    image_format="JPEG",
) -> bytes:
    image = Image.new(mode, size, color)
    output = BytesIO()
    image.save(output, format=image_format)
    return output.getvalue()


def _search_response(*, score=0.91, ranking=True):
    items = []
    if ranking:
        items.append(
            {
                "product_id": "S12345",
                "score": score,
                "best_score": score,
                "best_image_path": "source/S12345.jpg",
                "best_index_view": "full",
                "best_query_view": "full",
                "top_image_scores": [score],
            }
        )
    return CropAwareImageSearchResponse(
        query="public_crop.jpg",
        index_path="data/chroma#image_search_crop_views_v1",
        top_k=10,
        aggregate_k=1,
        ranking=items,
        top_images=[],
    )


def _request(crop=None):
    return PublicImageCropSearchRequest(
        conversation_id="conversation-1",
        image_url="https://example.com/image.jpg",
        crop=crop
        or PublicImageCropCoordinates(x1=0.1, y1=0.2, x2=0.6, y2=0.8),
    )


def _patch_httpx_stream(
    monkeypatch,
    *,
    status_code=200,
    headers=None,
    chunks=None,
    final_url="https://example.com/image.jpg",
):
    response_status_code = status_code
    response_headers = headers or {"content-type": "image/jpeg"}
    response_chunks = chunks if chunks is not None else [_image_bytes()]

    class _Response:
        status_code = response_status_code
        headers = response_headers
        url = final_url

        async def aiter_bytes(self):
            for chunk in response_chunks:
                yield chunk

    class _Stream:
        async def __aenter__(self):
            return _Response()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, url):
            return _Stream()

    monkeypatch.setattr(service.httpx, "AsyncClient", _Client)


def test_crop_public_image_to_source_format_bytes_uses_ratio_coordinates():
    result = service.crop_public_image_to_source_format_bytes(
        _image_bytes(size=(100, 50), image_format="PNG"),
        PublicImageCropCoordinates(x1=0.1, y1=0.2, x2=0.6, y2=0.8),
    )

    with Image.open(BytesIO(result.content)) as cropped:
        assert cropped.size == (50, 30)
        assert cropped.format == "PNG"
    assert result.extension == "png"
    assert result.content_type == "image/png"


def test_crop_public_image_to_source_format_bytes_preserves_jpeg_format():
    result = service.crop_public_image_to_source_format_bytes(
        _image_bytes(size=(100, 50), image_format="JPEG"),
        PublicImageCropCoordinates(x1=0.1, y1=0.2, x2=0.6, y2=0.8),
    )

    with Image.open(BytesIO(result.content)) as cropped:
        assert cropped.size == (50, 30)
        assert cropped.format == "JPEG"
    assert result.extension == "jpg"
    assert result.content_type == "image/jpeg"


def test_crop_public_image_to_source_format_bytes_rejects_invalid_crop():
    with pytest.raises(service.PublicImageCropSearchError) as exc:
        service.crop_public_image_to_source_format_bytes(
            _image_bytes(),
            PublicImageCropCoordinates(x1=0.8, y1=0.1, x2=0.2, y2=0.9),
        )

    assert exc.value.reason == service.PUBLIC_IMAGE_CROP_REASON_INVALID_CROP


def test_crop_public_image_to_source_format_bytes_rejects_out_of_bounds_crop():
    with pytest.raises(service.PublicImageCropSearchError) as exc:
        service.crop_public_image_to_source_format_bytes(
            _image_bytes(),
            PublicImageCropCoordinates(x1=-0.1, y1=0.1, x2=0.2, y2=0.9),
        )

    assert exc.value.reason == service.PUBLIC_IMAGE_CROP_REASON_INVALID_CROP


def test_crop_public_image_to_source_format_bytes_rejects_too_small_crop():
    with pytest.raises(service.PublicImageCropSearchError) as exc:
        service.crop_public_image_to_source_format_bytes(
            _image_bytes(size=(100, 100)),
            PublicImageCropCoordinates(x1=0.1, y1=0.1, x2=0.105, y2=0.9),
        )

    assert exc.value.reason == service.PUBLIC_IMAGE_CROP_REASON_INVALID_CROP


def test_crop_public_image_to_source_format_bytes_preserves_png_alpha():
    result = service.crop_public_image_to_source_format_bytes(
        _image_bytes(
            size=(20, 20),
            mode="RGBA",
            color=(0, 255, 0, 128),
            image_format="PNG",
        ),
        PublicImageCropCoordinates(x1=0, y1=0, x2=1, y2=1),
    )

    with Image.open(BytesIO(result.content)) as cropped:
        assert cropped.mode == "RGBA"
        assert cropped.format == "PNG"


def test_crop_public_image_to_source_format_bytes_keeps_full_source_bytes():
    content = _image_bytes(
        size=(20, 20),
        mode="RGBA",
        color=(0, 255, 0, 255),
        image_format="PNG",
    )

    result = service.crop_public_image_to_source_format_bytes(
        content,
        PublicImageCropCoordinates(x1=0, y1=0, x2=1, y2=1),
    )

    assert result.content == content
    assert result.extension == "png"
    assert result.content_type == "image/png"


def test_crop_public_image_to_source_format_bytes_rejects_invalid_image():
    with pytest.raises(service.PublicImageCropSearchError) as exc:
        service.crop_public_image_to_source_format_bytes(
            b"not-image",
            PublicImageCropCoordinates(x1=0.1, y1=0.1, x2=0.9, y2=0.9),
        )

    assert exc.value.reason == service.PUBLIC_IMAGE_CROP_REASON_INVALID_IMAGE_URL


def test_fetch_public_image_bytes_downloads_allowed_image(monkeypatch):
    image_content = _image_bytes()
    calls = []

    class _Response:
        status_code = 200
        headers = {
            "content-type": "image/jpeg",
            "content-length": str(len(image_content)),
        }
        url = "https://example.com/image.jpg"

        async def aiter_bytes(self):
            yield image_content

    class _Stream:
        async def __aenter__(self):
            return _Response()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _Client:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, url):
            calls.append({"method": method, "url": url})
            return _Stream()

    monkeypatch.setattr(service.httpx, "AsyncClient", _Client)

    result = anyio.run(
        service.fetch_public_image_bytes,
        "https://example.com/image.jpg",
    )

    assert result == image_content
    assert calls[0]["follow_redirects"] is True
    assert calls[1] == {"method": "GET", "url": "https://example.com/image.jpg"}


def test_fetch_public_image_bytes_rejects_non_image_response(monkeypatch):
    class _Response:
        status_code = 200
        headers = {"content-type": "text/html"}
        url = "https://example.com/image.jpg"

        async def aiter_bytes(self):
            yield b"<html></html>"

    class _Stream:
        async def __aenter__(self):
            return _Response()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, url):
            return _Stream()

    monkeypatch.setattr(service.httpx, "AsyncClient", _Client)

    with pytest.raises(service.PublicImageCropSearchError) as exc:
        anyio.run(
            service.fetch_public_image_bytes,
            "https://example.com/image.jpg",
        )

    assert exc.value.reason == service.PUBLIC_IMAGE_CROP_REASON_INVALID_IMAGE_URL


def test_fetch_public_image_bytes_rejects_invalid_scheme():
    with pytest.raises(service.PublicImageCropSearchError) as exc:
        anyio.run(service.fetch_public_image_bytes, "ftp://example.com/image.jpg")

    assert exc.value.reason == service.PUBLIC_IMAGE_CROP_REASON_INVALID_IMAGE_URL


def test_fetch_public_image_bytes_rejects_missing_hostname():
    with pytest.raises(service.PublicImageCropSearchError) as exc:
        anyio.run(service.fetch_public_image_bytes, "https:///image.jpg")

    assert exc.value.reason == service.PUBLIC_IMAGE_CROP_REASON_INVALID_IMAGE_URL


def test_fetch_public_image_bytes_rejects_too_long_url():
    long_url = f"https://example.com/{'a' * 2050}.jpg"

    with pytest.raises(service.PublicImageCropSearchError) as exc:
        anyio.run(service.fetch_public_image_bytes, long_url)

    assert exc.value.reason == service.PUBLIC_IMAGE_CROP_REASON_INVALID_IMAGE_URL


def test_fetch_public_image_bytes_rejects_private_url():
    with pytest.raises(service.PublicImageCropSearchError) as exc:
        anyio.run(service.fetch_public_image_bytes, "http://127.0.0.1/image.jpg")

    assert exc.value.reason == service.PUBLIC_IMAGE_CROP_REASON_INVALID_IMAGE_URL


def test_fetch_public_image_bytes_maps_request_error(monkeypatch):
    class _Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, url):
            raise service.httpx.RequestError("boom")

    monkeypatch.setattr(service.httpx, "AsyncClient", _Client)

    with pytest.raises(service.PublicImageCropSearchError) as exc:
        anyio.run(service.fetch_public_image_bytes, "https://example.com/image.jpg")

    assert exc.value.reason == service.PUBLIC_IMAGE_CROP_REASON_INVALID_IMAGE_URL


def test_fetch_public_image_bytes_rejects_http_error(monkeypatch):
    _patch_httpx_stream(
        monkeypatch,
        status_code=404,
        headers={"content-type": "image/jpeg"},
        chunks=[_image_bytes()],
    )

    with pytest.raises(service.PublicImageCropSearchError) as exc:
        anyio.run(service.fetch_public_image_bytes, "https://example.com/image.jpg")

    assert exc.value.reason == service.PUBLIC_IMAGE_CROP_REASON_INVALID_IMAGE_URL


def test_fetch_public_image_bytes_rejects_too_large_content_length(monkeypatch):
    _patch_httpx_stream(
        monkeypatch,
        headers={
            "content-type": "image/jpeg",
            "content-length": str(10 * 1024 * 1024 + 1),
        },
        chunks=[],
    )

    with pytest.raises(service.PublicImageCropSearchError) as exc:
        anyio.run(service.fetch_public_image_bytes, "https://example.com/image.jpg")

    assert exc.value.reason == service.PUBLIC_IMAGE_CROP_REASON_INVALID_IMAGE_URL


def test_fetch_public_image_bytes_rejects_empty_response(monkeypatch):
    _patch_httpx_stream(
        monkeypatch,
        headers={"content-type": "image/jpeg"},
        chunks=[],
    )

    with pytest.raises(service.PublicImageCropSearchError) as exc:
        anyio.run(service.fetch_public_image_bytes, "https://example.com/image.jpg")

    assert exc.value.reason == service.PUBLIC_IMAGE_CROP_REASON_INVALID_IMAGE_URL


def test_search_public_image_crop_service_returns_found(monkeypatch):
    async def fake_fetch(image_url):
        return _image_bytes(size=(100, 50), image_format="JPEG")

    captured = {}

    async def fake_search(**kwargs):
        upload = kwargs["upload"]
        captured["filename"] = upload.filename
        captured["content_type"] = upload.content_type
        captured["top_k"] = kwargs["top_k"]
        captured["aggregate_k"] = kwargs["aggregate_k"]
        content = await upload.read()
        with Image.open(BytesIO(content)) as cropped:
            captured["format"] = cropped.format
            captured["size"] = cropped.size
        return _search_response(score=0.9)

    monkeypatch.setattr(service, "fetch_public_image_bytes", fake_fetch)
    monkeypatch.setattr(service, "search_chroma_crop_aware_image_service", fake_search)

    result = anyio.run(service.search_public_image_crop_service, _request())

    assert result.model_dump() == {
        "success": True,
        "status": "found",
        "sku": "S12345",
        "confidence": 0.9,
        "reason": None,
    }
    assert captured == {
        "filename": "public_crop_conversation-1.jpg",
        "content_type": "image/jpeg",
        "top_k": 10,
        "aggregate_k": 1,
        "format": "JPEG",
        "size": (50, 30),
    }


def test_search_public_image_crop_service_returns_found_above_threshold(monkeypatch):
    async def fake_fetch(image_url):
        return _image_bytes()

    async def fake_search(**kwargs):
        return _search_response(score=0.91)

    monkeypatch.setattr(service, "fetch_public_image_bytes", fake_fetch)
    monkeypatch.setattr(service, "search_chroma_crop_aware_image_service", fake_search)

    result = anyio.run(service.search_public_image_crop_service, _request())

    assert result.status == "found"
    assert result.sku == "S12345"
    assert result.confidence == 0.91


def test_search_public_image_crop_service_returns_not_found_for_low_score(monkeypatch):
    async def fake_fetch(image_url):
        return _image_bytes()

    async def fake_search(**kwargs):
        return _search_response(score=0.8999)

    monkeypatch.setattr(service, "fetch_public_image_bytes", fake_fetch)
    monkeypatch.setattr(service, "search_chroma_crop_aware_image_service", fake_search)

    result = anyio.run(service.search_public_image_crop_service, _request())

    assert result.model_dump() == {
        "success": True,
        "status": "not_found",
        "sku": None,
        "confidence": None,
        "reason": "low_confidence",
    }


def test_search_public_image_crop_service_returns_not_found_for_empty_ranking(monkeypatch):
    async def fake_fetch(image_url):
        return _image_bytes()

    async def fake_search(**kwargs):
        return _search_response(ranking=False)

    monkeypatch.setattr(service, "fetch_public_image_bytes", fake_fetch)
    monkeypatch.setattr(service, "search_chroma_crop_aware_image_service", fake_search)

    result = anyio.run(service.search_public_image_crop_service, _request())

    assert result.status == "not_found"
    assert result.reason == "low_confidence"


def test_search_public_image_crop_service_maps_unknown_search_error(monkeypatch):
    async def fake_fetch(image_url):
        return _image_bytes()

    async def fake_search(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(service, "fetch_public_image_bytes", fake_fetch)
    monkeypatch.setattr(service, "search_chroma_crop_aware_image_service", fake_search)

    result = anyio.run(service.search_public_image_crop_service, _request())

    assert result.model_dump() == {
        "success": False,
        "status": "error",
        "sku": None,
        "confidence": None,
        "reason": service.PUBLIC_IMAGE_CROP_REASON_IMAGE_SEARCH_FAILED,
    }


def test_search_public_image_crop_service_maps_invalid_crop(monkeypatch):
    async def fake_fetch(image_url):
        return _image_bytes()

    monkeypatch.setattr(service, "fetch_public_image_bytes", fake_fetch)

    result = anyio.run(
        service.search_public_image_crop_service,
        _request(PublicImageCropCoordinates(x1=0.5, y1=0.1, x2=0.5, y2=0.9)),
    )

    assert result.model_dump() == {
        "success": False,
        "status": "error",
        "sku": None,
        "confidence": None,
        "reason": service.PUBLIC_IMAGE_CROP_REASON_INVALID_CROP,
    }


def test_search_public_image_crop_service_maps_missing_index(monkeypatch):
    async def fake_fetch(image_url):
        return _image_bytes()

    async def fake_search(**kwargs):
        raise CropAwareImageSearchError(ErrorCode.IMAGE_SEARCH_INDEX_NOT_FOUND, 404)

    monkeypatch.setattr(service, "fetch_public_image_bytes", fake_fetch)
    monkeypatch.setattr(service, "search_chroma_crop_aware_image_service", fake_search)

    result = anyio.run(service.search_public_image_crop_service, _request())

    assert result.model_dump() == {
        "success": False,
        "status": "error",
        "sku": None,
        "confidence": None,
        "reason": service.PUBLIC_IMAGE_CROP_REASON_IMAGE_SEARCH_INDEX_NOT_FOUND,
    }


def test_search_public_image_crop_service_maps_known_search_error(monkeypatch):
    async def fake_fetch(image_url):
        return _image_bytes()

    async def fake_search(**kwargs):
        raise CropAwareImageSearchError(ErrorCode.IMAGE_SEARCH_DEPENDENCY_MISSING, 503)

    monkeypatch.setattr(service, "fetch_public_image_bytes", fake_fetch)
    monkeypatch.setattr(service, "search_chroma_crop_aware_image_service", fake_search)

    result = anyio.run(service.search_public_image_crop_service, _request())

    assert result.model_dump() == {
        "success": False,
        "status": "error",
        "sku": None,
        "confidence": None,
        "reason": service.PUBLIC_IMAGE_CROP_REASON_IMAGE_SEARCH_FAILED,
    }
