import re

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.services import image_asset_service
from app.services.image_asset_service import (
    build_public_url,
    ensure_storage_directory,
    generate_unique_file_name,
    mount_rag_image_storage,
    normalize_code_for_filename,
    normalize_public_path,
    resolve_storage_file,
    split_stored_file_name,
)


def test_ensure_storage_directory_creates_and_reuses_directory(tmp_path):
    storage_dir = tmp_path / "nested" / "rag_images"

    first = ensure_storage_directory(storage_dir)
    second = ensure_storage_directory(storage_dir)

    assert first == storage_dir.resolve()
    assert second == first
    assert first.is_dir()


def test_image_storage_defaults_match_contract():
    assert settings.rag_image_storage_dir == "storage/rag_images"
    assert settings.rag_image_public_path == "/rag-images"
    assert settings.rag_image_target_max_bytes == 1_000_000


def test_normalize_public_path_and_build_public_url():
    assert normalize_public_path("rag-images/") == "/rag-images"
    assert build_public_url(
        "S123_random.jpg",
        base_url="https://api.example.com/",
        public_path="rag-images/",
    ) == "https://api.example.com/rag-images/S123_random.jpg"
    assert build_public_url(
        "S123_random.jpg",
        base_url="",
        public_path="/rag-images",
    ) == "/rag-images/S123_random.jpg"


def test_normalize_code_for_filename_replaces_unsafe_characters():
    assert normalize_code_for_filename("  s67 / 86--blue  ") == "S67_86--BLUE"


def test_generate_unique_file_name_and_split(tmp_path):
    first = generate_unique_file_name("s678657", storage_dir=tmp_path)
    second = generate_unique_file_name("s678657", storage_dir=tmp_path)

    assert first != second
    assert re.fullmatch(r"S678657_[a-z0-9]{20}\.jpg", first)
    assert split_stored_file_name(first) == (
        "S678657",
        first.removeprefix("S678657_").removesuffix(".jpg"),
        ".jpg",
    )


def test_generate_unique_file_name_retries_on_collision(tmp_path, monkeypatch):
    random_ids = iter(["a" * 20, "b" * 20])
    monkeypatch.setattr(image_asset_service, "_new_random_id", lambda: next(random_ids))
    (tmp_path / f"CODE_{'a' * 20}.jpg").write_bytes(b"existing")

    result = generate_unique_file_name("CODE", storage_dir=tmp_path)

    assert result == f"CODE_{'b' * 20}.jpg"


def test_resolve_storage_file_rejects_path_traversal(tmp_path):
    for file_name in ("../secret.jpg", "..\\secret.jpg", str(tmp_path / "absolute.jpg")):
        try:
            resolve_storage_file(file_name, storage_dir=tmp_path)
        except ValueError:
            pass
        else:
            raise AssertionError(f"path traversal should be rejected: {file_name}")


def test_static_route_serves_existing_file_and_returns_404(tmp_path):
    app = FastAPI()
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "health.txt").write_text("static-ok", encoding="utf-8")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    rag_dir = tmp_path / "rag_images"
    mount_rag_image_storage(
        app,
        storage_dir=rag_dir,
        public_path="/rag-images/",
    )
    (rag_dir / "sample.jpg").write_bytes(b"jpeg-content")
    client = TestClient(app)

    response = client.get("/rag-images/sample.jpg")
    missing = client.get("/rag-images/missing.jpg")
    upload_attempt = client.post("/rag-images/sample.jpg", content=b"replacement")
    directory_listing = client.get("/rag-images/")
    existing_static = client.get("/static/health.txt")

    assert response.status_code == 200
    assert response.content == b"jpeg-content"
    assert response.headers["content-type"] == "image/jpeg"
    assert missing.status_code == 404
    assert upload_attempt.status_code == 405
    assert directory_listing.status_code == 404
    assert existing_static.text == "static-ok"
    assert (rag_dir / "sample.jpg").read_bytes() == b"jpeg-content"
