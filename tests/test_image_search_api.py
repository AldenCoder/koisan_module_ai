from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies.error_codes import ErrorCode
from app.api.router_v1 import api_router as api_router_v1
from app.api.v1 import image_search as image_search_api
from app.services.foreground_common import CropAwareImageSearchError


def _client():
    app = FastAPI()
    app.include_router(image_search_api.router, prefix="/api/v1/image-search")
    return TestClient(app)


def _search_response():
    return {
        "query": "query.jpg",
        "query_foreground": "data/query_crop_aware_v4/run/query_foreground.png",
        "query_views": {
            "full": "data/query_crop_aware_v4/run/query_full.png",
        },
        "index_path": "data/chroma#image_search_crop_views_v1",
        "top_k": 3,
        "aggregate_k": 2,
        "ranking": [
            {
                "product_id": "S12345",
                "score": 0.91,
                "best_score": 0.95,
                "best_image_path": "source/S12345.jpg",
                "best_index_view": "upper_50",
                "best_query_view": "full",
                "top_image_scores": [0.95, 0.87],
            }
        ],
        "top_images": [
            {
                "product_id": "S12345",
                "score": 0.95,
                "source_image_path": "source/S12345.jpg",
                "index_view": "upper_50",
                "query_view": "full",
            }
        ],
    }


def test_router_v1_registers_image_search_route():
    paths = [route.path for route in api_router_v1.routes]

    assert "/image-search/crop-aware" in paths
    assert "/image-search/public-crop" in paths


def test_crop_aware_search_api_accepts_multipart_without_auth_and_passes_options(
    monkeypatch,
):
    service_mock = AsyncMock(return_value=_search_response())
    monkeypatch.setattr(
        image_search_api,
        "search_chroma_crop_aware_image_service",
        service_mock,
    )

    response = _client().post(
        "/api/v1/image-search/crop-aware?top_k=3&aggregate_k=2",
        files={"file": ("query.jpg", b"image", "image/jpeg")},
    )

    assert response.status_code == 200
    assert response.json()["ranking"][0]["product_id"] == "S12345"
    service_mock.assert_awaited_once()
    kwargs = service_mock.await_args.kwargs
    assert kwargs["top_k"] == 3
    assert kwargs["aggregate_k"] == 2
    assert kwargs["upload"].filename == "query.jpg"


def test_crop_aware_search_api_maps_service_errors(monkeypatch):
    service_mock = AsyncMock(
        side_effect=CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_INDEX_NOT_FOUND,
            404,
        )
    )
    monkeypatch.setattr(
        image_search_api,
        "search_chroma_crop_aware_image_service",
        service_mock,
    )

    response = _client().post(
        "/api/v1/image-search/crop-aware",
        files={"file": ("query.jpg", b"image", "image/jpeg")},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == ErrorCode.IMAGE_SEARCH_INDEX_NOT_FOUND.value


def test_public_crop_search_api_calls_service_without_auth(monkeypatch):
    service_mock = AsyncMock(
        return_value={
            "success": True,
            "status": "found",
            "sku": "S12345",
            "confidence": 0.91,
        }
    )
    monkeypatch.setattr(
        image_search_api,
        "search_public_image_crop_service",
        service_mock,
    )

    response = _client().post(
        "/api/v1/image-search/public-crop",
        json={
            "conversation_id": "conversation-1",
            "image_url": "https://example.com/image.jpg",
            "crop": {"x1": 0.1, "y1": 0.1, "x2": 0.9, "y2": 0.9},
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "status": "found",
        "sku": "S12345",
        "confidence": 0.91,
        "reason": None,
    }
    service_mock.assert_awaited_once()
    payload = service_mock.await_args.args[0]
    assert payload.conversation_id == "conversation-1"
