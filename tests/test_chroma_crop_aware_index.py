from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from app.api.dependencies.error_codes import ErrorCode
from app.services import chroma_crop_aware_index as service
from app.services.foreground_common import CropAwareImageSearchError


class FakeCollection:
    def __init__(self, *, count=0, query_result=None):
        self.current_count = count
        self.query_result = query_result or {}
        self.upsert_kwargs = None
        self.query_kwargs = None

    def count(self):
        return self.current_count

    def upsert(self, **kwargs):
        self.upsert_kwargs = kwargs
        self.current_count = len(kwargs["ids"])

    def query(self, **kwargs):
        self.query_kwargs = kwargs
        return self.query_result


def test_upsert_sources_writes_stable_crop_view_records(monkeypatch, tmp_path):
    collection = FakeCollection()
    monkeypatch.setattr(service, "_get_collection", lambda **kwargs: collection)
    monkeypatch.setattr(
        service,
        "get_clip_crop_aware_runtime",
        lambda **kwargs: SimpleNamespace(),
    )
    monkeypatch.setattr(
        service,
        "_prepare_crop_aware_index_rows",
        lambda *args, **kwargs: (
            [object(), object()],
            ["S123", "S123"],
            ["data/source_images/S123/a.jpg", "data/source_images/S123/a.jpg"],
            ["full", "upper_50"],
            0,
            1,
        ),
    )
    monkeypatch.setattr(
        service,
        "_embed_crop_aware_images",
        lambda *args, **kwargs: np.array(
            [[0.1, 0.2], [0.3, 0.4]],
            dtype="float32",
        ),
    )

    result = service.upsert_sources_to_chroma_index_service(
        rows=[
            {
                "product_id": "S123",
                "source_image_path": "data/source_images/S123/a.jpg",
            }
        ],
        persist_dir=tmp_path / "chroma",
    )

    assert result.source_count == 1
    assert result.added_view_count == 2
    assert result.total_view_count == 2
    assert result.created_index is True
    assert np.allclose(
        collection.upsert_kwargs["embeddings"],
        [[0.1, 0.2], [0.3, 0.4]],
    )
    assert collection.upsert_kwargs["metadatas"][0] == {
        "product_id": "S123",
        "source_image_path": "data/source_images/S123/a.jpg",
        "file_name": "a.jpg",
        "view_name": "full",
    }
    assert len(set(collection.upsert_kwargs["ids"])) == 2
    assert collection.upsert_kwargs["ids"][0] == service._record_id(
        "data/source_images/S123/a.jpg",
        "full",
    )


def test_chroma_search_converts_cosine_distance_and_deduplicates_records(
    monkeypatch,
    tmp_path,
):
    record_id = "record-1"
    metadata = {
        "product_id": "S123",
        "source_image_path": "data/source_images/S123/a.jpg",
        "file_name": "a.jpg",
        "view_name": "full",
    }
    collection = FakeCollection(
        count=1,
        query_result={
            "ids": [[record_id], [record_id], [], [], []],
            "metadatas": [[metadata], [metadata], [], [], []],
            "distances": [[0.2], [0.1], [], [], []],
        },
    )
    monkeypatch.setattr(service, "_get_collection", lambda **kwargs: collection)
    monkeypatch.setattr(
        service,
        "get_clip_crop_aware_runtime",
        lambda **kwargs: SimpleNamespace(),
    )
    monkeypatch.setattr(
        service,
        "extract_foreground_from_content",
        lambda *args, **kwargs: Image.new("RGBA", (8, 8), (0, 0, 0, 255)),
    )
    monkeypatch.setattr(
        service,
        "embed_prepared_images",
        lambda images, **kwargs: np.zeros((len(images), 2), dtype="float32"),
    )

    result = service.search_chroma_crop_aware_image_bytes(
        content=b"image",
        filename="query.jpg",
        persist_dir=tmp_path / "chroma",
        top_k=3,
        aggregate_k=1,
    )

    assert len(result.top_images) == 1
    assert result.top_images[0].score == pytest.approx(0.9)
    assert result.top_images[0].query_view == "upper_65"
    assert result.ranking[0].product_id == "S123"
    assert collection.query_kwargs["n_results"] == 1
    assert len(collection.query_kwargs["query_embeddings"]) == 5


def test_chroma_search_returns_not_found_for_empty_collection(monkeypatch):
    monkeypatch.setattr(
        service,
        "_get_collection",
        lambda **kwargs: FakeCollection(count=0),
    )

    with pytest.raises(CropAwareImageSearchError) as exc:
        service.search_chroma_crop_aware_image_bytes(content=b"image")

    assert exc.value.error_code == ErrorCode.IMAGE_SEARCH_INDEX_NOT_FOUND
    assert exc.value.status_code == 404
