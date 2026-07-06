from typing import List, Optional

from pydantic import BaseModel, Field


class ImageSearchSourceFile(BaseModel):
    file_name: str
    original_filename: Optional[str] = None
    source_image_path: str
    public_url: str
    content_type: str
    size_bytes: int
    width: int
    height: int


class ImageSearchSourceIndexUpdate(BaseModel):
    index_path: str
    source_count: int
    added_view_count: int
    total_view_count: int
    created_index: bool
    foreground_cache_hits: int = 0
    foreground_cache_misses: int = 0


class ImageSearchSourceImportResponse(BaseModel):
    code: str
    description: Optional[str] = None
    source_dir: str
    metadata_path: str
    imported_count: int = Field(default=0, ge=0)
    index_updated: bool = False
    index: Optional[ImageSearchSourceIndexUpdate] = None
    files: List[ImageSearchSourceFile] = Field(default_factory=list)


class ImageSearchSourceListItem(BaseModel):
    code: str
    description: Optional[str] = None
    image_count: int = Field(default=0, ge=0)
    updated_at: Optional[str] = None


class ImageSearchSourceListResponse(BaseModel):
    items: List[ImageSearchSourceListItem] = Field(default_factory=list)
    total: int = Field(default=0, ge=0)
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1)


class ImageSearchSourceDetailResponse(BaseModel):
    code: str
    description: Optional[str] = None
    source_dir: str
    metadata_path: str
    image_count: int = Field(default=0, ge=0)
    updated_at: Optional[str] = None
    images: List[ImageSearchSourceFile] = Field(default_factory=list)


class ImageSearchSourceUpdateResponse(BaseModel):
    code: str
    description: Optional[str] = None
    source_dir: str
    metadata_path: str
    image_count: int = Field(default=0, ge=0)
    updated_at: Optional[str] = None
    added_count: int = Field(default=0, ge=0)
    deleted_count: int = Field(default=0, ge=0)
    index_updated: bool = False
    index: Optional[ImageSearchSourceIndexUpdate] = None
    images: List[ImageSearchSourceFile] = Field(default_factory=list)


class ImageSearchSourceDeleteResponse(BaseModel):
    code: str
    source_dir: str
    metadata_path: str
    deleted_count: int = Field(default=0, ge=0)
    index_updated: bool = False
