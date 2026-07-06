from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.api.schemas.image_asset import (
    ImageAssetCreateMetadata,
    ImageAssetListResponse,
    ImageAssetResponse,
    ImageAssetUpdateMetadata,
)
from app.core.database import DOCUMENT_MODELS
from app.models.image_assets import ImageAsset


def test_image_asset_model_accepts_nullable_description_and_requires_images():
    asset = ImageAsset.model_construct(
        code="CODE",
        description=None,
        url_images=["/rag-images/a.jpg"],
    )

    assert asset.description is None
    assert asset.url_images == ["/rag-images/a.jpg"]

    with pytest.raises(ValidationError):
        ImageAsset.__pydantic_validator__.validate_python(
            {"code": "CODE", "description": None, "url_images": []}
        )


def test_image_asset_model_has_expected_collection_and_indexes():
    index_documents = [index.document for index in ImageAsset.Settings.indexes]

    assert ImageAsset.Settings.name == "image_assets"
    assert any(
        document.get("name") == "uniq_image_assets_code"
        and document.get("unique") is True
        for document in index_documents
    )
    assert any(
        document.get("name") == "idx_image_assets_updated_at"
        for document in index_documents
    )
    assert ImageAsset in DOCUMENT_MODELS


def test_create_metadata_normalizes_code_and_description():
    metadata = ImageAssetCreateMetadata(
        code="  s678657 ",
        description="  Product images  ",
    )
    empty_description = ImageAssetCreateMetadata(code="code", description="   ")

    assert metadata.code == "S678657"
    assert metadata.description == "Product images"
    assert empty_description.description is None


def test_metadata_rejects_empty_code_and_long_description():
    accepted = ImageAssetCreateMetadata(code="CODE", description="x" * 5000)
    assert len(accepted.description) == 5000

    with pytest.raises(ValidationError):
        ImageAssetCreateMetadata(code="   ")

    with pytest.raises(ValidationError):
        ImageAssetCreateMetadata(code="CODE", description="x" * 5001)


def test_update_metadata_distinguishes_omitted_and_cleared_description():
    omitted = ImageAssetUpdateMetadata()
    cleared = ImageAssetUpdateMetadata(description="")

    assert "description" not in omitted.model_fields_set
    assert "description" in cleared.model_fields_set
    assert cleared.description is None


def test_update_metadata_normalizes_and_deduplicates_remove_file_names():
    metadata = ImageAssetUpdateMetadata(
        remove_image_file_names=[" first.jpg ", "first.jpg", "second.jpg"]
    )

    assert metadata.remove_image_file_names == ["first.jpg", "second.jpg"]

    with pytest.raises(ValidationError):
        ImageAssetUpdateMetadata(remove_image_file_names=["../first.jpg"])


def test_image_asset_response_and_list_contract():
    now = datetime.now(timezone.utc)
    item = ImageAssetResponse(
        id="asset-id",
        code="CODE",
        description=None,
        url_images=["/rag-images/a.jpg"],
        created_at=now,
        updated_at=now,
    )
    response = ImageAssetListResponse(items=[item], total=1, page=1, size=10)

    assert response.items[0].id == "asset-id"
    assert response.total == 1
