from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies.error_codes import ErrorCode
from app.api.router_v1 import api_router as api_router_v1
from app.api.v1 import image_search_import as image_search_import_api
from app.core.security import get_current_user
from app.services.foreground_common import CropAwareImageSearchError


def _current_user(permissions):
    return SimpleNamespace(
        email="admin@example.com",
        quyen_han=[SimpleNamespace(ten=permission) for permission in permissions],
    )


def _client(permissions):
    app = FastAPI()
    app.include_router(
        image_search_import_api.router,
        prefix="/api/v1/image-search-import",
    )
    app.dependency_overrides[get_current_user] = lambda: _current_user(permissions)
    return TestClient(app)


def _import_response():
    return {
        "code": "S12345",
        "description": "Ao dai do",
        "source_dir": "data/source_images",
        "metadata_path": "data/source_images_metadata.csv",
        "imported_count": 1,
        "index_updated": True,
        "index": {
            "index_path": "data/chroma#image_search_crop_views_v1",
            "source_count": 1,
            "added_view_count": 5,
            "total_view_count": 10,
            "created_index": False,
            "foreground_cache_hits": 0,
            "foreground_cache_misses": 1,
        },
        "files": [
            {
                "file_name": "S12345_abcd.jpg",
                "original_filename": "source.jpg",
                "source_image_path": "data/source_images/S12345/S12345_abcd.jpg",
                "public_url": "/data/source_images/S12345/S12345_abcd.jpg",
                "content_type": "image/jpeg",
                "size_bytes": 123,
                "width": 16,
                "height": 12,
            }
        ],
    }


def _list_response(*, page=1, size=20):
    return {
        "items": [
            {
                "code": "S12345",
                "description": "Ao dai do",
                "image_count": 1,
                "updated_at": "2026-06-16T00:00:00+00:00",
            }
        ],
        "total": 1,
        "page": page,
        "size": size,
    }


def _detail_response():
    return {
        "code": "S12345",
        "description": "Ao dai do",
        "source_dir": "data/source_images",
        "metadata_path": "data/source_images_metadata.csv",
        "image_count": 1,
        "updated_at": "2026-06-16T00:00:00+00:00",
        "images": _import_response()["files"],
    }


def _update_response():
    response = _detail_response()
    response.update(
        {
            "added_count": 1,
            "deleted_count": 1,
            "index_updated": True,
            "index": _import_response()["index"],
        }
    )
    return response


def _delete_response():
    return {
        "code": "S12345",
        "source_dir": "data/source_images",
        "metadata_path": "data/source_images_metadata.csv",
        "deleted_count": 1,
        "index_updated": True,
    }


def test_router_v1_registers_image_search_import_route():
    paths = [route.path for route in api_router_v1.routes]

    assert "/image-search-import" in paths


def test_import_image_search_import_api_accepts_multipart(monkeypatch):
    service_mock = AsyncMock(return_value=_import_response())
    monkeypatch.setattr(
        image_search_import_api,
        "import_image_search_sources_service",
        service_mock,
    )

    response = _client({"image_assets:create"}).post(
        "/api/v1/image-search-import",
        data={"code": "S12345", "description": "Ao dai do"},
        files={"files": ("source.jpg", b"image", "image/jpeg")},
    )

    assert response.status_code == 201
    assert response.json()["code"] == "S12345"
    assert response.json()["imported_count"] == 1
    assert response.json()["index_updated"] is True
    assert response.json()["index"]["added_view_count"] == 5
    service_mock.assert_awaited_once()
    kwargs = service_mock.await_args.kwargs
    assert kwargs["code"] == "S12345"
    assert kwargs["description"] == "Ao dai do"
    assert kwargs["uploads"][0].filename == "source.jpg"


