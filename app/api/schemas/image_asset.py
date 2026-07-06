from datetime import datetime
from pathlib import PurePath
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


def normalize_image_asset_code(value: str) -> str:
    normalized = value.strip().upper()
    if not normalized:
        raise ValueError("code must not be empty")
    if len(normalized) > 100:
        raise ValueError("code must not exceed 100 characters")
    return normalized


def normalize_image_asset_description(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > 5000:
        raise ValueError("description must not exceed 5000 characters")
    return normalized


def normalize_remove_image_file_names(values: Optional[List[str]]) -> Optional[List[str]]:
    if values is None:
        return None

    normalized: List[str] = []
    seen = set()
    for value in values:
        file_name = value.strip()
        if (
            not file_name
            or PurePath(file_name).name != file_name
            or "/" in file_name
            or "\\" in file_name
        ):
            raise ValueError("remove_image_file_names must contain basenames only")
        if file_name not in seen:
            normalized.append(file_name)
            seen.add(file_name)
    return normalized


class ImageAssetCreateMetadata(BaseModel):
    code: str = Field(..., max_length=100)
    description: Optional[str] = Field(default=None, max_length=5000)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        return normalize_image_asset_code(value)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: Optional[str]) -> Optional[str]:
        return normalize_image_asset_description(value)


class ImageAssetUpdateMetadata(BaseModel):
    code: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = Field(default=None, max_length=5000)
    remove_image_file_names: Optional[List[str]] = Field(default=None)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return normalize_image_asset_code(value)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: Optional[str]) -> Optional[str]:
        return normalize_image_asset_description(value)

    @field_validator("remove_image_file_names")
    @classmethod
    def validate_remove_image_file_names(
        cls,
        values: Optional[List[str]],
    ) -> Optional[List[str]]:
        return normalize_remove_image_file_names(values)


class ImageAssetResponse(BaseModel):
    id: str
    code: str
    description: Optional[str] = None
    url_images: List[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ImageAssetListResponse(BaseModel):
    items: List[ImageAssetResponse] = Field(default_factory=list)
    total: int = Field(default=0, ge=0)
    page: int = Field(default=1, ge=1)
    size: int = Field(default=10, ge=1, le=100)
