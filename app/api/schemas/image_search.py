from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class CropAwareProductMatch(BaseModel):
    product_id: str
    score: float
    best_score: float
    best_image_path: str
    best_index_view: str
    best_query_view: str
    top_image_scores: List[float] = Field(default_factory=list)


class CropAwareImageMatch(BaseModel):
    product_id: str
    score: float
    source_image_path: str
    index_view: str
    query_view: str


class CropAwareImageSearchResponse(BaseModel):
    query: Optional[str] = None
    query_foreground: Optional[str] = None
    query_views: Dict[str, str] = Field(default_factory=dict)
    index_path: str
    top_k: int
    aggregate_k: int
    ranking: List[CropAwareProductMatch] = Field(default_factory=list)
    top_images: List[CropAwareImageMatch] = Field(default_factory=list)


class PublicImageCropCoordinates(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float


class PublicImageCropSearchRequest(BaseModel):
    conversation_id: str = Field(..., min_length=1)
    image_url: str = Field(..., min_length=1)
    crop: PublicImageCropCoordinates


class PublicImageCropSearchResponse(BaseModel):
    success: bool
    status: Literal["found", "not_found", "error"]
    sku: Optional[str] = None
    confidence: Optional[float] = None
    reason: Optional[str] = None