def test_import_image_search_import_api_requires_permission(monkeypatch):
    service_mock = AsyncMock(return_value=_import_response())
    monkeypatch.setattr(
        image_search_import_api,
        "import_image_search_sources_service",
        service_mock,
    )

    response = _client(set()).post(
        "/api/v1/image-search-import",
        data={"code": "S12345"},
        files={"files": ("source.jpg", b"image", "image/jpeg")},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == ErrorCode.FORBIDDEN.value
    service_mock.assert_not_awaited()


def test_import_image_search_import_api_maps_service_errors(monkeypatch):
    service_mock = AsyncMock(
        side_effect=CropAwareImageSearchError(
            ErrorCode.IMAGE_SEARCH_FILE_TYPE_NOT_ALLOWED,
            415,
        )
    )
    monkeypatch.setattr(
        image_search_import_api,
        "import_image_search_sources_service",
        service_mock,
    )

    response = _client({"image_assets:create"}).post(
        "/api/v1/image-search-import",
        data={"code": "S12345"},
        files={"files": ("source.txt", b"text", "text/plain")},
    )

    assert response.status_code == 415
    assert response.json()["detail"] == ErrorCode.IMAGE_SEARCH_FILE_TYPE_NOT_ALLOWED.value


def test_list_image_search_import_api_requires_view_permission(monkeypatch):
    service_mock = Mock(return_value=_list_response(page=2, size=10))
    monkeypatch.setattr(
        image_search_import_api,
        "list_image_search_sources_service",
        service_mock,
    )

    response = _client({"image_assets:view"}).get(
        "/api/v1/image-search-import",
        params={"page": 2, "size": 10, "keyword": "S123"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["page"] == 2
    assert response.json()["size"] == 10
    service_mock.assert_called_once_with(page=2, size=10, keyword="S123")


def test_get_image_search_import_api_returns_detail(monkeypatch):
    service_mock = Mock(return_value=_detail_response())
    monkeypatch.setattr(
        image_search_import_api,
        "get_image_search_source_service",
        service_mock,
    )

    response = _client({"image_assets:view"}).get(
        "/api/v1/image-search-import/S12345"
    )

    assert response.status_code == 200
    assert response.json()["code"] == "S12345"
    service_mock.assert_called_once_with(code="S12345")


def test_update_image_search_import_api_accepts_combined_update(monkeypatch):
    service_mock = AsyncMock(return_value=_update_response())
    monkeypatch.setattr(
        image_search_import_api,
        "update_image_search_source_service",
        service_mock,
    )

    response = _client({"image_assets:edit"}).patch(
        "/api/v1/image-search-import/S12345",
        data={
            "description": "Mo ta moi",
            "delete_file_names": '["S12345_old.jpg"]',
        },
        files={"add_files": ("new.jpg", b"image", "image/jpeg")},
    )

    assert response.status_code == 200
    assert response.json()["added_count"] == 1
    assert response.json()["deleted_count"] == 1
    service_mock.assert_awaited_once()
    kwargs = service_mock.await_args.kwargs
    assert kwargs["code"] == "S12345"
    assert kwargs["description"] == "Mo ta moi"
    assert kwargs["description_provided"] is True
    assert kwargs["delete_file_names"] == ["S12345_old.jpg"]
    assert kwargs["add_uploads"][0].filename == "new.jpg"


def test_update_image_search_import_api_rejects_invalid_delete_payload(monkeypatch):
    service_mock = AsyncMock(return_value=_update_response())
    monkeypatch.setattr(
        image_search_import_api,
        "update_image_search_source_service",
        service_mock,
    )

    response = _client({"image_assets:edit"}).patch(
        "/api/v1/image-search-import/S12345",
        data={"delete_file_names": "not-json"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == ErrorCode.INVALID_INPUT_DATA.value
    service_mock.assert_not_awaited()


def test_delete_image_search_import_api_deletes_code(monkeypatch):
    service_mock = AsyncMock(return_value=_delete_response())
    monkeypatch.setattr(
        image_search_import_api,
        "delete_image_search_source_service",
        service_mock,
    )

    response = _client({"image_assets:delete"}).delete(
        "/api/v1/image-search-import/S12345"
    )

    assert response.status_code == 200
    assert response.json()["deleted_count"] == 1
    service_mock.assert_awaited_once_with(code="S12345")
