from typing import Dict, List

from pydantic import BaseModel, Field


class DatasetCleaningResponse(BaseModel):
    original_filename: str = Field(...)
    cleaned_file_path: str = Field(...)
    rejected_file_path: str = Field(...)
    total_records: int = Field(..., ge=0)
    cleaned_records: int = Field(..., ge=0)
    rejected_records: int = Field(..., ge=0)
    rejection_reasons: Dict[str, int] = Field(default_factory=dict)
    sample_rejections: List[Dict[str, str]] = Field(default_factory=list)
